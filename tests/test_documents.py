import pytest

from hansard.documents import (
    chamber_from_header,
    choose_date,
    classify,
    date_from_filename,
    date_from_text,
    document_type,
    parliament_for_date,
    sitting_from_filename,
    sitting_from_text,
)


@pytest.mark.parametrize("filename, expected", [
    ("Hansard Report - Thursday, 25th July 2024 (P).pdf", "2024-07-25"),
    ("Hansard_Report_-_Tuesday_14th_April_2015P.pdf", "2015-04-14"),
    ("Hansard Report - Thursday, 15th November, 2018(A).pdf", "2018-11-15"),
    ("The Hansard - Thursday, 15 October 2026.pdf", "2026-10-15"),
    ("Wednesday_24th_February2016.pdf", "2016-02-24"),
    ("Thursday_April_25_2013_1.pdf", "2013-04-25"),
    ("Hansard_Senate_22.05.2013A.pdf", "2013-05-22"),
    ("27.05_2015.pdf", "2015-05-27"),
    ("Hansard Report - Wednesday, Ist December 2021 (A).pdf", "2021-12-01"),
    ("Thursday_25th_May_207.pdf", None),  # Typo in the year; the content date is used instead.
    ("28TH_APRIL.pdf", None),
])
def test_date_from_filename(filename, expected):
    assert date_from_filename(filename) == expected


@pytest.mark.parametrize("text, expected", [
    ("March 14, 2017 PARLIAMENTARY DEBATES 1 ... Tuesday, 14th March 2017 The House met", "2017-03-14"),
    ("THE SENATE THE HANSARD Wednesday, 14th May, 2025 Morning Sitting", "2025-05-14"),
    ("THE HANSARD 21st November 2024 VOL. III", "2024-11-21"),
    ("No date here", None),
])
def test_date_from_text(text, expected):
    assert date_from_text(text) == expected


@pytest.mark.parametrize("header, expected", [
    ("NATIONAL ASSEMBLY OFFICIAL REPORT", "hansard"),
    ("PARLIAMENT OF KENYA THE SENATE THE HANSARD", "hansard"),
    ("THE SENATE VOTES AND PROCEEDINGS TUESDAY", "votes_and_proceedings"),
    ("THE NATIONAL ASSEMBLY ORDERS OF THE DAY", "order_paper"),
    ("SOMETHING ELSE", "unknown"),
])
def test_document_type(header, expected):
    assert document_type(header) == expected


@pytest.mark.parametrize("header, expected", [
    ("JOINT SITTING OF THE NATIONAL ASSEMBLY AND THE SENATE THE HANSARD", "joint"),
    ("MAY 25, 2017 SENATE DEBATES PARLIAMENT OF KENYA THE SENATE", "senate"),
    ("NATIONAL ASSEMBLY OFFICIAL REPORT", "national_assembly"),
    ("THE HANSARD", None),
])
def test_chamber_from_header(header, expected):
    assert chamber_from_header(header) == expected


@pytest.mark.parametrize("text, expected", [
    ("The House met at 2.30 p.m.", "afternoon"),
    ("The Senate met at the Kenyatta International Conference Centre at 9.00 a.m.", "morning"),
    ("The House met at 6.30 p.m.", "evening"),
    ("Thursday, 14th May, 2025 Morning Sitting", "morning"),
    ("The House met at the Senate Chamber, Parliament Buildings at, 2.30 p.m.", "afternoon"),
    ("Parliament met at fifteen minutes past three o'clock in the", "afternoon"),
    ("Parliament met at five minutes to three O'clock", "afternoon"),
    ("Parliament met at ten o'clock", "morning"),
    ("No sitting time here", None),
])
def test_sitting_from_text(text, expected):
    assert sitting_from_text(text) == expected


@pytest.mark.parametrize("filename_date, content_date, weekday, expected", [
    ("2020-02-09", "2021-02-09", "Tuesday", "2021-02-09"),  # Year typo in the filename.
    ("2017-04-05", "2017-03-05", "Wednesday", "2017-04-05"),  # Month typo in the content.
    ("2019-02-10", "2020-02-10", "Tuesday", "2019-02-10"),  # Neither matches: use the filename.
    ("2019-02-10", "2020-02-10", None, "2019-02-10"),
    (None, "2020-02-10", "Monday", "2020-02-10"),
])
def test_choose_date(filename_date, content_date, weekday, expected):
    assert choose_date(filename_date, content_date, weekday) == expected


@pytest.mark.parametrize("filename, expected", [
    ("Hansard Report - Thursday, 13th May 2021(A).pdf", "morning"),
    ("Hansard Report - Monday, 25th November 2024 (E).pdf", "evening"),
    ("Hansard_Report_-_Wednesday_11th_April_2018P.pdf", "afternoon"),
    ("Wednesday_April_17_2013_AM.pdf", "morning"),
    ("Wednesday, 2nd August, 2023 - A.M.pdf", "morning"),
    ("Tuesday, 28th November, 2023 at 2.30 p.m. (1).pdf", "afternoon"),
    ("Thursday_14th_July_2016_-_Morning.pdf", "morning"),
    ("25th_November_2015.pdf", None),
])
def test_sitting_from_filename(filename, expected):
    assert sitting_from_filename(filename) == expected


@pytest.mark.parametrize("date, expected", [
    ("2013-03-28", 11), ("2017-08-30", 11), ("2017-08-31", 12), ("2022-09-08", 13), ("2012-01-01", None), (None, None),
])
def test_parliament_for_date(date, expected):
    assert parliament_for_date(date) == expected


def test_classify_prefers_content_chamber_over_folder():
    text = "May 25, 2017 SENATE DEBATES 1 PARLIAMENT OF KENYA THE SENATE THE HANSARD Thursday, 25th May, 2017 " \
           "The House met at the Senate Chamber, Parliament Buildings, at 2.30 p.m. PRAYERS"
    document = classify("Thursday_25th_May_207.pdf", text, page_count=1, text_chars=5000,
                        folder_chamber="national_assembly")
    assert document["chamber"] == "senate"
    assert document["date"] == "2017-05-25" and document["date"] == document["content_date"]
    assert document["sitting"] == "afternoon"


def test_classify_flags_scanned_documents():
    document = classify("scan.pdf", "", page_count=10, text_chars=50, folder_chamber="senate")
    assert document["doc_type"] == "no_text"
