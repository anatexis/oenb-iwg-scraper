# LLM Router And Hybrid RAG For OeNB Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CML-ready chatbot stack for the OeNB knowledge base that works locally with `Ollama` and later with `Mistral` on CML, using LLM routing, hybrid retrieval, and selective agentic ISAweb lookups.

**Architecture:** The new stack should sit on top of the existing crawl/export pipeline, not replace it. User queries first go through an LLM router that infers intent, domains, entities, and freshness needs; then a hybrid retriever combines structured ISAweb/table records with text retrieval; finally a selective agentic layer may issue targeted live lookups only when the router or retriever indicates that the static knowledge base is insufficient.

**Tech Stack:** Python 3.10, existing JSONL/SQLite knowledge base, local `Ollama` HTTP API, later CML-hosted `Mistral` HTTP endpoint, pytest, existing `analysis/*` CLI entry points.

## Assumptions

- Local development uses a small `Ollama` model via HTTP on the developer machine.
- CML production uses a `Mistral`-compatible HTTP endpoint that is reachable from within CML jobs/apps.
- The crawler remains round-based in CML because of firewall/time limits; [cml_crawl_runden.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/cml_crawl_runden.py) remains relevant as the operational crawl wrapper.
- The first production chatbot must prioritize correctness for OeNB statistics and ISAweb over conversational breadth.
- Agentic search is a bounded escalation step, not a default path.

## Non-Goals

- No full autonomous browsing agent over the open web.
- No generic chat memory or multi-user conversation state in the first version.
- No large frontend redesign before retrieval quality is validated.

## Success Criteria

- A query like `Wie hoch ist der Zinssatz für die Einlagenfazilität?` routes into the monetary-policy domain and returns a relevant rate-family answer instead of a random statistics table.
- A multi-topic query like `Mich interessieren Immobilienpreise und Gold` yields either a structured multi-part answer or explicit subquery handling.
- The same code path works with `Ollama` locally and `Mistral` in CML by changing config only.
- The retrieval layer explicitly prefers structured ISAweb/table data when available.
- Agentic live lookup is invoked only for cases with high freshness need or weak static retrieval confidence.

---

### Task 1: Add LLM Provider Abstraction

**Files:**
- Create: `analysis/llm/base.py`
- Create: `analysis/llm/ollama_provider.py`
- Create: `analysis/llm/mistral_provider.py`
- Create: `analysis/llm/factory.py`
- Test: `tests/test_llm_factory.py`

**Step 1: Write the failing tests**

Create provider selection tests covering:
- `OLLAMA` selection for local development
- `MISTRAL` selection for CML deployment
- missing configuration should raise a clear error

```python
def test_build_llm_provider_returns_ollama_provider_for_ollama_config():
    ...

def test_build_llm_provider_returns_mistral_provider_for_mistral_config():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_factory.py -q`

Expected: import errors or missing implementation failures.

**Step 3: Write minimal implementation**

Add:
- abstract `LLMProvider` interface with one request method for structured prompts
- `OllamaProvider` using configurable base URL/model name
- `MistralProvider` using configurable base URL/model name/api key if needed
- `build_llm_provider()` driven by env or explicit config

Keep the interface small:
- `invoke_json(system_prompt, user_prompt, schema_hint=None) -> dict`
- `invoke_text(system_prompt, user_prompt) -> str`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_factory.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/llm/base.py analysis/llm/ollama_provider.py analysis/llm/mistral_provider.py analysis/llm/factory.py tests/test_llm_factory.py
git commit -m "feat: add llm provider abstraction for ollama and mistral"
```

---

### Task 2: Add Query Router Schema And CLI

**Files:**
- Create: `analysis/query_router.py`
- Create: `analysis/prompts/router_prompt.txt`
- Test: `tests/test_query_router.py`

**Step 1: Write the failing tests**

Cover:
- simple monetary-policy question
- commodity question
- multi-topic question
- fallback for unknown question

Expected router output structure:

```python
{
    "intent": "fact_lookup",
    "domains": ["monetary_policy", "interest_rates"],
    "entities": ["Einlagenfazilität"],
    "freshness_need": "high",
    "subqueries": []
}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_router.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Implement:
- router schema normalization
- domain taxonomy for OeNB:
  - `monetary_policy`
  - `interest_rates`
  - `commodity_prices`
  - `real_estate`
  - `financial_soundness`
  - `external_sector`
  - `website_general`
