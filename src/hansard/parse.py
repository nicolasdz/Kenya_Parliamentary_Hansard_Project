"""Extract individual speeches from Hansard PDFs.

Based on the "Hansard Parser" notebook by Josh Been (August 2025).
"""

import hashlib
import html
import re
from pathlib import Path

import pymupdf
from unidecode import unidecode

from .documents import classify
from .language import analyze_language_distribution, primary_language

# Bump this whenever parsing logic changes, so `hansard parse` re-parses
# documents that were stored by an older version.
PARSER_VERSION = 3

# How many pages of opening text are used to classify a document.
OPENING_PAGES = 3

# --- Speaker Identification ---
# A speech starts with a line "<speaker>: <text>", where <speaker> is either an
# honorific and name ("Hon. Kimani Ichung'wah (Kikuyu, UDA)") or a role with the
# person's name in brackets ("The Temporary Deputy Chairman (Hon. Omulele)",
# "The Clerk of the National Assembly (Mr. Bundi)").
SPEAKER_PATTERN = re.compile(
    r'^(Hon\.|Sen\.|Dr\.|Prof\.|Mr\.|Mrs\.|Ms\.|The Speaker|The Deputy Speaker|The Temporary Speaker|Hon\. Chairlady|The Temporary Speaker \(Hon\.\)|Hon\. Members)',
    re.IGNORECASE,
)
ROLE_SPEAKER_PATTERN = re.compile(r'^The [A-Z][^()]{2,120}\(.+\)$')
# Longer "speaker" text is a sentence that happens to contain a colon.
MAX_SPEAKER_WORDS = 16

