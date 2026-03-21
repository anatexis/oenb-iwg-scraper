# Open-Ended Eval Handoff

Date: 2026-03-21

## Zweck dieser Notiz

Diese Notiz ist eine ausführliche Übergabe für den aktuellen Arbeitsstand rund um das Open-Ended-Eval des OeNB-Chatbot-/RAG-Stacks. Sie soll so geschrieben sein, dass ein anderes Modell oder ein Mensch nach Kontextverlust schnell wieder arbeitsfähig ist, ohne sich den gesamten Verlauf neu erschließen zu müssen.

Diese Übergabe beschreibt:

- das fachliche Ziel des aktuellen Arbeitsblocks
- die Architektur und die betroffenen Komponenten
- was bereits umgesetzt wurde
- welche Entscheidungen bewusst getroffen wurden
- welche Tests aktuell grün sind
- was noch offen ist
- wie die nächsten Schritte sinnvollerweise aussehen

## Kurzfassung des Projektbilds

Das Repo enthält einen OeNB-Crawler- und Chatbot-Stack mit zwei Wissensquellen:

- eine strukturierte Statistik-KB unter [data/statistics_production](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/data/statistics_production)
- eine Website-/Dokumenten-KB unter [data/full_site_production](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/data/full_site_production)

Der relevante Pfad für Nutzerfragen ist:

- Routing in [analysis/query_router.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/query_router.py)
- Retrieval in [analysis/query_knowledge_base.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/query_knowledge_base.py), [analysis/chatbot_retrieval.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/chatbot_retrieval.py) und [analysis/hybrid_retrieval.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/hybrid_retrieval.py)
- Antwortsynthese in [analysis/chatbot_answering.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/chatbot_answering.py)

## Ausgangspunkt und Problemverständnis

Der aktuelle Arbeitsstrang wurde durch das Open-Ended-Eval ausgelöst.

Wichtige Referenzen:

- Analyse: [docs/analysis/2026-03-20-open-ended-eval-priorities.md](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/docs/analysis/2026-03-20-open-ended-eval-priorities.md)
- Open-Ended-Fixture: [tests/fixtures/chatbot_eval_open_ended.json](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/fixtures/chatbot_eval_open_ended.json)
- letzter Report: [data/statistics_production/open_ended_eval_report_v1.json](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/data/statistics_production/open_ended_eval_report_v1.json)
- Umsetzungsplan: [docs/plans/2026-03-20-router-priority-1-implementation.md](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/docs/plans/2026-03-20-router-priority-1-implementation.md)

Die zentrale Diagnose aus der Analyse war:

- Der Engpass liegt nicht primär im Crawl.
- Der Engpass liegt vor allem in Routing, offenen Website-/Statistik-Mischfällen und dem Antwortmodus.
- Ein größerer Crawl würde die Kernprobleme voraussichtlich nicht direkt beheben, sondern zunächst mehr konkurrierende Treffer erzeugen.

Typische Problemfälle waren:

- `Was ist ISAweb und wie kann ich damit Daten abrufen?`
- `Wann werden die nächsten Inflationsdaten veröffentlicht?`
- `Wo finde ich die Tabelle zu Sparzinsen?`
- `Gibt es die Daten zum Bargeldumlauf auch als CSV oder Excel?`
- `Wie geht es den österreichischen Banken?`

## Fachliches Ziel des aktuellen Arbeitsblocks

Ziel ist nicht, einzelne kaputte Fragen mit Sonderregeln zu flicken. Ziel ist, die allgemeine Robustheit des Chatbots für offene OeNB-Fragen zu erhöhen.

Konkret heißt das:

- Fragetyp und Thema getrennt modellieren
- generische offene Fragetypen explizit machen
- OOD-Fragen defensiv behandeln
- Statistikfragen gegen fachfremde Treffer absichern
- Release- und Navigationsfragen nicht mehr wie reine Wertabfragen behandeln
- Website- und Statistik-Kontext bei Bedarf bewusst kombinieren

Die entscheidende Designidee lautet:

- nicht `wenn Query X dann Sonderfall Y`
- sondern `wenn Query-Typ release/navigation/explanation/trend ist, dann geeignete Routing-, Retrieval- und Answering-Regeln anwenden`

