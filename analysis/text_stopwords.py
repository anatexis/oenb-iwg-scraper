"""Shared package-based stopword helpers."""

from __future__ import annotations

import stopwordsiso

SUPPORTED_LANGS = ("de", "en")
STOPWORDS = set().union(*(stopwordsiso.stopwords(lang) for lang in SUPPORTED_LANGS))

# Queries often arrive ASCII-transliterated ("fuer", "ueber"); treat the
# folded spellings of stopwords as stopwords too.
_FOLD_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
STOPWORDS |= {word.translate(_FOLD_MAP) for word in STOPWORDS}


def is_stopword(token: str) -> bool:
    return token.lower() in STOPWORDS

