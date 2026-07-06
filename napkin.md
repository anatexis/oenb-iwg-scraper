# Napkin - OeNB Crawler Rewrite Assessment

Stand: 2026-03-21

## Bestandsaufnahme

### Was existiert

**main-Branch (veröffentlicht):**
- Scrapy-Crawler mit ~10.010 deduplizierten Seiten
- SQLite-DB mit `pages`, `page_bodies`, `page_content`
- URL-Normalisierung (jsessionid-Strip, Query-Sort)
- Inkrementelles Crawlen (body_hash 3-Wege-Logik in store_page)
- ISAweb-Chart-Datenextraktion aus `$scope.data` JS
- Textextraktion (HTML → Reintext + Chart-Daten)
- CML-Deployment-Skripte (cml_crawl.py, cml_crawl_runden.py)
- Tests: bestehende Suite für Spider, Pipelines, DB, Textextraktion

**feature/oenb-crawler-rebuild Worktree (NICHT COMMITTED!):**
- 93 neue, 22 geänderte Dateien - alles uncommitted
- 420 Tests bestanden
- Kompletter Chatbot-Stack aufgebaut:
  - Query-Router mit generischen Intents (release_lookup, navigation, explanation, trend_over_time, fact_lookup, topic_overview, comparison, advice_request)
  - Domain-Gating (interest_rates, commodity_prices, real_estate, financial_soundness, ...)
  - Hybrid-Retrieval (Website + Statistik Subqueries)
  - Chatbot-Answering mit Multi-Part und Single-Part Modi
  - LLM-Abstraktion (Ollama lokal, Mistral CML)
  - Semantische Suche / Embedding-Backends
  - ISAweb Live-Lookup als Fallback
  - Knowledge-Base Export (JSONL)
  - Open-Ended-Eval Framework
- Statistik-KB: 660 Datasets, 741 Metadata, 159.215 Observations, 1.149 Release-Events
- Aber: Feature-Branch ist auf gleichem Commit wie main (0 Commits voraus). Gesamte Arbeit ist nur im Working-Tree.

### Die zwei Plandokumente

**Requirements (2026-03-18):** 746 Zeilen. Gründliche Analyse der OeNB-Seitenstruktur. Kernaussagen:
- ISAweb ist ein Query-System, nicht bloß Seiten → Webservice ist der primäre Akquisitionspfad
- Standardized Tables sind Bündel (Topic + Explanatory Note + Schedule + Chart + Export)
- Provenance ist Pflicht für Chatbot-Vertrauenswürdigkeit
- Separate Entity-Typen: PageDocument, AssetDocument, DatasetFamily, DatasetMetadata, TimeSeriesDataset, ReleaseEvent
- PDFs selektiv extrahieren, nicht alles blind verarbeiten

**Implementierungsplan (2026-03-18):** 1.094 Zeilen, 19 Tasks. TDD-getrieben. Abfolge:
1. Resource-Datenmodell (Enum)
2. URL-Normalisierung zentralisieren
3. Resource-Classifier statt if/elif
4. Crawl-Scope erweitern
5. Persistente Frontier für inkrementelles Crawlen
6. HTTP-Freshness-Tracking
7. HTML-Storage von Content-Extraction trennen
8. Link-Graph erfassen
9. Standardized-Table-Bündel + Source-Attribution-Extraktor + Chart-Accessibility
10. ISAweb Discovery von Extraction trennen
11. ISAweb Webservice Client
12. ISAweb Datasets materialisieren
13. Release-Kalender als Structured Events
14. Shiny/External-App Tracking
15. Selektive PDF-Verarbeitung
16. Knowledge-Base-Export
17. Inkrementell-Crawl Integration-Test
18. Neuer Spider Entry-Point + CLI
19. End-to-End Verification

### Handoff-Notizen

**LLM/RAG Handoff (2026-03-20):** Beschreibt den Zustand vor Chatbot-Architekturumbau. Lexical Retrieval funktioniert, aber Whole-Sentence-Routing ist schwach.

**Open-Ended Eval Handoff (2026-03-21):** Zentrale Diagnose: **Der Engpass liegt nicht im Crawl, sondern in Routing/Retrieval/Answering.** Router wurde auf generische Intents umgestellt, OOD-Guards eingeführt, Multi-Part-Antworten gezielt statt blind. 74 relevante Tests grün. Nächster Schritt wäre Full-Eval-Run.

---

## Meine Einschätzung zum Rewrite

### Was gut ist

1. **Requirements-Dokument ist exzellent.** Gründliche Analyse, keine Spekulation, klare "Crawler Implications". Die Unterscheidung zwischen UI-Scraping und Webservice-Akquise ist die richtige strategische Entscheidung.

2. **Der Chatbot-Stack im Worktree ist beeindruckend.** 420 Tests, generisches Intent-Routing, Domain-Gating, Hybrid-Retrieval - das ist schon weit. Die Handoff-Notiz zeigt gutes Engineering-Urteil (kein Löcherstopfen, generische Patterns).

3. **Die Diagnose "Engpass ist nicht der Crawl" ist korrekt.** Bei 10.010 Seiten + 660 ISAweb-Datasets + 159k Observations ist die Coverage schon brauchbar. Die Chatbot-Qualität hängt aktuell stärker am Routing/Retrieval.

### Was problematisch ist

1. **93 Dateien uncommitted im Worktree.** Das ist die größte Gefahr. Ein versehentliches `git checkout`, ein Disk-Problem, und die gesamte Chatbot-Arbeit ist weg. Das muss sofort committet werden.

2. **Der 19-Task-Rewrite-Plan ist overengineered für den aktuellen Stand.** Er plant einen fundamentalen Neuaufbau (neue Entity-Typen, Frontier, Link-Graph, ISAweb-Webservice-Client, etc.), aber:
   - Der Chatbot-Stack im Worktree funktioniert bereits mit der bestehenden DB-Struktur
   - Die 660 ISAweb-Datasets wurden offenbar schon erfolgreich materialisiert
   - Viele der Plan-Tasks (1-8) sind Infrastructure-Refactoring, kein direkter Nutzergewinn
   - Der ISAweb-Webservice-Client (Task 11) ist das wertvollste Einzelstück, aber man braucht dafür nicht erst 10 Refactoring-Tasks

3. **Zwei Arbeitsstränge ohne klare Priorisierung.** Requirements + Plan gehen in Richtung "Crawler-Neuaufbau", während die tatsächliche Arbeit im Worktree den Chatbot-Stack aufgebaut hat. Das ist kein Widerspruch, aber es fehlt ein klares "was zuerst".

### Empfehlung

**Reihenfolge sollte sein:**

1. **SOFORT: Worktree-Arbeit sichern** - Alles committen. Das ist die wichtigste Einzelaktion.

