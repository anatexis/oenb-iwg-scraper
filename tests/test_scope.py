import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))

from oenb_scraper.scope import CrawlScope


def test_oenb_owned_subdomain_is_primary_scope():
    scope = CrawlScope(primary_hosts={"oenb.at", "www.oenb.at", "finanzbildung.oenb.at", "shiny.oenb.at"})

    assert scope.classify_host("www.oenb.at") == "primary"
    assert scope.classify_host("shiny.oenb.at") == "primary"


def test_shinyapps_host_is_secondary_scope():
    scope = CrawlScope(primary_hosts={"oenb.at"}, secondary_host_suffixes={"shinyapps.io"})

    assert scope.classify_host("myapp.shinyapps.io") == "secondary"
    assert scope.classify_host("google.com") == "out_of_scope"
