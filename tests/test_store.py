import csv

from hansard import report, store
from hansard.members import SpeakerMatcher

DOCUMENT = {
    "sha256": "abc", "filename": "a.pdf", "folder_chamber": "senate", "doc_type": "hansard",
    "chamber": "senate", "date": "2024-07-25", "filename_date": "2024-07-25", "content_date": "2024-07-25",
    "parliament": 13, "sitting": "afternoon", "special_sitting": False, "page_count": 3, "text_chars": 9000,
}
SPEECHES = [
    {"seq": 1, "page": 1, "speaker_raw": "Sen. Cheruiyot", "text": "Hello.", "word_count": 1,
     "language_distribution": '{"en": 1.0}', "primary_language": "en"},
    {"seq": 2, "page": 2, "speaker_raw": "Sen. Nobody", "text": "Bye.", "word_count": 1,
     "language_distribution": '{"en": 1.0}', "primary_language": "en"},
]
MEMBERS = [{"id": 7, "parliament": 13, "chamber": "senate", "full_name": "Cheruiyot, Aaron Kipkirui",
            "first_names": None, "last_name": None, "county": "Kericho", "constituency": None, "party": "UDA",
            "date_took_office": None, "date_left_office": None, "leadership_role": None,
            "county_woman_representative": None, "nominated": None, "note": None}]


def test_save_match_and_export(tmp_path):
    conn = store.connect(tmp_path / "test.db")
    store.save_document(conn, DOCUMENT, SPEECHES, parser_version=1)
    # Saving the same file again replaces it rather than duplicating it.
    store.save_document(conn, DOCUMENT, SPEECHES, parser_version=2)
    assert store.parsed_versions(conn) == {"abc": 2}

    store.update_source_urls(conn, {("senate", "a.pdf"): "https://example.org/a.pdf"})
    store.replace_members(conn, MEMBERS)
    assert store.match_all_speakers(conn, SpeakerMatcher(MEMBERS)) == 1

    output = tmp_path / "speeches.csv"
    assert report.export_speeches_csv(conn, output) == 2
    with open(output, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["member_name"] == "Cheruiyot, Aaron Kipkirui"
    assert rows[0]["party"] == "UDA"
    assert rows[0]["source_url"] == "https://example.org/a.pdf"
    assert rows[1]["member_name"] == ""

    report.print_report(conn)  # Smoke test: runs without errors.
