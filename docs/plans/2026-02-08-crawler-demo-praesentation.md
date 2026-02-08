# OeNB Crawler Demo - Praesentationsleitfaden

## Rahmen

- **Publikum:** 2 Kolleg:innen - eine forschungsorientiert, einer technisch (Co-PO Cloudera CML)
- **Dauer:** ~20 Min + Diskussion
- **Format:** Live-Demo im Jupyter Notebook (`analysis/crawler_demo.ipynb`)
- **Kernbotschaft:** "Ich hab einen POC fuer Agentic Search gebaut. Ist das besser als RAG? Reicht der Crawler? Was meint ihr?"

---

## Vorbereitung (vor der Praesentation)

### 1. Ollama starten und aufwaermen
```bash
ollama serve                     # Falls nicht schon laeuft
ollama run llama3.1:8b "Test"    # Modell in den Speicher laden
```

### 2. Notebook einmal durchlaufen
```bash
cd analysis && jupyter notebook crawler_demo.ipynb
```
- Kernel restart + alle Zellen bis Abschnitt 4 ausfuehren
- Abschnitt 5 (Agentic Search): die `frage()`-Zellen **einmal vorher ausfuehren**
  - Erstes Query ist immer langsam (~200s weil Modell noch kalt)
  - Danach gehts schneller (~30-60s)
- Die fertigen Outputs im Notebook lassen - dient als Backup falls live was haengt

### 3. DB-Datei fuer Transport (falls noetig)
```bash
# 640 MB -> 343 MB gezippt
cd data && zip -9 pages.db.zip pages.db
```

---

## Ablauf: 3 Akte

### Akt 1: "Was haben wir?" (5 Min)

**Notebook Abschnitte 2-4 durchklicken.**

**Talking Points:**
- "Ihr kennt den Crawler ja schon. Ich hab ihn verbessert - Duplikate bereinigt, inkrementelles Crawling."
- **Zahlen zeigen:** ~10.000 Seiten, 30+ Sektionen, DE/EN
- **Highlight: Chart-Daten** - "Der Crawler extrahiert jetzt automatisch Zeitreihen aus dem JavaScript der isawebstat-Seiten"
- **Leitzins-Beispiel live zeigen:** Euroraum 2025: 2.15, USA 2025: 3.75, Japan 2025: 0.75

**Ueberleitung:** "Ok, die Daten sind da. Wie machen wir jetzt einen Chatbot draus?"

---

### Akt 2: "RAG vs. Agentic Search" (8 Min)

**Notebook Abschnitt 5 - Live-Demo.**

**Talking Points:**
- "RAG braucht Embedding + Vector DB + LangChain. Stundenlanger Aufbau, und die Ergebnisse waren schlecht - hat bei 4 Testfragen nichts Brauchbares gefunden."
- "Ich hab stattdessen Agentic Search probiert: SQL-Stichwortsuche + LLM. Kein Embedding, kein Vector Store."
- **Live die Leitzins-Frage stellen** - zeigt echte Zahlen aus den Chart-Daten
- **1-2 weitere Fragen** (Kreditzinssaetze, Finanzbildung)
- "Das laeuft mit llama3.1:8b lokal auf meinem Laptop. Stellt euch vor was ein groesseres Modell auf CML koennte."

**Falls Ollama langsam ist:**
- "Das dauert ~30s auf meinem Laptop. Auf CML mit GPU waere das in 2-3s."
- Falls es haengt: vorher gespeicherte Outputs zeigen

**Falls falsche Antwort kommt (wahrscheinlich!):**
- Beispiel: Das 8B-Modell sagt "Leitzins ist 3.5%" obwohl im Kontext "Euroraum: 2025: 2.15" steht
- Der echte EZB-Hauptrefinanzierungssatz ist 2.15% (Stand Juni 2025) - die **Daten im Crawler sind korrekt!**
- "Das ist ein klassisches Halluzinations-Problem: das 8B-Modell erfindet Zahlen statt sie aus dem Kontext abzulesen."
- "Mit einem groesseren Modell (13B, 70B) auf CML wird das besser - die koennen Zahlen aus Kontext zuverlaessiger extrahieren."
- **Das ist ein gutes Argument fuer CML:** Die Search-Pipeline liefert die richtigen Daten, aber das Modell muss gross genug sein um sie korrekt zu interpretieren.

