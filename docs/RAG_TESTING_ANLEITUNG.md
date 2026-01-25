# RAG Testing Anleitung - Schritt für Schritt

## Übersicht

Du hast jetzt:
- **26.834 OeNB-Seiten** in SQLite mit extrahiertem Text (639 MB)
- **Ollama** installiert mit zwei Modellen:
  - `nomic-embed-text` (274 MB) - für Embeddings
  - `gemma:2b` (1.7 GB) - kleines LLM für CPU

---

## Teil 1: Lokaler Quick-Test (CPU)

### Schritt 1: Jupyter Notebook starten

```bash
cd /home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version
source venv/bin/activate
jupyter notebook analysis/rag_exploration.ipynb
```

### Schritt 2: Notebook durcharbeiten

Das Notebook hat 6 Abschnitte:

| Abschnitt | Was passiert | Dauer |
|-----------|--------------|-------|
| 1. Setup | SQLite verbinden, Daten laden | ~10 Sek |
| 2. Datenqualität | Statistiken, Duplikate, HTML-Reste prüfen | ~1 Min |
| 3. Text-Extraktion | (bereits erledigt) | - |
| 4. RAG Setup | Embeddings erstellen, Vector Store bauen | ~30-60 Min* |
| 5. RAG Testen | Fragen stellen, Antworten bekommen | ~30 Sek/Frage |
| 6. Erkenntnisse | Notizen machen | - |

*Vector Store Erstellung dauert auf CPU länger. Alternativ: Weniger Seiten laden (siehe unten).

### Schritt 3: Notebook anpassen für schnelleren Test

Im Notebook, Abschnitt 4.2, ändere die SQL-Query um weniger Seiten zu laden:

```python
# Original (alle 26.834 Seiten):
df = pd.read_sql('''
    SELECT p.url, pc.title, pc.text_content, pc.page_section
    FROM page_content pc
    JOIN pages p ON p.id = pc.page_id
    WHERE LENGTH(pc.text_content) > 100
''', conn)

# Schneller Test (nur 1.000 Seiten):
df = pd.read_sql('''
    SELECT p.url, pc.title, pc.text_content, pc.page_section
    FROM page_content pc
    JOIN pages p ON p.id = pc.page_id
    WHERE LENGTH(pc.text_content) > 100
    AND pc.page_section = 'Statistik'
    LIMIT 1000
''', conn)
```

### Schritt 4: Modell anpassen

Im Notebook, Abschnitt 4.1, verwende `gemma:2b` statt `llama3`:

```python
# Für CPU:
llm = OllamaLLM(model="gemma:2b")

# Später mit GPU/Colab:
# llm = OllamaLLM(model="llama3")
```

### Schritt 5: Test-Fragen stellen

Gute Test-Fragen für OeNB-Daten:

```python
ask("Was ist der aktuelle Leitzins?")
ask("Wie berechnet man die Zahlungsbilanz?")
ask("Welche Daten gibt es zu Wohnbaukrediten?")
ask("Was sind standardisierte Tabellen?")
ask("Wie hoch ist die Inflation in Österreich?")
```

### Schritt 6: Ergebnisse bewerten

Prüfe bei jeder Antwort:

| Kriterium | Frage |
|-----------|-------|
| Relevanz | Beantwortet die Antwort die Frage? |
| Korrektheit | Sind die Fakten richtig? |
| Quellen | Passen die angezeigten Quellen zur Antwort? |
| Vollständigkeit | Fehlen wichtige Informationen? |

---

## Teil 2: Google Colab (GPU)

### Warum Colab?

- Gratis T4 GPU (viel schneller als CPU)
- Bessere Modelle möglich (llama3, mistral)
- Keine lokale Hardware-Belastung

### Schritt 1: Parquet exportieren

```bash
cd /home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version
source venv/bin/activate
python analysis/export_parquet.py data/pages.db data/oenb_pages_full.parquet
```

### Schritt 2: Colab Notebook erstellen

1. Gehe zu https://colab.research.google.com
2. Neues Notebook erstellen
3. Runtime → Change runtime type → T4 GPU

### Schritt 3: Colab Code

