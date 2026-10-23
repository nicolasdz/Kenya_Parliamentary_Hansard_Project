import json

import pytest

from hansard.language import analyze_language_distribution
from hansard.members import clean_speaker_name, infer_speaker_metadata


@pytest.mark.parametrize("raw, expected", [
    ("The Temporary Speaker (Sen. Kathuri)", "Kathuri"),
    pytest.param("Hon. (Dr.) Pukose", "Pukose", marks=pytest.mark.xfail(
        reason="TODO(phase 2): parenthesised titles are taken as the name, leaving nothing")),
    ("Sen. Cheruiyot", "Cheruiyot"),
])
def test_clean_speaker_name(raw, expected):
    assert clean_speaker_name(raw) == expected


def test_infer_speaker_metadata_matches_after_2017():
    names = ["Kingi, Amason Jeffah", "Cheruiyot, Aaron Kipkirui"]
    record = infer_speaker_metadata({"speaker": "Sen. Cheruiyot", "date": "2024-07-25"}, names)
    assert record["matched_name"] == "Cheruiyot, Aaron Kipkirui"
    assert record["match_score"] >= 80


@pytest.mark.parametrize("record", [
    {"speaker": "Sen. Cheruiyot", "date": "2015-03-01"},  # Before member data starts.
    {"speaker": "Sen. Cheruiyot", "date": ""},           # Continuation chunk.
    {"speaker": "Hon. Members", "date": "2024-07-25"},
])
def test_infer_speaker_metadata_skips(record):
    record = infer_speaker_metadata(record, ["Cheruiyot, Aaron Kipkirui"])
    assert record["matched_name"] == "" and record["match_score"] == ""


def test_language_distribution():
    english = "I rise to support this important Bill because it helps our people. "
    swahili = "Kwa hivyo, ninaunga mkono Mswada huu kwa sababu ni muhimu sana kwa wananchi. "
    result = json.loads(analyze_language_distribution(english + swahili))
    assert set(result) == {"en", "sw"}
    assert analyze_language_distribution("") == "{}"
