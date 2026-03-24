import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.isaweb_service import extract_dataset_request


def test_extract_dataset_request_from_show_result_url():
    request = extract_dataset_request(
        (
            "https://www.oenb.at/isawebstat/dynabfrage/showResult"
            "?lang=EN&hierarchieId=11&pos=VDBFKBSC217000&pos=VDBFKBSC218000"
            "&dval2=00100KI&dval1=AT&freq=M&starttime=2020-01-01"
        )
    )

    assert request is not None
    assert request.hierid == 11
    assert request.lang == "EN"
    assert request.pos == ["VDBFKBSC217000", "VDBFKBSC218000"]
    assert request.dimensions == {"dval1": ["AT"], "dval2": ["00100KI"]}
    assert request.freq == "M"
    assert request.starttime == "2020-01-01"
    assert request.data_url.endswith(
        "data?dval1=AT&dval2=00100KI&freq=M&hierid=11&lang=EN"
        "&pos=VDBFKBSC217000&pos=VDBFKBSC218000&starttime=2020-01-01"
    )
