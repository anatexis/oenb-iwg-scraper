# IWG-Compliance Erweiterung + Sitemap-Visualisierung

## Übersicht

Erweiterung des Crawlers für volle IWG-Compliance und Integration einer Tufte-Stil Sitemap-Visualisierung ins Dashboard.

## Spider-Erweiterungen

### Neue Dateiformate

Hinzufügen zu `DOWNLOAD_EXTENSIONS`:
- Text/Docs: `.txt`, `.odt`, `.rtf`, `.epub`
- Geo: `.geojson`, `.kml`, `.gml`
- Strukturierte Daten: `.rdf`, `.ttl`, `.ods`

### HTML-Tabellen erkennen

- Bei jeder Seite prüfen: `response.css("table")`
- Neues Feld: `has_html_tables: bool`
- Neuer Typ: `type: "webpage_with_data"`
- Nur Seiten mit substantiellen Tabellen erfassen (min. 3 Zeilen)

### API-Endpunkte erkennen

- URL-Patterns: `/api/`, `/rest/`, `/oearb/`, `/data/`
- Content-Type validieren: `application/json`, `application/xml`
- Neuer Typ: `type: "api_endpoint"`

## Dashboard-Visualisierung

### Neuer Tab: "Sitemap"

Position: 5. Tab nach "Nicht IWG Relevant"

### Visualisierung

- Horizontale Balken, proportional zur Seitenzahl
- Tufte-Stil: keine Gitternetzlinien, hohe Daten-Tinte-Ratio
- Klickbare Links zu OeNB-Bereichen
- Hover-Effekt für Interaktivität

### Layout

```
[Bereich]       [Balken]                  [Seiten] │ [Downloads]
Statistik       ████████████████████████  73       │ 2.847
Über-Uns        ██████████████████████    92       │ 1.203
...
```

### Datenquellen

- Sitemap-Struktur: statisch aus geparstem HTML
- Download-Zahlen: dynamisch aus Crawl-Daten

## Dateien

### Zu ändern

1. `scraper/oenb_scraper/spiders/oenb_spider.py` - Neue Formate, Tabellen, APIs
2. `scraper/oenb_scraper/items.py` - Neue Felder
3. `analysis/templates/claude_dashboard.html` - Sitemap-Tab
4. `analysis/generate_claude_dashboard.py` - Sitemap-Daten

### Neu

- `analysis/sitemap_parser.py` - HTML-Sitemap parsen

## Verifizierung

1. Tests für neue Dateiformate
2. Tests für Tabellen-Erkennung
3. Tests für API-Erkennung
4. Dashboard öffnen, Sitemap-Tab prüfen
5. Links klicken, OeNB-Seiten öffnen
