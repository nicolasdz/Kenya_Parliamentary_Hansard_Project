"""Extract individual speeches from Hansard PDFs.

Originally written by Joshua Been as the "Hansard Parser" notebook (August 2025).
The logic is ported unchanged so outputs match the existing CSVs; known bugs are
marked TODO(phase 2) and will be fixed separately.
"""

import html
import re
import warnings
from datetime import datetime
from pathlib import Path

import pymupdf
from unidecode import unidecode

# --- Speaker Identification ---
# A regular expression to identify lines where a speaker begins.
# It looks for common honorifics and titles that precede a speaker's name.
SPEAKER_PATTERN = re.compile(
    r'^(Hon\.|Sen\.|Dr\.|Prof\.|Mr\.|Mrs\.|Ms\.|The Speaker|The Deputy Speaker|The Temporary Speaker|Hon\. Chairlady|The Temporary Speaker \(Hon\.\)|Hon\. Members)',
    re.IGNORECASE,
)

# --- Content Cleaning ---
# Exact phrases to be completely removed from the text (matched case-insensitively,
# with any whitespace between words). These are typically parenthetical notes
# about events in the chamber, or page headers and disclaimers.
EXACT_PHRASES_TO_REMOVE = [
    "(Applause)", "(Laughter)",
    "(Loud consultations)",
    "(Loud Consultations)",
    "(The Quorum Bell was rung)",
    "(The Division Bell was rung)",
    "(Voting in progress)",
    "(Serjeant-at-Arms closed the bars)",
    "(Question put and agreed to)",
    "(Question of the amendment proposed)",
    "(Question proposed)",
    "(The Speaker consulted the Clerks-at-the-Table)",
    "(The Clerk-at-the-Table consulted the Speaker)",
    "Disclaimer: The electronic version of the Official Hansard Report is for information purposes only.",
    # The disclaimer is often split by a line break right here, so both halves are listed too.
    "Disclaimer: The electronic version of the Official Hansard Report is for information purposes",
    "only. A certified version of this Report can be obtained from the Hansard Editor.",
    "A certified version of this Report can be obtained from the Hansard Editor.",
    "Disclaimer: The electronic version of the Senate Hansard Report is for information purposes only.",
    "A certified version of this Report can be obtained from the Hansard Editor, Senate.",
    "A certified version of this Report can be obtained from the Director, Hansard and Audio Services, Senate.",
    "Disclaimer: The electronic version of the Senate Hansard Report is for information purposes",
    "only. A certified version of this Report can be obtained from the Director, Hansard and Audio",
    "Services, Senate.",
    "NATIONAL ASSEMBLY DEBATES",
    "SENATE DEBATES",
]

# Make each phrase flexible by letting any run of whitespace match between words.
_EXACT_PHRASE_PATTERNS = [
    re.compile(re.escape(phrase).replace("\\ ", r"\s+"), re.IGNORECASE)
    for phrase in EXACT_PHRASES_TO_REMOVE
]

# More complex patterns, applied LINE BY LINE to the speech content.
REGEX_PATTERNS_TO_REMOVE = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\(.*?spoke off the record.*?\)",
        r"\(The Oath of Allegiance was administered to.*?\)",
        r"\(Question carried by.*?\)",
        r"\(The Bill was.*?\)",
        r"\(.*?laid the document on the Table\)",
    ]
]

# Patterns removed from the ENTIRE multi-line speech at once, before line-by-line
# cleaning. They remove page headers like "December 29, 2020 SENATE DEBATES 31"
# even when the extracted text splits them across lines.
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
MULTI_LINE_REGEX_PATTERNS_TO_REMOVE = [
    re.compile(rf'\b(?:{_MONTHS})\s+\d{{1,2}},\s+\d{{4}}[\s\r\n]+SENATE[\s\r\n]+DEBATES[\s\r\n]+\d+', re.IGNORECASE),
    re.compile(rf'\b(?:{_MONTHS})\s+\d{{1,2}},\s+\d{{4}}[\s\r\n]+PARLIAMENTARY[\s\r\n]+DEBATES[\s\r\n]+\d+', re.IGNORECASE),
]

