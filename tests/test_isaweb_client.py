import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.isaweb_client import IsawebClient


def test_client_fetch_positions_parses_content_response():
    """Client fetches content?hierid=X and returns parsed positions."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <groups>
        <group name="alle Daten">
          <position id="VDBESEFAZSPIFAGAB">
            <text lang="DE">Einlagefazilität</text>
          </position>
        </group>
      </groups>
    </content>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = xml.encode("utf-8")

    client = IsawebClient(rate_limit=0)
    with patch.object(client._session, "get", return_value=mock_response) as mock_get:
        positions = client.fetch_positions(hierid=22, lang="DE")

    mock_get.assert_called_once()
    assert "hierid=22" in mock_get.call_args[0][0]
    assert len(positions) == 1
    assert positions[0]["id"] == "VDBESEFAZSPIFAGAB"


def test_client_fetch_positions_returns_empty_on_http_error():
    """Client returns empty list on HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status = MagicMock(side_effect=Exception("Server error"))

    client = IsawebClient(rate_limit=0)
    with patch.object(client._session, "get", return_value=mock_response):
        positions = client.fetch_positions(hierid=99, lang="DE")

    assert positions == []


def test_client_discover_leaf_hierids_from_tree():
    """Client fetches navigation tree, identifies leaf nodes."""
    tree_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <content>
        <element id="1" parent="0"><text lang="DE">OeNB</text></element>
        <element id="11" parent="1"><text lang="DE">Bilanzpositionen</text></element>
        <element id="13" parent="1"><text lang="DE">Geldmengenaggregate</text></element>
        <element id="2" parent="0"><text lang="DE">Zinssätze</text></element>
        <element id="22" parent="2"><text lang="DE">Geldmarktzinssätze</text></element>
      </content>
    </content>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = tree_xml.encode("utf-8")

    client = IsawebClient(rate_limit=0)
    with patch.object(client._session, "get", return_value=mock_response):
        leaves = client.fetch_hierarchy_tree(lang="DE")

    # Leaves: 11, 13, 22 (never appear as parent). 1 and 2 are parents → not leaves.
    assert sorted(leaves, key=lambda x: x["hierid"]) == [
        {"hierid": 11, "label": "Bilanzpositionen"},
        {"hierid": 13, "label": "Geldmengenaggregate"},
        {"hierid": 22, "label": "Geldmarktzinssätze"},
    ]


def test_client_fetch_and_store_position(tmp_path):
    """Client fetches meta + data for a position and persists to DB."""
    from oenb_scraper.database import init_db

    meta_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <metainfo>
      <header><prepared>2026-03-24T10:00:00Z</prepared>
        <sender id="AT2"><name>OeNB</name></sender>
      </header>
      <meta>
        <title>Einlagefazilität</title>
        <region>-</region><unit>%</unit><comment>ECB rate</comment>
        <classification>-</classification><breaks>-</breaks>
        <frequency>Monate</frequency>
        <data_available><data>Jan. 99 - Feb. 26</data></data_available>
        <last_update>2026-03-01</last_update><source>OeNB</source><lag>-</lag>
        <releases></releases>
      </meta>
    </metainfo>
    """

    data_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <OeNBData>
      <data>
        <dataSet pos="VDBESEFAZSPIFAGAB" posTitle="Einlagefazilität" freq="M" unitMult="0" unitText="%">
          <values>
            <obs value="2.50" periode="2025-01"/>
            <obs value="2.75" periode="2025-02"/>
          </values>
        </dataSet>
      </data>
    </OeNBData>
    """

    def mock_get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "/meta?" in url:
            resp.content = meta_xml.encode("utf-8")
        else:
            resp.content = data_xml.encode("utf-8")
        return resp

    conn = init_db(tmp_path / "crawler.db")
    client = IsawebClient(rate_limit=0)

    with patch.object(client._session, "get", side_effect=mock_get_side_effect):
        result = client.fetch_and_store_position(
            conn=conn, hierid=22, pos="VDBESEFAZSPIFAGAB", lang="DE"
        )

    assert result["meta_stored"] is True
    assert result["data_stored"] == 1

    # Verify DB
    meta_row = conn.execute("SELECT title FROM isaweb_metadata WHERE pos = 'VDBESEFAZSPIFAGAB'").fetchone()
    obs_count = conn.execute("SELECT COUNT(*) AS c FROM isaweb_observations").fetchone()["c"]
    assert meta_row["title"] == "Einlagefazilität"
    assert obs_count == 2


def test_client_fetch_all_discovers_and_fetches_positions(tmp_path):
    """Full orchestration: tree → leaf positions → meta+data → DB."""
    from oenb_scraper.database import init_db

    tree_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <content>
        <element id="2" parent="0"><text lang="DE">Zinssätze</text></element>
        <element id="22" parent="2"><text lang="DE">Geldmarktzinssätze</text></element>
      </content>
    </content>
    """

    positions_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <content>
      <header><prepared>2026-03-24T22:00:00Z</prepared></header>
      <groups>
        <group name="alle Daten">
          <position id="POS1"><text lang="DE">Position 1</text></position>
        </group>
      </groups>
    </content>
    """

    meta_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <metainfo>
      <header><prepared>2026-03-24T10:00:00Z</prepared>
        <sender id="AT2"><name>OeNB</name></sender>
      </header>
      <meta>
        <title>Position 1</title><region>-</region><unit>%</unit>
        <comment>-</comment><classification>-</classification>
        <breaks>-</breaks><frequency>Monate</frequency>
        <data_available></data_available>
        <last_update>2026-03-01</last_update><source>OeNB</source><lag>-</lag>
        <releases></releases>
      </meta>
    </metainfo>
    """

    data_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <OeNBData>
      <data>
        <dataSet pos="POS1" posTitle="Position 1" freq="M" unitMult="0" unitText="%">
          <values><obs value="1.0" periode="2025-01"/></values>
        </dataSet>
      </data>
    </OeNBData>
    """

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "/content?" in url and "report=" in url:
            resp.content = tree_xml.encode()
        elif "/content?" in url:
            resp.content = positions_xml.encode()
        elif "/meta?" in url:
            resp.content = meta_xml.encode()
        else:
            resp.content = data_xml.encode()
        return resp

    conn = init_db(tmp_path / "crawler.db")
    client = IsawebClient(rate_limit=0)

    with patch.object(client._session, "get", side_effect=mock_get):
        report = client.fetch_all(conn=conn, lang="DE")

    assert report["hierarchies_discovered"] >= 1
    assert report["positions_discovered"] >= 1
    assert report["positions_fetched"] >= 1

    dataset_count = conn.execute("SELECT COUNT(*) AS c FROM isaweb_datasets").fetchone()["c"]
    assert dataset_count >= 1
