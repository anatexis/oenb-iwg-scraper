# Eval-Set v3 + CML-Eval-Jobs — Design

Datum: 2026-07-07
Status: validiert (alles auf CML erzeugen; LLM env-konfigurierbar; Set zuerst)

## Teil A: Eval-Set v3 (additiv)

`tests/fixtures/chatbot_eval_v2.json` wächst von 60 auf 67 Cases. Alte IDs
unverändert → Baseline-Diffs bleiben gültig.

- **+4 LEGAL** (legal_001–004): Rechtsgrundlage Meldewesen, gesetzliche
  Aufgaben der OeNB (Nationalbankgesetz), Meldebestimmungen finden,
  Sanktionen/Aufsichtsrecht. Feedback-Vorgabe: Eval muss
  NAV/FACT/TABLE/META/COMPARE/LEGAL/OOD abdecken.
- **+3 COMPARE** (comp_001–003): HVPI vs. VPI, Direkt- vs.
  Portfolioinvestitionen, Basiszins vs. Leitzins. Verdikt über
  `keywords_all` (beide Begriffe müssen in der Antwort vorkommen).
- **Keyword-Schärfung**: nav_001, nav_010, meta_001, meta_002 verlieren
  generische Stämme („statistik", „oenb") — Verdikt primär über URL-Pattern.
  Bekannte Restgrenze: Antworttext-Keywords bleiben ein schwaches Signal;
  URL-Patterns sind das verlässliche.

## Teil B: CML-Jobs

Prinzip: **Ein Datenlayout für lokal und CML** — die Runtime erwartet
`data/statistics_production/knowledge_base_active.jsonl` (+ Index) und
`data/full_site_production/…`; alle Jobs schreiben genau dorthin.

| Job | Datei | Was | Dauer |
|-----|-------|-----|-------|
| 1 | `cml_crawl.py` (Update) | Website-BFS-Crawl → `data/full_site_production/pages.db` | ~2–4h |
| 2 | `cml_isaweb.py` (neu) | ISAweb REST fetch_all → `data/statistics_production/pages.db` | ~50 min |
| 3 | `cml_eval.py` (neu) | Pipeline: extract_text → KB-Exporte → Index-Rebuild → Eval → Scoring | ~1h |

`cml_eval.py` ist ein dünner Wrapper über `analysis/eval_pipeline.py`
(testbare Orchestrierung):

1. `extract_text` auf full_site pages.db (inkrementell)
2. Export full_site KB → `knowledge_base_active.jsonl` (ohne Fehlerseiten)
3. Export statistics KB (nur wenn statistics pages.db existiert)
4. `kb_index` Rebuild für beide KBs (Pflicht nach Export — im Job automatisiert)
5. `run_chatbot_eval` (Fixture v3; LLM-Router per Env, Regel-Fallback)
6. `score_chatbot_eval` inkl. `--baseline` gegen den letzten Report
7. Report nach `data/eval_reports/eval_YYYY-MM-DD_HHMM.json` + Klartext-Summary

Fehlerverhalten: Schritt schlägt fehl → Abbruch mit Exit ≠ 0 (CML zeigt
den Job rot), bereits erzeugte Artefakte bleiben liegen (idempotent,
Neustart setzt auf).

## LLM auf CML

Bereits vorhanden: `OENB_LLM_PROVIDER=mistral` +
`OENB_MISTRAL_BASE_URL/MODEL/API_KEY` sprechen jeden OpenAI-kompatiblen
Endpoint (`/v1/chat/completions`) an — CML-Model-Endpoints eingeschlossen.
Kein Code nötig, nur Env-Variablen im CML-Projekt setzen (Doku in
CML-SETUP.md). Ohne erreichbares LLM: automatischer Regel-Fallback.

## Bewusst weggelassen (YAGNI)

- Kein separates CML-Config-Format — Env-Variablen reichen.
- Kein Daten-Upload-Mechanismus — beide Quellen entstehen auf CML selbst.
- Kein LLM-Judge im Scoring (deterministisch bleibt der Standard).
