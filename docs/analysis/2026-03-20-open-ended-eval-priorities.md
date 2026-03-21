# Open-Ended Eval Priorities

## Basis

Diese Priorisierung basiert auf:

- [open_ended_eval_report_v1.json](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/data/statistics_production/open_ended_eval_report_v1.json)
- gezielten Debug-Läufen auf den zuvor als `unknown` markierten Fällen
- [chatbot_eval_open_ended.json](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/fixtures/chatbot_eval_open_ended.json)

## Ergebnis

Der Engpass liegt aktuell **nicht primär im Crawl**, sondern im Fragerouting und im offenen Website-Retrieval.

Besonders klar:

- `Was ist ISAweb und wie kann ich damit Daten abrufen?`
  Fehlrouting in `corporate_topics`
- `Wann werden die nächsten Inflationsdaten veröffentlicht?`
  Fehlrouting Richtung Finanzbildung, danach PDF-Treffer
- `Gibt es die Daten zum Bargeldumlauf auch als CSV oder Excel?`
  Fehlrouting in `corporate_topics`
- `Wo finde ich die Tabelle zu Sparzinsen?`
  ähnliche Klasse: Statistiknavigation wird nicht als Statistiknavigation behandelt

Das heißt: Ein weiterer großer Crawl würde diese Fälle wahrscheinlich **nicht** sauber lösen. Mehr Daten würden hier eher noch mehr Rauschen erzeugen.

## Priorität 1: Routing für Statistiknavigation und Statistik-Erklärfragen

Zuerst sollte der Router besser zwischen diesen Klassen unterscheiden:

- `value lookup`
- `trend/question over time`
- `explanation of a statistic`
- `navigation to table / download / release`

Aktuell kippen Fragen wie `ISAweb`, `Inflationsdaten veröffentlicht`, `Bargeldumlauf als CSV/Excel`, `Sparzinsen` zu oft in allgemeine Website- oder Corporate-Pfade.

Konkrete betroffene Fälle:

- `open_ended_008`
- `open_ended_009`
- `open_ended_010`
- `open_ended_012`
- auch `open_ended_006`

## Priorität 2: Retrieval-Guardrails für `rag_first`

Wenn `rag_first` gewählt wird, gewinnen aktuell immer noch fachfremde PDFs zu leicht.

Betroffene Fälle:

- `Wie hoch sind die Kreditzinsen gerade?`
- `Was kann ich mir im Geldmuseum anschauen?`

Das Ziel ist nicht nur bessere Trefferbewertung, sondern härtere Ausschlüsse:

- Finanzbildungs-PDFs dürfen nicht Standardantwort auf Release-/Statistikfragen sein
- Museumsfragen sollten Seiten- oder Museumscontent vor Assets priorisieren

## Priorität 3: Antwortmodi ausbauen

Einige Fragen finden schon den richtigen Themenraum, aber der Antwortmodus ist zu schmal.

Betroffene Fälle:

- `Wie haben sich die Immobilienpreise entwickelt in den letzten Jahren?`
  braucht Trend- oder Zeitreihen-Antwort statt Punktwert
- `Wo liegen die Goldreserven von Österreich?`
  braucht Lager-/Erklärkontext statt Reservewert
- `Was ist der Unterschied zwischen Basiszinssatz und Referenzzinssatz?`
  braucht Definition plus aktuelle Werte

Das ist kein Crawl-Problem, sondern ein `answering orchestration`-Problem.

## Priorität 4: Echte Coverage-Lücken

Diese Fragen bleiben derzeit korrekt defensiv:

- `Was hat die OeNB in der NS-Zeit gemacht?`
- `Was schreibt die OeNB zu Frauen in Führungsfunktionen?`
- `Warum hat die OeNB eine Kunstsammlung?`
- `Wie viel Taschengeld soll ich meinen Kindern geben?`

Hier lohnt sich erst danach ein Crawl-/KB-Ausbau.

## Empfehlung

Vor dem nächsten großen Crawl:

1. Router für Statistiknavigation, Releases und Erklärfragen schärfen
2. `rag_first`-Retrieval für Website-/Museums-/Assetfragen härten
3. Antwortmodi für Trend, Erklärung und Navigation ausbauen

Erst danach entscheiden, ob ein weiterer großer Crawl noch echte Coverage-Lücken schließt.