# --- Content Cleaning ---
# Exact phrases to be completely removed from the text (matched case-insensitively,
# with any whitespace between words). These are parenthetical notes about events
# in the chamber.
EXACT_PHRASES_TO_REMOVE = [
    "(Applause)", "(Laughter)",
    "(Loud consultations)",
    "(The Quorum Bell was rung)",
    "(The Division Bell was rung)",
    "(Voting in progress)",
    "(Serjeant-at-Arms closed the bars)",
    "(Question put and agreed to)",
    "(Question of the amendment proposed)",
    "(Question proposed)",
    "(The Speaker consulted the Clerks-at-the-Table)",
    "(The Clerk-at-the-Table consulted the Speaker)",
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

# Patterns removed from the whole speech before line-by-line cleaning, because the
# extracted text often splits them across paragraphs:
#  - running page headers: "December 29, 2020 SENATE DEBATES 31",
#    "December, 05, 2018 PARLIAMENTARY DEBATES 8", "May 8, 2019 PARLIAMENTARY DEBATES ____ 24",
#    "Thursday, 25th July 2024 NATIONAL ASSEMBLY DEBATES 3"
#  - the disclaimer printed on every page.
# Header patterns are case-sensitive (headers are upper-case) so that a member
# saying "the Senate debates" keeps their words.
_CHAMBER_DEBATES = r'(?:PARLIAMENTARY|SENATE|NATIONAL\s+ASSEMBLY)\s+DEBATES'
MULTI_LINE_REGEX_PATTERNS_TO_REMOVE = [
    re.compile(p) for p in [
        rf'\b[A-Za-z]+,?\s+\d{{1,2}},?\s+\d{{4}}\s+{_CHAMBER_DEBATES}[\s_]*\d*',
        rf'\b(?:[A-Za-z]+,?\s+)?\d{{1,2}}(?:st|nd|rd|th)?,?\s+[A-Za-z]+,?\s+\d{{4}}\s+{_CHAMBER_DEBATES}[\s_]*\d*',
        rf'{_CHAMBER_DEBATES}[\s_]*\d*',
    ]
] + [
    re.compile(p, re.IGNORECASE) for p in [
        r'(?:Disclaimer\s*:\s*)?The\s+electronic\s+version\s+of\s+the\s+(?:Official|Senate)\s+Hansard\s+Report'
        r'\s+is\s+for\s+information\s+purposes(?:\s+only\.?)?',
        # "...from the Hansard Editor[, Senate]." / "...from the Director, Hansard [and Audio] Services, Senate."
        r'(?:only\.\s*)?A\s+certified\s+version\s+of\s+this\s+Report\s+can\s+be\s+obtained\s+from\s+the\s+'
        r'(?:Hansard\s+Editor|Director)[^.]{0,80}\.?',
    ]
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


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def repair_and_clean_text(text):
    """Repair encoding errors in text extracted from the PDF and reduce it to plain ASCII."""
    if not text:
        return ""

    # Repair common encoding errors (mojibake).
    try:
        text = text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # Remove HTML tags (e.g. <b>, <span>) before any other processing.
    text = re.sub(r'<.*?>', '', text)

    # Transliterate to plain ASCII, then put each paragraph on one line.
    text = unidecode(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _extract_blocks(doc):
    """Return (page_number, text) for every paragraph in the document, in order."""
    blocks = []
    for page_number, page in enumerate(doc, start=1):
        # Extracting each page as HTML preserves paragraph structure.
        decoded_html = html.unescape(page.get_text("html"))
        for p_html in re.findall(r'<p.*?>(.*?)</p>', decoded_html, re.DOTALL):
            p_text = repair_and_clean_text(p_html)
            if p_text:
                blocks.append((page_number, p_text))
    return blocks


def _find_speakers(blocks):
    """Return (speaker_name, block_index) for every block that starts a speech."""
    speakers = []
    for i, (_, text) in enumerate(blocks):
        if text.upper() in HEADINGS_TO_IGNORE:
            continue
        # A speaker line is assumed to contain a colon.
        if ':' in text:
            potential_speaker = text.split(':', 1)[0].strip()
            if len(potential_speaker.split()) <= MAX_SPEAKER_WORDS and (
                    SPEAKER_PATTERN.search(potential_speaker) or ROLE_SPEAKER_PATTERN.match(potential_speaker)):
                speakers.append((potential_speaker, i))
    return speakers


def clean_speech(paragraphs):
    """Join a speech's paragraphs (one per line) and strip procedural notes, headers, and disclaimers."""
    # Each paragraph is already on a single line, so joining with newlines lets the
    # patterns' \s+ match phrases that are split across paragraphs.
    full_content = "\n".join(filter(None, paragraphs))

    for pattern in MULTI_LINE_REGEX_PATTERNS_TO_REMOVE:
        full_content = pattern.sub('', full_content)
    for pattern in _EXACT_PHRASE_PATTERNS:
        full_content = pattern.sub('', full_content)

    cleaned_lines = []
    for line in full_content.split("\n"):
        for pattern in REGEX_PATTERNS_TO_REMOVE:
            line = pattern.sub('', line)
        cleaned_line = re.sub(r'\s+', ' ', line).strip()
        if cleaned_line:
            cleaned_lines.append(cleaned_line)
    return '\n'.join(cleaned_lines)


def extract_speeches(blocks):
    """Split a document's paragraphs into speeches: dicts of seq, page, speaker_raw, text."""
    speakers = _find_speakers(blocks)
    speeches = []
    for i, (speaker_name, start) in enumerate(speakers):
        # The speech ends where the next speaker begins, or at the end of the document.
        end = speakers[i + 1][1] if i + 1 < len(speakers) else len(blocks)

        # The first line of the speech is the text after the colon on the speaker's line.
        paragraphs = [blocks[start][1].split(':', 1)[1].strip()]
        for _, block_text in blocks[start + 1:end]:
            # Stop if a procedural heading is encountered mid-speech.
            if block_text.upper() in HEADINGS_TO_IGNORE:
                break
            paragraphs.append(block_text)

        text = clean_speech(paragraphs)
        if text:
            speeches.append({
                "seq": len(speeches) + 1,
                "page": blocks[start][0],
                "speaker_raw": speaker_name,
                "text": text,
            })
    return speeches


def _opening_text(doc):
    return "\n".join(doc[i].get_text() for i in range(min(OPENING_PAGES, len(doc))))


def reclassify_document(path, folder_chamber, text_chars):
    """Re-run documents.classify on a stored PDF without re-extracting its speeches."""
    path = Path(path)
    with pymupdf.open(path) as doc:
        return classify(path.name, _opening_text(doc), len(doc), text_chars, folder_chamber)


def parse_document(path, folder_chamber):
    """Parse one PDF into (document, speeches).

    `document` describes the file (see documents.classify); `speeches` is empty
    unless the file is a Hansard. Each speech also gets its language mix.
    Returns (None, []) if the file can't be opened.
    """
    path = Path(path)
    try:
        doc = pymupdf.open(path)
    except Exception as e:
        print(f"Could not open file {path.name}. Error: {e}")
        return None, []

    try:
        opening_text = _opening_text(doc)
        blocks = _extract_blocks(doc)
        page_count = len(doc)
    finally:
        doc.close()

    text_chars = sum(len(text) for _, text in blocks)
    document = classify(path.name, opening_text, page_count, text_chars, folder_chamber)
    document.update(filename=path.name, folder_chamber=folder_chamber, sha256=file_sha256(path))

    speeches = extract_speeches(blocks) if document["doc_type"] == "hansard" else []
    for speech in speeches:
        speech["language_distribution"] = analyze_language_distribution(speech["text"])
        speech["primary_language"] = primary_language(speech["language_distribution"])
        speech["word_count"] = len(speech["text"].split())
    return document, speeches
