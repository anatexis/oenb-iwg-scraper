from enum import Enum


class ResourceKind(str, Enum):
    """Canonical resource types for the rebuilt crawler."""

    PAGE_DOCUMENT = "page_document"
    ASSET_DOCUMENT = "asset_document"
    HTML_TABLE = "html_table"
    STANDARDIZED_TABLE_TOPIC = "standardized_table_topic"
    DATASET_METADATA = "dataset_metadata"
    ISAWEB_ENTRY = "isaweb_entry"
    ISAWEB_DATASET = "isaweb_dataset"
    ISAWEB_OBSERVATION_BATCH = "isaweb_observation_batch"
    RELEASE_EVENT = "release_event"
    SHINY_APP = "shiny_app"
    EXTERNAL_APP = "external_app"
