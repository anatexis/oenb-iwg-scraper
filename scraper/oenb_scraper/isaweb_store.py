from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from oenb_scraper.isaweb_resolver import infer_hierid_from_report_id, parse_content_response
from oenb_scraper.isaweb_resolver import parse_release_schedule_html
from oenb_scraper.isaweb_resolver import parse_report_table_html
from oenb_scraper.isaweb_service import (
    extract_dataset_request,
    extract_hierarchy_reference,
    parse_data_response,
    parse_meta_response,
)
from oenb_scraper.release_calendar import store_release_events
from oenb_scraper.urlnorm import normalize_url


def canonical_dataset_key(
    *,
    hierid: int,
    lang: str,
    pos: list[str],
    dimensions: dict[str, list[str]] | None = None,
    freq: str | None = None,
) -> str:
    """Build a stable canonical key for an ISAweb dataset definition."""

    parts = [f"hierid={hierid}", f"lang={lang}"]
    if freq:
        parts.append(f"freq={freq}")

    for value in sorted(pos):
        parts.append(f"pos={value}")

    for key in sorted((dimensions or {}).keys()):
        for value in sorted(dimensions[key]):
            parts.append(f"{key}={value}")

    return "|".join(parts)


def store_isaweb_dataset(
    conn: sqlite3.Connection,
    *,
    hierid: int,
    lang: str,
    pos: list[str],
    dimensions: dict[str, list[str]] | None = None,
    freq: str | None = None,
    title: str | None = None,
    source_url: str | None = None,
) -> int:
    """Upsert a canonical ISAweb dataset and its dimension bindings."""

    dataset_key = canonical_dataset_key(
        hierid=hierid,
        lang=lang,
        pos=pos,
        dimensions=dimensions,
        freq=freq,
    )
    now = datetime.utcnow().isoformat() + "Z"

    existing = conn.execute(
        "SELECT id FROM isaweb_datasets WHERE dataset_key = ?",
        (dataset_key,),
    ).fetchone()

    if existing:
        dataset_id = existing["id"]
        conn.execute(
            """
            UPDATE isaweb_datasets
            SET title = ?, source_url = ?, freq = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, source_url, freq, now, dataset_id),
        )
        conn.execute("DELETE FROM isaweb_dimensions WHERE dataset_id = ?", (dataset_id,))
    else:
        cursor = conn.execute(
            """
            INSERT INTO isaweb_datasets
              (dataset_key, hierid, lang, freq, title, source_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (dataset_key, hierid, lang, freq, title, source_url, now, now),
        )
        dataset_id = cursor.lastrowid

    for pos_value in sorted(pos):
        conn.execute(
            """
            INSERT INTO isaweb_dimensions (dataset_id, dimension_key, dimension_value)
            VALUES (?, ?, ?)
            """,
            (dataset_id, "pos", pos_value),
        )
    for key in sorted((dimensions or {}).keys()):
        for value in sorted(dimensions[key]):
            conn.execute(
                """
                INSERT INTO isaweb_dimensions (dataset_id, dimension_key, dimension_value)
                VALUES (?, ?, ?)
                """,
                (dataset_id, key, value),
            )

    conn.commit()
    return dataset_id


def store_isaweb_observations(
    conn: sqlite3.Connection,
    *,
    dataset_id: int,
    observations: list[dict],
) -> int:
    """Replace observation rows for a canonical ISAweb dataset."""

    now = datetime.utcnow().isoformat() + "Z"
    conn.execute("DELETE FROM isaweb_observations WHERE dataset_id = ?", (dataset_id,))
    for observation in observations:
        conn.execute(
            """
            INSERT INTO isaweb_observations
              (dataset_id, period, value, unit, series_label, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                observation["period"],
                observation.get("value"),
                observation.get("unit"),
                observation.get("series_label"),
                now,
            ),
        )
    conn.commit()
    return len(observations)


def store_isaweb_data_response(
    conn: sqlite3.Connection,
    *,
    response_url: str,
    xml_text: str | bytes,
) -> int:
    """Persist all datasets and observations from an ISAweb XML data response."""

    dataset_request = extract_dataset_request(response_url)
    if dataset_request is None:
        return 0

    stored_count = 0
    for series in parse_data_response(xml_text):
        dataset_id = store_isaweb_dataset(
            conn,
            hierid=dataset_request.hierid,
            lang=dataset_request.lang,
            pos=[series["pos"]],
            dimensions=series["dimensions"] or dataset_request.dimensions,
            freq=series["freq"] or dataset_request.freq,
            title=series["title"],
            source_url=response_url,
        )
        store_isaweb_observations(
            conn,
            dataset_id=dataset_id,
            observations=series["observations"],
        )
        stored_count += 1

    return stored_count


def store_isaweb_meta_response(
    conn: sqlite3.Connection,
    *,
    response_url: str,
    xml_text: str | bytes,
) -> int:
    """Persist family-level ISAweb metadata and release events from a meta response."""

    dataset_request = extract_dataset_request(response_url)
    if dataset_request is None or not dataset_request.pos:
        raise ValueError("Meta response URL must include hierid, lang and pos")

    metadata = parse_meta_response(xml_text)
    pos = dataset_request.pos[0]
    meta_key = f"hierid={dataset_request.hierid}|lang={dataset_request.lang}|pos={pos}"
    now = datetime.utcnow().isoformat() + "Z"

    existing = conn.execute(
        "SELECT id FROM isaweb_metadata WHERE meta_key = ?",
        (meta_key,),
    ).fetchone()

    payload = (
        dataset_request.hierid,
        dataset_request.lang,
        pos,
        response_url,
        metadata.get("title"),
        metadata.get("region"),
        metadata.get("unit"),
        metadata.get("comment"),
        metadata.get("classification"),
        metadata.get("breaks"),
        metadata.get("frequency"),
        json.dumps(metadata.get("data_available", [])),
        metadata.get("last_update"),
        metadata.get("source"),
        metadata.get("lag"),
        metadata.get("prepared_at"),
        metadata.get("sender", {}).get("id"),
        metadata.get("sender", {}).get("name"),
    )

    if existing:
        metadata_id = existing["id"]
        conn.execute(
            """
            UPDATE isaweb_metadata
            SET hierid = ?, lang = ?, pos = ?, meta_url = ?, title = ?, region = ?, unit = ?, comment = ?,
                classification = ?, breaks = ?, frequency = ?, data_available_json = ?, last_update = ?,
                source = ?, lag = ?, prepared_at = ?, sender_id = ?, sender_name = ?, updated_at = ?
            WHERE id = ?
            """,
            (*payload, now, metadata_id),
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO isaweb_metadata
              (meta_key, hierid, lang, pos, meta_url, title, region, unit, comment, classification,
               breaks, frequency, data_available_json, last_update, source, lag, prepared_at,
               sender_id, sender_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (meta_key, *payload, now, now),
        )
        metadata_id = cursor.lastrowid

    conn.commit()
    store_release_events(
        conn,
        metadata_id=metadata_id,
        hierid=dataset_request.hierid,
        lang=dataset_request.lang,
        pos=pos,
        source_url=response_url,
        releases=metadata.get("releases", []),
    )
    return metadata_id


def store_isaweb_report_html_response(
    conn: sqlite3.Connection,
    *,
    response_url: str,
    html_text: str | bytes,
) -> int:
    """Fallback materialization for ISAweb createReport HTML pages without service metadata."""

    parsed = parse_report_table_html(response_url, html_text)
    if parsed is None:
        return 0

    dataset_id = store_isaweb_dataset(
        conn,
        hierid=parsed["hierid"],
        lang=parsed["lang"],
        pos=[parsed["synthetic_pos"]],
        dimensions={"report_id": [parsed["report_id"]]},
        freq=parsed.get("frequency"),
        title=parsed.get("title"),
        source_url=response_url,
    )
    store_isaweb_observations(
        conn,
        dataset_id=dataset_id,
        observations=parsed["observations"],
    )
    _upsert_isaweb_metadata(
        conn,
        meta_key=f"hierid={parsed['hierid']}|lang={parsed['lang']}|pos={parsed['synthetic_pos']}",
        hierid=parsed["hierid"],
        lang=parsed["lang"],
        pos=parsed["synthetic_pos"],
        meta_url=parsed.get("metadata_url") or response_url,
        title=parsed.get("title"),
        region=None,
        unit=parsed.get("unit"),
        comment=parsed.get("comment"),
        classification=None,
        breaks=None,
        frequency=parsed.get("frequency"),
        data_available=None,
        last_update=None,
        source=parsed.get("source"),
        lag=None,
        prepared_at=None,
        sender_id=None,
        sender_name=None,
    )
    return dataset_id


def store_isaweb_content_response(
    conn: sqlite3.Connection,
    *,
    response_url: str,
    xml_text: str | bytes,
) -> int:
    """Persist ISAweb hierarchy content as navigable topic/family context."""

    content = parse_content_response(xml_text)
    elements = content.get("elements", [])
    if not elements:
        return 0

    lang, hierid = _extract_content_request_context(response_url)
    nodes = {element["id"]: element for element in elements}
    now = datetime.utcnow().isoformat() + "Z"
    stored_count = 0

    for element in elements:
        path = _build_node_path(element["id"], nodes)
        if not path:
            path = [element["id"]]

        section_id = path[0] if path else None
        family_id = path[1] if len(path) > 1 else None
        section_label = nodes.get(section_id, {}).get("text") if section_id is not None else None
        family_label = nodes.get(family_id, {}).get("text") if family_id is not None else None

        existing = conn.execute(
            "SELECT id FROM isaweb_content_nodes WHERE lang = ? AND node_id = ?",
            (lang, element["id"]),
        ).fetchone()

        payload = (
            hierid,
            lang,
            element["id"],
            element["parent"],
            element["text"],
            section_id,
            section_label,
            family_id,
            family_label,
            json.dumps(path),
            response_url,
            content.get("prepared_at"),
        )

        if existing:
            conn.execute(
                """
                UPDATE isaweb_content_nodes
                SET hierid = ?, lang = ?, node_id = ?, parent_id = ?, label = ?, section_id = ?, section_label = ?,
                    family_id = ?, family_label = ?, path_json = ?, content_url = ?, prepared_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (*payload, now, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO isaweb_content_nodes
                  (hierid, lang, node_id, parent_id, label, section_id, section_label, family_id, family_label,
                   path_json, content_url, prepared_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*payload, now, now),
            )
        stored_count += 1

    for element in elements:
        _backfill_page_contexts(conn, hierid=element["id"], lang=lang, updated_at=now)

    conn.commit()
    return stored_count


def store_isaweb_release_html_response(
    conn: sqlite3.Connection,
    *,
    response_url: str,
    html_text: str | bytes,
) -> int:
    """Persist release calendar HTML pages onto synthetic REPORT:* metadata rows."""

    parsed = parse_release_schedule_html(response_url, html_text)
    if parsed is None:
        return 0

    meta_key = f"hierid={parsed['hierid']}|lang={parsed['lang']}|pos={parsed['synthetic_pos']}"
    existing = conn.execute(
        """
        SELECT title, region, unit, comment, classification, breaks, frequency,
               data_available_json, last_update, source, lag, prepared_at, sender_id, sender_name
        FROM isaweb_metadata
        WHERE meta_key = ?
        """,
        (meta_key,),
    ).fetchone()

    metadata_id = _upsert_isaweb_metadata(
        conn,
        meta_key=meta_key,
        hierid=parsed["hierid"],
        lang=parsed["lang"],
        pos=parsed["synthetic_pos"],
        meta_url=response_url,
        title=parsed.get("title") or (existing["title"] if existing else None),
        region=existing["region"] if existing else None,
        unit=existing["unit"] if existing else None,
        comment=existing["comment"] if existing else None,
        classification=existing["classification"] if existing else None,
        breaks=existing["breaks"] if existing else None,
        frequency=existing["frequency"] if existing else None,
        data_available=json.loads(existing["data_available_json"] or "[]") if existing else None,
        last_update=existing["last_update"] if existing else None,
        source=existing["source"] if existing else None,
        lag=existing["lag"] if existing else None,
        prepared_at=existing["prepared_at"] if existing else None,
        sender_id=existing["sender_id"] if existing else None,
        sender_name=existing["sender_name"] if existing else None,
    )
    store_release_events(
        conn,
        metadata_id=metadata_id,
        hierid=parsed["hierid"],
        lang=parsed["lang"],
        pos=parsed["synthetic_pos"],
        source_url=response_url,
        releases=parsed["releases"],
    )
    return metadata_id


def _upsert_isaweb_metadata(
    conn: sqlite3.Connection,
    *,
    meta_key: str,
    hierid: int,
    lang: str,
    pos: str,
    meta_url: str,
    title: str | None,
    region: str | None,
    unit: str | None,
    comment: str | None,
    classification: str | None,
    breaks: str | None,
    frequency: str | None,
    data_available: list[str] | None,
    last_update: str | None,
    source: str | None,
    lag: str | None,
    prepared_at: str | None,
    sender_id: str | None,
    sender_name: str | None,
) -> int:
    now = datetime.utcnow().isoformat() + "Z"

    existing = conn.execute(
        "SELECT id FROM isaweb_metadata WHERE meta_key = ?",
        (meta_key,),
    ).fetchone()

    payload = (
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
        json.dumps(data_available or []),
        last_update,
        source,
        lag,
        prepared_at,
        sender_id,
        sender_name,
    )

    if existing:
        metadata_id = existing["id"]
        conn.execute(
            """
            UPDATE isaweb_metadata
            SET hierid = ?, lang = ?, pos = ?, meta_url = ?, title = ?, region = ?, unit = ?, comment = ?,
                classification = ?, breaks = ?, frequency = ?, data_available_json = ?, last_update = ?,
                source = ?, lag = ?, prepared_at = ?, sender_id = ?, sender_name = ?, updated_at = ?
            WHERE id = ?
            """,
            (*payload, now, metadata_id),
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO isaweb_metadata
              (meta_key, hierid, lang, pos, meta_url, title, region, unit, comment, classification,
               breaks, frequency, data_available_json, last_update, source, lag, prepared_at,
               sender_id, sender_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (meta_key, *payload, now, now),
        )
        metadata_id = cursor.lastrowid

    conn.commit()
    return metadata_id


def store_isaweb_page_context(
    conn: sqlite3.Connection,
    *,
    source_url: str,
    target_url: str,
    link_text: str | None = None,
    section_heading: str | None = None,
    relation_kind: str | None = None,
    fallback_lang: str | None = None,
) -> int | None:
    """Persist a page->ISAweb hierarchy relation for navigation-aware retrieval."""

    reference = extract_hierarchy_reference(target_url, fallback_lang=fallback_lang)
    if reference is None:
        return None

    normalized_target_url = normalize_url(target_url)
    now = datetime.utcnow().isoformat() + "Z"
    labels = _lookup_page_context_labels(conn, hierid=reference.hierid, lang=reference.lang)

    existing = conn.execute(
        """
        SELECT id
        FROM isaweb_page_contexts
        WHERE source_url = ? AND normalized_target_url = ? AND hierid = ? AND lang = ?
        """,
        (source_url, normalized_target_url, reference.hierid, reference.lang),
    ).fetchone()

    payload = (
        source_url,
        target_url,
        normalized_target_url,
        reference.hierid,
        reference.lang,
        relation_kind,
        link_text,
        section_heading,
        labels["section_id"],
        labels["section_label"],
        labels["family_id"],
        labels["family_label"],
    )

    if existing:
        conn.execute(
            """
            UPDATE isaweb_page_contexts
            SET source_url = ?, target_url = ?, normalized_target_url = ?, hierid = ?, lang = ?, relation_kind = ?,
                link_text = ?, section_heading = ?, section_id = ?, section_label = ?, family_id = ?, family_label = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (*payload, now, existing["id"]),
        )
        context_id = existing["id"]
    else:
        cursor = conn.execute(
            """
            INSERT INTO isaweb_page_contexts
              (source_url, target_url, normalized_target_url, hierid, lang, relation_kind, link_text,
               section_heading, section_id, section_label, family_id, family_label, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*payload, now, now),
        )
        context_id = cursor.lastrowid

    conn.commit()
    return context_id


def _extract_content_request_context(response_url: str) -> tuple[str, int | None]:
    parsed = urlparse(response_url)
    query = parse_qs(parsed.query)
    lang = (query.get("lang", ["DE"])[0] or "DE").upper()

    hierid = None
    hierid_values = query.get("hierid")
    if hierid_values:
        try:
            hierid = int(hierid_values[0])
        except ValueError:
            hierid = None
    elif query.get("report"):
        hierid = infer_hierid_from_report_id(query["report"][0])

    return lang, hierid


def _build_node_path(node_id: int, nodes: dict[int, dict]) -> list[int]:
    path: list[int] = []
    current_id = node_id
    visited: set[int] = set()

    while current_id not in visited:
        visited.add(current_id)
        node = nodes.get(current_id)
        if node is None:
            break
        path.append(current_id)
        parent_id = node.get("parent")
        if parent_id in (None, 0):
            break
        current_id = parent_id

    path.reverse()
    return path


def _lookup_page_context_labels(
    conn: sqlite3.Connection,
    *,
    hierid: int,
    lang: str,
) -> dict[str, int | str | None]:
    row = conn.execute(
        """
        SELECT section_id, section_label, family_id, family_label
        FROM isaweb_content_nodes
        WHERE node_id = ? AND lang = ?
        """,
        (hierid, lang),
    ).fetchone()
    if row is None:
        return {
            "section_id": None,
            "section_label": None,
            "family_id": None,
            "family_label": None,
        }
    return {
        "section_id": row["section_id"],
        "section_label": row["section_label"],
        "family_id": row["family_id"],
        "family_label": row["family_label"],
    }


def _backfill_page_contexts(
    conn: sqlite3.Connection,
    *,
    hierid: int,
    lang: str,
    updated_at: str,
) -> int:
    labels = _lookup_page_context_labels(conn, hierid=hierid, lang=lang)
    if labels["section_id"] is None and labels["family_id"] is None:
        return 0

    cursor = conn.execute(
        """
        UPDATE isaweb_page_contexts
        SET section_id = ?, section_label = ?, family_id = ?, family_label = ?, updated_at = ?
        WHERE hierid = ? AND lang = ?
        """,
        (
            labels["section_id"],
            labels["section_label"],
            labels["family_id"],
            labels["family_label"],
            updated_at,
            hierid,
            lang,
        ),
    )
    return cursor.rowcount