---

### Akt 3: "Was meint ihr?" (5+ Min)

**Diskussion mit konkreten Fragen.**

#### Frage 1: Reicht der Crawler?
- 10.000 Seiten gecrawlt, aber:
  - ~1.800 Seiten haben < 500 Zeichen Text
  - ~970 Duplikate (gleicher Text, verschiedene URLs)
  - mdi/entity-Seiten sind leer (dynamisch geladen?)
  - Manche Sektionen duenn abgedeckt
- "Sollen wir nochmal crawlen? Oder reicht das fuer den POC?"

#### Frage 2: Agentic Search auf CML?
- Aktuell: llama3.1:8b lokal, ~30-200s pro Antwort
- Auf CML: groesseres Modell (13B, 70B?), GPU, schneller
- "Macht es Sinn, das auf eurer CML-Instanz aufzusetzen?"

#### Frage 3: Keyword-Extraktion automatisieren
- **Aktuelles Problem:** User muss Suchbegriffe manuell eingeben (`["Leitzins", "EZB"]`)
- **Naechster Schritt:** LLM extrahiert Keywords automatisch aus der Frage
- Ist einfach zu bauen (ein zusaetzlicher LLM-Call), aber verdoppelt die Latenz auf dem Laptop
- Auf CML mit schnellem Modell kein Problem

#### Frage 4: isawebstat-Daten besser verschlagworten
- **Problem:** Chart-Seite "Leitzinssätze" enthaelt "Euroraum", aber nicht "EZB"
- User sucht "EZB Leitzins" -> findet die Daten nicht
- **Loesungsideen:**
  - Synonyme/Tags hinzufuegen bei der Extraktion ("Euroraum" -> auch "EZB", "Europaeische Zentralbank")
  - Oder: LLM generiert automatisch Synonyme beim Indexieren
  - Oder: Mehrere Suchdurchlaeufe mit verschiedenen Keywords
- "Wie wuerdet ihr das loesen?"

---

## Technische Details (falls gefragt)

### Architektur
```
oenb.at / finanzbildung.oenb.at
        |
  Scrapy Spider          (robots.txt, 0.5s delay, AutoThrottle)
        |
  URL-Normalisierung     (Session-IDs, Duplikate)
        |
  SQLite (pages.db)      (gzip-komprimierte Bodies)
        |
  Text-Extraktion        (BeautifulSoup + Chart-JS-Parsing)
        |
  Agentic Search         (SQL LIKE + Ollama LLM)
```

### Was der Crawler besser macht als vorher
- **URL-Normalisierung:** Session-IDs (`jsessionid`) werden entfernt -> keine Duplikate
- **Inkrementell:** SHA256-Hash vergleich, nur geaenderte Seiten werden aktualisiert
- **Chart-Daten:** JavaScript-Zeitreihen aus isawebstat werden automatisch extrahiert
- **Deduplizierung:** 26.834 -> 10.010 Seiten (16.824 Duplikate entfernt)

### Agentic Search vs. RAG
| | RAG | Agentic Search |
|---|---|---|
| Setup | Stunden (Embedding) | 0 Sekunden |
| Suchraum | 5.000 Chunks (Stichprobe) | Alle 10.010 Seiten |
| Suchzeit | ~0.5s | ~0.1s |
| Trefferqualitaet | Irrelevant | Exakte Treffer |
| Dependencies | LangChain + ChromaDB + Ollama | SQLite + requests + Ollama |
| Leitzins-Frage | "Keine Antwort gefunden" | Findet Zeitreihen-Daten |

---

## Naechste Schritte (Vorschlaege fuer Diskussion)

1. **Auto-Keywords:** LLM extrahiert Suchbegriffe aus natuerlicher Frage
2. **Synonym-Anreicherung:** isawebstat-Daten mit Synonymen taggen (EZB/Euroraum, etc.)
3. **CML-Deployment:** Groesseres Modell, GPU, schnelle Antworten
4. **Crawler verbessern:** Leere Seiten (mdi/entity), dynamische Inhalte
5. **Evaluation:** Testfragen-Set erstellen und systematisch Qualitaet messen
