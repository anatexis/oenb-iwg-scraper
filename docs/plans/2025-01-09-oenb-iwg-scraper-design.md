# OeNB Downloads Scraper - IWG-Analyse Design

## Ziel

Web-Scraper für oenb.at der alle Downloads erfasst und eine IWG-Relevanz-Analyse erstellt. Output: Interaktives HTML-Dashboard für den Open Data Beauftragten.

## Architektur

```
┌─────────────────┐
│   OeNB Website  │
│   + Sitemap     │
└────────┬────────┘
         │ Scrapy crawlt
         ▼
┌─────────────────┐
│  oenb_scraper   │
│  (Python/Scrapy)│
└────────┬────────┘
         │ speichert
         ▼
┌─────────────────┐
│  downloads.json │  ← Single Source of Truth
└────────┬────────┘
         │ analysiert
         ▼
┌─────────────────┐
│  analyze.py     │
│  - IWG-Heuristik│
│  - Konfidenz    │
└────────┬────────┘
         │ generiert
         ▼
┌─────────────────────────────────┐
│  output/                        │
│  ├── dashboard.html (interaktiv)│
│  └── downloads.csv  (für Excel) │
└─────────────────────────────────┘
```

## Projektstruktur

```
oenb_downloads/
├── scraper/          # Scrapy-Projekt
├── analysis/         # IWG-Analyse & Dashboard-Generator
├── data/             # JSON-Output vom Scraper
├── output/           # Generierte Reports
└── docs/plans/       # Dieses Dokument
```

## Scraper-Details

### Crawling-Strategie

- Start: `https://www.oenb.at/Service/Sitemap.html` + Hauptnavigation
- Folgt allen internen Links auf `oenb.at`
- Respektiert `robots.txt` und verwendet höfliches Rate-Limiting (1-2 Sekunden zwischen Requests)
- Keine Bereiche ausgeschlossen

### Erfasste Ressourcen

| Typ | Erkennung | Beispiel |
|-----|-----------|----------|
| Downloads | Dateiendung | `.pdf`, `.xlsx`, `.csv`, `.zip`, `.xml` |
| Shiny Apps | URL-Pattern | `shinyapps.io`, `/shiny/`, eingebettete iframes |
| Externe Daten | Domain + Kontext | Links zu Datenbanken, APIs |

### Datenstruktur pro Fund (JSON)

```json
{
  "url": "https://www.oenb.at/.../statistik.xlsx",
  "type": "download",
  "file_type": "xlsx",
  "file_size_bytes": 245760,
  "title": "Zinssätze 2024",
  "found_on_page": "https://www.oenb.at/Statistik/...",
  "page_section": "Statistik",
  "section_heading": "Zinssätze und Wechselkurse",
  "page_date": "2024-12-15",
  "scraped_at": "2025-01-09T14:30:00Z",
  "machine_readable": true,
  "has_tables": true
}
```

## IWG-Analyse

### Fokus: IWG (nicht IFG)

- **IFG (Informationsfreiheitsgesetz)**: Recht auf Zugang - Sache der Rechtsabteilung
- **IWG (Informationsweiterverwendungsgesetz)**: Weiterverwendung von Daten - Kern von Open Data

### Konfidenz-Score Heuristik

| Kriterium | Score-Einfluss |
|-----------|----------------|
| **Dateityp** | XLSX/CSV/XML: +40, PDF: +20, ZIP: +15 |
| **Maschinenlesbar** | Ja: +20, Nein: -20 |
| **Seitenbereich** | Statistik: +25, Meldewesen: +15, Geldpolitik: +10 |
| **Keywords im Titel** | "Daten", "Statistik", "Zeitreihe": +15 |
| **Shiny App** | +30 (Daten bereits visualisiert → sollten auch roh verfügbar sein) |

### Konfidenz-Stufen

- 🟢 **Hoch (70-100)**: Sehr wahrscheinlich IWG-relevant
- 🟡 **Mittel (40-69)**: Prüfung empfohlen
- 🔴 **Niedrig (0-39)**: Vermutlich nicht IWG-pflichtig

### PDF-Analyse

| PDF-Typ | IWG-Relevanz | Erkennung |
|---------|--------------|-----------|
| **Text-PDF** (maschinenlesbar) | Höher | Enthält extrahierbaren Text |
| **Scan-PDF** (Bild) | Niedriger | Nur Bilder, kein Text |
| **PDF mit Tabellen** | Hoch | Strukturierte Daten → sollte als CSV/Excel verfügbar sein |

## Dashboard

### Features

- Zusammenfassungs-Statistiken (Anzahl pro Kategorie, Dateitypen-Verteilung)
- Filter nach Konfidenz-Score, Dateityp, Bereich
- Sortierbare Tabelle
- CSV-Export Button
- Standalone HTML (kein Server nötig)

### Mockup

```
┌────────────────────────────────────────────────────────┐
│  OeNB Downloads - IWG Analyse                    [CSV] │
├────────────────────────────────────────────────────────┤
│  Zusammenfassung:                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │ 247      │ │ 🟢 89    │ │ 🟡 103   │ │ 🔴 55     │ │
│  │ Gesamt   │ │ Hoch     │ │ Mittel   │ │ Niedrig   │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘ │
├────────────────────────────────────────────────────────┤
│  Filter: [Alle ▼] [Dateityp ▼] [Bereich ▼] [Score ▼]  │
├────────────────────────────────────────────────────────┤
│  Datei          │ Typ  │ Bereich   │ IWG  │ Fundort   │
│  ────────────────────────────────────────────────────  │
│  zinssaetze.xlsx│ XLSX │ Statistik │ 🟢 85│ /Stat/... │
│  jahresber.pdf  │ PDF  │ Über uns  │ 🟡 52│ /Ueber/...│
│  app: Inflation │ Shiny│ Geldpol.  │ 🟢 78│ /Geld/... │
└────────────────────────────────────────────────────────┘
```

## Nutzung

```bash
# 1. Scrapen (dauert je nach Website-Größe 10-30 min)
cd scraper && scrapy crawl oenb -o ../data/downloads.json

# 2. Analysieren & Dashboard generieren
python analysis/analyze.py

# 3. Ergebnis öffnen
xdg-open output/dashboard.html  # Linux
open output/dashboard.html       # macOS
```

## Abhängigkeiten

- Python 3.10+
- Scrapy (Web-Scraping)
- PyPDF2 oder pdfplumber (PDF-Textextraktion)
- Jinja2 (HTML-Template)

## Nicht im Scope

- Automatischer Abgleich mit data.gv.at (könnte später ergänzt werden)
- Login-geschützte Bereiche
- Deep-Analysis von PDF-Inhalten

## Nächste Schritte

1. Scrapy-Projekt aufsetzen
2. Spider für oenb.at implementieren
3. PDF-Analyse einbauen
4. IWG-Scoring implementieren
5. Dashboard-Generator bauen
6. Testen & Feintuning
