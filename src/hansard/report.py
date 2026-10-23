"""Data-quality summary and CSV export of the database."""

import csv

EXPORT_QUERY = """
SELECT s.id AS speech_id, d.filename, d.chamber, d.date, d.sitting, d.special_sitting,
       d.parliament, s.seq, s.page, s.speaker_raw,
       m.full_name AS member_name, m.party, m.county, m.constituency, s.match_score,
       s.primary_language, s.language_distribution, s.word_count, s.text, d.source_url
FROM speeches s
JOIN documents d ON d.id = s.document_id
LEFT JOIN members m ON m.id = s.member_id
{where}
ORDER BY d.date, d.chamber, d.sitting, d.filename, s.seq
"""


def export_speeches_csv(conn, path, chamber=None):
    """Write one row per speech to a CSV. Returns the number of rows written."""
    where, params = ("WHERE d.chamber = ?", [chamber]) if chamber else ("", [])
    cursor = conn.execute(EXPORT_QUERY.format(where=where), params)
    columns = [c[0] for c in cursor.description]
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in cursor:
            writer.writerow(row)
            rows += 1
    return rows


def _section(title):
    print(f"\n== {title}")


def _examples(rows, limit=8):
    for row in rows[:limit]:
        print("   ", " | ".join("" if v is None else str(v) for v in row))
    if len(rows) > limit:
        print(f"    ... and {len(rows) - limit} more")


def print_report(conn):
    q = lambda sql: conn.execute(sql).fetchall()

    _section("Documents by type and chamber")
    for doc_type, chamber, n in q("SELECT doc_type, chamber, COUNT(*) FROM documents GROUP BY 1, 2 ORDER BY 1, 2"):
        print(f"    {doc_type:22s} {chamber or '?':18s} {n:6d}")

    hansards = "FROM documents WHERE doc_type = 'hansard'"

    rows = q(f"SELECT filename, folder_chamber, chamber {hansards} AND chamber != folder_chamber AND chamber != 'joint'")
    _section(f"Hansards whose content names a different chamber than their listing: {len(rows)}")
    _examples(rows)

    rows = q(f"SELECT filename {hansards} AND date IS NULL")
    _section(f"Hansards with no date: {len(rows)}")
    _examples(rows)

    rows = q(f"SELECT filename, filename_date, content_date, date {hansards} "
             "AND filename_date IS NOT NULL AND content_date IS NOT NULL AND filename_date != content_date")
    _section(f"Hansards whose filename and content dates disagree: {len(rows)} "
             "(filename | content | chosen: the one on the weekday named)")
    _examples(rows)

    rows = q(f"SELECT filename {hansards} AND sitting IS NULL")
    _section(f"Hansards with no sitting (morning/afternoon/evening): {len(rows)}")
    _examples(rows)

    rows = q(f"SELECT filename, page_count {hansards} AND id NOT IN (SELECT DISTINCT document_id FROM speeches)")
    _section(f"Hansards with no speeches found: {len(rows)}")
    _examples(rows)

    rows = q("SELECT filename, page_count, text_chars FROM documents WHERE doc_type IN ('no_text', 'unknown')")
    _section(f"Documents with no text layer (need OCR) or of unknown type: {len(rows)}")
    _examples(rows)

    rows = q(f"SELECT chamber, date, sitting, COUNT(*), GROUP_CONCAT(filename, ' ; ') {hansards} "
             "AND date IS NOT NULL GROUP BY chamber, date, sitting HAVING COUNT(*) > 1")
    _section(f"Sittings with more than one Hansard (possible revised copies): {len(rows)}")
    _examples(rows)

    rows = q(f"SELECT COUNT(*) {hansards} AND source_url IS NULL")
    _section(f"Hansards with no source URL in the manifest: {rows[0][0]}")

    _section("Speeches")
    total, = q("SELECT COUNT(*) FROM speeches")[0]
    print(f"    Total: {total}")
    coverage = "(SELECT DISTINCT parliament, chamber FROM members)"
    matchable_sql = (f"FROM speeches s JOIN documents d ON d.id = s.document_id WHERE EXISTS "
                     f"(SELECT 1 FROM {coverage} c WHERE c.parliament = d.parliament "
                     f"AND (c.chamber = d.chamber OR d.chamber = 'joint'))")
    matchable, matched = q(f"SELECT COUNT(*), COUNT(s.member_id) {matchable_sql}")[0]
    print(f"    In a chamber/Parliament covered by the member list: {matchable}")
    if matchable:
        print(f"    Matched to a member: {matched} ({matched / matchable:.0%})")
    for language, n in q("SELECT primary_language, COUNT(*) FROM speeches GROUP BY 1 ORDER BY 2 DESC"):
        print(f"    Primary language {language or '?'}: {n}")

    rows = q(f"SELECT s.speaker_raw, COUNT(*) {matchable_sql} AND s.member_id IS NULL "
             "GROUP BY s.speaker_raw ORDER BY 2 DESC LIMIT 15")
    _section("Most frequent unmatched speakers (in covered chambers/Parliaments)")
    _examples(rows, limit=15)
