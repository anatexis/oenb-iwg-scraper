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