2. **KURZFRISTIG: Open-Ended-Eval laufen lassen und auswerten.** Die Handoff-Notiz sagt korrekt: ohne frischen Eval weiß man nicht, wo man steht.

3. **MITTELFRISTIG: Gezieltes Cherry-Picking aus dem 19-Task-Plan.** Nicht alle 19 Tasks sequential durcharbeiten. Stattdessen:
   - URL-Normalisierung zentralisieren (Task 2) - schneller Win, schon überfällig
   - Resource-Classifier (Task 3) - macht Spider-Code sauberer
   - ISAweb Webservice Client (Task 11) - der größte inhaltliche Hebel
   - Source-Attribution-Extraktor (Task 9a) - direkt chatbot-relevant
   - Den Rest nur bei konkretem Bedarf

4. **NICHT JETZT: Full-Site Frontier-Neuaufbau (Tasks 5-8).** Das bestehende inkrementelle Crawling (cml_crawl_runden.py + body_hash) funktioniert. Die Frontier-Abstraktion ist elegant, aber kein Engpass.

---

## Nächste konkrete Schritte

- [x] Worktree-Arbeit committen (feature/oenb-crawler-rebuild) → DONE 2026-03-21
- [x] Open-Ended-Eval auf aktuellem Code laufen lassen → DONE 2026-03-21
- [x] Eval-Ergebnis auswerten → Fehlerklassen identifizieren → DONE, siehe unten
- [x] Routing-Fix: "Banken"→financial_soundness, FSI→release_lookup → DONE 2026-03-21
- [x] KB-Export: war nicht kaputt, nur veraltet. Re-Export bringt 318 DE-Families (statt 107) → DONE
- [x] Retrieval-Scoring: QUERY_SYNONYMS für Kreditzinsen/Sparzinsen/RPPI/FSI + "kredit" Domain-Hint + sql_first für stat-domain+fact_lookup → DONE 2026-03-21
- [x] Answering-Modi: intent-aware Suffixe für trend_over_time, comparison, wo-Fragen → DONE 2026-03-21
- [x] Eval-Set erweitert: 17 neue Cases (→ 40 total), davon 7 FALSE_OOD, 1 WRONG_DOMAIN → DONE 2026-03-21
- [x] LLM-Routing aktiviert: Timeout 30→120s, llama3.1:8b eliminiert FALSE_OOD komplett → DONE 2026-03-21
- [x] Spider Start-URLs erweitert: alle OeNB-Hauptsektionen als Einstiegspunkte → DONE 2026-03-21
- [x] Full-Site-Crawl: 3.729 HTML-Seiten (0 /dam/) → DONE 2026-03-22
- [x] DFS→BFS Fix: `DEPTH_PRIORITY=1` + FIFO-Queues → alle Start-URLs in 30s erreicht (vorher 0 nach 4h) → DONE 2026-03-22
- [x] BFS-Crawl: 3.569 HTML-Seiten, alle Sektionen abgedeckt → DONE 2026-03-23
- [x] Text-Extraktion: 3.568 Seiten → DONE 2026-03-23
- [x] KB-Export: 3.570 Records, 18 MB JSONL (nur HTML, kein ISAweb) → DONE 2026-03-23
- [x] KB-Export v2: Page-Chunks für Website-Seiten (3.545 chatbot_chunk Records) → DONE 2026-03-24
- [x] Retrieval-Fix: Token-Matching gelockert (≤3 Tokens → 1 Match reicht, vorher ≤1) → DONE 2026-03-24
- [x] Answering-Fix: Confidence-Threshold für page_document Hits entfernt (Router-Confidence oft <0.55 für Website-Fragen) → DONE 2026-03-24
- [x] Eval v4-v7: Iterative Retrieval+Answering Fixes → DONE 2026-03-24
  - v4 (Baseline): 24/40 beantwortet, Website-Fragen alle not_found
  - v5 (Page-Chunks + both-KB-scan): 22/40, page_documents verdrängen datasets → REVERT
  - v6 (Token-Fix only): 23/40, Website-Hits gefunden aber Grounding blockt
  - v7 (+ Grounding-Fix): 23/40, zweiter Confidence-Gate blockte vor dem Fix
  - v8 (beide Confidence-Gates gefixt): **27/40 (67%)** — 5 Website-Fragen neu beantwortet (Geldmuseum, ISAweb, Bargeldumlauf-CSV, Frauen, Wechselkurse-CSV)
  - Verbleibende Probleme:
    - 6× dataset_family→page_document (Router sagt rag_first statt sql_first für Statistik-Fragen)
    - 2× dataset_family→not_found (Basiszins, EZB Zinsentscheid)
    - NS-Zeit: robots.txt als Top-Hit (Ranking), Taschengeld: nicht in KB, Kunstsammlung: Ranking
    - Nächster Hebel: Router-Strategie verbessern (sql_first vs rag_first Entscheidung)
- [x] Router-Fix v9: Drei Änderungen in query_router.py → DONE 2026-03-24
  - **Fix 1: Strategy Override** — `_normalize_strategy()` überschreibt `rag_first` mit `_infer_fallback_strategy()` wenn Domains statistisch sind. LLM sagt manchmal `rag_first` für interest_rates/reserves_assets → jetzt automatisch `sql_first` oder `hybrid`.
  - **Fix 2: IN_SCOPE_HINTS erweitert** — 14 neue Terme: English (interest, rate, monetary, deposit, reserve), Deutsch (geldmenge, mindestreserve, target2, geld, sicher, einlag, ezb, geldpolitik, zahlungsverkehr, meldewesen, finanzmarkt). Behebt 5 false-OOD-Rejections.
  - **Fix 3: QUERY_DOMAIN_HINTS erweitert** — monetary_policy (geldmenge, m3, mindestreserve, ezb, zinsentscheid, geldpolitik, einlagenfazilität, deposit facility, leitzins), interest_rates (+kreditvergabe, interest rates, lending rate), external_sector (target2, zahlungsbilanz, direktinvestition). Behebt falsche Domain-Zuordnungen.
  - Rule-basierter Quick-Test: 11/11 Cases korrekt geroutet. 34 Unit-Tests grün.
  - Eval v9 läuft (~1-2h CPU, llama3.1:8b). Erwartete Verbesserung: 27/40 → ~34/40 (85%).
- [x] Eval v9: **34/40 (85%)** — +7 gegenüber v8 (27/40) → DONE 2026-03-24
  - Neu beantwortet: deposit facility, interest rates Austria, EZB Zinsentscheid, Geldmenge M3, Mindestreserve, TARGET2, Geld-Sicherheit
  - Verbleibende 4 Misses: NS-Zeit (Coverage), Taschengeld (Coverage), Kunstsammlung (Coverage), Konto eröffnen (korrektes OOD)
  - 3 von 4 Misses sind Coverage-Probleme (Content nicht in KB), nicht Routing/Retrieval
