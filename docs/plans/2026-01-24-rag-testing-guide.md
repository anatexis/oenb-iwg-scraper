# RAG Testing Guide - OeNB Daten

> **Für Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Ziel:** Datenqualität prüfen und RAG-Prototyp lokal testen, bevor Deployment auf Cloudera ML.

**Architektur:** Jupyter Notebook für interaktive Exploration. Ollama für lokale LLMs, ChromaDB als Vector Store.

**Tech Stack:** Python, SQLite, Ollama, ChromaDB, LangChain, Jupyter

---

## Voraussetzungen

### 1. Ollama installieren

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text   # Embedding Modell (~274 MB)
ollama pull llama3             # Chat Modell (~4.7 GB)
```

### 2. Python Packages

```bash
source venv/bin/activate
pip install chromadb langchain langchain-community langchain-ollama jupyter ipywidgets
```

---

## Jupyter Notebook: analysis/rag_exploration.ipynb

### Abschnitt 1: Setup & Laden

```python
import sqlite3
import pandas as pd
from pathlib import Path

# SQLite verbinden
DB_PATH = Path("../data/pages.db")
conn = sqlite3.connect(DB_PATH)

# Basis-Info
pages = pd.read_sql("SELECT COUNT(*) as count FROM pages", conn).iloc[0, 0]
bodies = pd.read_sql("SELECT COUNT(*) as count FROM page_bodies", conn).iloc[0, 0]
content = pd.read_sql("SELECT COUNT(*) as count FROM page_content", conn).iloc[0, 0]

print(f"Pages: {pages:,}")
print(f"Bodies: {bodies:,}")
print(f"Content: {content:,} (0 = Text-Extraktion noch nicht ausgeführt)")
```

### Abschnitt 2: Datenqualität prüfen

```python
# Statistik-Übersicht
stats = pd.read_sql("""
    SELECT
        COUNT(*) as total_pages,
        AVG(LENGTH(text_content)) as avg_text_len,
        MIN(LENGTH(text_content)) as min_text_len,
        MAX(LENGTH(text_content)) as max_text_len
    FROM page_content
""", conn)
print("=== Statistiken ===")
print(stats.to_string(index=False))
```

```python
# Leere oder sehr kurze Seiten
short_pages = pd.read_sql("""
    SELECT p.url, pc.title, LENGTH(pc.text_content) as text_len
    FROM page_content pc
    JOIN pages p ON p.id = pc.page_id
    WHERE LENGTH(pc.text_content) < 100
    ORDER BY text_len
    LIMIT 20
""", conn)
print(f"\n=== Kurze Seiten ({len(short_pages)}) ===")
print(short_pages.to_string())
```

```python
# Duplikate (gleicher Text)
duplicates = pd.read_sql("""
    SELECT text_content, COUNT(*) as count
    FROM page_content
    GROUP BY text_content
    HAVING COUNT(*) > 1
    ORDER BY count DESC
    LIMIT 10
""", conn)
print(f"\n=== Duplikate ({len(duplicates)}) ===")
print(duplicates)
```

```python
# HTML-Reste im Text
import re
html_pattern = re.compile(r'<[^>]+>')

html_issues = pd.read_sql("""
    SELECT page_id, title, text_content
    FROM page_content
    LIMIT 1000
""", conn)

html_issues['has_html'] = html_issues['text_content'].apply(
    lambda x: bool(html_pattern.search(x)) if x else False
)
issues = html_issues[html_issues['has_html']]
print(f"\n=== HTML-Reste ({len(issues)} von {len(html_issues)}) ===")
if len(issues) > 0:
    print(issues[['page_id', 'title']].head(10))
```

```python
# Sprachen-Verteilung
languages = pd.read_sql("""
    SELECT language, COUNT(*) as count
    FROM page_content
    GROUP BY language
    ORDER BY count DESC
""", conn)
print("\n=== Sprachen ===")
print(languages.to_string(index=False))
```

```python
# Section-Abdeckung
sections = pd.read_sql("""
    SELECT page_section, COUNT(*) as count
    FROM page_content
    GROUP BY page_section
    ORDER BY count DESC
    LIMIT 15
""", conn)
print("\n=== Sections ===")
print(sections.to_string(index=False))
```

```python
# Stichproben (10 zufällige Seiten)
samples = pd.read_sql("""
    SELECT p.url, pc.title, SUBSTR(pc.text_content, 1, 200) as preview
    FROM page_content pc
    JOIN pages p ON p.id = pc.page_id
    ORDER BY RANDOM()
    LIMIT 10
""", conn)
print("\n=== Stichproben ===")
for i, row in samples.iterrows():
    print(f"\n--- {row['title'][:60]} ---")
    print(f"URL: {row['url']}")
    print(f"Text: {row['preview']}...")
