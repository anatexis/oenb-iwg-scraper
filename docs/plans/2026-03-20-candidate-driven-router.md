# Candidate-Driven Router Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the rule-primary router with a knowledge-base-candidate router that uses Ollama/Mistral when available and falls back to deterministic routing only when candidate-guided routing cannot decide.

**Architecture:** Generate a small shortlist of route candidates from the structured statistics KB and the full-site KB, then let the router decide over those candidates. The LLM path consumes the query plus candidate shortlist; the deterministic fallback also uses the same shortlist and only falls back to hardcoded rules if no usable candidates exist.

**Tech Stack:** Python, JSONL knowledge bases, Ollama/Mistral provider abstraction, pytest.

### Task 1: Lock down candidate-driven routing with failing tests

**Files:**
- Modify: `tests/test_query_router.py`
- Modify: `tests/test_hybrid_retrieval.py`
- Modify: `tests/test_rag_answering_cli.py`

**Step 1: Write failing tests**
- Candidate-based corporate routing
- Candidate-based gold reserves vs. gold price routing
- Retrieval using KB candidates without explicit routed query

**Step 2: Run tests to verify failure**

Run: `pytest -q tests/test_query_router.py tests/test_hybrid_retrieval.py tests/test_rag_answering_cli.py`

### Task 2: Build candidate generation and candidate-informed routing

**Files:**
- Modify: `analysis/query_router.py`
- Modify: `analysis/prompts/router_prompt.txt`

**Step 1: Generate route candidates from KB records**
- Use `dataset_family`, `page_document`, `asset_document`, `isaweb_*` parents
- Score candidates lexically and keep only strong matches

**Step 2: Make routing candidate-first**
- `query + candidates -> LLM route` when provider exists
- `query + candidates -> deterministic candidate route` otherwise
- hardcoded rules remain only as last-resort fallback

### Task 3: Thread candidate router through retrieval

**Files:**
- Modify: `analysis/hybrid_retrieval.py`

**Step 1: Pass KB paths into router**
- So real retrieval uses candidate-informed routes automatically

### Task 4: Verify

**Step 1: Run focused tests**

Run: `pytest -q tests/test_query_router.py tests/test_hybrid_retrieval.py tests/test_query_knowledge_base.py tests/test_chatbot_answering.py tests/test_rag_answering_cli.py`

**Step 2: Run CLI checks**

Run:
- `python -m analysis.query_router "Wie viele Goldreserven hat die OeNB?"`
- `python -m analysis.query_router "Was schreibt die OeNB zu Frauen in Führungsfunktionen?"`
- `python -m analysis.rag_answering "Warum hat die OeNB eine Kunstsammlung?" --base-dir .`
