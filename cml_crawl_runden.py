# -*- coding: utf-8 -*-
"""
CML Job: OeNB Crawler in Runden (mit DB-Dupefilter).

Dieses Script crawlt die OeNB-Website in Runden und verwendet einen
DB-basierten Dupefilter, damit jede Runde nur NEUE Seiten herunterlädt.

Ohne Dupefilter: Jede Runde besucht dieselben ~500 Seiten von den Seed-URLs.
Mit Dupefilter:   Jede Runde überspringt bekannte URLs → erreicht neue Seiten.

Verwendung:
  - Als CML Job: Jobs > New Job > Script: cml_crawl_runden.py
  - Im Terminal:  python cml_crawl_runden.py
"""
import os
import sqlite3
import subprocess
import sys
import time

DB_PATH = "data/pages.db"
ROUNDS = 30
PAGES_PER_ROUND = 1000
PAUSE_SECONDS = 120  # 2 Minuten Pause zwischen Runden


def setup_dupefilter():
    """Schreibt den DB-Dupefilter als Python-Modul (immer neu, damit aktuell)."""
    dupefilter_path = "scraper/oenb_scraper/dupefilter.py"
    os.makedirs(os.path.dirname(dupefilter_path), exist_ok=True)

    code = '''\
"""DB-backed dupefilter: skips URLs already stored in pages.db (normalized)."""
import logging
import sqlite3
import inspect
from urllib.parse import urldefrag, urlparse, parse_qs, urlencode
from scrapy.dupefilters import RFPDupeFilter

logger = logging.getLogger(__name__)

def normalize_url(url: str) -> str:
    # Remove fragments
    url = urldefrag(url)[0]
    parsed = urlparse(url)

    # Strip jsessionid tokens from path
    path = parsed.path
    for token in (";jsessionid=", ";JSESSIONID="):
        if token in path:
            path = path.split(token)[0]

    # Drop common session-like query params
    session_params = {"jsessionid", "JSESSIONID", "PHPSESSID", "sid", "session_id"}

    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in query_params.items() if k not in session_params}

    # Stable sorting: sort keys AND values
    flat_items = []
    for k in sorted(filtered.keys()):
        for v in sorted(filtered[k]):
            flat_items.append((k, v))
    sorted_query = urlencode(flat_items, doseq=True)

    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if sorted_query:
        normalized += f"?{sorted_query}"
    return normalized


class DbDupeFilter(RFPDupeFilter):
    """Dupefilter that checks SQLite DB for already-crawled URLs.

    - Loads URLs from the 'pages' table into a normalized in-memory set.
    - Also adds normalized URLs as soon as they are seen in the current run,
      to avoid duplicates within the same crawl session.
    - Works across Scrapy versions by only passing 'fingerprinter' if the base
      class actually supports it.
    """

    def __init__(self, path=None, debug=False, *, db_path=None, **kwargs):
        super().__init__(path=path, debug=debug, **kwargs)
        self.db_urls = set()
        self.db_path = db_path
        self.db_skipped = 0

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        jobdir = settings.get("JOBDIR")
        debug = settings.getbool("DUPEFILTER_DEBUG")
        db_path = settings.get("SQLITE_DB_PATH")

        kwargs = {}

        # Prefer public API if available
        fp = getattr(crawler, "request_fingerprinter", None)

        # Fallback (private API) only if needed
        if fp is None:
            maybe = getattr(crawler, "_get_fingerprinter", None)
            if callable(maybe):
                try:
                    fp = maybe()
                except Exception:
                    fp = None

        # Only pass fingerprinter if base __init__ supports it
        try:
            params = inspect.signature(RFPDupeFilter.__init__).parameters
            if fp is not None and "fingerprinter" in params:
                kwargs["fingerprinter"] = fp
        except Exception:
            # If inspection fails, do not pass it (safer)
            pass

        return cls(
            path=jobdir if jobdir else None,
            debug=debug,
            db_path=db_path,
            **kwargs,
        )

    def open(self, *args, **kwargs):
        super().open(*args, **kwargs)
        if self.db_path:
            try:
                conn = sqlite3.connect(self.db_path)
                rows = conn.execute("SELECT url FROM pages").fetchall()
                conn.close()

                self.db_urls = {normalize_url(row[0]) for row in rows if row and row[0]}
                logger.info(
                    "DbDupeFilter: %s URLs aus DB geladen (normalisiert)",
                    f"{len(self.db_urls):,}".replace(",", "_"),
                )
            except Exception as e:
                logger.warning("DbDupeFilter: DB nicht geladen (%s)", e)

    def request_seen(self, request):
        normalized = normalize_url(request.url)

        # Skip if already in DB / already seen in this run
        if normalized in self.db_urls:
            self.db_skipped += 1
            return True

        seen = super().request_seen(request)

        # Mark as seen in this run using our normalized form
        if not seen:
            self.db_urls.add(normalized)

        return seen

    def close(self, reason, *args, **kwargs):
        logger.info(
            "DbDupeFilter: %s bereits gespeicherte URLs uebersprungen",
            f"{self.db_skipped:,}",
        )
        return super().close(reason, *args, **kwargs)
'''

    with open(dupefilter_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"Dupefilter aktualisiert: {dupefilter_path}")


