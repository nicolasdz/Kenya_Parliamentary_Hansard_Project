"""Full-text search over speeches, with filters by chamber, date, member, party and language."""

import re

# Length of each result's snippet, in words, around the best-matching passage.
SNIPPET_TOKENS = 24


def build_match_query(text):
    """Turn everyday search text into a safe FTS5 query on the speech text.

    Words are matched individually (all must appear), "quoted phrases" are
    matched exactly, `word*` matches any word starting with "word", and OR
    between terms matches either. Everything else is treated as literal text,
    so apostrophes, hyphens and colons ("Ichung'wah", "COVID-19") don't cause
    syntax errors.
    """
    terms = []
    for token in re.findall(r'"[^"]*"|\S+', text):
        if token == "OR":
            if terms and terms[-1] != "OR":
                terms.append(token)
            continue
        prefix = token.endswith("*") and not token.startswith('"')
        word = token.strip('"').rstrip("*").replace('"', '""')
        if not re.search(r'\w', word):
            continue
        terms.append(f'"{word}"' + ("*" if prefix else ""))
    while terms and terms[-1] == "OR":
        terms.pop()
    if not terms:
        raise ValueError("The search needs at least one word.")
    return "text : (" + " ".join(terms) + ")"


def _filters(chamber, date_from, date_to, member, party, language):
    clauses, params = [], []
    if chamber:
        clauses.append("d.chamber = ?")
        params.append(chamber)
    if date_from:
        clauses.append("d.date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("d.date <= ?")
        params.append(date_to)
    if member:
        # Matches the official name or the name as printed in the Hansard.
        clauses.append("(m.full_name LIKE ? OR s.speaker_raw LIKE ?)")
        params += [f"%{member}%"] * 2
    if party:
        clauses.append("m.party = ? COLLATE NOCASE")
        params.append(party)
    if language:
        clauses.append("s.primary_language = ?")
        params.append(language)
    return "".join(f" AND {c}" for c in clauses), params


_FROM = """
FROM speeches_fts
JOIN speeches s ON s.id = speeches_fts.rowid
JOIN documents d ON d.id = s.document_id
LEFT JOIN members m ON m.id = s.member_id
WHERE speeches_fts MATCH ?
"""


def search(conn, query, chamber=None, date_from=None, date_to=None, member=None, party=None,
           language=None, sort="rank", limit=20, offset=0, raw=False):
    """Return (total_matches, rows) for a search. Each row is a dict.

    With `raw`, `query` is passed to FTS5 unchanged (full FTS5 query syntax).
    `sort` is "rank" (best match first), "newest" or "oldest".
    """
    match = query if raw else build_match_query(query)
    where, params = _filters(chamber, date_from, date_to, member, party, language)
    order = {"rank": "rank", "newest": "d.date DESC, s.seq", "oldest": "d.date, s.seq"}[sort]

    total, = conn.execute(f"SELECT COUNT(*) {_FROM}{where}", [match, *params]).fetchone()
    cursor = conn.execute(
        f"""SELECT s.id AS speech_id, d.date, d.chamber, d.sitting, d.filename, s.page,
                   s.speaker_raw, m.full_name AS member_name, m.party, m.constituency,
                   snippet(speeches_fts, 0, '[', ']', ' ... ', {SNIPPET_TOKENS}) AS snippet,
                   d.source_url, bm25(speeches_fts) AS rank
            {_FROM}{where}
            ORDER BY {order} LIMIT ? OFFSET ?""",
        [match, *params, limit, offset],
    )
    rows = []
    for row in cursor:
        row = dict(row)
        # Browsers open a PDF link at "#page=N".
        row["pdf_link"] = f"{row['source_url']}#page={row['page']}" if row["source_url"] else None
        rows.append(row)
    return total, rows
