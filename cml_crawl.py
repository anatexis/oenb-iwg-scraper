"""CML Job: OeNB Crawler (Voll-Crawl) + Text-Extraktion.

Dieses Script ist fuer Cloudera CML gedacht (kein venv noetig).
Es crawlt die gesamte OeNB-Website und extrahiert den Text.

Verwendung:
  - Als CML Job: Jobs > New Job > Script: cml_crawl.py > Starten
  - Im Terminal:  python cml_crawl.py
  - Resource Profile: 2 vCPU, 4 GB RAM reicht
  - Laufzeit: ca. 10-12 Stunden (Voll-Crawl)

Der Crawl ist inkrementell - bricht er ab, einfach nochmal starten.
Bereits gecrawlte Seiten werden uebersprungen.
"""
import subprocess
import sys
import os
import sqlite3
import threading
import time

DB_PATH = "data/pages.db"
EXPECTED_PAGES = 10_000  # Ungefaehr so viele Seiten hat die OeNB-Website


def progress_monitor(stop_event):
    """Hintergrund-Thread: zeigt alle 30s den Fortschritt an."""
    start_time = time.time()
    while not stop_event.is_set():
        stop_event.wait(30)
        if stop_event.is_set():
            break
        try:
            conn = sqlite3.connect(DB_PATH)
            pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            conn.close()
        except Exception:
            continue

        elapsed = time.time() - start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        pct = min(pages / EXPECTED_PAGES, 1.0)
        bar_len = 30
        filled = int(bar_len * pct)
        bar = "#" * filled + "-" * (bar_len - filled)

        # Geschaetzte Restzeit
        if pages > 100 and pct < 1.0:
            rate = pages / elapsed  # Seiten pro Sekunde
            remaining = (EXPECTED_PAGES - pages) / rate
            eta_str = time.strftime("%H:%M:%S", time.gmtime(remaining))
            eta_info = f" | Rest: ~{eta_str}"
        else:
            eta_info = ""

        print(f"  [{bar}] {pages:,} / ~{EXPECTED_PAGES:,} ({pct:.0%}) | {elapsed_str}{eta_info}",
              flush=True)


# --- Schritt 1: Dependencies pruefen ---
print("=== Dependencies pruefen ===")
try:
    import scrapy
    print(f"Scrapy {scrapy.__version__} OK")
except ImportError:
    print("Scrapy nicht gefunden, installiere dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

os.makedirs("data", exist_ok=True)

# --- Schritt 2: Voll-Crawl mit Fortschrittsanzeige ---
print(f"\n{'='*60}")
print("=== Starte Voll-Crawl der OeNB-Website ===")
print(f"=== Erwartete Dauer: ~10-12 Stunden ===")
print(f"=== Inkrementell: bei Abbruch einfach nochmal starten ===")
print(f"{'='*60}\n")

# Fortschritts-Thread starten
stop_event = threading.Event()
monitor = threading.Thread(target=progress_monitor, args=(stop_event,), daemon=True)
monitor.start()

os.chdir("scraper")
result = subprocess.run([
    sys.executable, "-m", "scrapy", "crawl", "oenb",
    "-s", 'ITEM_PIPELINES={'
          '"oenb_scraper.pipelines.DeduplicationPipeline": 100, '
          '"oenb_scraper.pipelines.FileSizePipeline": 200, '
          '"oenb_scraper.pipelines.SQLitePipeline": 400}',
    "-s", "SQLITE_DB_PATH=../data/pages.db",
], check=False)
os.chdir("..")

# Fortschritts-Thread stoppen
stop_event.set()
monitor.join(timeout=5)

if result.returncode != 0:
    print(f"\nCrawler beendet mit returncode={result.returncode}")
    print("Das kann OK sein (z.B. bei Ctrl+C). Pruefe die Datenbank:")

# --- Schritt 3: Text extrahieren ---
print(f"\n{'='*60}")
print("=== Text extrahieren ===")
print(f"{'='*60}")
subprocess.run([sys.executable, "analysis/extract_text.py", DB_PATH], check=True)

# --- Schritt 4: Ergebnis ---
conn = sqlite3.connect(DB_PATH)
pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
content = conn.execute("SELECT COUNT(*) FROM page_content").fetchone()[0]
charts = conn.execute(
    "SELECT COUNT(*) FROM page_content "
    "WHERE title LIKE 'DATA Chart%' AND text_content LIKE '%, 2024:%'"
).fetchone()[0]
sections = conn.execute(
    "SELECT page_section, COUNT(*) FROM page_content "
    "GROUP BY page_section ORDER BY 2 DESC LIMIT 15"
).fetchall()
conn.close()

print(f"\n{'='*60}")
print(f"=== ERGEBNIS ===")
print(f"Seiten:  {pages:,}")
print(f"Texte:   {content:,}")
print(f"Charts:  {charts:,}")
print(f"\nTop Sections:")
for sec, count in sections:
    print(f"  {sec:30s} {count:>5,}")

if pages > 5000:
    print(f"\nOK - Voll-Crawl erfolgreich ({pages:,} Seiten).")
elif pages > 0:
    print(f"\nTeilweise gecrawlt ({pages:,} Seiten). Nochmal starten fuer mehr.")
else:
    print(f"\nFEHLER: Keine Seiten gecrawlt! Internet-Zugang pruefen.")
