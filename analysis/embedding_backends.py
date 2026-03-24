"""Embedding/semantic search backend interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SemanticSearchBackend(ABC):
    @abstractmethod
    def rerank(self, query: str, hits: list[dict], *, limit: int) -> list[dict]:
        raise NotImplementedError


class NoopSemanticSearchBackend(SemanticSearchBackend):
    def rerank(self, query: str, hits: list[dict], *, limit: int) -> list[dict]:
        return hits[:limit]
