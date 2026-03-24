# Router Priority 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve router behavior for open-ended statistics navigation, release lookup, ISAweb explanation, and bank health questions from the March 20 eval priorities.

**Architecture:** Extend deterministic router heuristics before touching retrieval. Add regression tests for the prioritized open-ended cases, then implement minimal fallback/domain-intent logic and supporting hint phrases so candidate-informed routing stays aligned with the deterministic route.

**Tech Stack:** Python, pytest

### Task 1: Add router regression tests

**Files:**
- Modify: `tests/test_query_router.py`

**Step 1: Write the failing tests**

Add focused assertions for:
- `Was ist ISAweb und wie kann ich damit Daten abrufen?`
- `Wann werden die naechsten Inflationsdaten veroeffentlicht?`
- `Wo finde ich die Tabelle zu Sparzinsen?`
- `Gibt es die Daten zum Bargeldumlauf auch als CSV oder Excel?`
- `Wie geht es den oesterreichischen Banken?`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_router.py -q`
Expected: FAIL on the new routing expectations

### Task 2: Implement minimal router heuristics

**Files:**
- Modify: `analysis/query_router.py`
- Modify: `analysis/domain_gating.py`
- Modify: `analysis/prompts/router_prompt.txt`

**Step 1: Add deterministic fallback/domain signals**

Introduce only the rules needed for:
- statistics release lookup
- statistics navigation/download questions
- ISAweb explanation
- bank health / FSI routing

**Step 2: Keep strategy selection minimal**

Ensure release/navigation queries that need structured data plus website context can become `hybrid`, while ISAweb/download explanation queries stay `rag_first` where appropriate.

**Step 3: Run tests to verify pass**

Run: `pytest tests/test_query_router.py -q`
Expected: PASS

### Task 3: Run regression verification

**Files:**
- Modify: `tests/fixtures/chatbot_eval_questions.json` if broader regression coverage is needed

**Step 1: Run targeted regression suite**

Run: `pytest tests/test_chatbot_eval_regressions.py tests/test_query_router.py -q`
Expected: PASS