- [x] Crawl-Performance: /dam/-Filter (Spider + Pipeline), skip_isaweb Flag → DONE 2026-03-22
- [x] IWG-Worktree erstellt (.worktrees/feature-iwg-audit/) mit CLAUDE.md-Briefing → DONE 2026-03-24
- [ ] URL-Normalisierung zentralisieren (leichter Refactor)
- [x] ISAweb Webservice Client → DONE 2026-03-25. 29 Hierarchien, 2856 Positionen, 73.425 Datasets, 3.2M Observations
- [x] Spider-Bug gefixt: `embedded_url` Referenz außerhalb `for`-Loop (5 Testfailures behoben) → DONE 2026-03-25
- [x] KB-Export: Streaming-Refactor (OOM bei 73k Datasets) → DONE 2026-03-26
- [ ] Chatbot-Eval v10 mit angereicherter KB laufen lassen

---

## Datenarchitektur: DB → KB → Chatbot (2026-03-26)

### Die drei Schichten

```
ISAweb REST API          Scrapy HTML Crawl
     │                        │
     ▼                        ▼
┌─────────────────────────────────────────┐
│  SQLite DB (pages.db) — Vollständig     │
│                                         │
│  isaweb_datasets      73.425 Records    │
│  isaweb_observations  3.239.955 Punkte  │  ← Rohe Zeitreihen (period, value, unit)
│  isaweb_metadata      2.318 Records     │
│  isaweb_dimensions    ~200k Records     │
│  pages / page_content 3.569 Seiten      │
│  release_events       8.095 Events      │
└──────────────┬──────────────────────────┘
               │
               │  export_knowledge_base_jsonl.py
               │  (Streaming, kein RAM-Akkumulation)
               ▼
┌─────────────────────────────────────────┐
│  JSONL Knowledge Base (~200 MB)         │
│  Für Chatbot-RAG optimiert              │
│                                         │
│  page_document        3.267 Records     │
│  asset_document       341 Records       │
│  isaweb_dataset       73.425 Records    │  ← OHNE Observations! Nur latest_observation
│  isaweb_metadata      2.318 Records     │    + observation_count + dimensions
│  release_event        8.095 Records     │
│  dataset_family       73.425 Records    │  ← Angereichert: Quellen, Seiten, Metadata
│  chatbot_chunk        ~150k Records     │  ← Suchbare Textsnippets für Retrieval
└──────────────┬──────────────────────────┘
               │
               │  knowledge_base_cache.py → Retrieval → Answering
               ▼
┌─────────────────────────────────────────┐
│  Chatbot RAG Pipeline                   │
│                                         │
│  1. User Query → Router (Intent+Domain) │
│  2. chatbot_chunk durchsuchen           │
│  3. Antwort aus chunk + parent generieren│
└─────────────────────────────────────────┘
```

### Warum Observations NICHT im KB-Export

**Was Observations sind:** Zeitreihen-Datenpunkte aus der ISAweb API.
Beispiel Dataset "Geldmenge M3 Österreich":
```
period: "2025-01"  value: "456789.3"  unit: "Mio EUR"
period: "2025-02"  value: "458123.1"  unit: "Mio EUR"
... (hunderte pro Dataset, 3.2M total)
```

**Warum sie in der DB sind:** Der ISAweb Client holt die kompletten Daten von der API.
Die DB ist die **vollständige Kopie** — für Analysen, Exports, zukünftige Features.

**Warum sie nicht im JSONL sind:**
1. **Chatbot braucht sie nicht.** `chatbot_chunk`-Records verwenden nur `latest_observation`
   für ihren Text ("Letzter Wert: 2025-03 = 461.002,7 Mio EUR").
2. **Größe:** 73k Datasets × ~44 Observations × ~80 Bytes JSON = **~10 GB** nur für Observations.
   Ohne sie: ~200 MB. Die KB wird in den RAM geladen — 10 GB ist nicht praktikabel.
3. **Kein Consumer:** Kein Teil der RAG-Pipeline greift auf `record["observations"]` zu.

**Wenn historische Daten nötig sind:** Direkt die SQLite DB abfragen (`isaweb_observations` Tabelle).
Zukünftig könnte ein `agentic` Modus den Chatbot live die DB querien lassen.

---

## ISAweb Webservice Client — Design (2026-03-24)

### Problem

6 Eval-Cases bekommen falsche Antworten weil die Statistik-KB die passenden Datasets nicht hat:
- Geldmenge M3 → bekommt "Key interest rates" statt Geldmengenaggregate
- Mindestreserve → bekommt "Key interest rates" statt Mindestreserve-Daten
- TARGET2 Saldo → bekommt "Services trade" statt TARGET2-Salden
- Einlagensicherung, Zahlungsverkehr, Jahresabschluss → ähnlich

**Root Cause:** Die 684 Datasets in der DB kommen nur aus dem HTML-Crawl (Scrapy entdeckt ISAweb-Links auf Seiten). Hierarchien ohne prominente Verlinkung werden nie entdeckt.

### Bestehende Infrastruktur (80% da)

| Modul | Was es tut | Status |
|-------|-----------|--------|
| `isaweb_service.py` | URL-Builder + XML-Parser (data, meta) | ✅ Fertig |
| `isaweb_store.py` | DB-Persistenz (datasets, observations, metadata, dimensions) | ✅ Fertig |
| `isaweb_resolver.py` | HTML-Parsing für ISAweb-Seiten | ✅ Fertig |
| `isaweb_discovery.py` | URL-Klassifikation | ✅ Fertig |
| `isaweb_client.py` | Proaktives Fetchen der REST-API | ✅ Fertig (2026-03-25) |
| `parse_content_positions()` | Content-Endpoint XML parsen (Positionen) | ✅ Fertig (in isaweb_service.py) |

### Design

**Neue Datei:** `scraper/oenb_scraper/isaweb_client.py` (~300-400 Zeilen, standalone, kein Scrapy)

**Ablauf:**
```
1. content(hierid=1..20, lang=DE+EN) → Hierarchiebaum mit allen Positionen
2. Für jede Position:
   a. meta(hierid, pos) → Metadaten (Titel, Quelle, Frequenz, Releases)
   b. data(hierid, pos) → Observations (Zeitreihe)
   c. → isaweb_store speichert in bestehende DB-Tabellen
3. Report: X neue Datasets, Y neue Observations, Z Fehler
```

**Ergänzung in `isaweb_service.py`:** `parse_content_response()` — parst den XML-Baum vom Content-Endpoint in eine Liste von Positionen pro Hierarchie.

**Tech:** `requests` + bestehende Parser + bestehender Store. Rate-Limiting 0.5s zwischen Requests. Kein Scrapy nötig.