- hard rules for obvious OeNB terms before calling the LLM
- LLM fallback for natural language queries

The router CLI should print normalized JSON.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_query_router.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/query_router.py analysis/prompts/router_prompt.txt tests/test_query_router.py
git commit -m "feat: add llm query router for oenb domains"
```

---

### Task 3: Add Domain Gating Rules For Retrieval

**Files:**
- Create: `analysis/domain_gating.py`
- Modify: `analysis/query_knowledge_base.py`
- Test: `tests/test_domain_gating.py`
- Test: `tests/test_query_knowledge_base.py`

**Step 1: Write the failing tests**

Add tests proving:
- `Goldpreis` cannot rank `RPPI` first if there are no commodity hits
- `Einlagenfazilität` cannot rank a services-trade family first
- multi-domain router output allows hits from both `real_estate` and `commodity_prices`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_domain_gating.py tests/test_query_knowledge_base.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Implement a gating layer that maps routed domains to allowed record families using:
- URL path hints
- report id families
- section labels
- title keywords

Important:
- domain gating must support multi-label queries
- if strict gating finds nothing, degrade gracefully to wider retrieval
- keep current synonym logic as a fallback, not the main decision maker

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_domain_gating.py tests/test_query_knowledge_base.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/domain_gating.py analysis/query_knowledge_base.py tests/test_domain_gating.py tests/test_query_knowledge_base.py
git commit -m "feat: add domain gating for oenb retrieval"
```

---

### Task 4: Add Hybrid Retrieval Interface

**Files:**
- Create: `analysis/hybrid_retrieval.py`
- Modify: `analysis/chatbot_retrieval.py`
- Test: `tests/test_hybrid_retrieval.py`

**Step 1: Write the failing tests**

Cover:
- structured ISAweb families outrank text-only pages inside same domain
- multiple subqueries merge into one result set without duplicates
- retrieval confidence is exposed

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_hybrid_retrieval.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Build a hybrid retriever that combines:
- structured family/dataset chunks from statistics KB
- text chunks from statistics KB
- optional full-site fallback

Return richer results:

```python
{
    "hits": [...],
    "confidence": 0.84,
    "routing": {...},
    "subquery_results": [...]
}
```

Do not add embeddings yet in this task; keep it as a retriever composition layer.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_hybrid_retrieval.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/hybrid_retrieval.py analysis/chatbot_retrieval.py tests/test_hybrid_retrieval.py
git commit -m "feat: add hybrid retrieval pipeline"
```

---

### Task 5: Add Embedding-Ready Search Adapter

**Files:**
- Create: `analysis/semantic_search.py`
- Create: `analysis/embedding_backends.py`
- Test: `tests/test_semantic_search.py`

**Step 1: Write the failing tests**

Cover:
- semantic backend can be disabled with config
- query path still works in lexical-only mode
- backend interface allows future CML vector store or local embedding model

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_semantic_search.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Do not overbuild.
Add a small adapter layer:
- `SemanticSearchBackend` protocol
- `NoopSemanticSearchBackend`
- placeholder local backend config

This task exists so the retrieval pipeline can later switch on embeddings without structural rewrites.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_semantic_search.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/semantic_search.py analysis/embedding_backends.py tests/test_semantic_search.py
git commit -m "feat: add embedding-ready semantic search adapter"
```

---

### Task 6: Add Selective Agentic ISAweb Lookup

**Files:**
- Create: `analysis/agentic_search.py`
- Create: `analysis/isaweb_live_lookup.py`
- Modify: `analysis/chatbot_answering.py`
- Test: `tests/test_agentic_search.py`

**Step 1: Write the failing tests**

Cover:
- agentic step is not called when retrieval confidence is high
- agentic step is called when freshness need is `high` and confidence is low
- live lookup is bounded to OeNB ISAweb endpoints only

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agentic_search.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Add a selective orchestration step:
- inspect router output and retrieval confidence
- if needed, call a bounded live ISAweb lookup helper
- merge live result into answer context

