from urllib.parse import parse_qs, urlencode, urldefrag, urlparse


SESSION_QUERY_PARAMS = {"jsessionid", "JSESSIONID", "PHPSESSID", "sid", "session_id"}
SESSION_PATH_TOKENS = (";jsessionid=", ";JSESSIONID=")


def normalize_url(url: str) -> str:
    """Normalize OeNB URLs for deduplication and canonical storage."""

    url = urldefrag(url)[0]
    parsed = urlparse(url)

    path = parsed.path
    for token in SESSION_PATH_TOKENS:
        if token in path:
            path = path.split(token)[0]

    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered_params = {
        key: values
        for key, values in query_params.items()
        if key not in SESSION_QUERY_PARAMS
    }
    sorted_query = urlencode(sorted(filtered_params.items()), doseq=True)

    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if sorted_query:
        normalized += f"?{sorted_query}"
    return normalized
