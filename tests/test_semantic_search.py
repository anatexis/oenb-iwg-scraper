import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.embedding_backends import NoopSemanticSearchBackend, SemanticSearchBackend
from analysis.semantic_search import apply_semantic_search


class ReverseBackend(SemanticSearchBackend):
    def rerank(self, query: str, hits: list[dict], *, limit: int) -> list[dict]:
        return list(reversed(hits[:limit]))


def test_apply_semantic_search_returns_original_hits_when_disabled():
    hits = [{"id": "a"}, {"id": "b"}]

    result = apply_semantic_search(
        query="aktueller Leitzins",
        hits=hits,
        backend=NoopSemanticSearchBackend(),
        enabled=False,
        limit=5,
    )

    assert result == hits


def test_apply_semantic_search_can_use_backend_when_enabled():
    hits = [{"id": "a"}, {"id": "b"}]

    result = apply_semantic_search(
        query="aktueller Leitzins",
        hits=hits,
        backend=ReverseBackend(),
        enabled=True,
        limit=5,
    )

    assert [hit["id"] for hit in result] == ["b", "a"]


def test_noop_backend_keeps_interface_stable():
    backend = NoopSemanticSearchBackend()

    assert isinstance(backend, SemanticSearchBackend)
