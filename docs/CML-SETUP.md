# OeNB Crawler auf Cloudera CML

Schritt-fuer-Schritt-Anleitung um den OeNB Web Crawler und die
Agentic-Search-Demo auf Cloudera Machine Learning (CML) zu betreiben.

**Uebersicht der Phasen:**

| Phase | Was                          | Dauer       | Voraussetzung  |
|-------|------------------------------|-------------|----------------|
| 1     | CML-Projekt einrichten       | 15 min      | Git-Zugang     |
| 2     | Crawler laufen lassen        | 1-2h / 12h  | Internet (oenb.at) |
| 3     | Text extrahieren             | 5 min       | Phase 2        |
| 4     | Ergebnis pruefen             | 5 min       | Phase 3        |
| 5     | Jupyter Notebook starten     | sofort      | Phase 3        |
| 6     | LLM anbinden (Mistral)       | spaeter     | Phase 3 + API-Zugang |

---

## Phase 1: CML-Projekt einrichten

### 1a. Neues Projekt erstellen

**Option A: Von GitHub (empfohlen wenn Internet vorhanden)**

1. In CML: "New Project" > "Git"
2. Repository-URL eingeben
3. Name: `oenb-crawler`

**Option B: ZIP hochladen (falls kein Git-Zugang)**

1. Die Datei `oenb-crawler-src.zip` per CML-Upload hochladen
2. In einer Session entpacken:
   ```bash
   unzip oenb-crawler-src.zip -d .
   ```

### 1b. Python-Umgebung

CML-Sessions haben Python vorinstalliert. Dependencies installieren:

```bash
# In einer CML-Session (Terminal oder JupyterLab-Terminal):
pip install -r requirements.txt
```

**Falls Proxy noetig:**
```bash
# Erst testen ob pip funktioniert:
pip install scrapy

# Falls Timeout/Fehler - Proxy setzen:
export HTTP_PROXY=http://proxy.oenb.at:8080
export HTTPS_PROXY=http://proxy.oenb.at:8080
export NO_PROXY=localhost,127.0.0.1

# Dann nochmal:
pip install -r requirements.txt
```

> **Tipp:** Die Proxy-Adresse findest du mit `env | grep -i proxy` falls
> sie schon in der CML-Umgebung gesetzt ist. Oder frag den CML-Admin.

### 1c. Verzeichnisstruktur pruefen

```bash
ls -la
# Sollte zeigen:
#   analysis/          <- Notebooks, extract_text.py, chart_synonyms.json
#   scraper/           <- Scrapy-Projekt
#   data/              <- Wird erstellt, DB kommt hierhin
#   docs/              <- Dokumentation
#   requirements.txt
#   run.sh

mkdir -p data
```

### 1d. Internet-Zugang testen

```bash
# Kann CML oenb.at erreichen?
curl -s -o /dev/null -w "%{http_code}" https://www.oenb.at/
# Erwartung: 200

# Falls 000 oder Timeout:
curl -s -o /dev/null -w "%{http_code}" --proxy http://proxy.oenb.at:8080 https://www.oenb.at/
```

Falls ein Proxy noetig ist, muss Scrapy konfiguriert werden (siehe
Troubleshooting am Ende).

---

## Phase 2: Crawler laufen lassen

### Option A: Selektiver Crawl (1-2 Stunden, empfohlen fuer Demo)

Nur die Sections crawlen die fuer die Demo relevant sind:

```bash
cd scraper

# isawebstat (Chart-Daten: Leitzins, Kreditzins, Zahlungsbilanz etc.)
scrapy crawl oenb -a section=isawebstat \
  -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}' \
  -s "SQLITE_DB_PATH=../data/pages.db"

# Wichtige inhaltliche Sections
for SECTION in Statistik Presse Geldpolitik Publikationen FAQ; do
  echo "=== $SECTION ==="
  scrapy crawl oenb -a section=$SECTION \
    -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}' \
    -s "SQLITE_DB_PATH=../data/pages.db"
done

cd ..
```

**Wichtig:** Jeder `scrapy crawl`-Aufruf ist inkrementell. Falls ein
Crawl abbricht (z.B. wegen Session-Timeout), einfach nochmal starten -
bereits gecrawlte Seiten werden nicht erneut heruntergeladen.