Guardrails:
- only OeNB ISAweb/Webservice endpoints
- max step count
- no recursive agent loops
- explicit provenance in answer payload

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agentic_search.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/agentic_search.py analysis/isaweb_live_lookup.py analysis/chatbot_answering.py tests/test_agentic_search.py
git commit -m "feat: add selective agentic isaweb lookup"
```

---

### Task 7: Upgrade Answer Synthesis To Use Routed/Hybrid Context

**Files:**
- Modify: `analysis/chatbot_answering.py`
- Test: `tests/test_chatbot_answering.py`

**Step 1: Write the failing tests**

Add answer-level tests for:
- `Wie hoch ist der Goldpreis aktuell?`
  - should prefer commodity/gold family or explicitly say no suitable gold series found
- `Wie hoch ist der Zinssatz für die Einlagenfazilität?`
  - should stay in monetary-policy domain
- `Mich interessieren Immobilienpreise und Gold`
  - should produce a two-part answer or structured split output

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_chatbot_answering.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Update answer building to:
- consume routed multi-subquery retrieval
- produce multi-part answers when multiple domains are requested
- include confidence or fallback phrasing when the system is unsure
- keep citations and source discipline

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_chatbot_answering.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/chatbot_answering.py tests/test_chatbot_answering.py
git commit -m "feat: upgrade answer synthesis for routed hybrid retrieval"
```

---

### Task 8: Add Runtime Config Layer For Local And CML Deployment

**Files:**
- Create: `analysis/runtime_config.py`
- Create: `docs/runbooks/llm-router-hybrid-rag-cml.md`
- Test: `tests/test_runtime_config.py`

**Step 1: Write the failing tests**

Cover:
- local `Ollama` config resolution
- CML `Mistral` config resolution
- fallback file paths for statistics/full-site KB
- round-crawl compatibility flags

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime_config.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Add config from env vars only:
- `OENB_LLM_PROVIDER=ollama|mistral`
- `OENB_OLLAMA_BASE_URL`
- `OENB_OLLAMA_MODEL`
- `OENB_MISTRAL_BASE_URL`
- `OENB_MISTRAL_MODEL`
- `OENB_MISTRAL_API_KEY`
- `OENB_AGENTIC_ENABLED`
- `OENB_SEMANTIC_ENABLED`

Runbook must explain:
- local developer mode
- CML application mode
- CML job mode
- interaction with round-based crawling

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_runtime_config.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/runtime_config.py docs/runbooks/llm-router-hybrid-rag-cml.md tests/test_runtime_config.py
git commit -m "feat: add runtime config for ollama and cml mistral"
```

---

### Task 9: Add CML-Friendly CLI Entry Points

**Files:**
- Create: `analysis/router_demo.py`
- Create: `analysis/rag_answering.py`
- Create: `cml/app/README.md`
- Create: `cml/app/streamlit_app.py`
- Test: `tests/test_rag_answering_cli.py`

**Step 1: Write the failing tests**

Cover:
- CLI can answer a query with configured provider
- CLI can print routing debug info
- CLI can run without agentic step

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_rag_answering_cli.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Add:
- `router_demo.py` for debugging route output
- `rag_answering.py` as the future stable CLI entry point
- minimal Streamlit application for CML:
  - question input
  - answer block
  - citations
  - route/debug panel

Keep the UI intentionally small.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_rag_answering_cli.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add analysis/router_demo.py analysis/rag_answering.py cml/app/README.md cml/app/streamlit_app.py tests/test_rag_answering_cli.py
git commit -m "feat: add cml ready rag cli and minimal app"
```

---

### Task 10: Add End-To-End Evaluation Set For OeNB Questions

**Files:**
- Create: `tests/fixtures/chatbot_eval_questions.json`
- Create: `tests/test_chatbot_eval_regressions.py`

**Step 1: Write the failing tests**

Create an eval set with real OeNB-style questions, including:
- `Wie hoch ist der Leitzins aktuell?`
- `Wie hoch ist der Zinssatz für die Einlagenfazilität?`
- `Wie hoch ist der Goldpreis aktuell?`
- `Was ist der RPPI in Österreich?`
- `Wann ist die nächste Veröffentlichung der Financial Soundness Indicators?`
- `Mich interessieren Immobilienpreise und Gold`
- `Wo finde ich die Standardized Tables zu Wechselkursen?`

