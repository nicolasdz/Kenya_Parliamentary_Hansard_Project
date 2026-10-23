import pymupdf
import pytest

from hansard.parse import (
    MAX_WORDS,
    chunk_text,
    extract_file_metadata,
    process_pdf_file,
    repair_and_clean_text,
)


@pytest.mark.parametrize("filename, expected", [
    ("Hansard Report - Thursday, 25th July 2024 (P).pdf", "2024-07-25"),
    ("Hansard_Report_-_Tuesday_14th_April_2015P.pdf", "2015-04-14"),
    ("Hansard Report - Thursday, 15th November, 2018(A).pdf", None),  # Comma breaks the filename pattern.
])
def test_date_from_filename(filename, expected):
    if expected is None:
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), "Thursday, 15th November, 2018")
        expected = "2018-11-15"
    else:
        doc = None  # Never read when the filename has a date.
    assert extract_file_metadata(filename, doc) == {"date": expected}


def test_repair_and_clean_text_strips_tags_and_whitespace():
    assert repair_and_clean_text("<b>Hon.   Speaker</b>\n said") == "Hon. Speaker said"


def test_chunk_text_splits_long_speeches():
    text = " ".join(f"w{i}" for i in range(MAX_WORDS * 2 + 10))
    chunks = chunk_text(text)
    assert [len(c.split()) for c in chunks] == [MAX_WORDS, MAX_WORDS, 10]
    assert chunk_text("") == []


def test_process_pdf_file_extracts_speeches(tmp_path):
    pdf_path = tmp_path / "Hansard Report - Thursday, 25th July 2024 (P).pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "PRAYERS",
        "Hon. Speaker: Order, Members. (Applause)",
        "Hon. Wetang'ula: Thank you, Hon. Speaker.",
        "I rise to support the Bill.",
    ]
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + 40 * i), line)
    doc.save(pdf_path)

    records = process_pdf_file(pdf_path)

    assert [(r["speaker"], r["content"]) for r in records] == [
        ("Hon. Speaker", "Order, Members."),
        # Chunking re-joins words with spaces, so paragraph breaks are lost.
        ("Hon. Wetang'ula", "Thank you, Hon. Speaker. I rise to support the Bill."),
    ]
    assert all(r["date"] == "2024-07-25" and not r["is_continuation"] for r in records)
