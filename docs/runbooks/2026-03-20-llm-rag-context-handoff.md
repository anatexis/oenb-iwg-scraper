# LLM/RAG Context Handoff

Date: 2026-03-20

## Scope

This handoff secures the current state before implementing the next chatbot layer:
- LLM provider abstraction
- query router
- domain gating
- hybrid retrieval
- selective agentic ISAweb lookups

Primary execution plan:
- [docs/plans/2026-03-20-llm-router-hybrid-rag-cml.md](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/docs/plans/2026-03-20-llm-router-hybrid-rag-cml.md)

## Current Knowledge Bases

Primary statistics knowledge base:
- [data/statistics_production/knowledge_base_active.jsonl](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/data/statistics_production/knowledge_base_active.jsonl)

Full-site fallback knowledge base:
- [data/full_site_production/knowledge_base_active.jsonl](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/data/full_site_production/knowledge_base_active.jsonl)

Primary statistics database:
- [data/statistics_production/pages.db](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/data/statistics_production/pages.db)

## Current Chatbot Stack

Current answer path:
- [analysis/chatbot_answering.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/chatbot_answering.py)
- [analysis/chatbot_retrieval.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/chatbot_retrieval.py)
- [analysis/query_knowledge_base.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/query_knowledge_base.py)

Current behavior:
- lexical retrieval over exported JSONL `chatbot_chunk` records
- stats-first retrieval, full-site fallback
- heuristic ranking with synonym boosts
- template-based answer synthesis

Current limitations:
- not real semantic RAG yet
- no embedding search
- no LLM router
- no domain gating for whole-sentence questions
- no selective live ISAweb lookups at query time

## Current Quality Status

What already works reasonably well:
- structured ISAweb/table families are preferred over PDFs
- `Leitzins` now resolves to `Key interest rates` rather than the older `2.1` family
- large multi-series answers are summarized instead of dumping every row
- core citations are reduced to primary page, dataset URL and metadata URL

Known weakness that motivates the next layer:
- whole-sentence questions can still route into the wrong domain
- example failures observed:
  - `wie hoch ist der Goldpreis aktuell?` matched a real-estate series
  - `wie hoch ist der Zinssatz für die Einlagenfazilität?` matched a services-trade family

Root cause:
- current retrieval is still token/synonym driven
- there is no explicit query understanding step that separates `commodity_prices`, `interest_rates`, `real_estate`, `financial_soundness`, etc.

## Current Example Output

Current CLI entry point:
- `python -m analysis.chatbot_answering "aktueller Leitzins" --base-dir`

Current answer quality for that query:
- `Key interest rates. Stand Wissensbasis: 2025. Euro area = 2.15 %. Tabelle enthält außerdem 11 weitere Reihen.`

Current relevant sources for that family are clean enough:
- `Eurostat`
- `Sveriges Riksbank`
- `Schweizerische Nationalbank`
- `Thomson Reuters`
- `ECB main refinancing operation (MRO)`
- `Macrobond`

## Recent Crawler/Export State

Recent statistics refresh produced:
- `isaweb_datasets = 660`
- `isaweb_metadata = 741`
- `isaweb_observations = 159215`
- `release_events = 1149`

Important operational fact:
- statistics/ISAweb data is the primary basis for chatbot fact answers
- full-site crawl remains useful as fallback for general website questions

## CML/Ollama/Mistral Constraints

Local development:
- only small local `Ollama` is available
- new code must be testable without requiring a remote CML model

Target production:
- model runs on CML as a `Mistral`-compatible HTTP endpoint
- switching from local `Ollama` to CML `Mistral` should happen via config only

Operational crawler constraint:
- the crawler in CML must remain round-based because of firewall/time limits
- root-level helper remains relevant:
  - [/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/cml_crawl_runden.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/cml_crawl_runden.py)

## Immediate Implementation Priorities

1. Add LLM provider abstraction with one interface for `Ollama` and `Mistral`.
2. Add query router that returns normalized `intent`, `domains`, `entities`, `freshness_need`, `subqueries`.
3. Add domain gating before retrieval.
4. Add hybrid retrieval that explicitly prefers structured ISAweb/table hits.
5. Keep agentic/live ISAweb lookup as a bounded fallback, not the default path.

## Verification Baseline

Most recent full test-suite result before starting this implementation phase:
- `318 passed in 12.79s`

This handoff is meant to preserve context before changing the chatbot architecture.
