# LLM Router Rebuild Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current rule-heavy query router with an LLM-first router that still has safe local fallbacks and emits explicit retrieval strategy decisions for OeNB chatbot queries.

**Architecture:** Keep the existing provider abstraction (`ollama` locally, `mistral` on CML), but move routing into a structured `RouteDecision` pipeline: normalize query, invoke provider when configured, validate/normalize the route JSON, apply a deterministic fallback classifier, then emit `strategy` such as `sql_first`, `rag_first`, `hybrid`, or `reject_or_clarify`. Retrieval and answering consume that strategy instead of inferring behavior indirectly from coarse domains.

**Tech Stack:** Python, Ollama/Mistral provider abstraction, JSONL retrieval, pytest.

### Task 1: Lock down router behavior with failing tests

**Files:**
- Modify: `tests/test_query_router.py`
- Modify: `tests/test_hybrid_retrieval.py`
- Modify: `tests/test_rag_answering_cli.py`

**Step 1: Write failing tests**
- Add cases for:
  - `Wie viele Goldreserven hat die OeNB?`
  - `Was schreibt die OeNB zu Frauen in Führungsfunktionen?`
  - `Wie viel Taschengeld soll ich meinen Kindern geben?`
  - `Warum hat die OeNB eine Kunstsammlung?`
- Assert the router returns a structured strategy and does not collapse everything to `website_general`.

**Step 2: Run tests to verify failure**

Run: `pytest -q tests/test_query_router.py tests/test_hybrid_retrieval.py tests/test_rag_answering_cli.py`

**Step 3: Minimal code later**

### Task 2: Rebuild router output model

**Files:**
- Modify: `analysis/query_router.py`
- Create or modify helper types only if needed in-place

**Step 1: Implement normalized route schema**
- Fields:
  - `intent`
  - `domains`
  - `entities`
  - `freshness_need`
  - `subqueries`
  - `strategy`
  - `confidence`
  - `reasoning_hint`

**Step 2: LLM-first routing**
- If provider config is available, invoke provider first.
- Validate/normalize provider JSON.
- If provider is unavailable or invalid, use deterministic fallback rules.

**Step 3: Strategy decision**
- Add explicit strategy mapping:
  - structured statistics -> `sql_first`
  - explanatory website content -> `rag_first`
  - mixed questions -> `hybrid`
  - clearly out-of-scope questions -> `reject_or_clarify`

### Task 3: Adapt retrieval to explicit strategy

**Files:**
- Modify: `analysis/hybrid_retrieval.py`
- Modify: `analysis/domain_gating.py`
- Modify: `analysis/query_knowledge_base.py`

**Step 1: Consume `strategy` explicitly**
- `sql_first`: stats KB first, stronger domain gating
- `rag_first`: broader website retrieval
- `hybrid`: run stats and website retrieval paths together
- `reject_or_clarify`: avoid spurious fact answers

**Step 2: Keep provider-agnostic design**
- No Ollama-specific behavior in retrieval
- Provider differences stay inside `analysis/llm/*`

### Task 4: Improve answer behavior for non-statistics/open-ended questions

**Files:**
- Modify: `analysis/chatbot_answering.py`
- Modify: `analysis/rag_answering.py`
- Modify tests as needed

**Step 1: Respect route strategy**
- Out-of-scope personal-finance/advice questions should not hallucinate OeNB statistics.
- Website/corporate-topic questions should prefer full-site/OeNB-page evidence over arbitrary PDFs/stat tables.

### Task 5: Verify with current CLI flows

**Files:**
- No new production files unless needed

**Step 1: Run focused pytest**

Run: `pytest -q tests/test_query_router.py tests/test_hybrid_retrieval.py tests/test_query_knowledge_base.py tests/test_chatbot_answering.py tests/test_rag_answering_cli.py`

**Step 2: Run live CLI checks**

Run:
- `python -m analysis.query_router "Warum hat die OeNB eine Kunstsammlung?"`
- `python -m analysis.rag_answering "Wie viele Goldreserven hat die OeNB?" --base-dir .`
- `python -m analysis.rag_answering "Wie viel Taschengeld soll ich meinen Kindern geben?" --base-dir .`

