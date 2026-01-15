# IWG-Bestandsliste Export - Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** CSV-Export aller erfassten Datenressourcen für die IWG-Bestandsliste mit Filteroptionen.

**Architecture:** Neuer Button im Dashboard-Tab "Übersicht", der einen Filter-Dialog öffnet und dann CSV generiert.

**Tech Stack:** JavaScript (im Dashboard-Template), CSV-Generation client-side

---

## Anforderungen

### Button
- Position: Tab "Übersicht", unter den Statistik-Karten
- Label: "IWG-Bestandsliste exportieren"
- Öffnet Modal-Dialog mit Filteroptionen

### Filter-Dialog
Drei Filter-Gruppen mit Checkboxen (alle standardmäßig ausgewählt):

**Typ:**
- [ ] Downloads
- [ ] Interaktive Portale (interactive_data)
- [ ] Standardisierte Tabellen (standardized_tables)
- [ ] Shiny Apps (shiny_app)
- [ ] Webseiten mit Daten (webpage_with_data)

**Format:**
- [ ] PDF
- [ ] CSV
- [ ] XLSX/XLS
- [ ] XML
- [ ] JSON
- [ ] HTML
- [ ] Sonstige

**Bereich:**
- [ ] Statistik
- [ ] Geldpolitik
- [ ] Finanzmarkt
- [ ] (dynamisch aus Daten)

Buttons: "Exportieren" | "Abbrechen"

### CSV-Export

**Spalten:**
| Spalte | Quelle |
|--------|--------|
| Titel | item.title |
| URL | item.url |
| Format | item.file_type |
| Typ | item.type (deutsche Labels) |
| Bereich | item.page_section |
| Sprache | item.language |
| Stand | item.page_date |
| Fundort | item.found_on_page |
| Größe (KB) | item.file_size_bytes / 1024 |
| Maschinenlesbar | item.machine_readable |

**Dateiformat:**
- Semikolon-Trennung (`;`)
- UTF-8 mit BOM
- Dateiname: `oenb-iwg-bestandsliste-YYYY-MM-DD.csv`

### Typ-Labels (Deutsch)
| type | Label |
|------|-------|
| download | Download |
| interactive_data | Interaktives Datenportal |
| standardized_tables | Standardisierte Tabellen |
| shiny_app | Shiny App |
| webpage_with_data | Webseite mit Datentabellen |

---

## Implementation Tasks

### Task 1: Filter-Dialog HTML hinzufügen
- Modal-Struktur in claude_dashboard.html
- Checkbox-Gruppen für Typ, Format, Bereich
- Buttons für Exportieren/Abbrechen

### Task 2: JavaScript für Dialog
- Modal öffnen/schließen
- Checkboxen dynamisch aus Daten befüllen (Formate, Bereiche)
- "Alle auswählen" / "Alle abwählen" pro Gruppe

### Task 3: Export-Funktion
- Items nach ausgewählten Filtern filtern
- CSV mit deutschen Typ-Labels generieren
- Download triggern

### Task 4: Button in Übersicht-Tab
- Button unter Statistik-Karten einfügen
- Click-Handler für Modal

### Task 5: Testen
- Dashboard generieren
- Filter testen
- CSV öffnen und prüfen

---

## Nicht im Scope (Phase 2+)
- Beschreibungsfeld
- Lizenz-Feld
- DCAT-AP-AT RDF Export
- ZIP-Inhalte