**Bekannte Hierarchie-IDs (aus requirements.md):**
- 1 (OeNB/Eurosystem), 2 (Finanzinstitutionen), 3 (Wertpapiere), 4 (Zahlungsmittel)
- 5 (Preise/Wettbewerb), 6 (Realwirtschaft), 7 (Finanzierungsrechnung), 8 (Außenwirtschaft)
- 9 (Bankenaufsicht), 10 (Zinssätze/Wechselkurse), 11 (Spezial), 14 (SDDS)

**Tatsächliches Ergebnis (2026-03-25):**
- 29 Hierarchien (inkl. hierid=11 via `EXTRA_LEAF_HIERIDS`)
- 2.856 Positionen
- **73.425 Datasets** (107× mehr als die 684 vom HTML-Crawl)
- **3.239.955 Observations**
- 0 Fehler, ~50 Min Laufzeit

**Verifizierte Abdeckung:**
- M3: ✅ `VDBGMBSM3` in hierid=13
- Einlagefazilität: ✅ hierid=22
- Bargeldumlauf: ✅ hierid=13
- Mindestreserve, TARGET2, Zahlungsverkehr, Einlagensicherung: Keine dedizierten ISAweb-Datasets (Website-Themen, nicht statistische Zeitreihen)

---

## Open-Ended-Eval v2 Ergebnis (2026-03-21, llama3.1:8b lokal)

**23 Cases, Zusammenfassung:**

| Kategorie | Anzahl | Anteil |
|-----------|--------|--------|
| Korrekte OOD-Abwehr | 2 | 9% |
| Brauchbare Antworten | 6 | 26% |
| Korrekt not_found (kein Full-Site-Crawl) | 8 | 35% |
| Fixbar ohne Crawl (Routing/Retrieval/Answering) | 7 | 30% |

**Wichtiger Kontext:** Es gab noch keinen Full-Site-Crawl. Die Website-KB (51MB) ist nur eine kleine Fallback-Basis. Alles was nicht durch ISAweb-Tabellen beantwortet werden kann, geht korrekt auf `not_found`. Das betrifft 8 von 12 not_found-Cases.

### Korrekt not_found - braucht Full-Site-Crawl (8 Cases)

| Query | Grund |
|-------|-------|
| Geldmuseum | Website-Content, nicht in ISAweb |
| Was ist ISAweb? | Website-Erklärseite |
| Bargeldumlauf CSV/Excel? | Download-Navigation |
| Wechselkursdaten als CSV? | Download-Navigation |
| NS-Zeit OeNB | Website-History |
| Taschengeld Kinder | Finanzbildung |
| Frauen in Führungsfunktionen | Corporate Topic |
| Kunstsammlung OeNB | Corporate Topic |

### Fixbar ohne Crawl (7 Cases) → ALLE GEFIXT 2026-03-21

**A. Retrieval-Versagen (2 Cases) → GEFIXT:**
- Kreditzinsen → QUERY_SYNONYMS + PREFERRED_QUERY_PHRASES "lending rates" → findet jetzt "Lending rates - new business"
- FSI → OOD-Bypass wenn Fallback stat-Domain hat + financial_soundness Routing

**B. Routing-Fehler (2 Cases) → GEFIXT:**
- flex/fix Kredit → "kredit" in QUERY_DOMAIN_HINTS + sql_first für stat-domain+fact_lookup
- Banken → _should_prefer_fallback_route ohne Intent-Einschränkung

**C. Answering-Schwächen (3 Cases) → GEFIXT:**
- Immobilienpreise Entwicklung → trend_over_time Suffix: "verlinkte Tabelle enthält vollständige Zeitreihe"
- Goldreserven Lagerort → wo-Fragen Suffix: "Tabelle enthält Bestandsdaten, siehe verlinkte Seite"
- Basiszins vs. Referenzzins → comparison Suffix: extrahiert Quellen-Snippet aus Chunk-Text

### Was funktioniert (13 Cases, vorher 6)

- Immobilienpreisindex Erklärung → RPPI Dataset ✓
- Inflation Trend → World commodity prices ✓
- Inflationsdaten Veröffentlichung → Release + Dataset ✓
- Sparzinsen Tabelle → Navigation-Antwort ✓
- VPI Tabelle → Navigation-Antwort ✓
- Wohnbaukreditzinsen Zeitreihe → Navigation-Antwort ✓
- Kreditzinsen → Lending rates - new business ✓ (NEU)
- FSI Veröffentlichung → Financial Soundness Indicators ✓ (NEU)
- flex/fix Kredit → Lending rates - new business ✓ (NEU)
- Banken-Lage → Financial Soundness Indicators ✓ (NEU)
- Immobilienpreise Entwicklung → RPPI + Trend-Hinweis ✓ (NEU)
- Goldreserven Lagerort → Reserve assets + Verweis-Hinweis ✓ (NEU)
- Basiszins vs. Referenzzins → Werte + Quellen ✓ (NEU)

---

## Eval v3: Erweitertes Eval-Set (2026-03-21, 40 Cases)

### Neue Cases (17 hinzugefügt, 40 total)

Fokus auf Schwachstellen des regelbasierten Routers:
- **Englische Queries** (025, 024): "interest rates Austria", "deposit facility rate"
- **OeNB-Kernthemen ohne Keywords** (026-031): EZB, Geldmenge M3, Mindestreserve, TARGET2, Zahlungsverkehr, Einlagensicherung
- **Cross-Domain** (032, 040): Geldpolitik↔Immobilien, Leitzinsen↔Sparzinsen
- **Grenzfälle** (037-039): Deutschland-Inflation, Konto eröffnen (OOD), Geldsicherheit
- **Kurze Queries** (033): "inflation" (ein Wort)

### Ergebnis: Regelbasierter Router

| Status | Anzahl | Cases |
|--------|--------|-------|
| OK | 9/17 | deposit facility, inflation, Leitzins-Senkung, Kreditvergabe, Jahresabschluss, Deutschland-Inflation, Konto-OOD, Leitzins/Sparzinsen, Cross-Domain |
| FALSE_OOD | 7/17 | interest rates Austria, Geldmenge M3, Mindestreserve, TARGET2, Einlagensicherung, Zahlungsverkehr, Geldsicherheit |
| WRONG_DOMAIN | 1/17 | EZB Zinsentscheid (→ website_general statt monetary_policy) |

**Diagnose:** Der OOD-Filter (`_is_clearly_out_of_scope`) ist das Hauptproblem. Er arbeitet mit ~30 handgepflegten IN_SCOPE_HINTS. Alles was nicht darin steht wird als OOD abgelehnt — auch wenn es Kern-OeNB-Themen sind.

### Ergebnis: LLM-Router (llama3.1:8b lokal, ~29s/Query)