Use assertions on:
- routed domain
- top answer family
- must-include answer snippets
- must-not-include obviously wrong domains

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_chatbot_eval_regressions.py -q`

Expected: FAIL

**Step 3: Write minimal implementation**

Hook the eval tests to the new router/retriever/answerer so regressions become visible before shipping.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_chatbot_eval_regressions.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/fixtures/chatbot_eval_questions.json tests/test_chatbot_eval_regressions.py
git commit -m "test: add oenb chatbot evaluation regressions"
```

---

### Task 11: Integrate With Round-Based CML Crawl Workflow

**Files:**
- Modify: `/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/cml_crawl_runden.py`
- Create: `docs/runbooks/cml-runden-rag-workflow.md`

**Step 1: Write the failing test or documented dry-run check**

Because this file is outside the worktree, use a documented dry-run checklist instead of a normal unit test:
- crawl rounds update DB
- export active KB after each successful round batch
- optional lightweight reranking or semantic index refresh

If moving this file into the worktree later becomes desirable, then add unit tests then.

**Step 2: Verify current script behavior**

Run a dry inspection:
```bash
python /home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/cml_crawl_runden.py --help
```

If no `--help`, document the current entrypoint behavior instead.

**Step 3: Write minimal implementation**

Extend the script or create a wrapper so each successful round batch can trigger:
- `analysis.export_knowledge_base_jsonl`
- optional semantic index refresh
- optional active artifact promotion for the app

This keeps the CML workflow compatible with short crawl windows.

**Step 4: Verify**

Run the wrapper or dry-run the commands in a non-destructive mode and confirm paths are correct.

**Step 5: Commit**

```bash
git add docs/runbooks/cml-runden-rag-workflow.md
git commit -m "docs: add cml round crawl rag workflow"
```

If the external file is modified in the main workspace, commit that change separately there.

---

### Task 12: Final Verification

**Files:**
- Verify all touched files

**Step 1: Run focused tests**

```bash
pytest tests/test_llm_factory.py \
  tests/test_query_router.py \
  tests/test_domain_gating.py \
  tests/test_hybrid_retrieval.py \
  tests/test_semantic_search.py \
  tests/test_agentic_search.py \
  tests/test_chatbot_answering.py \
  tests/test_runtime_config.py \
  tests/test_rag_answering_cli.py \
  tests/test_chatbot_eval_regressions.py -q
```

**Step 2: Run full suite**

```bash
pytest -q
```

**Step 3: Run manual smoke queries**

```bash
python -m analysis.router_demo "Wie hoch ist der Zinssatz für die Einlagenfazilität?"
python -m analysis.rag_answering "Wie hoch ist der Goldpreis aktuell?"
python -m analysis.rag_answering "Mich interessieren Immobilienpreise und Gold"
```

Expected:
- routed domains make sense
- no wild domain drift
- citations point to OeNB pages or ISAweb/meta URLs

**Step 4: Commit final integration**

```bash
git add analysis tests docs cml
git commit -m "feat: add llm routed hybrid rag stack for oenb chatbot"
```

---

## Implementation Notes

- Keep `analysis.chatbot_answering` working during the transition; do not break the existing CLI before `analysis.rag_answering` is ready.
- The provider abstraction is the contract boundary: local `Ollama` and CML `Mistral` must only differ in config and provider implementation.
- Agentic search must never become the default path for every question.
- The eval set is critical. If the pipeline cannot consistently answer `Leitzins`, `Einlagenfazilität`, `Goldpreis`, and `RPPI`, do not ship the app.

## Suggested Env Vars

```bash
OENB_LLM_PROVIDER=ollama
OENB_OLLAMA_BASE_URL=http://localhost:11434
OENB_OLLAMA_MODEL=mistral-small
OENB_AGENTIC_ENABLED=false
OENB_SEMANTIC_ENABLED=false
```

Later in CML:

```bash
OENB_LLM_PROVIDER=mistral
OENB_MISTRAL_BASE_URL=http://<cml-model-endpoint>
OENB_MISTRAL_MODEL=<model-name>
OENB_AGENTIC_ENABLED=true
OENB_SEMANTIC_ENABLED=true
```

