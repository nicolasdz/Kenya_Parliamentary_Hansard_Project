"""The SQLite database holding documents, speeches, and members.

    documents  one row per unique PDF (deduplicated by file hash)
    speeches   one row per speech, linked to its document and (when matched) a member
    members    one row per member per Parliament, loaded from the members TSV
"""

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY,
    sha256          TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    folder_chamber  TEXT NOT NULL,   -- Which download folder (website listing) it came from.
    source_url      TEXT,
    doc_type        TEXT NOT NULL,   -- hansard, order_paper, votes_and_proceedings, no_text, unknown
    chamber         TEXT,            -- national_assembly, senate, joint (read from the document)
    date            TEXT,            -- YYYY-MM-DD
    filename_date   TEXT,
    content_date    TEXT,
    parliament      INTEGER,
    sitting         TEXT,            -- morning, afternoon, evening
    special_sitting INTEGER NOT NULL,
    page_count      INTEGER NOT NULL,
    text_chars      INTEGER NOT NULL,
    parser_version  INTEGER NOT NULL,
    parsed_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    id                          INTEGER PRIMARY KEY,
    parliament                  INTEGER,
    chamber                     TEXT,
    full_name                   TEXT NOT NULL,
    first_names                 TEXT,
    last_name                   TEXT,
    county                      TEXT,
    constituency                TEXT,
    party                       TEXT,
    date_took_office            TEXT,
    date_left_office            TEXT,
    leadership_role             TEXT,
    county_woman_representative TEXT,
    nominated                   TEXT,
    note                        TEXT
);

CREATE TABLE IF NOT EXISTS speeches (
    id                    INTEGER PRIMARY KEY,
    document_id           INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    seq                   INTEGER NOT NULL,  -- Order within the document, from 1.
    page                  INTEGER NOT NULL,  -- PDF page where the speech starts.
    speaker_raw           TEXT NOT NULL,     -- As printed, e.g. "The Temporary Speaker (Sen. Kathuri)".
    member_id             INTEGER REFERENCES members(id),
    match_score           INTEGER,
    text                  TEXT NOT NULL,     -- Paragraphs separated by newlines.
    word_count            INTEGER NOT NULL,
    language_distribution TEXT NOT NULL,     -- JSON, e.g. {"en": 0.8, "sw": 0.2}
    primary_language      TEXT,
    UNIQUE (document_id, seq)
);

CREATE INDEX IF NOT EXISTS speeches_member ON speeches(member_id);
CREATE INDEX IF NOT EXISTS documents_date ON documents(chamber, date);
"""

_DOCUMENT_COLUMNS = [
    "sha256", "filename", "folder_chamber", "source_url", "doc_type", "chamber", "date",
    "filename_date", "content_date", "parliament", "sitting", "special_sitting",
    "page_count", "text_chars", "parser_version", "parsed_at",
]
_SPEECH_COLUMNS = [
    "document_id", "seq", "page", "speaker_raw", "text",
    "word_count", "language_distribution", "primary_language",
]


# Full-text index over speech text and speaker lines. It is an "external content"
# table: it stores only the index and reads text from `speeches`, and the triggers
# keep it in sync. (The `speeches_fts` name also lets Datasette find it.) The
# unicode61 tokenizer has no stemming, so English and Kiswahili are treated alike.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE speeches_fts USING fts5(
    text, speaker_raw,
    content='speeches', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER speeches_fts_insert AFTER INSERT ON speeches BEGIN
    INSERT INTO speeches_fts(rowid, text, speaker_raw) VALUES (new.id, new.text, new.speaker_raw);
END;

CREATE TRIGGER speeches_fts_delete AFTER DELETE ON speeches BEGIN
    INSERT INTO speeches_fts(speeches_fts, rowid, text, speaker_raw)
    VALUES ('delete', old.id, old.text, old.speaker_raw);
END;

CREATE TRIGGER speeches_fts_update AFTER UPDATE OF text, speaker_raw ON speeches BEGIN
    INSERT INTO speeches_fts(speeches_fts, rowid, text, speaker_raw)
    VALUES ('delete', old.id, old.text, old.speaker_raw);
    INSERT INTO speeches_fts(rowid, text, speaker_raw) VALUES (new.id, new.text, new.speaker_raw);
END;
"""