# Procedural headings (compared upper-case) that are not speeches and are skipped.
HEADINGS_TO_IGNORE = {
    "PRAYER",
    "PRAYERS", "COMMUNICATION FROM THE CHAIR", "PAPERS LAID", "NOTICE OF MOTION",
    "ORDINARY QUESTIONS", "REQUEST FOR STATEMENTS", "ADMINISTRATION OF OATH",
    "PETITION", "STATEMENTS", "PERSONAL STATEMENT", "MOTION", "MOTIONS", "BILL", "BILLS",
    "DIVISION", "ADJOURNMENT", "PAPER LAID", "PAPER", "PAPERS",
    "DETERMINATION OF QUORUM AT COMMENCEMENT OF SITTING",
}

# --- Chunking ---
# Long speeches are split into chunks. Excel can't handle much more than 30,000
# characters per cell, and the analysis notebook's ML models accept 512 tokens;
# a 480-word limit and a 30k character limit address both.
MAX_WORDS = 480
MAX_CHARS = 30000


def repair_and_clean_text(text):
    """Repair encoding errors in text extracted from the PDF and reduce it to plain ASCII."""
    if not text:
        return ""

    # Step 1: Repair common encoding errors (mojibake).
    try:
        repaired_text = text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        repaired_text = text

    # Step 2: Remove HTML tags (e.g. <b>, <span>) before any other processing.
    no_html = re.sub(r'<.*?>', '', repaired_text)

    # Step 3: Transliterate to plain ASCII.
    ascii_text = unidecode(no_html)

    # Step 4: Decode escaped sequences (e.g. "\\n" -> "\n"), then replace newlines.
    # TODO(phase 2): unicode_escape also mangles any literal backslash in the text.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ascii_text = ascii_text.encode('utf-8').decode('unicode_escape')
    except UnicodeDecodeError:
        pass
    ascii_text = re.sub(r'[\r\n]+', ' ', ascii_text).replace('\\n', ' ')

    # Step 5: Collapse runs of spaces or tabs.
    normalized_space = re.sub(r'[ \t]+', ' ', ascii_text)
    return normalized_space.strip()


def extract_file_metadata(filename, doc):
    """Extract the sitting date, preferring the filename and falling back to the first pages."""
    metadata = {"date": None}

    # Plan A: parse the date from the filename (e.g. "Hansard - 25th July 2024.pdf").
    date_match_name = re.search(r'(\d{1,2})(?:st|nd|rd|th)[\s_]([A-Za-z]+)[\s_](\d{4})', filename, re.IGNORECASE)
    if date_match_name:
        try:
            date_str = f"{date_match_name.group(1)} {date_match_name.group(2)} {date_match_name.group(3)}"
            metadata["date"] = datetime.strptime(date_str, "%d %B %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass  # e.g. "32nd July"; fall through to Plan B.

    # Plan B: scan the first couple of pages for "25th July, 2024" or "July 25, 2024".
    if not metadata["date"]:
        text_from_first_pages = ""
        for page_num in range(min(2, len(doc))):
            text_from_first_pages += doc[page_num].get_text()

        date_match1 = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})\b', text_from_first_pages)
        date_match2 = re.search(r'\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b', text_from_first_pages)

        date_str, date_format = None, None
        if date_match1:
            date_str = f"{date_match1.group(1)} {date_match1.group(2)} {date_match1.group(3)}"
            date_format = "%d %B %Y"
        elif date_match2:
            date_str = f"{date_match2.group(1)} {date_match2.group(2)} {date_match2.group(3)}"
            date_format = "%B %d %Y"

        if date_str and date_format:
            try:
                metadata["date"] = datetime.strptime(date_str, date_format).strftime("%Y-%m-%d")
            except ValueError:
                metadata["date"] = date_str  # Keep the raw string if the format is unexpected.

    return metadata