## Die neuen generischen Fragetypen

Im Router wurde eine explizite `query_intent`-Schicht eingeführt. Sie lebt in [analysis/query_router.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/query_router.py).

Die aktuell relevanten Klassen sind:

- `release_lookup`
- `navigation`
- `explanation`
- `trend_over_time`
- `fact_lookup`
- `topic_overview`
- `comparison`
- `advice_request`

Wichtig ist die Trennung:

- `query_intent` beschreibt die Form der Frage
- `domains` beschreiben den fachlichen Themenraum

Die Domain-Ebene umfasst u. a.:

- `interest_rates`
- `commodity_prices`
- `real_estate`
- `financial_soundness`
- `monetary_policy`
- `reserves_assets`
- `website_general`
- `financial_education`
- `corporate_topics`

## Bisher umgesetzte Änderungen

### 1. Open-Ended-Fixture verbreitert

Die Eval-Fixture [tests/fixtures/chatbot_eval_open_ended.json](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/fixtures/chatbot_eval_open_ended.json) wurde erweitert.

Neu abgedeckt sind jetzt nicht nur einzelne Originalfälle, sondern breitere Fragetypen:

- Release-Fragen
- Navigationsfragen zu Tabellen und Zeitreihen
- Download-/CSV-/Excel-Fragen
- Statistik-Erklärfragen
- Trendfragen
- explizite OOD-Fälle

Das Ziel war, nicht mehr nur auf den historischen offenen Fällen zu testen, sondern auf Klassen von Fragen.

### 2. Router auf generische Intents umgestellt

In [analysis/query_router.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/query_router.py) wurde der Router erweitert:

- generische `query_intent`-Erkennung
- candidate-informed Routing
- explizite Guardrails gegen Fehlrouten in fachfremde Bereiche
- bessere Domain-Auswahl anhand Query-Form plus Kandidaten

Der Router unterscheidet jetzt deutlich sauberer zwischen:

- echter Faktfrage
- Navigationsfrage
- Release-Frage
- Statistik-Erklärung
- Trendfrage

### 3. Domain-Hints fachlich verbreitert

In [analysis/domain_gating.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/domain_gating.py) wurden Domain-Hints ausgebaut.

Beispiele:

- `interest_rates` kennt jetzt unter anderem `sparzinsen`, `kreditzinsen`, `wohnbaukreditzinsen`
- `commodity_prices` kennt unter anderem `inflation`, `inflationsdaten`, `verbraucherpreisindex`, `vpi`
- `real_estate` kennt `wohnimmobilienpreisindex`
- `financial_soundness` kennt Banken-/FSI-nahe Signale

Wichtig:

- Das ist Themenmodellierung, nicht Einzelfallmodellierung.
- Ziel ist nicht, die letzten offenen Queries nachzubauen, sondern typische Themenräume abzugreifen.

### 4. OOD-Guardrails eingeführt

Der Router kann klar out-of-distribution Fragen jetzt defensiv auf `reject_or_clarify` setzen.

Abgesicherte Beispiele:

- Wetterfragen
- Sportfragen wie Champions League

Wichtige Erkenntnis aus diesem Teil:

- Es wäre falsch, OOD über ständig wachsende In-Scope-/OOD-Hint-Listen zu verwalten.
- Deshalb wurde der OOD-Guard zuletzt so angepasst, dass starke In-Scope-Kandidaten einen OOD-Abbruch überstimmen können.

Praktischer Effekt:

- `Financial Soundness Indicators` wird nicht mehr nur deshalb fälschlich als OOD behandelt, weil die Query kein klassisches deutsches OeNB-Hint-Wort enthält.
- Gleichzeitig bleiben echte OOD-Fälle weiter defensiv.

Die entscheidende Logik ist:

- OOD-Härtung standardmäßig streng
- aber wenn bereits ein starker, fachlich passender OeNB-Kandidat vorliegt, wird kein blinder OOD-Abbruch gemacht

### 5. Guardrails gegen fachfremde Retrieval-Pfade

Release- und Navigationsfragen sind zuvor häufig in fachfremde Treffer gekippt, insbesondere:

- `financial_education`
- `corporate_topics`
- irrelevante PDFs