### Option B: Voll-Crawl (~12 Stunden)

```bash
./run.sh --rag
```

Oder manuell:
```bash
cd scraper
scrapy crawl oenb \
  -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.DeduplicationPipeline": 100, "oenb_scraper.pipelines.FileSizePipeline": 200, "oenb_scraper.pipelines.SQLitePipeline": 400}' \
  -s "SQLITE_DB_PATH=../data/pages.db" \
  2>&1 | tee ../data/crawl.log
cd ..
```

### Zwischenstand pruefen (waehrend der Crawl laeuft)

In einem **zweiten Terminal** (oder neuer CML-Session):

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/pages.db')
pages = conn.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
print(f'Seiten bisher: {pages:,}')
"
```

### CML-spezifisch: Langen Crawl am Laufen halten

CML-Sessions haben oft ein **Idle-Timeout** (z.B. 1-2 Stunden ohne
Aktivitaet). Strategien:

1. **CML Job verwenden (beste Option fuer Voll-Crawl):**
   - In CML: "Jobs" > "New Job"
   - Script: `run.sh --rag` oder ein eigenes Script (siehe unten)
   - Resource Profile: 2 vCPU, 4 GB RAM reicht
   - Jobs laufen ohne Timeout im Hintergrund

2. **Session-Timeout erhoehen:**
   - Frag den CML-Admin ob das Timeout erhoeht werden kann
   - Oder halte die Session aktiv (ab und zu ein Befehl ausfuehren)

3. **nohup im Terminal:**
   ```bash
   nohup bash -c 'cd scraper && scrapy crawl oenb -a section=isawebstat \
     -s '"'"'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}'"'"' \
     -s "SQLITE_DB_PATH=../data/pages.db"' > ../data/crawl.log 2>&1 &
   echo "Crawler laeuft im Hintergrund. Log: data/crawl.log"
   ```

**CML Job Script** (falls du einen Job verwendest):

Erstelle eine Datei `cml_crawl.py` im Projektverzeichnis:
```python
"""CML Job: OeNB Crawler (selektiv)"""
import subprocess
import os

os.makedirs("data", exist_ok=True)
os.chdir("scraper")

sections = ["isawebstat", "Statistik", "Presse", "Geldpolitik", "Publikationen", "FAQ"]

for section in sections:
    print(f"\n=== Crawling: {section} ===")
    subprocess.run([
        "scrapy", "crawl", "oenb",
        "-a", f"section={section}",
        "-s", 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}',
        "-s", "SQLITE_DB_PATH=../data/pages.db",
    ], check=False)  # check=False: weitermachen auch wenn eine Section Fehler hat

os.chdir("..")

# Text extrahieren
print("\n=== Text extrahieren ===")
subprocess.run(["python", "analysis/extract_text.py", "data/pages.db"], check=True)

# Ergebnis anzeigen
import sqlite3
conn = sqlite3.connect("data/pages.db")
pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
content = conn.execute("SELECT COUNT(*) FROM page_content").fetchone()[0]
charts = conn.execute(
    "SELECT COUNT(*) FROM page_content WHERE title LIKE 'DATA Chart%' AND text_content LIKE '%, 2024:%'"
).fetchone()[0]
print(f"\n=== Ergebnis ===")
print(f"Seiten:  {pages:,}")
print(f"Texte:   {content:,}")
print(f"Charts:  {charts:,}")
```

In CML: "Jobs" > "New Job" > Script: `cml_crawl.py` > Starten.

---

## Phase 3: Text extrahieren

Falls du den Crawler manuell (nicht ueber `cml_crawl.py`) laufen lassen
hast, muss der Text noch extrahiert werden:

```bash
python analysis/extract_text.py data/pages.db
```

Das Skript:
- Entpackt die HTML-Bodies (gzip)
- Extrahiert sauberen Text mit BeautifulSoup
- Extrahiert Zeitreihen-Daten aus isawebstat-Charts (JavaScript `$scope.data`)
- Speichert alles in der `page_content`-Tabelle

Dauert ca. 2-5 Minuten fuer ~5.000 Seiten.

---

## Phase 4: Ergebnis pruefen

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/pages.db')
pages = conn.execute('SELECT COUNT(*) FROM pages').fetchone()[0]
content = conn.execute('SELECT COUNT(*) FROM page_content').fetchone()[0]
charts = conn.execute(\"\"\"
    SELECT COUNT(*) FROM page_content
    WHERE title LIKE 'DATA Chart%' AND text_content LIKE '%, 2024:%'
\"\"\").fetchone()[0]
sections = conn.execute('''
    SELECT page_section, COUNT(*) as c FROM page_content
    GROUP BY page_section ORDER BY c DESC LIMIT 10
''').fetchall()

print(f'=== Ergebnis ===')
print(f'Seiten:      {pages:,}')
print(f'Mit Text:    {content:,}')
print(f'Charts:      {charts:,}')
print()
print('Sections:')
for sec, count in sections:
    print(f'  {sec:30s} {count:>5,}')

if charts > 0:
    print('\nOK - Chart-Daten vorhanden')
else:
    print('\nWARNUNG: Keine Chart-Daten! isawebstat nochmal crawlen.')
"
```

