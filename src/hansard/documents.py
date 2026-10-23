"""Work out what a PDF is: document type, chamber, sitting date, and sitting time.

Each fact is read from the document's opening text where possible, because the
website's filenames and listings are inconsistent (Senate Hansards appear in the
National Assembly listing, order papers are mixed in, and filenames use many
date formats). The filename is used as a fallback.
"""

import re
from datetime import datetime

# Text before the first "PRAYER(S)" heading (or the first few thousand characters)
# is treated as the document header.
HEADER_MAX_CHARS = 3000
# Documents with less extractable text than this per page are probably scanned images.
MIN_CHARS_PER_PAGE = 200

_WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"

# Start dates of each Parliament (first sitting after the general election).
PARLIAMENT_START_DATES = [
    (13, "2022-09-08"),
    (12, "2017-08-31"),
    (11, "2013-03-28"),
]


def _to_iso_date(day, month, year):
    """Return 'YYYY-MM-DD' for day/month/year strings, or None if they aren't a real date."""
    for month_format in ("%B", "%b", "%m"):
        try:
            date = datetime.strptime(f"{int(day)} {month} {year}", f"%d {month_format} %Y")
        except ValueError:
            continue
        if 2000 <= date.year <= 2100:
            return date.strftime("%Y-%m-%d")
    return None


# (pattern, order of day/month/year groups); tried in turn until one gives a valid date.
_FILENAME_DATE_PATTERNS = [
    # "25th July 2024", "15 October 2026", "15th November, 2018", "24th_February2016"
    (re.compile(r'(?<!\d)(\d{1,2})(?:st|nd|rd|th)?[\s_,.-]*([A-Za-z]{3,9})[\s_,.-]*(\d{4})(?!\d)', re.I), (1, 2, 3)),
    # "April_25_2013", "March 28 2013"
    (re.compile(r'([A-Za-z]{3,9})[\s_,.-]+(\d{1,2})(?:st|nd|rd|th)?[\s_,.-]+(\d{4})(?!\d)', re.I), (2, 1, 3)),
    # "28.03.2013", "27.05_2015"
    (re.compile(r'(?<!\d)(\d{1,2})\.(\d{1,2})[._](\d{4})(?!\d)'), (1, 2, 3)),
]


def date_from_filename(filename):
    """Return the sitting date written in a filename as 'YYYY-MM-DD', or None."""
    name = re.sub(r'\bIst\b', '1st', filename)  # A common typo on the website.
    for pattern, (d, m, y) in _FILENAME_DATE_PATTERNS:
        for match in pattern.finditer(name):
            date = _to_iso_date(match.group(d), match.group(m), match.group(y))
            if date:
                return date
    return None


def date_from_text(text):
    """Return the sitting date from a Hansard's opening text as 'YYYY-MM-DD', or None."""
    # The title line, e.g. "Tuesday, 14th March 2017" or "Wednesday, 14th May, 2025".
    match = re.search(rf'\b(?:{_WEEKDAYS}),?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS}),?\s+(\d{{4}})', text, re.I)
    if match:
        return _to_iso_date(*match.groups())
    # The running page header, e.g. "March 14, 2017 PARLIAMENTARY DEBATES".
    match = re.search(rf'\b({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})', text, re.I)
    if match:
        return _to_iso_date(match.group(2), match.group(1), match.group(3))
    # A bare date, e.g. "21st November 2024" on newer cover pages.
    match = re.search(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS}),?\s+(\d{{4}})', text, re.I)
    if match:
        return _to_iso_date(*match.groups())
    return None


def named_weekday(text):
    """Return the first weekday name in the text, e.g. 'Tuesday', or None."""
    match = re.search(rf'\b({_WEEKDAYS})\b', text, re.I)
    return match.group(1).capitalize() if match else None


def choose_date(filename_date, content_date, weekday):
    """Pick between the filename and content dates when they disagree.

    Either can contain a typo (a wrong year or month), so prefer the one that
    falls on the weekday the document names; otherwise use the filename date.
    """
    if not (filename_date and content_date) or filename_date == content_date:
        return filename_date or content_date
    if weekday:
        for date in (filename_date, content_date):
            if datetime.strptime(date, "%Y-%m-%d").strftime("%A") == weekday:
                return date
    return filename_date


def document_type(header):
    if re.search(r'THE HANSARD|OFFICIAL REPORT|\bDEBATES\b', header):
        return "hansard"
    if "VOTES AND PROCEEDINGS" in header:
        return "votes_and_proceedings"
    if "ORDER PAPER" in header or "ORDERS OF THE DAY" in header:
        return "order_paper"
    return "unknown"


