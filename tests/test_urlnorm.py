import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.urlnorm import normalize_url


def test_normalize_url_removes_session_and_fragment():
    url = "https://www.oenb.at/isawebstat/dynabfrage/defineParams;jsessionid=ABC?hierarchieId=11&lang=DE#foo"
    assert normalize_url(url) == "https://www.oenb.at/isawebstat/dynabfrage/defineParams?hierarchieId=11&lang=DE"


def test_normalize_url_drops_session_query_params_and_sorts():
    url = "https://www.oenb.at/isawebstat/dynabfrage/showResult?lang=EN&sid=99&hierid=11&pos=A&pos=B"
    assert normalize_url(url) == "https://www.oenb.at/isawebstat/dynabfrage/showResult?hierid=11&lang=EN&pos=A&pos=B"