```

### Abschnitt 3: Text-Extraktion (falls nötig)

```python
# Prüfen ob Text-Extraktion schon gelaufen ist
content_count = pd.read_sql("SELECT COUNT(*) as count FROM page_content", conn).iloc[0, 0]

if content_count == 0:
    print("Text-Extraktion noch nicht ausgeführt!")
    print("Führe aus: python analysis/extract_text.py data/pages.db")
else:
    print(f"Text-Extraktion bereits erledigt: {content_count:,} Seiten")
```

### Abschnitt 4: RAG Setup

```python
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

# Embedding Modell
embeddings = OllamaEmbeddings(model="nomic-embed-text")

# LLM
llm = Ollama(model="llama3")

print("Ollama Modelle geladen!")
```

```python
# Daten laden
df = pd.read_sql("""
    SELECT p.url, pc.title, pc.text_content, pc.page_section
    FROM page_content pc
    JOIN pages p ON p.id = pc.page_id
    WHERE LENGTH(pc.text_content) > 100
""", conn)

print(f"Geladene Dokumente: {len(df):,}")
```

```python
# Text Chunking
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    length_function=len,
)

documents = []
for _, row in df.iterrows():
    chunks = text_splitter.split_text(row['text_content'])
    for chunk in chunks:
        documents.append(Document(
            page_content=chunk,
            metadata={
                "url": row['url'],
                "title": row['title'],
                "section": row['page_section']
            }
        ))

print(f"Chunks erstellt: {len(documents):,}")
```

```python
# Vector Store erstellen (dauert etwas!)
import os
CHROMA_PATH = "../data/chromadb"

# Löschen falls existiert (für Neuaufbau)
if os.path.exists(CHROMA_PATH):
    import shutil
    shutil.rmtree(CHROMA_PATH)

vectorstore = Chroma.from_documents(
    documents=documents,
    embedding=embeddings,
    persist_directory=CHROMA_PATH
)

print(f"Vector Store erstellt mit {len(documents):,} Chunks")
```

### Abschnitt 5: RAG Testen

```python
from langchain.chains import RetrievalQA

# RAG Chain erstellen
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=vectorstore.as_retriever(search_kwargs={"k": 5}),
    return_source_documents=True
)
```

```python
def ask(question: str):
    """Frage stellen und Antwort mit Quellen anzeigen."""
    result = qa_chain({"query": question})

    print("=" * 60)
    print(f"FRAGE: {question}")
    print("=" * 60)
    print(f"\nANTWORT:\n{result['result']}")
    print("\n" + "-" * 60)
    print("QUELLEN:")
    for i, doc in enumerate(result['source_documents'], 1):
        print(f"\n[{i}] {doc.metadata['title'][:50]}...")
        print(f"    URL: {doc.metadata['url']}")
        print(f"    Section: {doc.metadata['section']}")
        print(f"    Text: {doc.page_content[:100]}...")
    print("=" * 60)
```

```python
# Test-Fragen
ask("Was ist der aktuelle Leitzins?")
```

```python
ask("Wie funktioniert die Zahlungsbilanz?")
```

```python
ask("Welche Statistiken gibt es zu Wohnbaukrediten?")
```

```python
# Eigene Frage
ask("DEINE FRAGE HIER")
```

### Abschnitt 6: Erkenntnisse

```python
# Hier Notizen festhalten:
#
# Was funktioniert gut?
# -
#
# Was muss verbessert werden?
# -
#
# Nächste Schritte:
# -
```

---

## Checkliste

- [ ] Ollama installiert
- [ ] Modelle heruntergeladen (nomic-embed-text, llama3)
- [ ] Python Packages installiert
- [ ] Text-Extraktion ausgeführt (`python analysis/extract_text.py data/pages.db`)
- [ ] Jupyter Notebook durchgearbeitet
- [ ] Datenqualität bewertet
- [ ] RAG-Prototyp getestet
- [ ] Erkenntnisse dokumentiert

---

## Erwartete Ergebnisse

| Metrik | Erwartung |
|--------|-----------|
| Seiten in DB | ~27.000 |
| Durchschn. Textlänge | ~1.500-2.000 Zeichen |
| Leere Seiten | < 5% |
| Duplikate | < 1% |
| HTML-Reste | < 1% |
| Chunks für RAG | ~50.000-100.000 |
| Antwortqualität | Relevante Infos mit korrekten Quellen |
