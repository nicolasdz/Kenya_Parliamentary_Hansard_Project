"""Estimate the English/Kiswahili mix of each speech.

Each speech is split into sentences, which are grouped into chunks of at least
MIN_WORDS_PER_CHUNK words because very short sentences confuse language
detection. Each chunk's language is detected, and chunks that can't be
identified inherit the language of the previous chunk.
"""

import json
import re
from collections import defaultdict

from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

ALLOWED_LANGUAGES = ['en', 'sw']
MIN_WORDS_PER_CHUNK = 5
# Assumed at the start of a speech, or when no language can be identified.
DEFAULT_LANGUAGE = 'en'

# Makes langdetect's results deterministic.
DetectorFactory.seed = 0


def _sentence_chunks(speech_content):
    chunks = []
    current_chunk = ""
    for sentence in re.split(r'[.?!]', speech_content):
        current_chunk += sentence + ". "
        if len(current_chunk.split()) >= MIN_WORDS_PER_CHUNK:
            chunks.append(current_chunk.strip())
            current_chunk = ""
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks


def analyze_language_distribution(speech_content):
    """Return a JSON string mapping language codes to their share of words, e.g. '{"en": 0.8, "sw": 0.2}'."""
    if not speech_content or not isinstance(speech_content, str):
        return json.dumps({})

    language_word_counts = defaultdict(int)
    total_words = 0
    last_known_language = DEFAULT_LANGUAGE

    for chunk in _sentence_chunks(speech_content):
        num_words = len(chunk.split())
        if num_words == 0:
            continue
        total_words += num_words

        try:
            candidates = [lang for lang in detect_langs(chunk) if lang.lang in ALLOWED_LANGUAGES]
            if candidates:
                last_known_language = max(candidates, key=lambda x: x.prob).lang
        except LangDetectException:
            pass  # Too ambiguous; falls back to the previous chunk's language.

        language_word_counts[last_known_language] += num_words

    if total_words == 0:
        return json.dumps({})

    language_percentage = {}
    for lang, count in language_word_counts.items():
        percentage = round(count / total_words, 2)
        if percentage > 0.0:
            language_percentage[lang] = percentage
    return json.dumps(language_percentage)


def primary_language(distribution_json):
    """Return the language with the largest share in a distribution, or None if it is empty."""
    distribution = json.loads(distribution_json)
    return max(distribution, key=distribution.get) if distribution else None
