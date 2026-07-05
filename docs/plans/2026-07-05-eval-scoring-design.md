# Automatisches Eval-Scoring — Design

Datum: 2026-07-05
Status: validiert (Verdikte pass/partial/fail, kein LLM-Judge)

## Problem

Eval-Reports (`eval_v2_report*.json`) zählen nur `answer_type`. Ob eine Antwort
*richtig* ist, erfordert manuelles Lesen aller 60 Cases — bei 1–2h Laufzeit pro
Run (CPU-Ollama) kostet jede Tuning-Iteration einen halben Tag.

## Lösung

Deterministischer Post-hoc-Scorer: `analysis/score_chatbot_eval.py` liest einen
fertigen Report und bewertet jeden Case gegen Erwartungen aus der Fixture.
Post-hoc, damit auch historische Reports rückwirkend gescort werden können.

## Erwartungs-Schema (in `tests/fixtures/chatbot_eval_v2.json`)

```json
"expect": {
  "url_patterns": ["/Statistik/"],
  "keywords_any": ["Statistik", "Daten"],
  "keywords_all": [],
  "reject": false
}
```

- `url_patterns`: Case-insensitive Substring-Match gegen Citation-URLs;
  mindestens ein Pattern muss treffen.
- `keywords_any` / `keywords_all`: Match gegen den Antworttext, normalisiert
  (lowercase + Umlaut-Transliteration ä→ae, ö→oe, ü→ue, ß→ss — Fixture ist
  ASCII, Antworten enthalten echte Umlaute).
- `reject: true` für OOD-Cases: Antwort muss `not_found` sein.

Der Runner kopiert Case-Felder in den Report, daher stehen Erwartungen in
künftigen Reports automatisch drin. Für alte Reports joint der Scorer über die
Case-ID mit der Fixture.

## Verdikt-Logik

- `reject: true`: pass wenn `answer_type == not_found`, sonst fail.
- Sonst: `not_found` → fail. Andernfalls zählen nur die *spezifizierten*
  Dimensionen (URL, Keywords): alle treffen → **pass**, einige → **partial**,
  keine → **fail**.
- Case ohne `expect` → **unscored** (Validierungstest verhindert das für v2).

## Output

- Per-Case-Verdikt mit Begründung (welche Dimension verfehlt).
- Summary: pass/partial/fail je Fragetyp (NAV/FACT/TABLE/META/COMPARE/OOD),
  Gesamtscore = (pass + 0.5·partial) / total.
- `--baseline anderer_report.json`: listet geflippte Cases (Verbesserungen und
  Regressionen) — das Kernwerkzeug für Tuning-Iterationen.

## Integration

`run_chatbot_eval` ruft den Scorer am Ende auf; Verdikt-Zählung landet in der
Report-Summary. CLI:

```bash
python -m analysis.score_chatbot_eval REPORT.json \
  [--fixture tests/fixtures/chatbot_eval_v2.json] [--baseline OTHER.json]
```

## Bewusst weggelassen (YAGNI)

- LLM-Judge (auf CPU 1–2h pro Scoring-Run — genau das zu lösende Problem;
  nachrüstbar als Flag, falls CML/GPU verfügbar).
- Regex-Patterns (Substring reicht für OeNB-URLs).