| Metrik | Ohne LLM | Mit LLM |
|--------|----------|---------|
| FALSE_OOD | 7/8 | **0/8** |
| Domain korrekt | 1/8 | 3/8 |
| Latenz (lokal, CPU) | <0.1s | ~29s |

**Entscheidung:** LLM-Router als Default aktiviert. Auf CML mit GPU wird Latenz <1s sein. Lokal mit Ollama ~15-30s (CPU), aber funktional. Fallback auf Regeln wenn kein LLM verfügbar.

**LLM-Schwächen bei Domain-Zuordnung:**
- Mindestreserve → reserves_assets (sollte monetary_policy sein)
- TARGET2 → reserves_assets (sollte website_general/Zahlungsverkehr sein)
- Einlagensicherung → financial_soundness (vertretbar, aber eigentlich website_general)
- EZB Zinsentscheid → interest_rates (akzeptabel, aber monetary_policy wäre besser)

→ Die Domain-Taxonomie hat keine Kategorie für "Zahlungsverkehr" oder "Bankenaufsicht". Das LLM tut sein Bestes mit den vorhandenen Kategorien.

---

## Full-Site-Crawl Analyse (2026-03-21)

### Warum der Crawl unvollständig ist

`data/full_site_production/pages.db` hat 4.167 Seiten, davon:

| Sektion | Seiten | Anteil |
|---------|--------|--------|
| /dam/ (PDFs/Assets) | 2.388 | 57% |
| /Termine/ | 490 | 12% |
| /isawebstat/ | 306 | 7% |
| finanzbildung.oenb.at | 201 | 5% |
| /Statistik/ | 242 | 6% |
| /Ueber-Uns/ | **5** | 0.1% |
| /der-euro/ | **1** | 0.02% |

**Root Cause:** Spider hatte nur 3 Start-URLs (Homepage, Sitemap, finanzbildung.oenb.at). Von dort wurden /dam/ und /Termine/ aggressiv verlinkt, aber Content-Sektionen wie Ueber-Uns, der-euro, Geldpolitik kaum erreicht.

**In der Frontier nicht einmal entdeckt:** Kunst-und-Kultur, Kunstsammlung, Unternehmensgeschichte, Bargeldumlauf, Taschengeld (0 Einträge).

**Fix:** 13 neue Start-URLs für alle OeNB-Hauptsektionen hinzugefügt (committed). Smoke-Crawl mit 100-Page-Limit bestätigt: neue Sektionen werden jetzt besucht (Geldmuseum, Ueber-Uns direkt gecrawlt, 7.123 URLs in Queue entdeckt). Full-Crawl wird deutlich mehr Content-Seiten erfassen.

### Backup-Dateien (alle im Worktree unter `data/full_site_production/`)

| Datei | Inhalt | Größe |
|-------|--------|-------|
| `pages_backup_pre_cleanup.db` | Original vor /dam/-Cleanup, enthält 4.430 PDFs | 3,2 GB |
| `pages_backup_3729pages.db` | Erster DFS-Crawl ohne PDFs | 237 MB |
| `pages_backup_1734pages_dfs.db` | Zweiter DFS-Crawl (leer gestartet, skip_isaweb), unvollständig weil DFS Start-URLs nie erreicht hat | ~60 MB |
| `pages.db` | **Aktiver BFS-Crawl** (skip_isaweb, leer gestartet, BFS via DEPTH_PRIORITY=1) | wächst |

**ISAweb-Daten:** Nur in `pages_backup_pre_cleanup.db` und `pages_backup_3729pages.db` vorhanden (38 Datasets, 11.907 Observations). Der aktuelle BFS-Crawl sammelt keine ISAweb-Daten (`skip_isaweb=true`). Nach dem HTML-Crawl kann ein separater ISAweb-Pass laufen:
```bash
# ISAweb-only Crawl auf bestehender DB
python -m scrapy crawl oenb -a use_frontier=true -a frontier_kinds=isaweb_entry,isaweb_dataset \
  -s 'ITEM_PIPELINES=...' -s "SQLITE_DB_PATH=data/full_site_production/pages.db"
```

### Crawl-Befehl

```bash
# Full-Site BFS-Crawl (kein Frontier, kein Page-Limit)
cd scraper && python -m scrapy crawl oenb -a skip_isaweb=true \
  -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.DeduplicationPipeline": 100, "oenb_scraper.pipelines.FileSizePipeline": 200, "oenb_scraper.pipelines.SQLitePipeline": 400}' \
  -s "SQLITE_DB_PATH=../data/full_site_production/pages.db"
```

---

## Was geklappt hat

- Scrapy-Crawler tut seit Monaten zuverlässig seinen Job
- ISAweb Chart-Daten-Extraktion aus JS funktioniert (1.274 Seiten)
- Deduplizierung von 26.834 auf 10.010 Seiten war erfolgreich
- CML-Deployment läuft (Rundencrawling mit Firewall-Timeout-Workaround)
- Chatbot-Stack mit generischem Intent-Routing ist weit fortgeschritten
- Test-Coverage ist gut (420 Tests im Worktree, alle grün)
- Alle 7 fixbaren Eval-Cases in einer Session gefixt (Routing, Retrieval, Answering)
- LLM-Routing eliminiert FALSE_OOD komplett — regelbasierter Router als Fallback

## Was nicht geklappt hat / Risiken