def chamber_from_header(header):
    if "JOINT SITTING" in header:
        return "joint"
    if re.search(r'\bSENATE\b', header):
        return "senate"
    if "NATIONAL ASSEMBLY" in header:
        return "national_assembly"
    return None


def _sitting_from_time(hour, am_pm):
    hour = int(hour)
    if am_pm.lower() == "a":
        return "morning"
    return "evening" if 5 <= hour < 12 else "afternoon"


_HOUR_WORDS = {w: i for i, w in enumerate(
    "one two three four five six seven eight nine ten eleven twelve".split(), start=1)}


def _sitting_from_hour(hour):
    """Bucket an hour written without a.m./p.m. (Parliament doesn't sit at night)."""
    if 7 <= hour <= 11:
        return "morning"
    return "evening" if 5 <= hour <= 6 else "afternoon"


def sitting_from_text(text):
    """Return 'morning', 'afternoon' or 'evening' from "The House met at 2.30 p.m.", or None."""
    match = re.search(r'\bmet\b.{0,150}?\bat,?\s+(\d{1,2})[.:]\d{2}\s*([ap])\.?\s*m\b', text, re.I | re.S)
    if match:
        return _sitting_from_time(*match.groups())
    # Joint sittings spell the time out: "Parliament met at ten minutes past three o'clock".
    match = re.search(rf"\bmet at (?:[\w\s-]{{1,30}}? (past|to) )?({'|'.join(_HOUR_WORDS)})\s*o\W{{0,2}}clock",
                      text, re.I)
    if match:
        hour = _HOUR_WORDS[match.group(2).lower()]
        return _sitting_from_hour(hour - 1 if (match.group(1) or "").lower() == "to" else hour)
    match = re.search(r'\b(MORNING|AFTERNOON|EVENING) SITTING\b', text, re.I)
    if match:
        return match.group(1).lower()
    return None


_SITTING_CODES = {"A": "morning", "P": "afternoon", "E": "evening"}


def sitting_from_filename(filename):
    """Read the sitting from filename markers such as "(A)", "2018P", "AM", or "Morning"."""
    stem = re.sub(r'\.pdf$', '', filename, flags=re.I)
    match = re.search(r'morning|afternoon|evening', stem, re.I)
    if match:
        return match.group(0).lower()
    match = re.search(r'(?<![A-Za-z])(\d{1,2})[.:]\d{2}\s*([ap])\.?m\b', stem, re.I)
    if match:
        return _sitting_from_time(*match.groups())
    match = re.search(r'(?<![A-Za-z])([ap])\.?m\.?(?![A-Za-z])', stem, re.I)
    if match:
        return "morning" if match.group(1).lower() == "a" else "afternoon"
    match = re.search(r'(?<![A-Za-z])([APE])(?![A-Za-z])', stem)
    if match:
        return _SITTING_CODES[match.group(1)]
    return None


def parliament_for_date(date):
    """Return the Parliament number (11, 12, 13) in session on a 'YYYY-MM-DD' date, or None."""
    if not date:
        return None
    for number, start in PARLIAMENT_START_DATES:
        if date >= start:
            return number
    return None


def classify(filename, opening_text, page_count, text_chars, folder_chamber):
    """Describe a PDF from its filename and the text of its first pages."""
    normalized = re.sub(r'\s+', ' ', opening_text)
    upper = normalized.upper()
    prayer = upper.find("PRAYER")
    header = upper[:prayer] if 0 <= prayer < HEADER_MAX_CHARS else upper[:HEADER_MAX_CHARS]

    if text_chars < MIN_CHARS_PER_PAGE * max(page_count, 1):
        doc_type = "no_text"
    else:
        doc_type = document_type(header)

    filename_date = date_from_filename(filename)
    content_date = date_from_text(normalized)
    date = choose_date(filename_date, content_date, named_weekday(filename) or named_weekday(normalized))

    return {
        "doc_type": doc_type,
        "chamber": chamber_from_header(header) or folder_chamber,
        "date": date,
        "filename_date": filename_date,
        "content_date": content_date,
        "parliament": parliament_for_date(date),
        "sitting": sitting_from_text(normalized) or sitting_from_filename(filename),
        "special_sitting": "SPECIAL SITTING" in header or "special" in filename.lower(),
        "page_count": page_count,
        "text_chars": text_chars,
    }