Das wurde an mehreren Stellen gehärtet:

- im Router
- in der Domain-Gating-Logik
- in der Retrieval-Gewichtung

Ziel:

- Statistiknahe Queries sollen nicht von schwachen Texttreffern in falschen Themenräumen gekapert werden

### 6. Retrieval für Release- und Navigationsfragen angepasst

In [analysis/query_knowledge_base.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/query_knowledge_base.py) wurde das Ranking für website-sensitive Intents erweitert.

Für `release_lookup` und `navigation` gilt jetzt stärker:

- Website- und Seitentreffer dürfen strukturierte Reihen überholen, wenn die Frage eigentlich nach Veröffentlichungs-, Download- oder Navigationskontext fragt
- Release-/Download-Kontext wird im Ranking sichtbarer gemacht
- Website-first-Antworten sind für diese Fragetypen grundsätzlich erlaubt und erwünscht

### 7. Hybrid Retrieval um orchestrierte Subqueries erweitert

In [analysis/hybrid_retrieval.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/hybrid_retrieval.py) wurde für `release_lookup` und `navigation` eine gezielte Subquery-Orchestrierung ergänzt.

Logik:

- Wenn `website_general` plus Statistikdomäne(n) relevant sind, werden bewusste Teilqueries erzeugt
- zuerst eine Website-Query mit der Originalfrage
- danach fokussierte Statistik-Queries für die nicht-Website-Domänen

Das ist bewusst keine volle Planungsengine, sondern eine kleine, robuste Orchestrierung für die häufigsten Mischfälle.

### 8. Answering für Release-/Navigation-Mischfälle ausgebaut

In [analysis/chatbot_answering.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/chatbot_answering.py) wurde der Antwortmodus erweitert.

Wesentliche Punkte:

- `multi_part` wird nicht mehr blind auf jede Situation mit `subquery_results` angewendet
- `multi_part` wird bewusst genutzt für:
  - `release_lookup`
  - `navigation`
  - echte Mehrthemen-`topic_overview`-Queries wie `Immobilienpreise und Gold`
- bei `release_lookup` und `navigation` wird die `website_general`-Teilantwort zuerst gerendert
- die erste Website-Teilantwort wird ohne unnötiges Query-Präfix an den Anfang gestellt
- klassische Einzelantworten wie `aktueller Leitzins` bleiben Einzelantworten und werden nicht durch Nebenpfade versehentlich zu `multi_part`

Das war ein wichtiger Korrekturschritt, weil die erste Version dieser Änderung bestehende Einzelantworten beschädigt hatte.

## Relevante Dateien mit echten Änderungen

Die Hauptdateien dieses Arbeitsblocks sind:

- [analysis/query_router.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/query_router.py)
- [analysis/domain_gating.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/domain_gating.py)
- [analysis/query_knowledge_base.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/query_knowledge_base.py)
- [analysis/hybrid_retrieval.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/hybrid_retrieval.py)
- [analysis/chatbot_answering.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/chatbot_answering.py)
- [analysis/prompts/router_prompt.txt](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/analysis/prompts/router_prompt.txt)

Relevante Testdateien:

- [tests/test_query_router.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/test_query_router.py)
- [tests/test_query_knowledge_base.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/test_query_knowledge_base.py)
- [tests/test_hybrid_retrieval.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/test_hybrid_retrieval.py)
- [tests/test_chatbot_answering.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/test_chatbot_answering.py)
- [tests/test_domain_gating.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/test_domain_gating.py)
- [tests/test_chatbot_eval_open_ended_fixture.py](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/test_chatbot_eval_open_ended_fixture.py)

## Wichtige Designentscheidungen

### Entscheidung 1: Kein reines Löcherstopfen

Es wurde bewusst gegen einen Ansatz entschieden, der nur die offenen Eval-Fragen einzeln nachbaut.

Nicht gewollt:

- `wenn query == inflationsdaten veröffentlicht`
- `wenn query enthält bargeldumlauf csv`
- `wenn query enthält isaweb`

Stattdessen:

- generische Query-Intent-Klassen
- thematische Domain-Hints
- Guardrails zwischen Frageform und Retrieval-Pfad