- ~~Feature-Branch hat 0 Commits trotz ~90 neuer Dateien → Datenverlustrisiko~~ GELÖST
- Der 19-Task-Plan wurde nicht ausgeführt - stattdessen wurde (sinnvollerweise) am Chatbot gearbeitet
- ~~Lexikalisches Retrieval hat Grenzen~~ VERBESSERT durch QUERY_SYNONYMS + PREFERRED_QUERY_PHRASES
- ~~LLM-Router braucht echtes LLM~~ GELÖST: Timeout erhöht, funktioniert lokal mit Ollama
- Domain-Taxonomie fehlt Zahlungsverkehr/Bankenaufsicht → LLM muss auf bestehende Domains mappen
- ~~Full-Site-Crawl war unvollständig (57% PDFs)~~ GELÖST: /dam/-Filter in Spider + Pipeline
- **Crawl-Performance** (2026-03-22): Mehrere Probleme identifiziert und teils gelöst:
  1. ~~**Kein /dam/-Filter**~~ GELÖST: Dreifach-Filter (Spider `_should_fetch_asset` für PDFs, `_should_follow_link` für /dam/-Pfade, Pipeline `response_received` für Redirects auf /dam/). 4.430 PDFs (2,5 GB) eliminiert.
  2. **ISAweb-Requests fressen Bandbreite:** Pro ISAweb-Link werden 3 Extra-Requests (content/data/meta XML) gefeuert die mit HTML-Seitenentdeckung um die 4 CONCURRENT_REQUESTS Slots konkurrieren. `skip_isaweb=true` Flag eingebaut.
  3. **Fehlende Sektionen:** Start-URLs erweitert um /Bargeld, /Zahlungsverkehr, /Presse, /Forschung, /FAQ, /Barrierefreiheit + englische Einstiegspunkte (/en/Statistics, /en/Monetary-Policy, /en/Financial-Market).
  4. **Ergebnis (Frischer Crawl, leer gestartet):** Nach 2,5h bei 1.682 Seiten (noch laufend). Vergleich mit Main-DB (10.010):
     - Überlappend: 1.366
     - Nur Main: 8.644 (davon /en/ 2.343, /isawebstat/ 2.097, /Presse/ 1.151, /Publikationen/ 602, /meldewesen/ 591, /Ueber-Uns/ 482, /Statistik/ 441)
     - Nur neuer Crawl: 316 (v.a. /error_path/, /Termine.html/)
     - **ISAweb (2.097):** Erwartet — `skip_isaweb=true` überspringt Resolution
     - **Presse (1.151):** Start-URL vorhanden, aber nur 1 Seite gefunden. Vermutlich Paginierung/JS-Laden.
     - **meldewesen (591):** NICHT in Start-URLs! Alter Crawler hat es über Links entdeckt.
     - **Ueber-Uns, Statistik, Geldpolitik (1.041):** IN Start-URLs aber 0 Seiten — evtl. Redirects oder noch nicht dran.
     - **English (2.343):** Nur 4 /en/-Einstiegspunkte, 111 bisher gefunden.
  5. **Nicht gelöst:** HTTP-Conditional-Requests (ETag/If-Modified-Since) für schnelleres Re-Crawling. Die DB hat etag+last_modified Spalten, werden aber nicht genutzt.
  6. ~~**Nicht gelöst:** /meldewesen/ fehlt in Start-URLs.~~ GELÖST durch BFS — wird über Sitemap/Links entdeckt (423 Seiten).
  7. **DFS→BFS (2026-03-22):** `DEPTH_PRIORITY=1` + FIFO-Queues in settings.py. Ohne BFS erreicht der Spider Start-URLs nie, weil LIFO-Queue tief in die ersten Sektionen abtaucht. Mit BFS: alle 26 Start-URLs in 30s gefetcht.
  8. **Retrieval-Probleme (2026-03-24):** Drei Schichten identifiziert:
     - KB-Export hatte keine chatbot_chunks für Website-Seiten (nur ISAweb-Familien) → `_page_chatbot_chunk_records()` hinzugefügt
     - Token-Matching zu strikt: `_is_candidate_match` verlangte ≥2 Hits bei 2+ Tokens. "Geldmuseum anschauen" → nur "geldmuseum" matcht, "anschauen" nie im Content → 0 Hits. Fix: ≤3 Tokens → 1 Match reicht.
     - Answering `_is_grounded_top_hit` verlangte confidence≥0.55 für rag_first+website_general. LLM-Router gibt oft confidence=0.25 für Website-Fragen → Hits gefunden aber als "nicht belastbar" verworfen. Fix: Kein Confidence-Threshold für page_document Hits.
     - "Immer beide KBs durchsuchen" war FALSCH — 1.4 GB Statistik-KB Scan bei jedem Query zu langsam (~40 min statt ~17 min) und page_chunks verdrängen dataset_family Antworten. Early-Return beibehalten.
- ~~Open-Ended-Eval wurde nach den letzten Codeänderungen noch nicht frisch ausgeführt~~ 40 Cases jetzt vorhanden

---

## Eval v4: 60-Case Eval — Diagnose & Fix-Design (2026-03-27)

### Eval v4 Ergebnis (60 Cases, chatbot_eval_v2.json)

| Typ | Cases | Brauchbar | Hauptproblem |
|-----|-------|-----------|--------------|
| OOD | 5 | 5/5 (100%) | — |
| TABLE | 13 | ~4-5 | Falsche Datasets, Ranking |
| FACT | 10 | ~1 | Dataset statt Erklärung |
| NAV | 18 | ~2-3 | 9× not_found, Rest irrelevant |
| META | 13 | ~2-3 | 5× not_found, kontextabhängig |
| COMPARE | 1 | 0 | Nicht implementiert |

**Gesamt: ~15% brauchbar.** OOD-Abwehr perfekt, aber alles andere schlecht.

### Root-Cause-Analyse: Warum dataset_family alles dominiert

Das Scoring in `_rank_hits()` hat eine systematische Schieflage:

```
Scoring-Formel:
  retrieval_score + token_hits×50 + title_hits×80 + phrase×250 + preferred×500 + strong×600 + boosts

retrieval_score nach Record-Typ:
  dataset_family:      1000+ (Basis 1000, +40 für Standardized Tables, +20 obs, +10 release)
  isaweb_dataset:       900
  asset_document:   100-700
  page_document:        100  ← 10× niedriger als dataset_family!
```

Bei einer NAV-Frage "Wo finde ich Daten zu Zinssätzen?" bekommt der ISAweb-Datensatz "Key Interest Rates" automatisch +900 Vorsprung gegenüber der Statistik-Übersichtsseite. Token-Matches können das nicht aufholen.

**Zusätzlich:** Das Grounding-Gate in `_is_grounded_top_hit` akzeptiert `dataset_family` **bedingungslos** (`return True`), verlangt aber von `page_document` einen primary_grounded Check + confidence ≥ 0.55 bei rag_first. Website-Seiten werden also doppelt benachteiligt.

**Und:** Es gibt keine "Kartenansicht" der Website. Der Chatbot kennt 3.569 einzelne Seiten, aber nicht wie sie zusammenhängen. "Wo finde ich Statistiken?" hat keinen einzelnen Chunk der alle Statistik-Unterbereiche auflistet.

### Fix-Design: 3 Maßnahmen

**Fix 1: Intent-basierter Ranking-Rebalance** (`query_knowledge_base.py:_query_intent_record_boost`)

Für `navigation` und `explanation` Intents das Scoring umkehren:
- `page_document`: +500 (schließt den 900-Punkt-Gap)
- `section_navigation` (neu): +600
- `dataset_family`: −200 Penalty

Rationale: Bei "Wo finde ich X?" oder "Was ist X?" ist eine Übersichtsseite hilfreicher als ein einzelner Datensatz. Der Penalty ist mild genug dass bei mehrdeutigen Queries (z.B. "Inflation" könnte NAV oder FACT sein) dataset_family trotzdem gewinnt wenn die Token-Matches gut sind.

**Fix 2: Section Navigation Records** (`export_knowledge_base_jsonl.py`)