**Erwartete Werte (selektiver Crawl):**
- Seiten: 3.000 - 5.000
- Charts mit Daten: 400+
- Text: gleich viele wie Seiten

**Erwartete Werte (Voll-Crawl):**
- Seiten: ~10.000
- Charts mit Daten: ~440
- Text: ~10.000

---

## Phase 5: Jupyter Notebook starten

### In einer CML JupyterLab-Session:

1. Navigiere zu `analysis/`
2. Oeffne `crawler_demo.ipynb`
3. Kernel starten, alle Zellen ausfuehren

Die Abschnitte 1-4 (Statistiken, Inhalte, Chart-Daten) funktionieren
**ohne LLM** - das ist schon eine gute Demo des Crawlers.

Abschnitt 5 (Agentic Search) braucht ein LLM - siehe Phase 6.

### Ohne LLM erstmal testen

Du kannst die Such-Funktion ohne LLM testen, indem du nur
`search_sqlite()` direkt aufrufst:

```python
# In einer neuen Zelle:
results = search_sqlite(["Leitzins"])
for _, row in results.iterrows():
    print(f"{row['title'][:60]}")
    print(f"  {row['url']}")
    print()
```

Das zeigt dir, dass die Suche funktioniert - nur die LLM-Zusammenfassung
fehlt dann.

---

## Phase 6: LLM anbinden (Mistral 3 14B)

> **Spaeter.** Erstmal den Crawler zum Laufen bringen (Phasen 1-5).

### Was muss angepasst werden?

In den Notebooks gibt es eine Funktion `ask_ollama()` die Ollama
aufruft. Diese muss durch einen Aufruf an euren Mistral-Chatbot
ersetzt werden.

**Aktueller Code (Ollama):**
```python
def ask_ollama(prompt, model="llama3.1:8b"):
    resp = requests.post("http://localhost:11434/api/generate", json={
        "model": model,
        "prompt": prompt,
        "stream": False,
    })
    return resp.json()["response"]
```

**Anpassung fuer OpenAI-kompatible API (z.B. vLLM, TGI):**
```python
def ask_llm(prompt, api_url="http://<mistral-endpoint>/v1/chat/completions"):
    resp = requests.post(api_url, json={
        "model": "mistral-small-3.1-24b-instruct-2503",  # oder wie euer Modell heisst
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }, headers={"Authorization": "Bearer <token>"})  # falls noetig
    return resp.json()["choices"][0]["message"]["content"]
```

**Anpassung fuer CML Model Serving:**
```python
import cmlapi

def ask_llm(prompt):
    client = cmlapi.default_client()
    # Details haengen von eurem Model-Serving-Setup ab
    response = client.predict(
        model_name="mistral-chatbot",
        input_data={"prompt": prompt}
    )
    return response["output"]
```

### Was du herausfinden musst

Bevor du die LLM-Anbindung machst, klaere:

1. **Endpoint-URL:** Wie ist die URL des Mistral-Chatbots?
   ```bash
   # Probiere:
   curl http://<chatbot-url>/v1/models
   # oder:
   curl http://<chatbot-url>/health
   ```