### Entscheidung 2: OOD nicht über immer mehr Stichwörter lösen

Ein wichtiger Diskussionspunkt war die Frage, ob neue OOD-/In-Scope-Hints nur wieder eine neue Form von Löcherstopfen sind.

Die aktuell gewählte Richtung ist:

- OOD-Fragen weiterhin defensiv behandeln
- aber keine eskalierende Hint-Sammlung aufbauen
- stattdessen bekannte, starke Kandidaten als Gegenbeweis gegen OOD verwenden

Das ist wesentlich robuster als ständig neue Stichwörter einzubauen.

### Entscheidung 3: Kein Full-Crawl als reflexartiger nächster Schritt

Die aktuelle Einschätzung ist:

- Ein kompletter Crawl würde wahrscheinlich zunächst mehr Rauschen erzeugen
- viele der aktuellen Fehler sind Routing-/Retrieval-/Answering-Fehler, nicht reine Coverage-Lücken
- ein gezielter Crawl kann später sinnvoll sein, aber erst nach der nächsten Eval-Runde und nur bei echter Lücke

## Teststatus

Die wesentlichen neuen Änderungen sind aktuell durch lokale Regressionstests abgesichert.

Letzter breiter Lauf:

```bash
pytest tests/test_query_router.py tests/test_query_knowledge_base.py tests/test_hybrid_retrieval.py tests/test_chatbot_answering.py tests/test_domain_gating.py tests/test_chatbot_eval_open_ended_fixture.py -q
```

Ergebnis:

- `74 passed in 0.29s`

Zusätzlich wichtig:

- Die letzten Korrekturen in `chatbot_answering` wurden TDD-getrieben gemacht
- dabei wurden zuerst neue bzw. rote Regressionen in `tests/test_hybrid_retrieval.py` und `tests/test_chatbot_answering.py` geschrieben und danach minimal grün gezogen

## Was zuletzt konkret korrigiert wurde

Der letzte Feinschliff bestand aus zwei Kernkorrekturen:

### A. Multi-Part-Antworten nicht zu breit anwenden

Ein Zwischenstand hatte dazu geführt, dass auch normale Faktantworten wie `aktueller Leitzins` plötzlich als `multi_part` herausfielen.

Das wurde korrigiert:

- `multi_part` für `release_lookup` und `navigation`
- `multi_part` für echte Mehrthemen-`topic_overview`-Queries
- nicht mehr für normale Einzelqueries mit zufälligen Subquery-Nebenprodukten

### B. OOD-Guard darf starke In-Scope-Kandidaten nicht überfahren

Ein Zwischenstand hatte zur Folge, dass eine Query wie `Financial Soundness Indicators` in kleinen Fixtures auf `not_found` bzw. `reject_or_clarify` kippte.

Das wurde nicht mit neuen Hint-Wörtern gefixt, sondern strukturell:

- starker Kandidatenmatch auf bekannte Statistik-/OeNB-Inhalte verhindert OOD-Abbruch

## Aktueller bekannter Zustand des Open-Ended-Reports

Der Report [data/statistics_production/open_ended_eval_report_v1.json](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/data/statistics_production/open_ended_eval_report_v1.json) wurde im Verlauf mehrfach neu erzeugt.

Wichtig für die Übergabe:

- Der gespeicherte Report ist sehr wahrscheinlich nicht mehr exakt auf dem allerletzten Codezustand.
- Nach den jüngsten Fixes in `chatbot_answering` und dem kandidatengestützten OOD-Bypass wurde meines Wissens noch kein frischer Voll-Eval mehr dokumentiert.

Das heißt:

- Unit- und Regressionstests sind aktuell grün
- der End-to-End-Open-Ended-Report muss als nächster Schritt neu erzeugt werden

## Was noch nicht als erledigt gelten sollte

Folgende Punkte sind noch offen oder mindestens erneut zu prüfen:

- Wie gut lösen die neuen Release-/Navigation-Pfade die echten Open-Ended-Fälle im Voll-Eval
- Ob `ISAweb`, `Inflationsdaten veröffentlicht`, `Sparzinsen`, `Bargeldumlauf CSV/Excel` jetzt inhaltlich wirklich besser sind oder nur defensiver geworden sind
- Ob `website_general`-Priorisierung in `release_lookup`/`navigation` zu neuen Seiteneffekten führt
- Ob es echte Coverage-Lücken bei Release-Kalenderseiten, Downloadseiten oder ISAweb-Erklärseiten gibt