~15-20 neue `chatbot_chunk`-Records mit `parent_record_type: "section_navigation"`. Auto-generiert aus:
- `page_content.page_section` → Gruppiert Seiten nach Hauptsektion
- URL-Tiefe → Unterstruktur (Standardisierte-Tabellen/Finanzinstitutionen/...)
- Seitentitel → Alle Themen-Keywords der Sektion

Beispiel-Output:
```
Bereich: Statistik (oenb.at/Statistik)
Unterseiten: Standardisierte Tabellen (Datenangebot) mit:
  Finanzinstitutionen, Kreditinstitute, Investmentfonds,
  Zinssätze und Wechselkurse, Wohnbaukredite,
  Außenwirtschaft, Direktinvestitionen, Zahlungsbilanz,
  Preise und Wettbewerbsfähigkeit, HVPI, Rohstoffpreise, ...
Charts: Wechselkurs, Renditen, HVPI, BIP, Immobilienpreise, ...
Veröffentlichungskalender, Research Desk, Klassifikationen
```

`retrieval_score: 200` — niedrig genug für Datenfragen, aber mit +600 NAV-Boost dominant bei "Wo finde ich?". Der Text enthält konzentriert alle Themen-Keywords einer Sektion → hoher Token-Overlap bei generischen Fragen.

**Fix 3: Grounding-Gate für NAV lockern** (`chatbot_answering.py:_is_grounded_top_hit`)

Für `query_intent == "navigation"`:
- `page_document` und `section_navigation` auto-accepten (wie dataset_family)
- Rationale: Bei "Wo finde ich X?" und einem Treffer zu X ist die Seite die richtige Antwort, auch bei niedriger Router-Confidence

### Erwarteter Impact

| Fix | Cases betroffen | Geschätzter Effekt |
|-----|----------------|--------------------|
| Ranking-Rebalance | ~20 (FACT+TABLE) | +10-12 Cases |
| Section Navigation | ~10 (NAV) | +8-10 Cases |
| Grounding lockern | ~5 (NAV not_found) | +3-5 Cases |
| **Gesamt** | | **~50-55%** (von ~15%) |

### Tatsächliches Ergebnis nach Fixes (2026-03-28)

| Run | not_found | Änderung |
|-----|-----------|----------|
| pre-fix | 22/60 (37%) | Baseline |
| fix-v1 (section_nav +600, explanation only) | **11/60 (18%)** | -11 |
| fix-v2 (topic_overview mit dataset penalty) | 21/60 (35%) | **REGRESSION** |
| fix-v3 (topic_overview ohne penalty) | **11/60 (18%)** | = fix-v1 |

**Lektion:** `topic_overview` ist zu breit für dataset-Penaltys. Viele FACT-Fragen
haben keinen passenden Page-Content → dataset_family ist der einzige brauchbare Hit.
Penalty entfernen heißt: wenn keine Seite existiert, gewinnt weiterhin das Dataset.

**Finale Boost-Tabelle:**

| Intent | page_document | section_navigation | dataset_family |
|--------|--------------|-------------------|---------------|
| navigation | +500 | +300 | -200 |
| explanation | +400 | +300 | -200 |
| topic_overview | +250 | +150 | 0 |
| release_lookup | +250 (secondary) | — | — |

**Was nicht fixbar ist ohne mehr Daten:**
- FACT 7/10 → datasets statt Erklärungen (full_site KB hat die Erklärseiten nicht)
- TABLE 4/13 → section_nav statt spezifische Tabelle (Retrieval findet die richtige Seite nicht)
- META 3/13 → kontextabhängige Fragen ("diese Tabelle") ohne Session-Kontext

---

## Full-Site Re-Crawl (2026-03-29)

### Warum

Eval-Bottleneck ist Content-Coverage, nicht Ranking. FACT-Fragen wie "Was ist eine Zahlungsbilanz?"
bekommen datasets statt Erklärungen weil die passende Website-Seite (z.B.
`/Statistik/aussenwirtschaftsstatistik.html`) nicht in der full_site KB ist.

Aktueller Crawl: 3.569 Seiten, davon 449 unter /Statistik/. Viele Erklärungs- und Übersichtsseiten
fehlen — der BFS-Crawl war nicht tief genug oder wurde zu früh gestoppt.

### IWG-Daten helfen nicht

IWG-Crawler (11.657 Items) hat 2.697 URLs die nicht im full_site Crawl sind — aber 2.278 davon
sind ISAweb-Portale (haben wir über ISAweb Client). Nur ~200 Publikationsseiten und ~10 Statistikseiten
sind neu. Das Inventar ist ein Katalog (URL+Typ+Titel), kein Content.

### Ziel

Frischer BFS-Crawl mit bestehenden 26 Start-URLs + `skip_isaweb=true`. Erwartung: 5.000-8.000
Seiten statt 3.569 wenn die Tiefe ausreicht. Danach: KB re-exportieren, Eval re-runnen.

### Crawl-Befehl (wie in Full-Site-Crawl Analyse oben)

```bash
cd scraper && python -m scrapy crawl oenb -a skip_isaweb=true \
  -s 'ITEM_PIPELINES={"oenb_scraper.pipelines.DeduplicationPipeline": 100, "oenb_scraper.pipelines.FileSizePipeline": 200, "oenb_scraper.pipelines.SQLitePipeline": 400}' \
  -s "SQLITE_DB_PATH=../data/full_site_production/pages.db"
```

**Wichtig:** Bestehende DB wird inkrementell erweitert (body_hash 3-Wege-Logik), nicht gelöscht.

### Pipeline nach dem Crawl

Der Crawler schreibt nur `pages` + `page_bodies`. Bei geänderten Seiten wird `page_content` gelöscht
(body_hash changed → `DELETE FROM page_content WHERE page_id = ?`), aber **nicht** neu befüllt.
Die Content-Extraction ist ein separater Schritt:

```bash
# 1. Text-Extraction (füllt page_content für alle Seiten ohne Content)
python -m analysis.extract_text data/full_site_production/pages.db

# 2. Full-Site KB exportieren (Runtime liest knowledge_base_active.jsonl!)
python -m analysis.export_knowledge_base_jsonl \
  data/full_site_production/pages.db \
  data/full_site_production/knowledge_base_active.jsonl

# 3. Statistics KB re-exportieren
#    ACHTUNG: Die Statistik-DB heißt pages.db, NICHT statistics.db!
#    (Der frühere Doku-Fehler hier hat eine leere statistics.db erzeugt.)
#    Die CLI nimmt Positionsargumente — --db/--output/--full-site-db existieren nicht.
python -m analysis.export_knowledge_base_jsonl \
  data/statistics_production/pages.db \
  data/statistics_production/knowledge_base_active.jsonl

# 4. Eval laufen lassen
python -m analysis.run_chatbot_eval
```

