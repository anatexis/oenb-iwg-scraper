# OeNB Crawler V1 Smoke Run

## Ziel

Schneller Live-Check, dass der Rebuild-Crawler auf echten OeNB-Seiten lauffähig ist, eine kleine Wissensbasis exportiert und die wichtigsten Record-Typen produziert.

## Smoke-Run

Im Worktree ausführen:

```bash
python -m analysis.refresh_knowledge_base \
  data/smoke/pages.db \
  data/smoke/knowledge_base.jsonl \
  --crawl-output data/smoke/crawl_items.json \
  --smoke
```

Optional mit Statistikfokus:

```bash
python -m analysis.refresh_knowledge_base \
  data/smoke/pages.db \
  data/smoke/knowledge_base.jsonl \
  --crawl-output data/smoke/crawl_items.json \
  --smoke \
  --section statistics
```

## Validierung

```bash
python -m analysis.validate_knowledge_base data/smoke/knowledge_base.jsonl
```

Erwartung für einen brauchbaren Smoke-Run:

- `page_document` > 0
- `dataset_family` > 0
- `chatbot_chunk` > 0
- `chunk_parent_counts.dataset_family` > 0

Wenn der Lauf Statistikpfade/ISAweb erwischt, sollten zusätzlich erscheinen:

- `isaweb_dataset` > 0
- `asset_document` > 0
- `dataset_families_with_sources` > 0

## Inkrementeller Re-Run

Der zweite Lauf sollte dieselbe DB wiederverwenden:

```bash
python -m analysis.refresh_knowledge_base \
  data/smoke/pages.db \
  data/smoke/knowledge_base.jsonl \
  --crawl-output data/smoke/crawl_items.json \
  --smoke
```

Damit werden Frontier und Persistenz erneut benutzt, statt wieder bei null zu starten.

## Wenn etwas schiefgeht

- Keine `dataset_family`-Records:
  Prüfen, ob der Smoke-Run überhaupt Statistik-/ISAweb-Seiten getroffen hat.
- Keine `isaweb_dataset`-Records:
  Prüfen, ob ISAweb-Links im Crawl enthalten waren oder ein stärkerer Statistik-Seed nötig ist.
- Keine `chatbot_chunk`-Records:
  Export erneut laufen lassen und die Validator-Ausgabe prüfen.
