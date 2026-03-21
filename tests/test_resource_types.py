import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.resource_types import ResourceKind


def test_resource_kinds_cover_site_and_statistics_scope():
    assert ResourceKind.PAGE_DOCUMENT.value == "page_document"
    assert ResourceKind.ASSET_DOCUMENT.value == "asset_document"
    assert ResourceKind.HTML_TABLE.value == "html_table"
    assert ResourceKind.STANDARDIZED_TABLE_TOPIC.value == "standardized_table_topic"
    assert ResourceKind.DATASET_METADATA.value == "dataset_metadata"
    assert ResourceKind.ISAWEB_ENTRY.value == "isaweb_entry"
    assert ResourceKind.ISAWEB_DATASET.value == "isaweb_dataset"
    assert ResourceKind.ISAWEB_OBSERVATION_BATCH.value == "isaweb_observation_batch"
    assert ResourceKind.RELEASE_EVENT.value == "release_event"
    assert ResourceKind.SHINY_APP.value == "shiny_app"
    assert ResourceKind.EXTERNAL_APP.value == "external_app"