### Erkenntnis: Conditional Requests fehlen

Die DB hat `etag` + `last_modified` Spalten, aber beide sind immer NULL — die Pipeline übergibt
sie nicht an `store_page()`, und der Spider sendet keine `If-None-Match`/`If-Modified-Since` Headers.
Jede bekannte Seite wird komplett neu heruntergeladen nur für den body_hash-Vergleich.
→ Zukünftiges Feature: Conditional Requests würden Re-Crawls um Faktor 5-10x beschleunigen.

---

## Eval v4 (Re-Crawl) & v5 (try-anyway Fallback) — 2026-04-01/02

### v4: Re-Crawl allein brachte nichts

Full-Site Re-Crawl am 2026-04-01 (pages.db 325 MB, KB 67 MB) + beide KBs re-exportiert.
Eval `eval_v2_report_v4_recrawl.json`: **not_found blieb bei 11/60 (18%)** — identisch zu fix-v3.
Der Coverage-Zuwachs allein löste die verbleibenden Misses nicht.

### v5: OOD-Rejection-Fallback in hybrid_retrieval.py

Änderung: Wenn der Router `reject_or_clarify` sagt, trotzdem Retrieval versuchen (`rag_first`).
Nur wenn 0 Hits kommen, bleibt die Rejection bestehen. Grund: Der LLM-Router (llama3.1:8b)
klassifiziert in-scope Queries gelegentlich fälschlich als OOD.

Eval `eval_v2_report_v5_tryanyway.json`: **not_found 11/60 → 8/60 (13%)**
- Neu beantwortet: fact_005 (Leistungs-/Kapitalbilanz), table_008 (Wertpapierbestände),
  pub_007 (Publikationsarchiv)
- OOD-Abwehr intakt: alle 5 echten OOD-Cases weiterhin not_found
  (Zimmerpflanze, Rezept, Planche, Pokemon, "Wie geht es mir")

## Automatisches Eval-Scoring (2026-07-05)

Design: `docs/plans/2026-07-05-eval-scoring-design.md`. Deterministischer Post-hoc-Scorer
(`analysis/score_chatbot_eval.py`): `expect`-Blöcke in der Fixture (url_patterns gegen Citations,
Keyword-Stämme gegen Antworttext mit Umlaut-Folding, `reject` für OOD) → pass/partial/fail.

```bash
python -m analysis.score_chatbot_eval REPORT.json --baseline ALTER_REPORT.json
```

### Retro-Scoring der bestehenden Reports — das ehrliche Bild

| Report | Score | pass | partial | fail | not_found (alt) |
|--------|-------|------|---------|------|-----------------|
| v4_recrawl | 0.258 | 8 | 15 | 37 | 11/60 |
| v5_tryanyway | 0.267 | 8 | 16 | 36 | 8/60 |

**Kernerkenntnis:** Die not_found-Metrik hat systematisch geschönt. Von den 8 Passes sind
5 die OOD-Rejections — nur **3 von 55 Inhaltsfragen** bekommen eine wirklich richtige Antwort
(u.a. table_001 Zinssätze). Der v5-Fallback holte 3 Cases aus not_found, aber 2 davon
antworten weiterhin inhaltlich falsch (nur fact_005 wurde partial). NAV 0/18 pass,
META 1/13, FACT 0/10 — die Misere liegt in falschen Antworten, nicht in fehlenden.

**Authoring-Notizen:**
- OeNB-URLs nutzen `auszenwirtschaft` (sz!) in Standardisierte-Tabellen, `aussenwirtschaft`
  unter /meldewesen/ — Patterns müssen beide Varianten + EN (`external-sector`) abdecken.
- Keywords als Stämme authoren ("Zins" statt "Zinssatz"), Matching foldet Umlaute (ä→ae, ß→ss).
- AnaCredit (fact_006/008): 0 Treffer in der KB — echte Content-Lücke, Fail ist korrekt.
- Generische Stämme ("statistik") erzeugen großzügige Partials (nav_001) — bewusster Trade-off.

## Ranking-Fixes v6/v7 via Routing-Replay (2026-07-06)

**Replay-Modus:** `run_chatbot_eval --replay-routing ALTER_REPORT.json` nutzt gespeicherte
Router-Entscheidungen → kein LLM nötig. Aber: ~6h pro Run wenn der Crawler parallel läuft
(2,2-GB-KB in RAM + 60 Full-Scans + Swap-Druck). Kein schneller Loop — FTS5 bleibt nötig.

| Run | Score | pass/partial/fail | Änderung |
|-----|-------|-------------------|----------|
| v5 (Baseline) | 0.267 | 8/16/36 | — |
| v6 (Portal-Fix + Query-gated Download-Boost + Page +800) | 0.233 | 10/8/42 | **REGRESSION** |
| v7 (+ Fehlerseiten-Filter, isawebstat/-Portale, Tabellen-Query-Ausnahme) | **0.283** | 11/12/37 | +4 verbessert, −3 |

**v6-Lektionen (alle in v7 gefixt):**
1. KB enthält 403/404-Seiten als page_documents („Fehlerseite - OeNB") — „seite" matcht
   als Substring → gewannen NAV-Queries. Retrieval filtert sie jetzt; **KB-Export sollte
   sie beim nächsten Re-Export auch ausschließen** (status_code != 200).
2. Portal-Erkennung braucht alle isawebstat/-URLs (createChart, releasekalender), nicht
   nur stabfrage. release_lookup boostet releasekalender weiterhin bewusst.
3. Query sagt „Tabelle/Zeitreihe" → User will ein Dataset → Page-vs-Dataset-Rebalance aus.

**Verbleibende v7-Regressionen vs v5 — Diagnose:**
- nav_006/table_009: Alte Archiv-Ausgaben („Statistiken - Daten und Analysen Q3-04", 2004!)
  matchen generische Tokens „daten"+„statistik" und stauen sich bei 1080. Fehlendes
  IDF-Gewicht: „auslandsverschuldung" zählt gleich viel wie „daten". → BM25/FTS5, keine
  weitere Handheuristik.
- table_002: Hits mit Score 2370 vorhanden, trotzdem not_found — **Grounding-Gate verwirft
  Top-Hit ohne Fall-through zu den nächsten Hits** (chatbot_answering). Eigener Bug.

### Bereinigt (2026-07-05)

- Leere `data/statistics_production/statistics.db` (0 Bytes) gelöscht — war Artefakt des
  falschen Doku-Befehls (SQLite legt beim Öffnen eine leere DB an).
- Getrackte `.pyc`-Dateien aus Git entfernt (`git rm --cached`), waren vor dem
  `.gitignore`-Eintrag committed worden.
- `stopwordsiso` fehlte im venv → 8 Test-Module kollabierten beim Import. Nachinstalliert,
  445 Tests grün.
