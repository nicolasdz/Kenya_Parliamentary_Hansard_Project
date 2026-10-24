import sqlite3

import pytest

from hansard import search, store


def document(sha, chamber, date):
    return {
        "sha256": sha, "filename": f"{sha}.pdf", "folder_chamber": chamber, "doc_type": "hansard",
        "chamber": chamber, "date": date, "filename_date": date, "content_date": date,
        "parliament": 13, "sitting": "afternoon", "special_sitting": False, "page_count": 3, "text_chars": 9000,
    }


def speech(seq, speaker, text, language="en"):
    return {"seq": seq, "page": seq, "speaker_raw": speaker, "text": text, "word_count": len(text.split()),
            "language_distribution": f'{{"{language}": 1.0}}', "primary_language": language}


@pytest.fixture
def conn(tmp_path):
    conn = store.connect(tmp_path / "test.db")
    store.save_document(conn, document("a", "senate", "2023-05-10"), [
        speech(1, "Sen. Cheruiyot", "The housing levy will build homes for Kenyans."),
        speech(2, "Sen. Omtatah", "The levy is unconstitutional; the Housing Fund lacks a law."),
        speech(3, "Sen. Faki", "Kwa hivyo, ninaunga mkono Mswada huu wa elimu.", language="sw"),
    ], parser_version=3)
    store.save_document(conn, document("b", "national_assembly", "2024-02-01"), [
        speech(1, "Hon. Ichung'wah", "The Affordable Housing Bill implements the housing levy."),
        speech(2, "Hon. Housing", "Nothing to see here; the speaker's name is not searched."),
    ], parser_version=3)
    with conn:
        conn.execute("INSERT INTO members (id, parliament, chamber, full_name, party) "
                     "VALUES (1, 13, 'senate', 'Cheruiyot, Aaron Kipkirui', 'UDA')")
        conn.execute("UPDATE speeches SET member_id = 1 WHERE speaker_raw = 'Sen. Cheruiyot'")
    return conn


def speakers(rows):
    return sorted(r["speaker_raw"] for r in rows)


@pytest.mark.parametrize("text, expected", [
    ("housing levy", 'text : ("housing" "levy")'),
    ('"housing levy"', 'text : ("housing levy")'),
    ("elim*", 'text : ("elim"*)'),
    ("levy OR elimu", 'text : ("levy" OR "elimu")'),
    ("Ichung'wah COVID-19:", "text : (\"Ichung'wah\" \"COVID-19:\")"),
    ("OR levy OR", 'text : ("levy")'),
])
def test_build_match_query(text, expected):
    assert search.build_match_query(text) == expected


@pytest.mark.parametrize("text", ["", "  ", '"" * :'])
def test_empty_queries_are_rejected(text):
    with pytest.raises(ValueError):
        search.build_match_query(text)


def test_words_and_phrases(conn):
    assert speakers(search.search(conn, "housing levy")[1]) == ["Hon. Ichung'wah", "Sen. Cheruiyot", "Sen. Omtatah"]
    assert speakers(search.search(conn, '"housing levy"')[1]) == ["Hon. Ichung'wah", "Sen. Cheruiyot"]
    assert speakers(search.search(conn, "elim*")[1]) == ["Sen. Faki"]
    # Only speech text is searched, not the speaker line.
    assert speakers(search.search(conn, "Ichung'wah")[1]) == []


def test_filters(conn):
    assert speakers(search.search(conn, "levy", chamber="senate")[1]) == ["Sen. Cheruiyot", "Sen. Omtatah"]
    assert speakers(search.search(conn, "levy", date_from="2024-01-01")[1]) == ["Hon. Ichung'wah"]
    assert speakers(search.search(conn, "levy", date_to="2023-12-31")[1]) == ["Sen. Cheruiyot", "Sen. Omtatah"]
    assert speakers(search.search(conn, "levy", member="cheruiyot")[1]) == ["Sen. Cheruiyot"]
    assert speakers(search.search(conn, "levy", member="Omtatah")[1]) == ["Sen. Omtatah"]  # Printed name.
    assert speakers(search.search(conn, "levy", party="uda")[1]) == ["Sen. Cheruiyot"]
    assert speakers(search.search(conn, "mkono", language="sw")[1]) == ["Sen. Faki"]


def test_results_have_snippet_link_and_total(conn):
    total, rows = search.search(conn, "levy", sort="oldest", limit=1)
    assert total == 3 and len(rows) == 1
    row = rows[0]
    assert row["date"] == "2023-05-10"
    assert "[levy]" in row["snippet"]
    assert row["pdf_link"] is None  # No source URL stored in this test.
    store.update_source_urls(conn, {("senate", "a.pdf"): "https://example.org/a.pdf"})
    assert search.search(conn, "levy", sort="oldest", limit=1)[1][0]["pdf_link"] == "https://example.org/a.pdf#page=1"


def test_index_follows_replaced_documents(conn):
    store.save_document(conn, document("a", "senate", "2023-05-10"), [speech(1, "Sen. Cheruiyot", "Only roads now.")], parser_version=3)
    assert speakers(search.search(conn, "levy")[1]) == ["Hon. Ichung'wah"]
    assert speakers(search.search(conn, "roads")[1]) == ["Sen. Cheruiyot"]


def test_migration_indexes_an_existing_database(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.row_factory = sqlite3.Row
    old.execute("PRAGMA foreign_keys = ON")
    old.executescript(store.SCHEMA)  # A database from before the search index existed.
    store.save_document(old, document("a", "senate", "2023-05-10"), [speech(1, "Sen. Faki", "Housing matters.")], parser_version=3)
    old.close()

    conn = store.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(store.MIGRATIONS)
    assert speakers(search.search(conn, "housing")[1]) == ["Sen. Faki"]
