"""Match speaker names found in the Hansard against the official list of members."""

import csv
import re

from thefuzz import process

# Only records dated this year or later are matched; member data starts in 2017.
MATCH_SINCE_YEAR = 2017

# The confidence threshold for a fuzzy match (0-100). 80 is a safe choice.
MATCH_SCORE_CUTOFF = 80

# Titles and procedural text removed from the speaker's name before matching.
JUNK_WORDS_TO_REMOVE = [
    'The Speaker of the Senate', 'The Speaker', 'The Deputy Speaker',
    'The Temporary Speaker', 'Hon', 'Sen', 'Dr', 'Prof',
]
_JUNK_PATTERNS = [
    re.compile(r'\b' + re.escape(junk) + r'\b\.?', re.IGNORECASE)
    for junk in JUNK_WORDS_TO_REMOVE
]


def load_official_names(path):
    """Read the "Full Name" column from the members TSV (exported from the Google Sheet)."""
    with open(path, newline='', encoding='utf-8') as f:
        return [row['Full Name'] for row in csv.DictReader(f, delimiter='\t') if row.get('Full Name')]


def clean_speaker_name(speaker_name):
    """Reduce a raw speaker line such as "The Temporary Speaker (Sen. Kathuri)" to "Kathuri"."""
    # Prefer text inside parentheses, which usually holds the person's name.
    text_in_parentheses = re.search(r'\((.*)\)', speaker_name)
    cleaned_name = text_in_parentheses.group(1) if text_in_parentheses else speaker_name

    for pattern in _JUNK_PATTERNS:
        cleaned_name = pattern.sub('', cleaned_name)

    # Remove remaining punctuation and surrounding whitespace.
    return re.sub(r'[^\w\s]', '', cleaned_name).strip()


def infer_speaker_metadata(record, official_names):
    """Add 'matched_name' and 'match_score' to a record by fuzzy-matching its speaker.

    Records without a date (including continuation chunks) or dated before
    MATCH_SINCE_YEAR are left unmatched.
    """
    record['matched_name'] = ''
    record['match_score'] = ''

    date = record.get('date')
    if not (date and date[:4].isdigit() and int(date[:4]) >= MATCH_SINCE_YEAR):
        return record

    speaker_name = record.get('speaker', '').strip()
    # Skip records for "Hon. Members" or with no speaker.
    if not speaker_name or 'members' in speaker_name.lower():
        return record

    final_clean_name = clean_speaker_name(speaker_name)
    if not final_clean_name:
        return record

    match = process.extractOne(final_clean_name, official_names, score_cutoff=MATCH_SCORE_CUTOFF)
    if match:
        record['matched_name'], record['match_score'] = match[0], match[1]
    return record
