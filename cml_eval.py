"""CML Job: Chatbot-Auswertung (KB-Aufbau + Eval + Scoring).

Läuft die komplette Auswertungs-Pipeline auf dem aktuellen Datenstand:
  1. Text-Extraktion (full-site pages.db)
  2. KB-Exporte (full-site + Statistik, ohne Fehlerseiten)
  3. FTS-Index-Rebuild (Pflicht nach jedem Export!)
  4. 67-Case-Eval (LLM-Router per Env, sonst Regel-Fallback)
  5. Scoring mit Baseline-Diff gegen den letzten Report

Verwendung:
  - Als CML Job: Jobs > New Job > Script: cml_eval.py > Starten
  - Im Terminal:  python cml_eval.py
  - Resource Profile: 2 vCPU, 8 GB RAM
  - Laufzeit: ~30-60 min (dominiert vom Statistik-KB-Export)

Voraussetzungen:
  - cml_crawl.py ist gelaufen (data/full_site_production/pages.db)
  - optional: cml_isaweb.py ist gelaufen (data/statistics_production/pages.db);
    ohne sie läuft der Eval nur gegen die Website-KB.

LLM-Router (optional, sonst Regel-Fallback) — als Project Environment
Variables in CML setzen (jeder OpenAI-kompatible Endpoint funktioniert):
  OENB_LLM_PROVIDER=mistral
  OENB_MISTRAL_BASE_URL=https://<dein-endpoint>   (spricht /v1/chat/completions)
  OENB_MISTRAL_MODEL=<modellname>
  OENB_MISTRAL_API_KEY=<key>

Ergebnis: data/eval_reports/eval_<datum>.json + Klartext-Summary im Job-Log.
Exit-Code != 0 wenn ein Schritt fehlschlägt (Job wird in CML rot).
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "scraper"))


def main() -> int:
    from analysis.eval_pipeline import run_eval_pipeline

    print("=" * 60)
    print("OeNB Chatbot-Eval Pipeline")
    print("=" * 60)

    result = run_eval_pipeline(base_dir=BASE_DIR)

    for step in result["steps"]:
        marker = {"ok": "✓", "failed": "✗", "skipped": "–"}[step["status"]]
        print(f"{marker} {step['name']:<24} {step['duration_s']:>7.1f}s  {step['detail'][:120]}")

    artifacts = result["artifacts"]
    if "score" in artifacts:
        print("-" * 60)
        print(f"Score: {artifacts['score']:.3f}  Verdikte: {artifacts['verdict_counts']}")
        print(f"Nach Typ: {json.dumps(artifacts.get('by_type', {}), ensure_ascii=False)}")
        if artifacts.get("baseline"):
            print(f"Baseline: {artifacts['baseline']}")
            for entry in artifacts.get("improved", []):
                print(f"  + {entry['id']} [{entry['type']}] {entry['from']} -> {entry['to']}")
            for entry in artifacts.get("regressed", []):
                print(f"  - {entry['id']} [{entry['type']}] {entry['from']} -> {entry['to']}")
        print(f"Report: {artifacts.get('report_path')}")

    if result["status"] != "ok":
        print("PIPELINE FEHLGESCHLAGEN — Details oben.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
