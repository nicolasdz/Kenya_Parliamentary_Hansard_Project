import json

import pytest

from hansard.language import analyze_language_distribution, primary_language
from hansard.members import SpeakerMatcher, clean_speaker_name

MEMBERS = [
    {"id": 1, "parliament": 13, "chamber": "senate", "full_name": "Cheruiyot, Aaron Kipkirui"},
    {"id": 2, "parliament": 13, "chamber": "national_assembly", "full_name": "Ichung'wah, Anthony Kimani"},
    {"id": 3, "parliament": 12, "chamber": "national_assembly", "full_name": "Cheruiyot, Someone Else"},
]


@pytest.mark.parametrize("raw, expected", [
    ("The Temporary Speaker (Sen. Kathuri)", "Kathuri"),
    ("The Temporary Speaker (Hon. (Ms.) Shollei)", "Shollei"),
    ("Hon. (Dr.) Pukose", "Pukose"),
    ("Hon. Kimani Ichung'wah (Kikuyu, UDA)", "Kimani Ichung wah"),
    ("Hon. (Ms.) Odhiambo-Mabona (Suba North, ODM)", "Odhiambo Mabona"),
    ("Hon. (Dr) James Nyikal (Seme, ODM)", "James Nyikal"),
    ("Sen. Cheruiyot", "Cheruiyot"),
    ("Hon. Speaker", ""),
    ("Hon. Deputy Speaker", ""),
    ("Hon. Chairman", ""),
])
def test_clean_speaker_name(raw, expected):
    assert clean_speaker_name(raw) == expected


def test_matches_within_chamber_and_parliament():
    matcher = SpeakerMatcher(MEMBERS)
    member_id, score = matcher.match("Sen. Cheruiyot", "senate", 13)
    assert member_id == 1 and score >= 80
    assert matcher.match("Hon. Kimani Ichung'wah (Kikuyu, UDA)", "national_assembly", 13)[0] == 2


def test_constituency_identifies_member_despite_name_difference():
    members = MEMBERS + [
        {"id": 4, "parliament": 13, "chamber": "national_assembly",
         "full_name": "Odhiambo, Millie Grace Akoth", "constituency": "Suba North", "county": "Homa Bay"},
        {"id": 5, "parliament": 13, "chamber": "national_assembly",
         "full_name": "Odhiambo, Elisha Ochieng", "constituency": "Gem", "county": "Siaya"},
    ]
    matcher = SpeakerMatcher(members)
    member_id, _ = matcher.match("Hon. Millie Odhiambo-Mabona (Suba North, ODM)", "national_assembly", 13)
    assert member_id == 4
    # A constituency typo must not attach the speech to that constituency's member.
    assert matcher.match("Hon. Paul Koinange (Gem, JP)", "national_assembly", 13) == (None, None)


@pytest.mark.parametrize("speaker", [
    "Hon. (Dr.) Robert Pukose",  # Only "Robert" is shared with "Mbui, Robert".
    "Hon. Robert's letter raised the following issues",  # Not a speaker line.
])
def test_one_shared_word_is_not_a_match(speaker):
    members = [{"id": 9, "parliament": 13, "chamber": "national_assembly", "full_name": "Mbui, Robert"}]
    assert SpeakerMatcher(members).match(speaker, "national_assembly", 13) == (None, None)


def test_joint_sittings_match_both_chambers():
    assert SpeakerMatcher(MEMBERS).match("Hon. Ichung'wah", "joint", 13)[0] == 2


@pytest.mark.parametrize("speaker, chamber, parliament", [
    ("Sen. Cheruiyot", "senate", 12),  # No Senate data for the 12th Parliament.
    ("Sen. Cheruiyot", "senate", None),
    ("Hon. Members", "senate", 13),
    ("Hon. Speaker", "senate", 13),
])
def test_no_match_without_member_data(speaker, chamber, parliament):
    assert SpeakerMatcher(MEMBERS).match(speaker, chamber, parliament) == (None, None)


def test_language_distribution():
    english = "I rise to support this important Bill because it helps our people. "
    swahili = "Kwa hivyo, ninaunga mkono Mswada huu kwa sababu ni muhimu sana kwa wananchi. "
    result = analyze_language_distribution(english + swahili)
    assert set(json.loads(result)) == {"en", "sw"}
    assert primary_language(result) in {"en", "sw"}
    assert analyze_language_distribution("") == "{}"
    assert primary_language("{}") is None