## Empfohlene nächste Schritte

Die sinnvolle Weiterentwicklung ist aus meiner Sicht:

### 1. Voll-Eval auf dem aktuellen Code neu laufen lassen

Das ist der direkt nächste Pflichtschritt. Ohne diesen Lauf weiß man nicht, ob die letzten Änderungen nur die Unit-Tests oder auch die reale Open-Ended-Leistung verbessert haben.

Konkreter Befehl im Worktree:

```bash
python -m analysis.run_chatbot_eval tests/fixtures/chatbot_eval_open_ended.json data/statistics_production/open_ended_eval_report_v1.json --base-dir .
```

Optional mit Debug:

```bash
python -m analysis.run_chatbot_eval tests/fixtures/chatbot_eval_open_ended.json data/statistics_production/open_ended_eval_report_v1.json --base-dir . --debug
```

### 2. Die verbleibenden schlechten Fälle nach Fehlerklasse gruppieren

Nach dem neuen Eval sollten Restprobleme nicht wieder pro Query gefixt werden, sondern nach Ursache:

- Routing-Problem
- Retrieval-/Ranking-Problem
- Answering-/Orchestrierungs-Problem
- echte Coverage-Lücke

### 3. Erst danach über Crawl entscheiden

Wenn die Restfälle danach zeigen, dass wichtige Seitentypen wirklich nicht in der KB vorhanden sind, dann ist ein gezielter Crawl sinnvoll.

Sinnvolle Kandidaten für gezielte Coverage-Prüfung:

- Release-Kalenderseiten
- ISAweb-Erklärseiten
- Download-/CSV-/Excel-Seiten
- Statistik-Landingpages

Ein kompletter Full-Crawl sollte nur dann kommen, wenn die Coverage-Lücke real belegt ist.

## Konkrete Resume-Strategie für ein anderes Modell

Wenn ein anderes Modell nach Kontextwipe übernimmt, sollte es so starten:

1. In den Worktree wechseln:

```bash
cd /home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild
```

2. Zuerst diese Referenzen lesen:

- [docs/analysis/2026-03-20-open-ended-eval-priorities.md](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/docs/analysis/2026-03-20-open-ended-eval-priorities.md)
- [docs/plans/2026-03-20-router-priority-1-implementation.md](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/docs/plans/2026-03-20-router-priority-1-implementation.md)
- [docs/runbooks/2026-03-21-open-ended-eval-handoff.md](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/docs/runbooks/2026-03-21-open-ended-eval-handoff.md)

3. Danach zuerst die Regression verifizieren:

```bash
pytest tests/test_query_router.py tests/test_query_knowledge_base.py tests/test_hybrid_retrieval.py tests/test_chatbot_answering.py tests/test_domain_gating.py tests/test_chatbot_eval_open_ended_fixture.py -q
```

4. Danach den Voll-Eval neu erzeugen:

```bash
python -m analysis.run_chatbot_eval tests/fixtures/chatbot_eval_open_ended.json data/statistics_production/open_ended_eval_report_v1.json --base-dir .
```

5. Erst dann neue Codeänderungen planen

## Arbeitsprinzipien, die in diesem Strang wichtig waren

Diese Prinzipien sollten beim Weiterarbeiten beibehalten werden:

- keine Einzelfall-Hacks, wenn sich ein generischer Fragetyp modellieren lässt
- keine eskalierende OOD-Hint-Sammlung
- kein reflexartiger Crawl, solange Routing/Retrieval/Answering die Ursache sind
- TDD für Verhaltensänderungen
- End-to-End-Eval als Realitätstest, nicht nur Unit-Tests

## Aktueller Arbeitsstatus in einem Satz

Die Architektur wurde erfolgreich von fallweiser Router-Flickerei in Richtung `query_intent + domain separation + guardrails + website/statistics subquery orchestration` verschoben; die breite Regression ist grün, aber der aktualisierte Voll-Eval ist der nächste zwingende Schritt.
