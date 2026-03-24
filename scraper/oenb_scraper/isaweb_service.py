from __future__ import annotations

from dataclasses import dataclass, field
import re
from urllib.parse import parse_qs, urlencode, urlparse
from xml.etree import ElementTree as ET


BASE_URL = "https://www.oenb.at/isadataservice"


@dataclass(frozen=True)
class IsawebDatasetRequest:
    hierid: int
    lang: str
    pos: list[str]
    dimensions: dict[str, list[str]] = field(default_factory=dict)
    freq: str | None = None
    starttime: str | None = None
    endtime: str | None = None

    @property
    def content_url(self) -> str:
        return build_content_url(hierid=self.hierid, lang=self.lang)

    @property
    def meta_url(self) -> str:
        return build_meta_url(hierid=self.hierid, lang=self.lang, pos=self.pos)

    @property
    def datafrequency_url(self) -> str:
        return build_datafrequency_url(hierid=self.hierid, lang=self.lang, pos=self.pos)

    @property
    def data_url(self) -> str:
        return build_data_url(
            hierid=self.hierid,
            lang=self.lang,
            pos=self.pos,
            dimensions=self.dimensions,
            starttime=self.starttime,
            endtime=self.endtime,
            freq=self.freq,
        )


@dataclass(frozen=True)
class IsawebHierarchyReference:
    hierid: int
    lang: str

    @property
    def content_url(self) -> str:
        return build_content_url(hierid=self.hierid, lang=self.lang)


def build_content_url(*, hierid: int, lang: str, mode: str | None = None) -> str:
    return _build_url("content", {"hierid": hierid, "lang": lang, "mode": mode})


def build_meta_url(*, hierid: int, lang: str, mode: str | None = None, pos: list[str] | None = None) -> str:
    params: dict[str, object] = {"hierid": hierid, "lang": lang, "mode": mode}
    if pos:
        params["pos"] = pos
    return _build_url("meta", params)


def build_datafrequency_url(*, hierid: int, lang: str, pos: list[str] | None = None) -> str:
    params: dict[str, object] = {"hierid": hierid, "lang": lang}
    if pos:
        params["pos"] = pos
    return _build_url("datafrequency", params)


def build_data_url(
    *,
    hierid: int,
    lang: str,
    pos: list[str],
    dimensions: dict[str, list[str]] | None = None,
    starttime: str | None = None,
    endtime: str | None = None,
    freq: str | None = None,
) -> str:
    params: dict[str, object] = {"hierid": hierid, "lang": lang, "pos": pos}
    if dimensions:
        for key in sorted(dimensions):
            params[key] = dimensions[key]
    if starttime:
        params["starttime"] = starttime
    if endtime:
        params["endtime"] = endtime
    if freq:
        params["freq"] = freq
    return _build_url("data", params)


def _build_url(endpoint: str, params: dict[str, object]) -> str:
    filtered: list[tuple[str, str]] = []
    for key in sorted(params):
        value = params[key]
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                filtered.append((key, str(item)))
        else:
            filtered.append((key, str(value)))

    return f"{BASE_URL}/{endpoint}?{urlencode(filtered, doseq=True)}"


def extract_dataset_request(url: str, fallback_lang: str | None = None) -> IsawebDatasetRequest | None:
    """Extract a canonical ISAweb dataset request from a result or service URL."""

    parsed = urlparse(url)
    path = parsed.path.lower()
    if not any(segment in path for segment in ("/isawebstat/", "/dynabfrage/", "/isadataservice/")):
        return None

    query = parse_qs(parsed.query, keep_blank_values=False)
    hierid_values = query.get("hierid") or query.get("hierarchieId") or query.get("hierarchieid")
    pos_values = _normalized_values(query.get("pos", []))

    if not hierid_values or not pos_values:
        return None

    try:
        hierid = int(hierid_values[0])
    except ValueError:
        return None

    lang = (query.get("lang", [fallback_lang or "DE"])[0] or fallback_lang or "DE").upper()
    dimensions = {}
    for key, values in query.items():
        normalized_key = key.lower()
        normalized_values = _normalized_values(values)
        if normalized_key.startswith("dval") and normalized_values:
            dimensions[normalized_key] = normalized_values

    return IsawebDatasetRequest(
        hierid=hierid,
        lang=lang,
        pos=pos_values,
        dimensions=dimensions,
        freq=_first_value(query.get("freq")),
        starttime=_first_value(query.get("starttime")),
        endtime=_first_value(query.get("endtime")),
    )


def extract_hierarchy_reference(url: str, fallback_lang: str | None = None) -> IsawebHierarchyReference | None:
    """Extract an ISAweb hierarchy reference from service, result, report or chart URLs."""

    parsed = urlparse(url)
    path = parsed.path.lower()
    if not any(segment in path for segment in ("/isawebstat/", "/dynabfrage/", "/isadataservice/")):
        return None

    query = parse_qs(parsed.query, keep_blank_values=False)
    lang = (query.get("lang", [fallback_lang or "DE"])[0] or fallback_lang or "DE").upper()

    hierid_values = (
        query.get("hierid")
        or query.get("hierarchieId")
        or query.get("hierarchieid")
        or query.get("hierarchy")
    )
    if hierid_values:
        try:
            return IsawebHierarchyReference(hierid=int(hierid_values[0]), lang=lang)
        except ValueError:
            pass

    report_id = _first_value(query.get("report"))
    if report_id:
        hierid = _infer_hierid_from_report_id(report_id)
        if hierid is not None:
            return IsawebHierarchyReference(hierid=hierid, lang=lang)

    chart_id = _first_value(query.get("chart")) or _first_value(query.get("chartOld"))
    if chart_id:
        hierid = _infer_hierid_from_chart_id(chart_id)
        if hierid is not None:
            return IsawebHierarchyReference(hierid=hierid, lang=lang)

    return None


