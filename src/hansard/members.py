"""Load the official member list and match Hansard speaker names against it."""

import csv
import re

from thefuzz import fuzz, process

# The confidence threshold for a fuzzy match (0-100). 80 is a safe choice.
MATCH_SCORE_CUTOFF = 80
# The lower threshold used when the speaker's constituency also matches.
CONSTITUENCY_MATCH_SCORE_CUTOFF = 60

# Titles, roles, and honorifics removed from the speaker's name before matching.
JUNK_WORDS_TO_REMOVE = [
    'The Speaker of the Senate', 'The Speaker', 'The Deputy Speaker',
    'The Temporary Speaker', 'Speaker', 'Deputy', 'Chairman', 'Chairperson', 'Chairlady',
    'Hon', 'Sen', 'Dr', 'Prof',
    'Mr', 'Mrs', 'Ms', 'Eng', 'Amb', 'Rev', 'Rtd', 'Gen', 'Capt', 'Maj', 'Col', 'Lt',
    # Honours and post-nominals, e.g. "Sen. Mungatana, MGH", "Hon. Paul Muite, SC".
    'SC', 'EGH', 'MGH', 'CBS', 'EBS', 'MBS', 'OGW', 'HSC',
]
_JUNK_PATTERNS = [
    re.compile(r'\b' + re.escape(junk) + r'\b\.?', re.IGNORECASE)
    for junk in JUNK_WORDS_TO_REMOVE
]

_CHAMBER_KEYS = {"National Assembly": "national_assembly", "Senate": "senate"}

# Columns of the members TSV (exported from the Google Sheet) -> members table columns.
MEMBER_COLUMNS = {
    "Full Name": "full_name",
    "First Name(s)": "first_names",
    "Last Name": "last_name",
    "County": "county",
    "Constituency": "constituency",
    "Party Affiliation": "party",
    "Date Took Office": "date_took_office",
    "Date Left Office": "date_left_office",
    "Leadership Role": "leadership_role",
    "County Woman Representative": "county_woman_representative",
    "Nominated Members": "nominated",
    "Note": "note",
}


def load_members(path):
    """Read the members TSV into a list of dicts, one per member per Parliament.

    Each member gets an `id` (their row number), `parliament` (e.g. 13 for
    "13th Parliament") and `chamber` ("national_assembly" or "senate").
    """
    members = []
    with open(path, newline='', encoding='utf-8') as f:
        for row_number, row in enumerate(csv.DictReader(f, delimiter='\t'), start=1):
            if not row.get('Full Name'):
                continue
            session = re.match(r'(\d+)', row.get('Session') or '')
            member = {column: (row.get(source) or '').strip() or None for source, column in MEMBER_COLUMNS.items()}
            member.update(
                id=row_number,
                parliament=int(session.group(1)) if session else None,
                chamber=_CHAMBER_KEYS.get(row.get('Chamber')),
            )
            members.append(member)
    return members


def clean_speaker_name(speaker_name):
    """Reduce a raw speaker line such as "The Temporary Speaker (Sen. Kathuri)" to "Kathuri"."""

    def strip_junk(text):
        for pattern in _JUNK_PATTERNS:
            text = pattern.sub('', text)
        # Turn remaining punctuation into spaces, as thefuzz does to the official names
        # ("Ichung'wah" -> "Ichung wah"), and collapse whitespace.
        return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', text)).strip()

    # Parentheses mean different things: after a role they hold the person's name
    # ("The Temporary Speaker (Sen. Kathuri)"); after a name they hold a title or
    # the member's constituency and party ("Hon. (Dr.) Pukose",
    # "Hon. Kimani Ichung'wah (Kikuyu, UDA)"). Drop a trailing "(constituency, party)" first.
    speaker_name = re.sub(r'\s*\([^()]*,[^()]*\)\s*$', '', speaker_name)
    text_in_parentheses = re.search(r'\((.*)\)', speaker_name)
    if not text_in_parentheses:
        return strip_junk(speaker_name)
    inside = strip_junk(text_in_parentheses.group(1))
    outside = strip_junk(speaker_name[:text_in_parentheses.start()] + ' ' + speaker_name[text_in_parentheses.end():])
    if speaker_name.lower().startswith('the '):
        return inside or outside
    return outside or inside


