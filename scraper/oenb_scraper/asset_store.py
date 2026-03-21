from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime

from oenb_scraper.asset_extraction import EXTRACTOR_VERSION, extract_asset_payload


def store_asset_document(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    url: str,
    content_type: str,
    body: bytes,
) -> int:
    """Extract and persist asset knowledge for a fetched non-HTML resource."""

    payload = extract_asset_payload(url=url, content_type=content_type, body=body)
    body_hash = hashlib.sha256(body).hexdigest() if body else None
    now = datetime.utcnow().isoformat() + "Z"

    existing = conn.execute(
        "SELECT page_id, body_hash, extractor_version FROM asset_documents WHERE page_id = ?",
        (page_id,),
    ).fetchone()
    if existing and existing["body_hash"] == body_hash and existing["extractor_version"] == EXTRACTOR_VERSION:
        return page_id

    conn.execute(
        """
        INSERT INTO asset_documents
          (page_id, asset_type, extraction_status, text_content, metadata_json, body_hash, extracted_at, extractor_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(page_id) DO UPDATE SET
          asset_type = excluded.asset_type,
          extraction_status = excluded.extraction_status,
          text_content = excluded.text_content,
          metadata_json = excluded.metadata_json,
          body_hash = excluded.body_hash,
          extracted_at = excluded.extracted_at,
          extractor_version = excluded.extractor_version
        """,
        (
            page_id,
            payload["asset_type"],
            payload["extraction_status"],
            payload.get("text_content"),
            json.dumps(payload.get("metadata", {}), ensure_ascii=False),
            body_hash,
            now,
            EXTRACTOR_VERSION,
        ),
    )
    conn.commit()
    return page_id
