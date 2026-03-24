"""Shared package-based stopword helpers."""

from __future__ import annotations

import stopwordsiso

SUPPORTED_LANGS = ("de", "en")
STOPWORDS = set().union(*(stopwordsiso.stopwords(lang) for lang in SUPPORTED_LANGS))


def is_stopword(token: str) -> bool:
    return token.lower() in STOPWORDS

