import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.freshness import should_reextract_content


def test_same_body_hash_skips_reextraction():
    assert should_reextract_content(previous_hash="abc", current_hash="abc") is False


def test_changed_body_hash_triggers_reextraction():
    assert should_reextract_content(previous_hash="abc", current_hash="xyz") is True


def test_http_304_skips_reextraction():
    assert should_reextract_content(previous_hash="abc", current_hash="abc", http_status=304) is False