```python
# Cell 1: Setup
!pip install -q langchain langchain-community chromadb sentence-transformers

# Cell 2: Daten hochladen
from google.colab import files
uploaded = files.upload()  # Wähle oenb_pages_full.parquet

# Cell 3: Daten laden
import pandas as pd
df = pd.read_parquet('oenb_pages_full.parquet')
print(f"Geladene Seiten: {len(df):,}")

# Cell 4: Embeddings mit HuggingFace (GPU-beschleunigt)
from langchain_community.embeddings import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-large",
    model_kwargs={'device': 'cuda'}
)
print("Embedding Modell geladen (GPU)")

# Cell 5: Chunking
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

documents = []
for _, row in df.iterrows():
    if not row['text_content']:
        continue
    chunks = text_splitter.split_text(row['text_content'])
    for chunk in chunks:
        documents.append(Document(
            page_content=chunk,
            metadata={"url": row['url'], "title": row['title'] or "", "section": row['page_section'] or ""}
        ))
print(f"Chunks: {len(documents):,}")

# Cell 6: Vector Store (GPU-beschleunigt)
from langchain_community.vectorstores import Chroma

vectorstore = Chroma.from_documents(
    documents=documents,
    embedding=embeddings,
)
print("Vector Store erstellt")

# Cell 7: LLM (HuggingFace)
from langchain_community.llms import HuggingFacePipeline
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import torch

model_id = "mistralai/Mistral-7B-Instruct-v0.2"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.float16,
    device_map="auto"
)
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, max_new_tokens=512)
llm = HuggingFacePipeline(pipeline=pipe)
print("LLM geladen")

# Cell 8: RAG Chain
from langchain.chains import RetrievalQA

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=vectorstore.as_retriever(search_kwargs={"k": 5}),
    return_source_documents=True
)

# Cell 9: Fragen stellen
def ask(question):
    result = qa_chain.invoke({"query": question})
    print(f"FRAGE: {question}\n")
    print(f"ANTWORT: {result['result']}\n")
    print("QUELLEN:")
    for i, doc in enumerate(result['source_documents'], 1):
        print(f"  [{i}] {doc.metadata['title'][:40]}... - {doc.metadata['url']}")

ask("Was ist der aktuelle Leitzins?")
```

---

## Teil 3: Nächste Schritte nach dem Testen

### Wenn die Ergebnisse gut sind:

1. **Volle Daten testen** - Alle 26.834 Seiten mit GPU
2. **Chunking optimieren** - Verschiedene Chunk-Größen testen
3. **Prompt Engineering** - System-Prompt anpassen für bessere Antworten
4. **Deployment planen** - Cloudera ML Setup

### Wenn die Ergebnisse schlecht sind:

1. **Datenqualität prüfen** - Mehr HTML-Reste? Falsche Texte?
2. **Embedding-Modell wechseln** - Anderes multilingual Modell
3. **Chunk-Größe anpassen** - Größer (mehr Kontext) oder kleiner (präziser)
4. **Re-Ranking** - Relevantere Chunks durch zweiten Schritt filtern

---

## Checkliste

### Lokal (Quick-Test)
- [x] Ollama installiert
- [x] nomic-embed-text geladen
- [x] gemma:2b geladen
- [x] Python Packages installiert
- [ ] Jupyter Notebook gestartet
- [ ] Datenqualität geprüft
- [ ] RAG mit 1.000 Seiten getestet
- [ ] Ergebnisse dokumentiert

### Google Colab (GPU-Test)
- [ ] Parquet exportiert
- [ ] Colab Notebook erstellt
- [ ] GPU Runtime aktiviert
- [ ] Daten hochgeladen
- [ ] RAG mit allen Seiten getestet
- [ ] Ergebnisse verglichen

---

## Fehlerbehebung

### "Ollama connection refused"
```bash
# Ollama Service starten
sudo systemctl start ollama
# Oder manuell
ollama serve
```

### "CUDA out of memory" (Colab)
- Weniger Seiten laden (LIMIT in SQL)
- Kleineres Modell verwenden
- Runtime neu starten

### "Slow embedding generation"
- Batch-Größe reduzieren
- Weniger Seiten für ersten Test

### "Schlechte Antworten"
- Chunk-Größe erhöhen (mehr Kontext)
- Andere Fragen probieren
- Quellen prüfen - werden die richtigen Seiten gefunden?

---

## Kontakt & Ressourcen

- **Notebook:** `analysis/rag_exploration.ipynb`
- **Daten:** `data/pages.db` (639 MB)
- **Design-Dokument:** `docs/plans/2026-01-24-rag-testing-guide.md`
- **LangChain Docs:** https://python.langchain.com/docs/
- **Ollama:** https://ollama.com/
