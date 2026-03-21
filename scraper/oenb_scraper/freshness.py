def should_reextract_content(
    *,
    previous_hash: str | None,
    current_hash: str | None,
    http_status: int | None = None,
) -> bool:
    """Decide whether derived content must be regenerated."""

    if http_status == 304:
        return False
    if previous_hash is None:
        return True
    return previous_hash != current_hash