def get_page_count():
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


# === Setup ===
print("=== OeNB Crawler (Runden mit DB-Dupefilter) ===\n")
os.makedirs("data", exist_ok=True)

# Dependencies
try:
    import scrapy  # noqa: F401
    print("Scrapy OK")
except ImportError:
    print("Installiere dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

# Dupefilter-Modul schreiben
setup_dupefilter()

pages_start = get_page_count()
print(f"Seiten in DB vor Start: {pages_start:,}\n")

# === Runden-Crawl ===
for i in range(1, ROUNDS + 1):
    pages_before = get_page_count()
    print(f"{'='*60}")
    print(f"=== Runde {i}/{ROUNDS} (Seiten: {pages_before:,}) ===")
    print(f"{'='*60}")

    result = subprocess.run(
        [
            sys.executable, "-m", "scrapy", "crawl", "oenb",
            "-s", 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}',
            "-s", f"SQLITE_DB_PATH=../{DB_PATH}",
            "-s", "DOWNLOAD_TIMEOUT=15",
            "-s", "CONCURRENT_REQUESTS=1",
            "-s", f"CLOSESPIDER_PAGECOUNT={PAGES_PER_ROUND}",
            "-s", "DUPEFILTER_CLASS=oenb_scraper.dupefilter.DbDupeFilter",
        ],
        cwd="scraper",
        check=False,
    )

    # Wenn Scrapy mit Fehler endet, bringt "weitere Runden" praktisch nichts
    if result.returncode != 0:
        print(f"\nScrapy beendet mit Returncode {result.returncode} – Crawl wird abgebrochen.")
        break

    pages_after = get_page_count()
    new_pages = pages_after - pages_before
    print(f"\nRunde {i}: {new_pages:,} neue Seiten (gesamt: {pages_after:,})")

    # Abbruch wenn keine neuen Seiten mehr
    if new_pages == 0 and i > 1:
        print("Keine neuen Seiten mehr gefunden - Crawl abgeschlossen!")
        break

    if i < ROUNDS:
        print(f"Pause {PAUSE_SECONDS}s...\n")
        time.sleep(PAUSE_SECONDS)

# === Text extrahieren ===
pages_total = get_page_count()
print(f"\n{'='*60}")
print(f"=== Text extrahieren ({pages_total:,} Seiten) ===")
print(f"{'='*60}")
subprocess.run([sys.executable, "analysis/extract_text.py", DB_PATH], check=True)

# === Ergebnis ===
conn = sqlite3.connect(DB_PATH)
pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
try:
    content = conn.execute("SELECT COUNT(*) FROM page_content").fetchone()[0]
except Exception:
    content = 0
conn.close()

print(f"\n{'='*60}")
print("=== ERGEBNIS ===")
print(f"Seiten:  {pages:,}")
print(f"Texte:   {content:,}")
print(f"Neue:    {pages - pages_start:,} (in dieser Session)")

if pages > 5000:
    print(f"\nOK - Crawl erfolgreich ({pages:,} Seiten).")
elif pages > 0:
    print(f"\nTeilweise gecrawlt ({pages:,} Seiten). Nochmal starten fuer mehr.")
else:
    print("\nFEHLER: Keine Seiten gecrawlt!")