def _normalize_place(place):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', place)).strip().lower()


def constituency_from_speaker(speaker_raw):
    """Return the lower-cased constituency from "Hon. X (Suba North, ODM)", or None.

    Nominated members ("(Nominated, UDA)") have no constituency.
    """
    match = re.search(r'\(([^(),]+),[^()]*\)\s*$', speaker_raw)
    if not match:
        return None
    place = _normalize_place(match.group(1))
    return None if place.startswith('nominated') else place


def _all_words_present(name, official_name):
    """True if each word (3+ letters) of `name` is close to a word of `official_name`.

    A word also counts if it appears inside the official name with spaces removed,
    so "Ng eno" matches "Ngeno".
    """
    official_words = _normalize_place(official_name).split()
    joined = "".join(official_words)
    for word in _normalize_place(name).split():
        if len(word) < 3 or word in joined:
            continue
        if not any(fuzz.ratio(word, w) >= MATCH_SCORE_CUTOFF for w in official_words):
            return False
    return True


class SpeakerMatcher:
    """Fuzzy-match cleaned speaker names to members of the right chamber and Parliament."""

    def __init__(self, members):
        self.members = members
        self._cache = {}
        # Lower-cased constituency and county ("nairobi", "nairobi county") of each member.
        self._places = {m["id"]: {_normalize_place(p) for p in (m.get("constituency"), m.get("county")) if p}
                        for m in members}
        for places in self._places.values():
            places.update({f"{p} county" for p in list(places)})

    def candidates(self, chamber, parliament):
        """Members who could be speaking: joint sittings include both chambers."""
        chambers = {"national_assembly", "senate"} if chamber == "joint" else {chamber}
        return {m["id"]: m["full_name"] for m in self.members
                if m["chamber"] in chambers and m["parliament"] == parliament}

    def match(self, speaker_raw, chamber, parliament):
        """Return (member_id, score), or (None, None) if there is no confident match.

        Speakers are only matched when the member list covers that chamber and
        Parliament; otherwise a member of another chamber or term could be picked.
        """
        key = (speaker_raw, chamber, parliament)
        if key not in self._cache:
            self._cache[key] = self._match(speaker_raw, chamber, parliament)
        return self._cache[key]

    def _match(self, speaker_raw, chamber, parliament):
        name = clean_speaker_name(speaker_raw)
        if not name or 'members' in name.lower():
            return None, None
        candidates = self.candidates(chamber, parliament)

        # Since 2022 speaker lines name the constituency ("Hon. X (Suba North, ODM)").
        # If exactly one candidate represents it and the names broadly agree, accept a
        # lower name score (e.g. a married name). The constituency alone isn't enough:
        # Hansard typos and gaps in the member list would give wrong matches.
        place = constituency_from_speaker(speaker_raw)
        if place:
            by_place = {i: n for i, n in candidates.items() if place in self._places[i]}
            if len(by_place) == 1:
                member_id, = by_place
                score = fuzz.WRatio(name, by_place[member_id])
                if score >= CONSTITUENCY_MATCH_SCORE_CUTOFF:
                    return member_id, score

        # WRatio scores ~86 when just one word matches ("Robert Pukose" vs "Mbui, Robert"),
        # so also require every word of the printed name to appear in the official one.
        matches = process.extract(name, candidates, limit=5) if candidates else []
        for _, score, member_id in matches:  # With a dict of choices: (choice, score, key).
            if score >= MATCH_SCORE_CUTOFF and _all_words_present(name, candidates[member_id]):
                return member_id, score
        return None, None
