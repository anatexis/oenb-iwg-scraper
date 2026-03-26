"""Export unified crawler knowledge-base records to JSONL."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import re
from urllib.parse import urlparse

try:
    from oenb_scraper.source_extraction import extract_source_metadata
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
    from oenb_scraper.source_extraction import extract_source_metadata


def export_knowledge_base_jsonl(db_path: Path, output_path: Path) -> int:
    """Export pages, assets and ISAweb datasets as JSONL records.

    Streams large record types (isaweb_dataset) to disk to avoid OOM on
    databases with millions of observations.
    """

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    count = 0

    with output_path.open("w", encoding="utf-8") as handle:
        def _write(record: dict) -> None:
            nonlocal count
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

        page_records = _page_records(conn)
        asset_records = _asset_records(conn)
        for r in page_records:
            _write(r)
        for r in asset_records:
            _write(r)

        # Stream isaweb records to disk; keep slim copies (no observations)
        # for chatbot chunk generation.
        isaweb_slim: list[dict] = []
        for record in _iter_isaweb_records(conn):
            _write(record)
            isaweb_slim.append(record)

        metadata_records = _isaweb_metadata_records(conn)
        release_records = _release_event_records(conn)
        for r in metadata_records:
            _write(r)
        for r in release_records:
            _write(r)

        # Stream family records to disk; keep slim copies for chatbot chunks.
        family_slim: list[dict] = []
        for record in _iter_dataset_family_records(conn):
            _write(record)
            family_slim.append(_slim_family_for_chunks(record))

        for r in _chatbot_chunk_records(family_slim, isaweb_slim, asset_records):
            _write(r)
        for r in _page_chatbot_chunk_records(page_records):
            _write(r)

    conn.close()
    return count


def _page_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            p.url,
            p.final_url,
            p.status_code,
            p.content_type,
            p.fetched_at,
            pc.title,
            pc.text_content,
            pc.page_section,
            pc.language,
            pc.extracted_at,
            pc.extractor_version
        FROM page_content pc
        JOIN pages p ON p.id = pc.page_id
        ORDER BY p.url
        """
    ).fetchall()

    return [
        {
            "record_type": "page_document",
            "id": f"page:{row['url']}",
            "url": row["url"],
            "final_url": row["final_url"],
            "status_code": row["status_code"],
            "content_type": row["content_type"],
            "fetched_at": row["fetched_at"],
            "title": row["title"],
            "text": row["text_content"],
            "page_section": row["page_section"],
            "language": row["language"],
            "extracted_at": row["extracted_at"],
            "extractor_version": row["extractor_version"],
        }
        for row in rows
    ]


def _asset_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            p.url,
            p.final_url,
            p.status_code,
            p.content_type,
            p.fetched_at,
            ad.asset_type,
            ad.extraction_status,
            ad.text_content,
            ad.metadata_json,
            ad.extracted_at,
            ad.extractor_version
        FROM asset_documents ad
        JOIN pages p ON p.id = ad.page_id
        ORDER BY p.url
        """
    ).fetchall()

    records = []
    for row in rows:
        linked_from = conn.execute(
            """
            SELECT source_url, link_text, section_heading, resource_kind
            FROM resource_links
            WHERE normalized_target_url = ?
            ORDER BY discovered_at ASC, id ASC
            """,
            (row["url"],),
        ).fetchall()
        records.append(
            {
                "record_type": "asset_document",
                "id": f"asset:{row['url']}",
                "url": row["url"],
                "final_url": row["final_url"],
                "status_code": row["status_code"],
                "content_type": row["content_type"],
                "fetched_at": row["fetched_at"],
                "asset_type": row["asset_type"],
                "extraction_status": row["extraction_status"],
                "text": row["text_content"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "extracted_at": row["extracted_at"],
                "extractor_version": row["extractor_version"],
                "linked_from": [
                    {
                        "source_url": link["source_url"],
                        "link_text": link["link_text"],
                        "section_heading": link["section_heading"],
                        "resource_kind": link["resource_kind"],
                    }
                    for link in linked_from
                ],
            }
        )
    return records


def _iter_isaweb_records(conn: sqlite3.Connection):
    """Yield isaweb_dataset records one at a time to avoid OOM."""
    rows = conn.execute(
        """
        SELECT id, dataset_key, hierid, lang, freq, title, source_url
        FROM isaweb_datasets
        ORDER BY dataset_key
        """
    ).fetchall()

    for row in rows:
        dimensions = conn.execute(
            """
            SELECT dimension_key, dimension_value
            FROM isaweb_dimensions
            WHERE dataset_id = ?
            ORDER BY dimension_key, dimension_value
            """,
            (row["id"],),
        ).fetchall()
        observations = conn.execute(
            """
            SELECT period, value, unit, series_label
            FROM isaweb_observations
            WHERE dataset_id = ?
            ORDER BY period
            """,
            (row["id"],),
        ).fetchall()
        page_contexts = conn.execute(
            """
            SELECT source_url, target_url, link_text, section_heading, section_id, section_label, family_id, family_label
            FROM isaweb_page_contexts
            WHERE hierid = ? AND lang = ?
            ORDER BY source_url, id
            """,
            (row["hierid"], row["lang"]),
        ).fetchall()
        yield {
                "record_type": "isaweb_dataset",
                "id": row["dataset_key"],
                "dataset_key": row["dataset_key"],
                "hierid": row["hierid"],
                "lang": row["lang"],
                "freq": row["freq"],
                "title": row["title"],
                "source_url": row["source_url"],
                "dimensions": _group_dimensions(dimensions),
                "observation_count": len(observations),
                "latest_observation": _latest_observation(observations),
                "latest_observations": _latest_observations_by_series(observations),
                "page_contexts": [
                    {
                        "source_url": context["source_url"],
                        "target_url": context["target_url"],
                        "link_text": context["link_text"],
                        "section_heading": context["section_heading"],
                        "section_id": context["section_id"],
                        "section_label": context["section_label"],
                        "family_id": context["family_id"],
                        "family_label": context["family_label"],
                    }
                    for context in page_contexts
                ],
            }


def _isaweb_metadata_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            id,
            meta_key,
            hierid,
            lang,
            pos,
            meta_url,
            title,
            region,
            unit,
            comment,
            classification,
            breaks,
            frequency,
            data_available_json,
            last_update,
            source,
            lag,
            prepared_at,
            sender_id,
            sender_name
        FROM isaweb_metadata
        ORDER BY meta_key
        """
    ).fetchall()

    return [
        {
            "record_type": "isaweb_metadata",
            "id": row["meta_key"],
            "meta_key": row["meta_key"],
            "hierid": row["hierid"],
            "lang": row["lang"],
            "pos": row["pos"],
            "meta_url": row["meta_url"],
            "title": row["title"],
            "region": row["region"],
            "unit": row["unit"],
            "comment": row["comment"],
            "classification": row["classification"],
            "breaks": row["breaks"],
            "frequency": row["frequency"],
            "data_available": json.loads(row["data_available_json"] or "[]"),
            "last_update": row["last_update"],
            "source": row["source"],
            "lag": row["lag"],
            "prepared_at": row["prepared_at"],
            "sender": {"id": row["sender_id"], "name": row["sender_name"]},
        }
        for row in rows
    ]


