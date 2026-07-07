"""CML Job: ISAweb-Statistikdaten per REST-API laden.

Zieht alle ISAweb-Hierarchien, Datasets, Observations und Metadaten
über den Webservice (kein Scrapy, nur requests) und speichert sie in
data/statistics_production/pages.db. Danach kann cml_eval.py die
Statistik-KB exportieren.

Verwendung:
  - Als CML Job: Jobs > New Job > Script: cml_isaweb.py > Starten
  - Im Terminal:  python cml_isaweb.py
  - Resource Profile: 1 vCPU, 2 GB RAM reicht
  - Laufzeit: ~50-90 min (Rate-Limit 0.5s zwischen Requests)

Der Lauf ist idempotent: bestehende Datasets werden aktualisiert.
Referenzlauf lokal (2026-03-25): 29 Hierarchien, 2.856 Positionen,
73.425 Datasets, 3,2 Mio. Observations, 0 Fehler.
"""

import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "scraper"))

DB_PATH = BASE_DIR / "data" / "statistics_production" / "pages.db"


def main() -> int:
    from oenb_scraper.database import init_db
    from oenb_scraper.isaweb_client import IsawebClient

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(DB_PATH)
    try:
        client = IsawebClient(rate_limit=0.5)
        total_errors = 0
        for lang in ("DE", "EN"):
            print(f"=== ISAweb fetch_all lang={lang} ===")
            report = client.fetch_all(conn=conn, lang=lang)
            print(f"  Hierarchien: {report['hierarchies_discovered']}")
            print(f"  Positionen:  {report['positions_discovered']}")
            print(f"  Gefetcht:    {report['positions_fetched']}")
            print(f"  Fehler:      {report['errors']}")
            total_errors += int(report["errors"] or 0)
    finally:
        conn.close()

    print(f"Fertig. DB: {DB_PATH}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
