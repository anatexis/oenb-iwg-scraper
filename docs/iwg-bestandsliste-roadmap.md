# IWG-Bestandsliste - Roadmap

## Aktueller Stand (Phase 1)

Export als CSV/Excel mit folgenden Feldern:
- Titel
- URL (Access URL)
- Format (file_type)
- Kategorie (page_section)
- Sprache
- Stand/Datum (page_date)
- Fundort (found_on_page)
- Dateigröße
- Maschinenlesbar (ja/nein)
- Typ (download, interactive_data, standardized_tables, etc.)

## Fehlend für DCAT-AP-AT Konformität (Phase 2)

| Feld | Status | Aufwand |
|------|--------|---------|
| Beschreibung | Fehlt | Mittel - aus Kontext extrahieren oder manuell |
| Publisher | Hardcoded "OeNB" | Gering - Konfiguration |
| Kontakt | Fehlt | Gering - Konfiguration |
| Lizenz | Fehlt | Klärung mit OeNB nötig |
| Keywords | Fehlt | Mittel - aus Titel/Section ableiten |
| Räumlicher Bezug | Fehlt | Gering - meist "Österreich" |
| Zeitlicher Bezug | Teilweise (page_date) | Mittel - Zeitreihen erkennen |

## Zukünftige Erweiterungen (Phase 3)

### ZIP-Inhalte erfassen
- ZIPs herunterladen und Dateiliste extrahieren
- Neues Feld `zip_contents: ["file1.csv", "file2.json", ...]`
- Optional: Nur ZIPs < 50 MB

### DCAT-AP-AT Export
- RDF/XML oder JSON-LD Format
- Direkt harvesterbar für data.gv.at
- Dataset/Distribution Struktur

### Automatische Beschreibungen
- Umgebenden Text auf Fundseite extrahieren
- Oder: GPT-basierte Zusammenfassung aus Titel + Kontext

## Offene Fragen

- [ ] Welche Lizenz gilt für OeNB-Daten?
- [ ] Soll die Liste auf data.gv.at veröffentlicht werden?
- [ ] Gibt es eine bestehende Kontakt-E-Mail für Datenanfragen?