def _release_event_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            re.metadata_id,
            re.hierid,
            re.lang,
            re.pos,
            re.release_date_text,
            re.reference_text,
            re.revision_text,
            re.source_url,
            im.meta_key,
            im.title
        FROM release_events re
        JOIN isaweb_metadata im ON im.id = re.metadata_id
        ORDER BY re.release_date_text, re.id
        """
    ).fetchall()

    return [
        {
            "record_type": "release_event",
            "id": f"release:{row['metadata_id']}:{row['release_date_text']}",
            "metadata_id": row["metadata_id"],
            "meta_key": row["meta_key"],
            "title": row["title"],
            "hierid": row["hierid"],
            "lang": row["lang"],
            "pos": row["pos"],
            "release_date_text": row["release_date_text"],
            "reference_text": row["reference_text"],
            "revision_text": row["revision_text"],
            "source_url": row["source_url"],
        }
        for row in rows
    ]


def _iter_dataset_family_records(conn: sqlite3.Connection):
    """Yield dataset_family records one at a time to avoid OOM."""
    dataset_rows = conn.execute(
        """
        SELECT id, dataset_key, hierid, lang, freq, title, source_url
        FROM isaweb_datasets
        ORDER BY dataset_key
        """
    ).fetchall()

    for dataset_row in dataset_rows:
        dimensions = conn.execute(
            """
            SELECT dimension_key, dimension_value
            FROM isaweb_dimensions
            WHERE dataset_id = ?
            ORDER BY dimension_key, dimension_value
            """,
            (dataset_row["id"],),
        ).fetchall()
        observations = conn.execute(
            """
            SELECT period, value, unit, series_label
            FROM isaweb_observations
            WHERE dataset_id = ?
            ORDER BY period
            """,
            (dataset_row["id"],),
        ).fetchall()
        page_contexts = conn.execute(
            """
            SELECT source_url, target_url, link_text, section_heading, section_id, section_label, family_id, family_label
            FROM isaweb_page_contexts
            WHERE hierid = ? AND lang = ?
            ORDER BY source_url, id
            """,
            (dataset_row["hierid"], dataset_row["lang"]),
        ).fetchall()
        pos_values = [
            row["dimension_value"]
            for row in dimensions
            if row["dimension_key"] == "pos"
        ]
        metadata_rows = _metadata_rows_for_dataset(
            conn,
            hierid=dataset_row["hierid"],
            lang=dataset_row["lang"],
            pos_values=pos_values,
        )
        release_rows = _release_rows_for_metadata(conn, [row["id"] for row in metadata_rows])
        source_urls = sorted({row["source_url"] for row in page_contexts if row["source_url"]})
        source_pages = _source_page_rows(conn, source_urls)
        asset_rows = _asset_rows_for_source_pages(conn, source_urls)
        filtered_assets = _filter_asset_rows(
            asset_rows,
            {
                row["section_heading"].strip()
                for row in page_contexts
                if row["section_heading"] and row["section_heading"].strip()
            },
        )
        supporting_pages = _supporting_page_rows(
            conn,
            source_urls,
            asset_urls=[row["url"] for row in filtered_assets],
        )[:10]

        primary_metadata = metadata_rows[0] if metadata_rows else None
        title = (
            (primary_metadata["title"] if primary_metadata else None)
            or dataset_row["title"]
            or next((row["link_text"] for row in page_contexts if row["link_text"]), None)
            or next((row["family_label"] for row in page_contexts if row["family_label"]), None)
            or next((row["section_heading"] for row in page_contexts if row["section_heading"]), None)
        )
        if not release_rows and title:
            related_metadata_rows = _metadata_rows_for_title(
                conn,
                hierid=dataset_row["hierid"],
                lang=dataset_row["lang"],
                title=title,
                exclude_ids=[row["id"] for row in metadata_rows],
            )
            if related_metadata_rows:
                release_rows = _release_rows_for_metadata(conn, [row["id"] for row in related_metadata_rows])
                if primary_metadata is None:
                    primary_metadata = related_metadata_rows[0]
        if not release_rows and pos_values and all(value.startswith("REPORT:") for value in pos_values):
            release_rows = _fallback_release_rows_for_report_hierarchy(
                conn,
                hierid=dataset_row["hierid"],
                lang=dataset_row["lang"],
                exclude_metadata_ids=[row["id"] for row in metadata_rows],
            )
        primary_page = _select_primary_family_page(
            title=title,
            source_pages=source_pages,
            supporting_pages=supporting_pages,
            page_contexts=page_contexts,
        )
        if title is None and primary_page is not None:
            title = primary_page["title"]
        family_key = primary_metadata["meta_key"] if primary_metadata else dataset_row["dataset_key"]
        family_sources = _collect_family_sources(
            primary_page=primary_page,
            source_pages=source_pages,
            supporting_pages=supporting_pages,
            asset_rows=filtered_assets,
            primary_metadata=primary_metadata,
            observations=observations,
        )
        latest_observation = _latest_observation(observations)
        latest_observations = _latest_observations_by_series(observations)

        yield {
                "record_type": "dataset_family",
                "id": f"dataset_family:{family_key}",
                "family_key": family_key,
                "title": title,
                "hierid": dataset_row["hierid"],
                "lang": dataset_row["lang"],
                "latest_observation": latest_observation,
                "latest_observations": latest_observations,
                "source_page": _serialize_page_row(primary_page) if primary_page else None,
                "source_pages": [_serialize_page_row(row) for row in source_pages],
                "supporting_pages": [_serialize_page_row(row) for row in supporting_pages],
                "section_labels": [
                    {
                        "section_id": row["section_id"],
                        "section_label": row["section_label"],
                        "family_id": row["family_id"],
                        "family_label": row["family_label"],
                        "section_heading": row["section_heading"],
                    }
                    for row in page_contexts
                ],
                "asset_documents": [_serialize_asset_row(row) for row in filtered_assets],
                "isaweb_dataset": {
                    "dataset_key": dataset_row["dataset_key"],
                    "source_url": dataset_row["source_url"],
                    "freq": dataset_row["freq"],
                    "title": dataset_row["title"],
                    "dimensions": _group_dimensions(dimensions),
                    "latest_observation": latest_observation,
                    "latest_observations": latest_observations,
                    "observation_count": len(observations),
                },
                "isaweb_metadata": _serialize_metadata_row(primary_metadata) if primary_metadata else None,
                "release_events": [_serialize_release_row(row) for row in release_rows],
                "sources": family_sources["sources"],
                "reporting_institutions": family_sources["reporting_institutions"],
                "source_text_raw": family_sources["source_text_raw"],
                "page_contexts": [
                    {
                        "source_url": context["source_url"],
                        "target_url": context["target_url"],
                        "link_text": context["link_text"],
                        "section_heading": context["section_heading"],
                        "section_id": context["section_id"],
                        "section_label": context["section_label"],
                        "family_id": context["family_id"],
                        "family_label": context["family_label"],
                    }
                    for context in page_contexts
                ],
            }


def _slim_family_for_chunks(family: dict) -> dict:
    """Keep only fields needed by _chatbot_chunk_records / _build_family_chunk_text."""
    return {
        "id": family["id"],
        "family_key": family["family_key"],
        "title": family.get("title"),
        "latest_observation": family.get("latest_observation"),
        "sources": family.get("sources"),
        "source_page": family.get("source_page"),
        "supporting_pages": [
            {"url": p.get("url"), "title": p.get("title")}
            for p in family.get("supporting_pages", [])
        ],
        "asset_documents": [
            {"url": a.get("url")} for a in family.get("asset_documents", [])
        ],
        "isaweb_dataset": family.get("isaweb_dataset"),
        "isaweb_metadata": family.get("isaweb_metadata"),
        "release_events": family.get("release_events"),
    }


def _chatbot_chunk_records(
    family_records: list[dict],
    isaweb_records: list[dict],
    asset_records: list[dict],
) -> list[dict]:
    records = []
    for family in family_records:
        text = _build_family_chunk_text(family)
        if not text:
            continue
        reference_urls = []
        if family.get("source_page") and family["source_page"].get("url"):
            reference_urls.append(family["source_page"]["url"])
        for page in family.get("supporting_pages", []):
            if page.get("url") and page["url"] not in reference_urls:
                reference_urls.append(page["url"])
        for asset in family.get("asset_documents", []):
            if asset.get("url") and asset["url"] not in reference_urls:
                reference_urls.append(asset["url"])
        metadata = family.get("isaweb_metadata")
        if metadata and metadata.get("meta_url") and metadata["meta_url"] not in reference_urls:
            reference_urls.append(metadata["meta_url"])
        retrieval_score = _family_chunk_retrieval_score(family)

        records.append(
            {
                "record_type": "chatbot_chunk",
                "id": f"chatbot_chunk:{family['id']}:summary",
                "parent_id": family["id"],
                "parent_record_type": "dataset_family",
                "family_key": family["family_key"],
                "chunk_kind": "family_summary",
                "title": family["title"],
                "text": text,
                "sources": family.get("sources", []),
                "reference_urls": reference_urls,
                "retrieval_score": retrieval_score,
                "retrieval_tier": _retrieval_tier(retrieval_score),
            }
        )
    for record in isaweb_records:
        text = _build_isaweb_chunk_text(record)
        if not text:
            continue
        retrieval_score = _isaweb_chunk_retrieval_score(record)
        records.append(
            {
                "record_type": "chatbot_chunk",
                "id": f"chatbot_chunk:{record['id']}:dataset",
                "parent_id": record["id"],
                "parent_record_type": "isaweb_dataset",
                "family_key": None,
                "chunk_kind": "isaweb_dataset_summary",
                "title": record["title"],
                "text": text,
                "sources": [],
                "reference_urls": [url for url in [record.get("source_url")] if url],
                "retrieval_score": retrieval_score,
                "retrieval_tier": _retrieval_tier(retrieval_score),
            }
        )
    for record in asset_records:
        text = _build_asset_chunk_text(record)
        if not text:
            continue
        retrieval_score = _asset_chunk_retrieval_score(record)
        records.append(
            {
                "record_type": "chatbot_chunk",
                "id": f"chatbot_chunk:{record['id']}:asset",
                "parent_id": record["id"],
                "parent_record_type": "asset_document",
                "family_key": None,
                "chunk_kind": "asset_document_summary",
                "title": _asset_chunk_title(record),
                "text": text,
                "sources": [],
                "reference_urls": [record["url"]],
                "retrieval_score": retrieval_score,
                "retrieval_tier": _retrieval_tier(retrieval_score),
            }
        )
    return sorted(records, key=lambda record: (-record["retrieval_score"], record["id"]))


def _page_chatbot_chunk_records(page_records: list[dict]) -> list[dict]:
    """Generate chatbot_chunk records from website page_documents."""
    MIN_TEXT_LENGTH = 50
    records = []
    for page in page_records:
        text = (page.get("text") or "").strip()
        title = (page.get("title") or "").strip()
        if len(text) < MIN_TEXT_LENGTH:
            continue
        # Build a concise snippet: title + first ~500 chars of text
        snippet = text[:500]
        if len(text) > 500:
            # Cut at last sentence boundary
            cut = snippet.rfind(". ")
            if cut > 200:
                snippet = snippet[: cut + 1]
        chunk_text = f"{title}\n\n{snippet}" if title else snippet
        records.append(
            {
                "record_type": "chatbot_chunk",
                "id": f"chatbot_chunk:{page['id']}:page",
                "parent_id": page["id"],
                "parent_record_type": "page_document",
                "family_key": None,
                "chunk_kind": "page_summary",
                "title": title,
                "text": chunk_text,
                "sources": [],
                "reference_urls": [page["url"]],
                "retrieval_score": 100,
                "retrieval_tier": "low",
            }
        )
    return records


def _group_dimensions(rows: list[sqlite3.Row]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row["dimension_key"], []).append(row["dimension_value"])
    return grouped


def _latest_observation(rows: list[sqlite3.Row]) -> dict | None:
    if not rows:
        return None
    row = max(rows, key=lambda item: _period_sort_key(item["period"]))
    return {
        "period": row["period"],
        "value": row["value"],
        "unit": row["unit"],
        "series_label": row["series_label"],
    }


def _latest_observations_by_series(rows: list[sqlite3.Row]) -> list[dict]:
    latest_by_series: dict[str, sqlite3.Row | dict] = {}
    for row in rows:
        series_label = row["series_label"] or ""
        current = latest_by_series.get(series_label)
        if current is None or _period_sort_key(row["period"]) > _period_sort_key(current["period"]):
            latest_by_series[series_label] = row

    serialized = [
        {
            "period": row["period"],
            "value": row["value"],
            "unit": row["unit"],
            "series_label": row["series_label"],
        }
        for _, row in sorted(
            latest_by_series.items(),
            key=lambda item: (
                -_period_sort_key(item[1]["period"])[0],
                -_period_sort_key(item[1]["period"])[1] if len(_period_sort_key(item[1]["period"])) > 1 and isinstance(_period_sort_key(item[1]["period"])[1], int) else 0,
                item[0].lower(),
            ),
        )
    ]
    if serialized:
        best_period = max(serialized, key=lambda item: _period_sort_key(item["period"]))["period"]
        serialized = [item for item in serialized if item["period"] == best_period]
    return serialized


def _period_sort_key(period: str | None) -> tuple:
    value = (period or "").strip()
    if not value:
        return (0, "")

    if match := re.match(r"^(\d{2})\.(\d{2})\.(\d{2,4})$", value):
        day, month, year = int(match.group(1)), int(match.group(2)), _normalize_period_year(match.group(3))
        return (5, year, month, day)

    if match := re.match(r"^(\d{4})-Q([1-4])$", value):
        return (4, int(match.group(1)), int(match.group(2)))

    if match := re.match(r"^Q([1-4])\s+(\d{2,4})$", value):
        return (4, _normalize_period_year(match.group(2)), int(match.group(1)))

    if match := re.match(r"^(\d{4})-(\d{2})$", value):
        return (3, int(match.group(1)), int(match.group(2)))

    if match := re.match(r"^(\d{4})$", value):
        return (2, int(match.group(1)))

    return (1, value)


def _normalize_period_year(raw_year: str) -> int:
    year = int(raw_year)
    if len(raw_year) == 2:
        return 2000 + year if year < 70 else 1900 + year
    return year


def _metadata_rows_for_dataset(
    conn: sqlite3.Connection,
    *,
    hierid: int,
    lang: str,
    pos_values: list[str],
) -> list[sqlite3.Row]:
    if not pos_values:
        return []
    placeholders = ", ".join("?" for _ in pos_values)
    return conn.execute(
        f"""
        SELECT
            id,
            meta_key,
            hierid,
            lang,
            pos,
            meta_url,
            title,
            region,
            unit,
            comment,
            classification,
            breaks,
            frequency,
            data_available_json,
            last_update,
            source,
            lag,
            prepared_at,
            sender_id,
            sender_name
        FROM isaweb_metadata
        WHERE hierid = ? AND lang = ? AND pos IN ({placeholders})
        ORDER BY pos
        """,
        (hierid, lang, *pos_values),
    ).fetchall()


def _release_rows_for_metadata(conn: sqlite3.Connection, metadata_ids: list[int]) -> list[sqlite3.Row]:
    if not metadata_ids:
        return []
    placeholders = ", ".join("?" for _ in metadata_ids)
    return conn.execute(
        f"""
        SELECT
            metadata_id,
            hierid,
            lang,
            pos,
            release_date_text,
            reference_text,
            revision_text,
            source_url
        FROM release_events
        WHERE metadata_id IN ({placeholders})
        ORDER BY release_date_text, id
        """,
        metadata_ids,
    ).fetchall()


def _metadata_rows_for_title(
    conn: sqlite3.Connection,
    *,
    hierid: int,
    lang: str,
    title: str,
    exclude_ids: list[int],
) -> list[sqlite3.Row]:
    clauses = [
        "hierid = ?",
        "lang = ?",
        "lower(title) = lower(?)",
    ]
    params: list[object] = [hierid, lang, title]
    if exclude_ids:
        placeholders = ", ".join("?" for _ in exclude_ids)
        clauses.append(f"id NOT IN ({placeholders})")
        params.extend(exclude_ids)

    return conn.execute(
        f"""
        SELECT
            id,
            meta_key,
            hierid,
            lang,
            pos,
            meta_url,
            title,
            region,
            unit,
            comment,
            classification,
            breaks,
            frequency,
            data_available_json,
            last_update,
            source,
            lag,
            prepared_at,
            sender_id,
            sender_name
        FROM isaweb_metadata
        WHERE {' AND '.join(clauses)}
        ORDER BY pos
        """,
        params,
    ).fetchall()


def _fallback_release_rows_for_report_hierarchy(
    conn: sqlite3.Connection,
    *,
    hierid: int,
    lang: str,
    exclude_metadata_ids: list[int],
) -> list[sqlite3.Row]:
    clauses = [
        "re.hierid = ?",
        "re.lang = ?",
        "im.pos NOT LIKE 'REPORT:%'",
    ]
    params: list[object] = [hierid, lang]
    if exclude_metadata_ids:
        placeholders = ", ".join("?" for _ in exclude_metadata_ids)
        clauses.append(f"re.metadata_id NOT IN ({placeholders})")
        params.extend(exclude_metadata_ids)

    rows = conn.execute(
        f"""
        SELECT
            re.metadata_id,
            re.hierid,
            re.lang,
            re.pos,
            re.release_date_text,
            re.reference_text,
            re.revision_text,
            re.source_url,
            im.title
        FROM release_events re
        JOIN isaweb_metadata im ON im.id = re.metadata_id
        WHERE {' AND '.join(clauses)}
        ORDER BY re.release_date_text, re.id
        """,
        params,
    ).fetchall()
    distinct_titles = {row["title"] for row in rows if row["title"]}
    if len(distinct_titles) != 1:
        return []
    return rows


def _source_page_rows(conn: sqlite3.Connection, source_urls: list[str]) -> list[sqlite3.Row]:
    if not source_urls:
        return []
    placeholders = ", ".join("?" for _ in source_urls)
    return conn.execute(
        f"""
        SELECT
            p.url,
            p.final_url,
            p.status_code,
            p.content_type,
            p.fetched_at,
            pc.title,
            pc.text_content,
            pc.page_section,
            pc.language,
            pc.extracted_at,
            pc.extractor_version
        FROM pages p
        LEFT JOIN page_content pc ON pc.page_id = p.id
        WHERE p.url IN ({placeholders})
        ORDER BY p.url
        """,
        source_urls,
    ).fetchall()


def _asset_rows_for_source_pages(conn: sqlite3.Connection, source_urls: list[str]) -> list[sqlite3.Row]:
    if not source_urls:
        return []
    placeholders = ", ".join("?" for _ in source_urls)
    return conn.execute(
        f"""
        SELECT
            rl.source_url,
            rl.link_text,
            rl.section_heading,
            p.url,
            p.final_url,
            p.status_code,
            p.content_type,
            p.fetched_at,
            ad.asset_type,
            ad.extraction_status,
            ad.text_content,
            ad.metadata_json,
            ad.extracted_at,
            ad.extractor_version
        FROM resource_links rl
        JOIN pages p ON p.url = rl.normalized_target_url
        JOIN asset_documents ad ON ad.page_id = p.id
        WHERE rl.resource_kind = 'asset_document'
          AND rl.source_url IN ({placeholders})
        ORDER BY rl.source_url, p.url, rl.id
        """,
        source_urls,
    ).fetchall()


def _supporting_page_rows(
    conn: sqlite3.Connection,
    source_urls: list[str],
    *,
    asset_urls: list[str] | None = None,
) -> list[sqlite3.Row]:
    if not source_urls:
        return []

    candidate_urls = set(_direct_neighbor_page_urls(conn, source_urls))
    candidate_urls.update(_shared_asset_page_urls(conn, source_urls, asset_urls or []))
    candidate_urls.update(_shared_path_page_urls(conn, source_urls))

    rows = _source_page_rows(conn, sorted(candidate_urls))

    return [row for row in rows if _looks_like_statistics_supporting_page(row)]


def _direct_neighbor_page_urls(conn: sqlite3.Connection, source_urls: list[str]) -> list[str]:
    placeholders = ", ".join("?" for _ in source_urls)
    rows = conn.execute(
        f"""
        WITH neighbor_urls AS (
            SELECT DISTINCT rl.source_url AS page_url
            FROM resource_links rl
            WHERE rl.resource_kind = 'page_document'
              AND rl.normalized_target_url IN ({placeholders})
              AND rl.source_url NOT IN ({placeholders})
            UNION
            SELECT DISTINCT rl.normalized_target_url AS page_url
            FROM resource_links rl
            WHERE rl.resource_kind = 'page_document'
              AND rl.source_url IN ({placeholders})
              AND rl.normalized_target_url NOT IN ({placeholders})
        )
        SELECT page_url
        FROM neighbor_urls
        ORDER BY page_url
        """,
        (*source_urls, *source_urls, *source_urls, *source_urls),
    ).fetchall()
    return [row["page_url"] for row in rows]


def _shared_asset_page_urls(
    conn: sqlite3.Connection,
    source_urls: list[str],
    asset_urls: list[str],
) -> list[str]:
    if not asset_urls:
        return []

    asset_placeholders = ", ".join("?" for _ in asset_urls)
    source_placeholders = ", ".join("?" for _ in source_urls)
    rows = conn.execute(
        f"""
        SELECT DISTINCT rl.source_url AS page_url
        FROM resource_links rl
        WHERE rl.resource_kind = 'asset_document'
          AND rl.normalized_target_url IN ({asset_placeholders})
          AND rl.source_url NOT IN ({source_placeholders})
        ORDER BY rl.source_url
        """,
        (*asset_urls, *source_urls),
    ).fetchall()
    return [row["page_url"] for row in rows]


def _shared_path_page_urls(conn: sqlite3.Connection, source_urls: list[str]) -> list[str]:
    prefixes = sorted({prefix for prefix in (_page_directory_prefix(url) for url in source_urls) if prefix})
    if not prefixes:
        return []

    source_placeholders = ", ".join("?" for _ in source_urls)
    prefix_clause = " OR ".join("p.url LIKE ?" for _ in prefixes)
    rows = conn.execute(
        f"""
        SELECT DISTINCT p.url AS page_url
        FROM pages p
        LEFT JOIN page_content pc ON pc.page_id = p.id
        WHERE p.url NOT IN ({source_placeholders})
          AND ({prefix_clause})
        ORDER BY p.url
        """,
        (*source_urls, *(f"%{prefix}%" for prefix in prefixes)),
    ).fetchall()
    return [row["page_url"] for row in rows]


def _page_directory_prefix(url: str) -> str:
    path = urlparse(url).path
    if not path or "/" not in path:
        return ""
    return path.rsplit("/", 1)[0] + "/"


def _select_primary_family_page(
    *,
    title: str | None,
    source_pages: list[sqlite3.Row],
    supporting_pages: list[sqlite3.Row],
    page_contexts: list[sqlite3.Row],
) -> sqlite3.Row | None:
    candidates: dict[str, sqlite3.Row] = {}
    source_page_urls = {row["url"] for row in source_pages}
    for row in [*source_pages, *supporting_pages]:
        if row["url"] not in candidates:
            candidates[row["url"]] = row
    if not candidates:
        return None

    context_terms = [
        value
        for context in page_contexts
        for value in (context["family_label"], context["section_label"])
        if value
    ]
    target_terms = _meaningful_target_terms(title, context_terms)

    return max(
        candidates.values(),
        key=lambda row: (
            _page_relevance_score(row, target_terms, is_direct_source=row["url"] in source_page_urls),
            row["url"],
        ),
    )


def _page_relevance_score(row: sqlite3.Row, target_terms: list[str], *, is_direct_source: bool) -> int:
    row_title = (row["title"] or "").lower()
    row_url = (row["url"] or "").lower()
    row_text = (row["text_content"] or "").lower()
    haystack = " ".join(part for part in [row_title, row_url, row_text] if part)
    title_url_tokens = set(_relevance_tokens(" ".join(part for part in [row_title, row_url] if part)))
    body_tokens = set(_relevance_tokens(row_text))
    score = 5 if is_direct_source else 0
    score += _supporting_page_penalty(row)
    score += _page_kind_bonus(row)
    score += _page_path_specificity_bonus(row)

    for term in target_terms:
        normalized_term = term.lower()
        term_tokens = set(_relevance_tokens(normalized_term))
        if not term_tokens:
            continue
        score += len(title_url_tokens & term_tokens) * 15
        score += len(body_tokens & term_tokens) * 3
        if normalized_term in row_title:
            score += 80
        elif normalized_term in haystack:
            score += 25

    return score


def _relevance_tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]{3,}", text.lower())]


def _meaningful_target_terms(title: str | None, context_terms: list[str]) -> list[str]:
    ignored_terms = {
        "chart",
        "table",
        "publication schedule",
        "release calendar",
        "prices, competitiveness",
        "statistics",
    }
    seen: set[str] = set()
    meaningful_terms: list[str] = []
    for value in [title, *context_terms]:
        normalized = " ".join((value or "").split()).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in ignored_terms:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        meaningful_terms.append(normalized)
    return meaningful_terms


def _supporting_page_penalty(row: sqlite3.Row) -> int:
    text = " ".join(part for part in [row["title"] or "", row["url"] or ""] if part).lower()
    penalties = (
        "explanatory",
        "erläuter",
        "release calendar",
        "publication schedule",
        "methodological",
    )
    return -80 if any(token in text for token in penalties) else 0


def _page_kind_bonus(row: sqlite3.Row) -> int:
    url = (row["url"] or "").lower()
    if "/statistics/standardized-tables/" in url:
        return 30
    if "/isawebstat/" in url:
        return -30
    return 0


def _page_path_specificity_bonus(row: sqlite3.Row) -> int:
    path = urlparse((row["url"] or "")).path.strip("/")
    if not path:
        return 0
    return min(len([segment for segment in path.split("/") if segment]), 12)


def _collect_family_sources(
    *,
    primary_page: sqlite3.Row | None,
    source_pages: list[sqlite3.Row],
    supporting_pages: list[sqlite3.Row],
    asset_rows: list[sqlite3.Row],
    primary_metadata: sqlite3.Row | None,
    observations: list[sqlite3.Row],
) -> dict[str, list[str]]:
    sources: list[str] = []
    reporting_institutions: list[str] = []
    source_text_raw: list[str] = []
    seen_texts: set[str] = set()
    primary_url = primary_page["url"] if primary_page else None
    series_labels = {
        _clean_family_source_value(row["series_label"]).lower()
        for row in observations
        if row["series_label"]
    }

    if primary_page and primary_page["text_content"]:
        _merge_source_metadata(
            extract_source_metadata(_normalize_source_text(primary_page["text_content"])),
            sources=sources,
            reporting_institutions=reporting_institutions,
            source_text_raw=source_text_raw,
            seen_texts=seen_texts,
            excluded_sources=series_labels,
        )

    if primary_metadata and primary_metadata["source"]:
        _merge_source_metadata(
            extract_source_metadata(f"Source: {primary_metadata['source']}"),
            sources=sources,
            reporting_institutions=reporting_institutions,
            source_text_raw=source_text_raw,
            seen_texts=seen_texts,
            excluded_sources=series_labels,
        )

    for row in asset_rows:
        if row["text_content"] and (primary_url is None or row["source_url"] == primary_url):
            _merge_source_metadata(
                extract_source_metadata(_normalize_source_text(row["text_content"])),
                sources=sources,
                reporting_institutions=reporting_institutions,
                source_text_raw=source_text_raw,
                seen_texts=seen_texts,
                excluded_sources=series_labels,
            )

    return {
        "sources": sources,
        "reporting_institutions": reporting_institutions,
        "source_text_raw": source_text_raw,
    }


def _normalize_source_text(text: str) -> str:
    normalized = text or ""
    normalized = re.sub(
        r"(?i)\s+(?=(?:quelle|quellen|source|sources|datenquelle|data\s+source|reporting institutions?)\s*:)",
        "\n",
        normalized,
    )
    return normalized


def _merge_source_metadata(
    metadata,
    *,
    sources: list[str],
    reporting_institutions: list[str],
    source_text_raw: list[str],
    seen_texts: set[str],
    excluded_sources: set[str],
) -> None:
    for source in metadata.sources:
        cleaned_source = _clean_family_source_value(source)
        if (
            cleaned_source
            and cleaned_source.lower() not in excluded_sources
            and not _is_non_source_geography(cleaned_source)
            and cleaned_source not in sources
        ):
            sources.append(cleaned_source)
    for institution in metadata.reporting_institutions:
        cleaned_institution = _clean_family_source_value(institution)
        if (
            cleaned_institution
            and cleaned_institution.lower() not in excluded_sources
            and not _is_non_source_geography(cleaned_institution)
            and cleaned_institution not in reporting_institutions
        ):
            reporting_institutions.append(cleaned_institution)
    for raw_text in metadata.source_text_raw:
        if raw_text not in seen_texts:
            source_text_raw.append(raw_text)
            seen_texts.add(raw_text)


def _build_family_chunk_text(family: dict) -> str:
    parts: list[str] = []

    if family.get("title"):
        parts.append(f"Dataset family: {family['title']}.")
    if family.get("source_page") and family["source_page"].get("title"):
        parts.append(f"Primary page: {family['source_page']['title']}.")

    dataset = family.get("isaweb_dataset") or {}
    latest = family.get("latest_observation") or dataset.get("latest_observation")
    if latest:
        unit = f" {latest['unit']}" if latest.get("unit") else ""
        parts.append(f"Latest observation: {latest['period']} = {latest['value']}{unit}.")

    metadata = family.get("isaweb_metadata") or {}
    if metadata.get("comment"):
        parts.append(metadata["comment"].strip())

    if family.get("sources"):
        parts.append(f"Sources: {'; '.join(family['sources'])}.")

    supporting_titles = [
        page["title"]
        for page in family.get("supporting_pages", [])
        if page.get("title")
    ]
    if supporting_titles:
        supporting_preview = supporting_titles[:5]
        supporting_text = ", ".join(supporting_preview)
        remaining_count = len(supporting_titles) - len(supporting_preview)
        if remaining_count > 0:
            supporting_text = f"{supporting_text}, +{remaining_count} more"
        parts.append(f"Supporting pages: {supporting_text}.")

    return " ".join(part for part in parts if part).strip()


def _clean_family_source_value(value: str) -> str:
    cleaned = (value or "").strip()
    if ". " in cleaned:
        cleaned = cleaned.split(". ", 1)[0].strip()
    return cleaned.rstrip(".").strip()


_NON_SOURCE_GEOGRAPHIES = {
    "austria",
    "belgium",
    "bulgaria",
    "croatia",
    "cyprus",
    "czech republic",
    "denmark",
    "estonia",
    "euro area",
    "finland",
    "france",
    "germany",
    "greece",
    "hungary",
    "ireland",
    "italy",
    "japan",
    "latvia",
    "lithuania",
    "luxembourg",
    "malta",
    "netherlands",
    "norway",
    "poland",
    "portugal",
    "romania",
    "slovakia",
    "slovenia",
    "spain",
    "sweden",
    "switzerland",
    "united kingdom",
    "u.s.a",
    "usa",
}


def _is_non_source_geography(value: str) -> bool:
    return value.strip().lower() in _NON_SOURCE_GEOGRAPHIES


def _build_isaweb_chunk_text(record: dict) -> str:
    parts: list[str] = []
    if record.get("title"):
        parts.append(f"ISAweb dataset: {record['title']}.")
    if record.get("freq"):
        parts.append(f"Frequency: {record['freq']}.")
    latest = record.get("latest_observation")
    if latest:
        unit = f" {latest['unit']}" if latest.get("unit") else ""
        parts.append(f"Latest observation: {latest['period']} = {latest['value']}{unit}.")
    dimensions = record.get("dimensions") or {}
    if dimensions:
        flat_parts = []
        for key, values in sorted(dimensions.items()):
            flat_parts.append(f"{key}={', '.join(values)}")
        parts.append(f"Dimensions: {'; '.join(flat_parts)}.")
    return " ".join(parts).strip()


def _family_chunk_retrieval_score(family: dict) -> int:
    score = 1000
    source_page = family.get("source_page") or {}
    url = (source_page.get("url") or "").lower()
    if "/statistics/standardized-tables/" in url:
        score += 40
    if family.get("latest_observation"):
        score += 20
    if family.get("release_events"):
        score += 10
    if "/isawebstat/" in url:
        score -= 15
    return score


def _isaweb_chunk_retrieval_score(record: dict) -> int:
    score = 900
    if record.get("latest_observation"):
        score += 20
    if record.get("page_contexts"):
        score += 10
    return score


def _asset_chunk_retrieval_score(record: dict) -> int:
    asset_type = (record.get("asset_type") or "").lower()
    if asset_type in {"csv", "xlsx", "xls", "json", "xml", "zip", "ods"}:
        score = 700
    elif asset_type == "pdf":
        score = 250
    else:
        score = 350

    linked_from = record.get("linked_from") or []
    if any("/statistics/standardized-tables/" in (link.get("source_url") or "").lower() for link in linked_from):
        score += 20
    return score


def _retrieval_tier(score: int) -> str:
    if score >= 850:
        return "primary"
    if score >= 500:
        return "secondary"
    return "background"


def _asset_chunk_title(record: dict) -> str:
    linked_from = record.get("linked_from") or []
    first_link = linked_from[0] if linked_from else {}
    return first_link.get("link_text") or Path(record["url"]).name


def _build_asset_chunk_text(record: dict) -> str:
    parts: list[str] = [f"Asset document: {_asset_chunk_title(record)}."]
    if record.get("asset_type"):
        parts.append(f"Type: {record['asset_type']}.")
    if record.get("text"):
        preview = " ".join(str(record["text"]).split())
        if len(preview) > 280:
            preview = preview[:277].rstrip() + "..."
        parts.append(f"Content preview: {preview}.")
    return " ".join(parts).strip()


def _filter_asset_rows(rows: list[sqlite3.Row], section_headings: set[str]) -> list[sqlite3.Row]:
    if not rows:
        return []
    if not section_headings:
        return rows

    matching = [
        row for row in rows
        if row["section_heading"] and row["section_heading"].strip() in section_headings
    ]
    return matching or rows


def _looks_like_statistics_supporting_page(row: sqlite3.Row) -> bool:
    text = " ".join(
        part for part in (
            row["url"],
            row["title"],
            row["page_section"],
            row["text_content"],
        )
        if part
    ).lower()
    return "/statistics/" in text or "/statistik/" in text or "statistics" in text or "statistik" in text


def _serialize_page_row(row: sqlite3.Row) -> dict:
    return {
        "url": row["url"],
        "final_url": row["final_url"],
        "status_code": row["status_code"],
        "content_type": row["content_type"],
        "fetched_at": row["fetched_at"],
        "title": row["title"],
        "page_section": row["page_section"],
        "language": row["language"],
    }


def _serialize_asset_row(row: sqlite3.Row) -> dict:
    return {
        "source_url": row["source_url"],
        "url": row["url"],
        "final_url": row["final_url"],
        "status_code": row["status_code"],
        "content_type": row["content_type"],
        "fetched_at": row["fetched_at"],
        "asset_type": row["asset_type"],
        "extraction_status": row["extraction_status"],
        "text": row["text_content"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "extracted_at": row["extracted_at"],
        "extractor_version": row["extractor_version"],
        "link_text": row["link_text"],
        "section_heading": row["section_heading"],
    }


def _serialize_metadata_row(row: sqlite3.Row) -> dict:
    return {
        "meta_key": row["meta_key"],
        "hierid": row["hierid"],
        "lang": row["lang"],
        "pos": row["pos"],
        "meta_url": row["meta_url"],
        "title": row["title"],
        "region": row["region"],
        "unit": row["unit"],
        "comment": row["comment"],
        "classification": row["classification"],
        "breaks": row["breaks"],
        "frequency": row["frequency"],
        "data_available": json.loads(row["data_available_json"] or "[]"),
        "last_update": row["last_update"],
        "source": row["source"],
        "lag": row["lag"],
        "prepared_at": row["prepared_at"],
        "sender": {"id": row["sender_id"], "name": row["sender_name"]},
    }


def _serialize_release_row(row: sqlite3.Row) -> dict:
    return {
        "metadata_id": row["metadata_id"],
        "hierid": row["hierid"],
        "lang": row["lang"],
        "pos": row["pos"],
        "release_date_text": row["release_date_text"],
        "reference_text": row["reference_text"],
        "revision_text": row["revision_text"],
        "source_url": row["source_url"],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export unified knowledge base to JSONL")
    parser.add_argument("db_path", type=Path, help="Path to SQLite database")
    parser.add_argument("output_path", type=Path, help="Output JSONL file")
    args = parser.parse_args()

    count = export_knowledge_base_jsonl(args.db_path, args.output_path)
    print(f"Exported {count} records to {args.output_path}")
