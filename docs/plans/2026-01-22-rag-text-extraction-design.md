# RAG Text-Extraction Design

## Ziel

Seitentext der OeNB-Website extrahieren und speichern für späteren Chatbot/RAG-Einsatz.

## Scope

**In Scope:**
- Raw HTML speichern (compressed)
- Text-Extraktion in separate Tabelle
- Lokaler Zugriff via SQLite
- Export nach Parquet für Cloudera ML

**Nicht in Scope (später):**
- Embedding-Generierung
- Modellauswahl
- Chat-Interface

## Zielgruppe

Allgemeiner OeNB-Auskunfts-Bot für:
- Interne OeNB-Mitarbeiter (schneller Zugriff auf Statistiken/Publikationen)
- Externe Datennutzer (Journalisten, Forscher)

## Infrastruktur

- Komplett lokal (keine Cloud-APIs)
- SQLite als Primärspeicher
- Parquet-Export bei Bedarf für Cloudera/Hive/Iceberg

## Geschätzte Größen

| Was | Größe |
|-----|-------|
| Raw HTML (~33k Seiten, gzip) | ~100-150 MB |
| Extrahierter Text | ~50-80 MB |
| SQLite gesamt | ~200-250 MB |
| Parquet Export | ~50-100 MB |

## Datenbank-Schema

```sql
PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- Crawl Run Metadata
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crawl_runs (
  id          INTEGER PRIMARY KEY,
  seed_url    TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  user_agent  TEXT
);

------------------------------------------------------------
-- Pages (HTTP metadata)
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pages (
  id               INTEGER PRIMARY KEY,
  crawl_run_id     INTEGER REFERENCES crawl_runs(id) ON DELETE SET NULL,

  url              TEXT NOT NULL UNIQUE,
  final_url        TEXT,
  status_code      INTEGER,
  content_type     TEXT,
  fetched_at       TEXT,
  fetch_ms         INTEGER,
  bytes_downloaded INTEGER,

  etag             TEXT,
  last_modified    TEXT,

  body_hash        TEXT,
  headers_json     TEXT,

  fetch_error      TEXT
);

CREATE INDEX IF NOT EXISTS idx_pages_fetched_at ON pages(fetched_at);
CREATE INDEX IF NOT EXISTS idx_pages_body_hash  ON pages(body_hash);
CREATE INDEX IF NOT EXISTS idx_pages_final_url  ON pages(final_url);

------------------------------------------------------------
-- Raw HTML Storage (compressed)
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS page_bodies (
  page_id      INTEGER PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
  storage      TEXT NOT NULL CHECK(storage IN ('file','db')),
  compression  TEXT NOT NULL DEFAULT 'gzip' CHECK(compression IN ('none','gzip','zstd')),
  file_path    TEXT,
  body_blob    BLOB
);

------------------------------------------------------------
-- Extracted Content (for RAG)
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS page_content (
  page_id           INTEGER PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,

  title             TEXT,
  text_content      TEXT,
  page_section      TEXT,
  language          TEXT,

  extracted_at      TEXT,
  extractor_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_content_section ON page_content(page_section);
```

## Workflow

```
1. Scrapy crawlt OeNB
         ↓
2. Pipeline speichert in SQLite:
   - pages (HTTP metadata)
   - page_bodies (raw HTML, gzip compressed)
         ↓
3. Extraktion-Script (separat):
   - Liest page_bodies
   - Extrahiert clean text
   - Schreibt page_content
         ↓
4. (Später) Embedding-Script:
   - Liest page_content
   - Generiert Embeddings
   - Speichert in page_embeddings
         ↓
5. Export bei Bedarf:
   - SQLite → Parquet für Cloudera ML
```

## Vorteile

- **Einmal crawlen, mehrfach extrahieren**: Raw HTML gespeichert
- **Extraktion verbesserbar**: Bei besserer Logik nur page_content neu generieren
- **Lokal + Cloud**: SQLite für Entwicklung, Parquet für Produktion
- **Inkrementell**: etag/last_modified für Delta-Crawls

## Nächste Schritte

1. SQLite-Pipeline für Scrapy implementieren
2. Text-Extraktion-Script schreiben
3. Parquet-Export-Script erstellen
