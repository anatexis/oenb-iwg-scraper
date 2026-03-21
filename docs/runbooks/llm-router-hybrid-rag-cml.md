# LLM Router / Hybrid RAG On CML

## Local Developer Mode

Set:
- `OENB_LLM_PROVIDER=ollama`
- `OENB_OLLAMA_BASE_URL=http://localhost:11434`
- `OENB_OLLAMA_MODEL=qwen2.5:3b`

Knowledge bases default to:
- `data/statistics_production/knowledge_base_active.jsonl`
- `data/full_site_production/knowledge_base_active.jsonl`

## CML Application Mode

Set:
- `OENB_LLM_PROVIDER=mistral`
- `OENB_MISTRAL_BASE_URL=<cml mistral endpoint>`
- `OENB_MISTRAL_MODEL=<model name>`
- `OENB_MISTRAL_API_KEY=<token if required>`

Optional:
- `OENB_AGENTIC_ENABLED=1`
- `OENB_SEMANTIC_ENABLED=1`

## CML Job Mode

Use the same environment as application mode, but keep crawl and answer workloads separate:
- round-based crawler jobs
- export/refresh job
- app or CLI for answering

## Round-Based Crawling

Set `OENB_CML_ROUND_MODE=1` when the deployment should assume short crawl rounds.
This is aligned with the existing round-wrapper approach in:
- [/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/cml_crawl_runden.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/cml_crawl_runden.py)

The chatbot stack itself should treat this flag as an operational signal, not as a retrieval toggle.