def _first_value(values: list[str] | None) -> str | None:
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _normalized_values(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


def _infer_hierid_from_report_id(report_id: str) -> int | None:
    parts = [part for part in report_id.split(".") if part]
    if len(parts) < 2 or not all(part.isdigit() for part in parts):
        return None
    try:
        return int("".join(parts[:-1]))
    except ValueError:
        return None


def _infer_hierid_from_chart_id(chart_id: str) -> int | None:
    parts = [part for part in chart_id.split(".") if part]
    if len(parts) < 3 or not all(part.isdigit() for part in parts):
        return None
    return _infer_hierid_from_report_id(".".join(parts[:-1]))


def parse_data_response(xml_text: str | bytes) -> list[dict]:
    """Parse an OeNB ISAweb XML data response into canonical series payloads."""

    if isinstance(xml_text, bytes):
        xml_text = xml_text.decode("utf-8", errors="replace")

    root = ET.fromstring(xml_text)
    series_payloads: list[dict] = []

    for data_set in root.findall(".//dataSet"):
        attrs = data_set.attrib
        unit = attrs.get("unitText")
        title = attrs.get("posTitle")
        dimensions: dict[str, list[str]] = {}
        dimension_labels: dict[str, str] = {}

        for key, value in attrs.items():
            match = re.fullmatch(r"attr(\d+)", key)
            if match and value:
                dimensions[f"dval{match.group(1)}"] = [value]
                continue

            match = re.fullmatch(r"attr(\d+)Dim", key)
            if match and value:
                dimension_labels[f"dval{match.group(1)}"] = value

        observations: list[dict] = []
        for obs in data_set.findall("./values/obs"):
            period = obs.attrib.get("periode") or obs.attrib.get("period")
            if not period:
                continue
            observations.append(
                {
                    "period": period,
                    "value": obs.attrib.get("value"),
                    "unit": unit,
                    "series_label": title,
                }
            )

        series_payloads.append(
            {
                "pos": attrs.get("pos"),
                "title": title,
                "freq": attrs.get("freq"),
                "unit": unit,
                "unit_multiplier": attrs.get("unitMult"),
                "dimensions": dimensions,
                "dimension_labels": dimension_labels,
                "observations": observations,
            }
        )

    return [series for series in series_payloads if series.get("pos")]


def parse_meta_response(xml_text: str | bytes) -> dict:
    """Parse an OeNB ISAweb XML metadata response."""

    if isinstance(xml_text, bytes):
        xml_text = xml_text.decode("utf-8", errors="replace")

    root = ET.fromstring(xml_text)
    header = root.find("./header")
    meta = root.find("./meta")

    sender = header.find("./sender") if header is not None else None
    releases = []
    if meta is not None:
        for release in meta.findall("./releases/release"):
            releases.append(
                {
                    "release_date": _normalized_text(release.findtext("./release_date")),
                    "reference": _normalized_text(release.findtext("./reference")) or "",
                    "revision": _normalized_text(release.findtext("./revision")) or "",
                }
            )

    return {
        "prepared_at": _normalized_text(header.findtext("./prepared")) if header is not None else None,
        "header_last_update": _normalized_text(header.findtext("./last_update")) if header is not None else None,
        "sender": {
            "id": sender.get("id") if sender is not None else None,
            "name": _normalized_text(sender.findtext("./name")) if sender is not None else None,
        },
        "title": _normalized_text(meta.findtext("./title")) if meta is not None else None,
        "region": _normalized_text(meta.findtext("./region")) if meta is not None else None,
        "unit": _normalized_text(meta.findtext("./unit")) if meta is not None else None,
        "comment": _normalized_text(meta.findtext("./comment")) if meta is not None else None,
        "classification": _normalized_text(meta.findtext("./classification")) if meta is not None else None,
        "breaks": _normalized_text(meta.findtext("./breaks")) if meta is not None else None,
        "frequency": _normalized_text(meta.findtext("./frequency")) if meta is not None else None,
        "data_available": [
            _normalized_text(item.text)
            for item in (meta.findall("./data_available/data") if meta is not None else [])
            if _normalized_text(item.text)
        ],
        "last_update": _normalized_text(meta.findtext("./last_update")) if meta is not None else None,
        "source": _normalized_text(meta.findtext("./source")) if meta is not None else None,
        "lag": _normalized_text(meta.findtext("./lag")) if meta is not None else None,
        "releases": releases,
    }


def parse_content_positions(xml_text: str | bytes) -> dict:
    """Parse an ISAweb content response into a list of available positions.

    The content endpoint returns positions when called with a leaf hierid:
    /isadataservice/content?hierid=LEAF_ID&lang=DE
    """
    if isinstance(xml_text, bytes):
        xml_text = xml_text.decode("utf-8", errors="replace")

    root = ET.fromstring(xml_text)
    positions: list[dict] = []

    for group in root.findall(".//group"):
        group_name = group.get("name")
        for position in group.findall("./position"):
            pos_id = position.get("id")
            text = _normalized_text(position.findtext("./text"))
            if pos_id and text:
                positions.append({"id": pos_id, "text": text, "group": group_name})

    return {
        "prepared_at": _normalized_text(root.findtext("./header/prepared")),
        "positions": positions,
    }


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None