# Changes to an existing database, applied in order; PRAGMA user_version records
# how many have been applied.
MIGRATIONS = [
    FTS_SCHEMA + "INSERT INTO speeches_fts(speeches_fts) VALUES ('rebuild');",
]


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn):
    version, = conn.execute("PRAGMA user_version").fetchone()
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        if conn.execute("SELECT COUNT(*) FROM speeches").fetchone()[0]:
            print(f"Updating the database (migration {number}; one-off, may take a few minutes)...")
        conn.executescript(f"BEGIN; {script} PRAGMA user_version = {number}; COMMIT;")


def parsed_versions(conn):
    """Return {sha256: parser_version} for every stored document."""
    return dict(conn.execute("SELECT sha256, parser_version FROM documents"))


def save_document(conn, document, speeches, parser_version):
    """Insert (or replace) one document and its speeches in a single transaction."""
    row = dict(document, parser_version=parser_version,
               parsed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    row["special_sitting"] = int(row["special_sitting"])
    with conn:
        conn.execute("DELETE FROM documents WHERE sha256 = ?", (row["sha256"],))
        cursor = conn.execute(
            f"INSERT INTO documents ({', '.join(_DOCUMENT_COLUMNS)}) "
            f"VALUES ({', '.join('?' * len(_DOCUMENT_COLUMNS))})",
            [row.get(c) for c in _DOCUMENT_COLUMNS],
        )
        document_id = cursor.lastrowid
        conn.executemany(
            f"INSERT INTO speeches ({', '.join(_SPEECH_COLUMNS)}) "
            f"VALUES ({', '.join('?' * len(_SPEECH_COLUMNS))})",
            [[document_id if c == "document_id" else s.get(c) for c in _SPEECH_COLUMNS] for s in speeches],
        )
    return document_id


_CLASSIFICATION_COLUMNS = [
    "doc_type", "chamber", "date", "filename_date", "content_date",
    "parliament", "sitting", "special_sitting",
]


def update_classification(conn, document_id, classification):
    """Overwrite a document's classified fields. If its type changed, mark it for re-parsing."""
    values = dict(classification, special_sitting=int(classification["special_sitting"]))
    with conn:
        old_type, = conn.execute("SELECT doc_type FROM documents WHERE id = ?", (document_id,)).fetchone()
        conn.execute(
            f"UPDATE documents SET {', '.join(f'{c} = ?' for c in _CLASSIFICATION_COLUMNS)} WHERE id = ?",
            [values[c] for c in _CLASSIFICATION_COLUMNS] + [document_id],
        )
        if old_type != values["doc_type"]:
            conn.execute("UPDATE documents SET parser_version = 0 WHERE id = ?", (document_id,))


def update_source_urls(conn, urls):
    """Fill in source URLs from the manifest: urls is {(folder_chamber, filename): url}."""
    with conn:
        conn.executemany(
            "UPDATE documents SET source_url = ? WHERE folder_chamber = ? AND filename = ?",
            [(url, chamber, filename) for (chamber, filename), url in urls.items()],
        )


def replace_members(conn, members):
    """Reload the members table and clear existing matches (they are redone afterwards)."""
    columns = ["id", "parliament", "chamber", "full_name", "first_names", "last_name", "county",
               "constituency", "party", "date_took_office", "date_left_office", "leadership_role",
               "county_woman_representative", "nominated", "note"]
    with conn:
        conn.execute("UPDATE speeches SET member_id = NULL, match_score = NULL")
        conn.execute("DELETE FROM members")
        conn.executemany(
            f"INSERT INTO members ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            [[m[c] for c in columns] for m in members],
        )


def match_all_speakers(conn, matcher):
    """Match every speech's speaker to a member. Returns the number of matched speeches."""
    rows = conn.execute(
        "SELECT s.id, s.speaker_raw, d.chamber, d.parliament "
        "FROM speeches s JOIN documents d ON d.id = s.document_id"
    ).fetchall()
    updates = []
    for row in rows:
        member_id, score = matcher.match(row["speaker_raw"], row["chamber"], row["parliament"])
        if member_id is not None:
            updates.append((member_id, score, row["id"]))
    with conn:
        conn.executemany("UPDATE speeches SET member_id = ?, match_score = ? WHERE id = ?", updates)
    return len(updates)
