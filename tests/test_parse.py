import pymupdf
import pytest

from hansard.parse import clean_speech, extract_speeches, parse_document, repair_and_clean_text


def make_pdf(path, lines):
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + 30 * i), line)
    doc.save(path)


def test_repair_and_clean_text_strips_tags_and_whitespace():
    assert repair_and_clean_text("<b>Hon.   Speaker</b>\n said") == "Hon. Speaker said"


def test_repair_and_clean_text_keeps_backslashes():
    assert repair_and_clean_text(r"KSh 10\- only") == r"KSh 10\- only"


def test_clean_speech_removes_notes_and_keeps_paragraphs():
    text = clean_speech(["Order, Members. (Applause)", "I   rise to support.", "SENATE DEBATES"])
    assert text == "Order, Members.\nI rise to support."


@pytest.mark.parametrize("paragraphs", [
    # Page header and disclaimer split across paragraphs mid-sentence.
    ["The Jubilee", "December, 05, 2018 PARLIAMENTARY DEBATES 8", "A",
     "certified version of this Report can be obtained from the Hansard Editor.", "Government has acted."],
    ["The Jubilee", "May 8, 2019 PARLIAMENTARY DEBATES ____ 24", "Government has acted."],
    ["The Jubilee", "A certified version of this Report can be obtained from the Director, Hansard Services,",
     "Senate.", "Government has acted."],
    ["The Jubilee", "Thursday, 25th July 2024 NATIONAL ASSEMBLY DEBATES 3", "Government has acted."],
])
def test_clean_speech_removes_split_headers_and_disclaimers(paragraphs):
    assert clean_speech(paragraphs) == "The Jubilee\nGovernment has acted."


def test_clean_speech_keeps_ordinary_mentions_of_debates():
    assert clean_speech(["During the Senate debates on this Bill."]) == "During the Senate debates on this Bill."


def test_role_lines_start_new_speeches():
    blocks = [(1, "Hon. Speaker: Order."), (1, "The Temporary Deputy Chairman (Hon. Omulele): Proceed."),
              (1, "The Clerk of the National Assembly (Mr. Bundi): Thank you."),
              (1, "Hon. Oluoch's letter raised the following issues that I must now put to the House for a ruling: one")]
    assert [s["speaker_raw"] for s in extract_speeches(blocks)] == [
        "Hon. Speaker", "The Temporary Deputy Chairman (Hon. Omulele)", "The Clerk of the National Assembly (Mr. Bundi)",
    ]


def test_parse_document(tmp_path):
    path = tmp_path / "Hansard Report - Thursday, 25th July 2024 (P).pdf"
    make_pdf(path, [
        "NATIONAL ASSEMBLY",
        "OFFICIAL REPORT",
        "Thursday, 25th July 2024",
        "The House met at 2.30 p.m.",
        "PRAYERS",
        "Hon. Speaker: Order, Members. (Applause)",
        "Hon. Wetang'ula: Thank you, Hon. Speaker.",
        "I rise to support the Bill.",
    ] + ["Filler text so the page counts as having a text layer."] * 5)

    document, speeches = parse_document(path, "national_assembly")

    assert document["doc_type"] == "hansard"
    assert document["chamber"] == "national_assembly"
    assert document["date"] == "2024-07-25"
    assert document["sitting"] == "afternoon"
    assert document["parliament"] == 13
    assert [(s["seq"], s["page"], s["speaker_raw"]) for s in speeches] == [
        (1, 1, "Hon. Speaker"), (2, 1, "Hon. Wetang'ula"),
    ]
    assert speeches[0]["text"] == "Order, Members."
    assert speeches[1]["text"].startswith("Thank you, Hon. Speaker.\nI rise to support the Bill.")
    assert speeches[1]["primary_language"] == "en"


def test_non_hansard_documents_have_no_speeches(tmp_path):
    path = tmp_path / "ORDER PAPER FOR TUESDAY, 12TH AUGUST 2025.pdf"
    make_pdf(path, ["THE NATIONAL ASSEMBLY", "ORDERS OF THE DAY", "Hon. Speaker: not a speech"]
             + ["Filler text so the page counts as having a text layer."] * 5)

    document, speeches = parse_document(path, "national_assembly")

    assert document["doc_type"] == "order_paper"
    assert speeches == []
