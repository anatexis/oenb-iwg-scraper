import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.agentic_search import maybe_run_agentic_search
from analysis.isaweb_live_lookup import is_allowed_live_lookup_url


def test_maybe_run_agentic_search_skips_live_lookup_when_confidence_is_high():
    calls = []

    result = maybe_run_agentic_search(
        query="Wie hoch ist der Zinssatz für die Einlagenfazilität?",
        retrieval_payload={
            "confidence": 0.91,
            "routing": {"freshness_need": "high"},
            "hits": [],
        },
        live_lookup=lambda query, hits, routing: calls.append((query, hits, routing)) or {"status": "live"},
        enabled=True,
    )

    assert result is None
    assert calls == []


def test_maybe_run_agentic_search_calls_live_lookup_for_high_freshness_low_confidence():
    calls = []

    result = maybe_run_agentic_search(
        query="Wie hoch ist der Zinssatz für die Einlagenfazilität?",
        retrieval_payload={
            "confidence": 0.21,
            "routing": {"freshness_need": "high"},
            "hits": [{"id": "stats:family:10.4"}],
        },
        live_lookup=lambda query, hits, routing: calls.append((query, hits, routing)) or {"status": "live", "source": "isaweb"},
        enabled=True,
    )

    assert result == {"status": "live", "source": "isaweb"}
    assert len(calls) == 1


def test_is_allowed_live_lookup_url_is_bounded_to_oenb_isaweb_endpoints():
    assert is_allowed_live_lookup_url("https://www.oenb.at/isadataservice/data?hierid=10&lang=DE")
    assert is_allowed_live_lookup_url("https://www.oenb.at/isawebstat/stabfrage/createReport?lang=DE&report=10.4")
    assert not is_allowed_live_lookup_url("https://example.com/isadataservice/data?hierid=10")
    assert not is_allowed_live_lookup_url("https://www.oenb.at/en/Statistics/Standardized-Tables.html")