2. **API-Format:** Ist es OpenAI-kompatibel (`/v1/chat/completions`)?
   ```bash
   curl -X POST http://<chatbot-url>/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "mistral", "messages": [{"role": "user", "content": "Hallo"}]}'
   ```

3. **Authentifizierung:** Braucht man einen API-Key oder Token?

4. **Modellname:** Wie heisst das Modell im API-Aufruf?

### Vorteil: Mistral 3 14B > llama3.1:8b

Euer Mistral-Modell ist deutlich groesser als das llama3.1:8b das ich
lokal verwendet habe. Das sollte zwei bekannte Probleme loesen:

- **Halluzination:** llama3.1:8b erfindet Zahlen (sagt z.B. "3.5%"
  obwohl im Kontext "2.15%" steht). Ein 14B-Modell liest Kontext
  zuverlaessiger.
- **Geschwindigkeit:** Auf CML mit GPU sollte die Antwort in Sekunden
  kommen statt in 3-5 Minuten auf meinem Laptop-CPU.

---

## Projektstruktur-Referenz

```
oenb-crawler/
├── analysis/
│   ├── crawler_demo.ipynb       <- Haupt-Demo-Notebook
│   ├── rag_exploration.ipynb    <- RAG vs Agentic Search Vergleich
│   ├── extract_text.py          <- Text aus HTML extrahieren
│   ├── extract_chart_data.py    <- Zeitreihen aus JS extrahieren
│   ├── chart_synonyms.json      <- Synonym-Dictionary (MANUELL!)
│   └── cleanup_db.py            <- DB-Duplikate bereinigen
├── scraper/
│   └── oenb_scraper/
│       ├── spiders/
│       │   └── oenb_spider.py   <- Der eigentliche Crawler
│       ├── pipelines.py         <- Deduplizierung, SQLite-Speicherung
│       ├── database.py          <- SQLite DB-Logik
│       └── settings.py          <- Scrapy-Konfiguration
├── data/
│   └── pages.db                 <- Wird vom Crawler erstellt
├── docs/
│   ├── CML-SETUP.md             <- Diese Datei
│   └── SCHNELLSTART-DEMO.md     <- Kurzanleitung fuer lokalen Rechner
├── requirements.txt
├── run.sh                       <- Crawler-Startscript
└── cml_crawl.py                 <- CML Job Script (optional)
```

### Wichtige Dateien die NICHT automatisch erstellt werden

| Datei | Beschreibung | Was tun? |
|-------|-------------|----------|
| `analysis/chart_synonyms.json` | Synonym-Mapping fuer Chart-Suche | Ist im Git. Nach Re-Crawl mit neuen Charts manuell ergaenzen |
| `data/pages.db` | Die Datenbank | Wird vom Crawler erstellt. Nicht im Git (zu gross) |

---

## Troubleshooting

### Proxy-Probleme beim Crawlen

Falls der Crawler Timeouts oder Connection-Errors bekommt:

```bash
# Scrapy Proxy-Einstellung (in der Shell):
export HTTP_PROXY=http://proxy.oenb.at:8080
export HTTPS_PROXY=http://proxy.oenb.at:8080

# Oder in scraper/oenb_scraper/settings.py hinzufuegen:
# HTTPPROXY_ENABLED = True
# HTTP_PROXY = 'http://proxy.oenb.at:8080'
```

### pip install schlaegt fehl

```bash
pip install --proxy http://proxy.oenb.at:8080 -r requirements.txt
```

### Crawler bricht ab / Session-Timeout

Kein Problem - einfach nochmal starten. Der Crawler ist inkrementell
und ueberspringt bereits gecrawlte Seiten (gleicher SHA256-Hash).

### "No module named oenb_scraper"

Du musst im `scraper/`-Verzeichnis sein wenn du `scrapy crawl` aufrufst:

```bash
cd scraper
scrapy crawl oenb ...
cd ..
```

### DB ist leer nach dem Crawl

Pruefe ob die SQLitePipeline aktiviert ist. Die Pipeline muss
**explizit** angegeben werden:

```bash
scrapy crawl oenb \
  -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.SQLitePipeline": 400}' \
  -s "SQLITE_DB_PATH=../data/pages.db"
```

Ohne `-s ITEM_PIPELINES=...` wird nur JSON geschrieben, nicht SQLite.

### Text-Extraktion: "table page_content already exists"

Das ist OK - `extract_text.py` aktualisiert existierende Eintraege
und fuegt neue hinzu. Keine Daten gehen verloren.

### Jupyter Notebook: "chart_synonyms.json not found"

Die Datei muss im selben Verzeichnis wie das Notebook liegen
(`analysis/`). Falls sie fehlt:

```bash
# Pruefen:
ls analysis/chart_synonyms.json

# Falls nicht da - aus Git wiederherstellen:
git checkout analysis/chart_synonyms.json
```

### robots.txt blockiert den Crawler

Der Crawler respektiert `robots.txt` (`ROBOTSTXT_OBEY = True`).
Falls bestimmte Seiten blockiert sind, ist das beabsichtigt.
Nicht deaktivieren.

---

## Checkliste

- [ ] CML-Projekt erstellt (Git Clone oder ZIP)
- [ ] `pip install -r requirements.txt` erfolgreich
- [ ] Internet-Zugang zu oenb.at getestet
- [ ] Crawler gestartet (selektiv oder voll)
- [ ] Text extrahiert (`extract_text.py`)
- [ ] Ergebnis geprueft (Seiten > 1.000, Charts > 0)
- [ ] `crawler_demo.ipynb` Abschnitte 1-4 laufen
- [ ] (Spaeter) LLM-Endpoint identifiziert
- [ ] (Spaeter) `ask_ollama()` durch `ask_llm()` ersetzt
- [ ] (Spaeter) Agentic Search (Abschnitt 5) funktioniert

---

## Auswertungs-Pipeline als CML-Jobs (2026-07-07)

Drei Jobs, ein Datenlayout (identisch zu lokal — die Chatbot-Runtime
erwartet genau diese Pfade):

| Job | Script | Schreibt nach | Dauer | Wie oft |
|-----|--------|---------------|-------|---------|
| 1. Website-Crawl | `cml_crawl.py` | `data/full_site_production/pages.db` | ~2–4h | bei Bedarf |
| 2. ISAweb-Statistik | `cml_isaweb.py` | `data/statistics_production/pages.db` | ~1–2h | bei Bedarf |
| 3. **Auswertung** | `cml_eval.py` | `data/eval_reports/eval_<datum>.json` | ~30–60 min | beliebig oft |

**Workflow:** Git clone → Job 1 und Job 2 einmal laufen lassen →
Job 3 wann immer eine frische Auswertung gebraucht wird. Job 3 macht
alles selbst: Text-Extraktion → KB-Exporte (ohne Fehlerseiten) →
FTS-Index-Rebuild → 67-Case-Eval → Scoring mit Baseline-Diff gegen
den letzten Report. Schlägt ein Schritt fehl, wird der Job rot
(Exit ≠ 0) und das Log zeigt den Schritt.

### LLM-Router anbinden (optional)

Ohne LLM fällt der Router automatisch auf Regeln zurück. Mit LLM
(empfohlen, realistischer End-to-End-Test): In CML unter
Project Settings > Advanced > Environment Variables setzen —
funktioniert mit **jedem OpenAI-kompatiblen Endpoint**
(CML Model Endpoints, Mistral, vLLM, …):

```
OENB_LLM_PROVIDER=mistral
OENB_MISTRAL_BASE_URL=https://<endpoint>   # spricht /v1/chat/completions
OENB_MISTRAL_MODEL=<modellname>
OENB_MISTRAL_API_KEY=<key>
```

### Auswertung lesen

Das Job-Log endet mit der Summary: Score (0–1, pass=1/partial=0.5),
Verdikte nach Fragetyp (NAV/FACT/TABLE/META/COMPARE/LEGAL/OOD) und dem
Diff zur Baseline (welche Cases besser/schlechter wurden). Der volle
Report (jede Frage mit Antwort, Citations, Verdikt und Begründung)
liegt als JSON in `data/eval_reports/`.
