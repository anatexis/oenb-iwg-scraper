# Alternative: Agentic Search statt RAG

> **Status:** Notiz für später. Aktuell wird zuerst der RAG-Ansatz getestet.

## Hintergrund

Boris Cherny (Claude Code Team, Anthropic) berichtet, dass frühe Versionen von Claude Code RAG + lokale Vector DB verwendeten, aber agentic search sich als besser herausstellte:

> "Early versions of Claude Code used RAG + a local vector db, but we found pretty quickly that agentic search generally works better. It is also simpler and doesn't have the same issues around security, privacy, staleness, and reliability."

## Was ist Agentic Search?

Statt Text vorab in Embeddings umzuwandeln und per Similarity Search zu suchen, bekommt das LLM **Tools** (SQL, Grep, etc.) und sucht selbst nach relevanten Informationen.

## Vorteile gegenüber RAG

- **Keine Staleness** - Immer aktuelle Daten, kein Re-Indexing nötig
- **Präziser** - LLM kann gezielt nachfragen und Suche verfeinern
- **Einfacher** - Kein Embedding-Modell, kein Vector Store, keine Chunking-Strategie
- **Privacy** - Daten bleiben in SQLite, werden nicht in separaten Store kopiert
- **Zuverlässiger** - Kein "Lost in the Middle" Problem bei der Chunk-Auswahl

## Umsetzung für OeNB-Bot

Bereits vorhanden:
- SQLite mit 26.834 Seiten + extrahiertem Text
- Metadaten: Section, Sprache, URL, Titel

Der Bot bräuchte nur Tools wie:
```python
# Tool 1: Volltextsuche
SELECT title, url, SUBSTR(text_content, 1, 500)
FROM page_content
WHERE text_content LIKE '%suchbegriff%'
LIMIT 10

# Tool 2: Seite lesen
SELECT text_content FROM page_content
WHERE page_id = ?

# Tool 3: Sections auflisten
SELECT DISTINCT page_section, COUNT(*)
FROM page_content
GROUP BY page_section

# Tool 4: FTS5 (SQLite Full-Text Search, optional)
SELECT title, url, snippet(page_fts, 1, '<b>', '</b>', '...', 30)
FROM page_fts
WHERE page_fts MATCH 'suchbegriff'
```

## Wann umsteigen?

Nach dem RAG-Test evaluieren:
1. Wenn RAG-Ergebnisse schlecht sind → Agentic Search als Alternative
2. Wenn RAG-Ergebnisse gut sind → Trotzdem vergleichen (weniger Infrastruktur)
3. Für Cloudera ML prüfen: Welcher Ansatz passt besser zur Plattform?

## Referenzen

- Boris Cherny (@bcherny) - Claude Code Entwickler
- Claude Code Architektur: Agentic Search > RAG für Code-Assistenten