def _extract_blocks(doc):
    """Return the cleaned text of every paragraph in the document, in order."""
    blocks = []
    for page in doc:
        # Extracting each page as HTML preserves paragraph structure.
        decoded_html = html.unescape(page.get_text("html"))
        for p_html in re.findall(r'<p.*?>(.*?)</p>', decoded_html, re.DOTALL):
            p_text = repair_and_clean_text(p_html)
            if p_text:
                blocks.append(p_text)
    return blocks


def _find_speakers(blocks):
    """Return (speaker_name, block_index) for every block that starts a speech."""
    speakers = []
    for i, text in enumerate(blocks):
        if text.strip().upper() in HEADINGS_TO_IGNORE:
            continue
        # A speaker line is assumed to contain a colon.
        if ':' in text:
            potential_speaker = text.split(':', 1)[0].strip()
            if SPEAKER_PATTERN.search(potential_speaker):
                speakers.append((potential_speaker, i))
    return speakers


def _clean_speech(content_parts):
    """Join a speech's paragraphs and strip procedural notes, headers, and disclaimers."""
    # Paragraph breaks are kept with a marker so multi-line phrases can be removed first.
    full_content = " [NEWLINE] ".join(filter(None, content_parts))

    for pattern in _EXACT_PHRASE_PATTERNS:
        full_content = pattern.sub('', full_content)
    for pattern in MULTI_LINE_REGEX_PATTERNS_TO_REMOVE:
        full_content = pattern.sub('', full_content)

    cleaned_lines = []
    for line in full_content.split(" [NEWLINE] "):
        for pattern in REGEX_PATTERNS_TO_REMOVE:
            line = pattern.sub('', line)
        # TODO(phase 2): r'\\s+' matches a literal "\s", not whitespace.
        cleaned_line = re.sub(r'\\s+', ' ', line).strip()
        if cleaned_line:
            cleaned_lines.append(cleaned_line)
    return '\n'.join(cleaned_lines)


def chunk_text(text):
    """Split text into chunks of at most MAX_WORDS words and MAX_CHARS characters.

    Note that chunks are re-joined with single spaces, so line breaks are lost.
    """
    chunks = []
    remaining_content = text.strip()
    while remaining_content:
        words = remaining_content.split()
        chunk = " ".join(words[:MAX_WORDS])[:MAX_CHARS]
        remaining_content = " ".join(words[MAX_WORDS:])
        chunks.append(chunk)
    return chunks


def process_pdf_file(filepath):
    """Parse one Hansard PDF into a list of speech records (one per chunk).

    `is_continuation` marks the second and later chunks of a single long speech;
    it does not mean the speaker is the same as in the previous speech.
    """
    filepath = Path(filepath)
    filename = filepath.name
    try:
        doc = pymupdf.open(filepath)
    except Exception as e:
        print(f"Could not open file {filename}. Error: {e}")
        return []

    try:
        metadata = extract_file_metadata(filename, doc)
        blocks = _extract_blocks(doc)
    finally:
        doc.close()

    speakers = _find_speakers(blocks)
    records = []
    for i, (speaker_name, start) in enumerate(speakers):
        # The speech ends where the next speaker begins, or at the end of the document.
        end = speakers[i + 1][1] if i + 1 < len(speakers) else len(blocks)

        # The first line of the speech is the text after the colon on the speaker's line.
        content_parts = [blocks[start].split(':', 1)[1].strip()]
        for block_text in blocks[start + 1:end]:
            # Stop if a procedural heading is encountered mid-speech.
            if block_text.strip().upper() in HEADINGS_TO_IGNORE:
                break
            content_parts.append(block_text)

        final_content = _clean_speech(content_parts)
        if not final_content:
            continue

        for chunk_index, chunk in enumerate(chunk_text(final_content)):
            records.append({
                "filename": filename,
                "speaker": speaker_name,
                "content": chunk,
                # TODO(phase 2): store the source URL rather than an Excel formula.
                "source_link": f'=HYPERLINK("{filename}", "Open PDF")',
                "is_continuation": chunk_index > 0,
                # TODO(phase 2): continuation chunks should keep the date.
                "date": metadata["date"] if chunk_index == 0 else "",
            })
    return records
