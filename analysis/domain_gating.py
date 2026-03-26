"""Domain gating helpers for OeNB retrieval."""

from __future__ import annotations

DOMAIN_HINTS = {
    "monetary_policy": [
        "einlagenfazilität",
        "deposit facility",
        "leitzins",
        "policy rate",
        "main refinancing",
        "geldpolitik",
        "mindestreserve",
        "minimum reserve",
        "beitrag zu m3",
        "monetärstatistik",
        "geldmengenaggregate",
    ],
    "interest_rates": [
        "interest rate",
        "interest rates",
        "zinssatz",
        "key interest rates",
        "base and reference rates",
        "basiszinssatz",
        "referenzzinssatz",
        "sparzinsen",
        "kreditzinsen",
        "wohnbaukreditzinsen",
        "report=10.4",
        "report=2.1",
    ],
    "commodity_prices": [
        "goldpreis",
        "gold price",
        "gold",
        "commodity prices",
        "rohstoffpreise",
        "inflation",
        "inflationsdaten",
        "verbraucherpreisindex",
        "vpi",
        "commodity-prices",
    ],
    "real_estate": [
        "residential property price index",
        "rppi",
        "real-estate",
        "immobilienpreis",
        "wohnimmobilienpreisindex",
        "property price",
        "wohnimmobilien",
    ],
    "financial_soundness": [
        "financial soundness",
        "soundness indicators",
        "fsi",
        "österreichische banken",
        "oesterreichische banken",
        "bankenstabilität",
        "bankenstabilitaet",
        "tier 1 capital",
        "report=3.24.15",
    ],
    "external_sector": [
        "dienstleistungsverkehr",
        "services trade",
        "external sector",
        "außenwirtschaft",
        "report=9.",
        "target2",
        "target2-securities",
        "zahlungsbilanz",
        "direktinvestition",
    ],
    "reserves_assets": [
        "gold reserve",
        "gold reserves",
        "goldreserven",
        "reserve assets",
        "währungsreserven",
    ],
    "financial_education": [
        "taschengeld",
        "financial education",
        "finanzbildung",
        "kinder",
        "jugendliche",
        "budget",
        "sparen",
    ],
    "corporate_topics": [
        "kunstsammlung",
        "art collection",
        "frauen in führungsfunktionen",
        "führungsfunktionen",
        "gleichstellung",
        "diversität",
        "oenb about us",
    ],
}


def classify_record_domains(record: dict) -> list[str]:
    primary_reference = ""
    reference_urls = record.get("reference_urls") or []
    if reference_urls:
        primary_reference = str(reference_urls[0])

    haystack = " ".join(
        str(part)
        for part in (
            record.get("title"),
            record.get("text"),
            primary_reference,
            record.get("parent_id"),
            record.get("id"),
        )
        if part
    ).lower()

    matched = []
    for domain, hints in DOMAIN_HINTS.items():
        if any(hint in haystack for hint in hints):
            matched.append(domain)
    return matched or ["website_general"]


def filter_records_for_route(records: list[dict], route: dict | None) -> list[dict]:
    if not route:
        return records
    allowed_domains = [domain for domain in route.get("domains", []) if domain != "website_general"]
    if not allowed_domains:
        return records

    filtered = [
        record
        for record in records
        if set(classify_record_domains(record)).intersection(allowed_domains)
    ]
    return filtered
