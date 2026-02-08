# Schnellstart: Crawler + Demo auf neuem Rechner

Anleitung um den Crawler auf einem Arbeitsrechner laufen zu lassen und
die Demo-Notebooks zu starten. Dauert ca. **1-2 Stunden** (statt 12h
fuer einen Voll-Crawl).

## Voraussetzungen

- Python 3.10+
- Git
- Ollama mit `llama3.1:8b` (fuer Agentic Search)

## 1. Projekt klonen und einrichten

```bash
git clone <repo-url> oenb-crawler
cd oenb-crawler

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

mkdir -p data
```

## 2. Selektiv crawlen (nur Demo-relevante Sections)

Statt die gesamte Website zu crawlen (~12h), nur die Sections die
fuer die Demo gebraucht werden. Dauert ca. 1-2h.

```bash
source venv/bin/activate
cd scraper

# --- Schritt 1: isawebstat (Chart-Daten, Leitzins etc.) ---
echo "=== isawebstat crawlen ==="
scrapy crawl oenb -a section=isawebstat \
  -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}' \
  -s "SQLITE_DB_PATH=../data/pages.db"

# --- Schritt 2: Wichtige inhaltliche Sections ---
for SECTION in Statistik Presse Geldpolitik Publikationen FAQ; do
  echo "=== $SECTION crawlen ==="
  scrapy crawl oenb -a section=$SECTION \
    -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}' \
    -s "SQLITE_DB_PATH=../data/pages.db"
done

cd ..
```

Oder alles in einem Befehl (laeuft im Hintergrund):

```bash
source venv/bin/activate && cd scraper && \
for S in isawebstat Statistik Presse Geldpolitik Publikationen FAQ; do \
  echo "=== $S ===" && \
  scrapy crawl oenb -a section=$S \
    -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}' \
    -s "SQLITE_DB_PATH=../data/pages.db" 2>&1 | tail -1; \
done && cd ..
```

### Zwischenstand pruefen

```bash
source venv/bin/activate
python3 -c "
import sqlite3
conn = sqlite3.connect('data/pages.db')
print(f'Seiten: {conn.execute(\"SELECT COUNT(*) FROM pages\").fetchone()[0]:,}')
"
```

## 3. Text extrahieren

```bash
source venv/bin/activate
python analysis/extract_text.py data/pages.db
```

## 4. Pruefen ob alles da ist

```bash
source venv/bin/activate
python3 -c "
import sqlite3
conn = sqlite3.connect('data/pages.db')
pages = conn.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
content = conn.execute('SELECT COUNT(*) FROM page_content').fetchone()[0]
charts = conn.execute(\"\"\"
    SELECT COUNT(*) FROM page_content
    WHERE title LIKE 'DATA Chart%' AND text_content LIKE '%, 2024:%'
\"\"\").fetchone()[0]
print(f'Seiten:      {pages:,}')
print(f'Mit Text:    {content:,}')
print(f'Charts:      {charts:,}')
if charts > 0:
    print('OK - Chart-Daten vorhanden')
else:
    print('WARNUNG: Keine Chart-Daten gefunden!')
"
```

Erwartete Werte (ungefaehr):
- Seiten: 3.000 - 5.000 (nur ausgewaehlte Sections)
- Charts: 400+
- Text: sollte gleich viele wie Seiten sein

## 5. Ollama starten

```bash
# In einem separaten Terminal:
ollama serve

# Modell vorladen (einmalig):
ollama pull llama3.1:8b

# Aufwaermen (damit die Demo schneller geht):
ollama run llama3.1:8b "Test" --verbose
```

## 6. Notebook starten

```bash
source venv/bin/activate
cd analysis
jupyter notebook crawler_demo.ipynb
```

Kernel starten, alle Zellen durchlaufen lassen. Die Agentic-Search-Zellen
(Abschnitt 5) einmal vorher ausfuehren damit Ollama warm ist.

## Troubleshooting

### "Keine Chart-Daten gefunden"
Der isawebstat-Crawl hat nicht geklappt. Nochmal nur isawebstat crawlen:
```bash
cd scraper && scrapy crawl oenb -a section=isawebstat \
  -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}' \
  -s "SQLITE_DB_PATH=../data/pages.db" && cd ..
python analysis/extract_text.py data/pages.db
```

### Ollama antwortet nicht
```bash
# Laeuft Ollama?
curl http://localhost:11434/api/tags

# Falls nicht:
ollama serve
```

### LLM halluziniert falsche Zahlen
Das ist bekannt mit dem 8B-Modell. Die Daten im Kontext sind korrekt
(z.B. Euroraum 2025: 2.15 = echter EZB-Hauptrefinanzierungssatz),
aber das kleine Modell liest sie nicht zuverlaessig ab.
-> Diskussionspunkt: groesseres Modell auf CML.

### chart_synonyms.json
ACHTUNG: Diese Datei wird NICHT automatisch erstellt. Sie muss im
`analysis/` Ordner liegen. Falls sie fehlt, aus dem Git kopieren.
Nach einem Re-Crawl mit neuen Charts ggf. manuell ergaenzen.

## Alternativ: Voll-Crawl (12h)

Falls du die gesamte Website brauchst:

```bash
./run.sh --rag
# Dann:
python analysis/extract_text.py data/pages.db
```
