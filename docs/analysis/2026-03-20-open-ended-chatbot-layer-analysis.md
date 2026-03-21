# Open-Ended Chatbot Layer Analysis

## Purpose

This eval set is not a list of memorized demo questions. It is a compact stress test for the target OeNB assistant:

- open-ended website questions
- structured statistics questions
- mixed questions that need both
- consumer or visitor questions that may require a defensive answer

The goal is to distinguish between four failure layers instead of treating every bad answer as "the crawler is incomplete."

## Eval Set Scope

The fixture lives in [tests/fixtures/chatbot_eval_open_ended.json](/home/christoph/Dokumente/Baumhaus/Programmieren/oenb_downloads_skilled_version/.worktrees/feature-oenb-crawler-rebuild/tests/fixtures/chatbot_eval_open_ended.json).

It covers these question families:

- structured trend and current-value questions
- structured comparison questions
- release and source/navigation questions
- website history and corporate-topic questions
- museum and visitor-information questions
- consumer guidance questions

This split matters because the correct answer path is not uniform:

- `sql_first` for direct statistics
- `rag_first` for website and explanatory content
- `hybrid` for mixed questions that need structured data plus text context

## Layer Model

The current system can fail in four distinct layers:

### Coverage

The required content is not present, not grounded enough, or not safely retrievable from the current knowledge base.

Examples:

- `Was hat die OeNB in der NS-Zeit gemacht?`
- `Was schreibt die OeNB zu Frauen in Fuehrungsfunktionen?`
- `Warum hat die OeNB eine Kunstsammlung?`

This is not mainly a router problem. A larger or better-targeted site/corporate-content knowledge base is needed.

### Routing

The system chooses the wrong domain or answer strategy.

Examples:

- `Wie viel muss ich fuer einen flexiblen und einen fixen Kredit zahlen?`
- `Wie geht es den oesterreichischen Banken?`
- `Wo finde ich die Tabelle zu Sparzinsen?`

These questions show why open-ended handling cannot rely on hardcoded keyword maps. The target router needs candidate grounding from the knowledge base and an LLM decision over candidates.

### Retrieval

The route is plausible, but the retrieval step still promotes the wrong page, asset, or PDF.

Examples:

- `Wie hoch sind die Kreditzinsen gerade?`
- `Was kann ich mir im Geldmuseum anschauen?`

This is where broad full-site coverage can actually make things worse: more PDFs and generic assets increase noise unless retrieval is field-aware and domain-aware.

### Answering

The correct data family is found, but the answer mode is too narrow.

Examples:

- `Wie haben sich die Immobilienpreise entwickelt in den letzten Jahren?`
- `Wo liegen die Goldreserven von Oesterreich?`

In these cases the problem is not missing data. The system finds a relevant dataset but answers a trend question like a point lookup, or answers a location question with a value.

## Current Architectural Reading

The current architecture is already good enough for a subset of OeNB questions:

- direct ISAweb-backed fact questions
- release-aware structured statistics
- some policy-rate and reserve-asset queries

The weak layer is now mostly `rag_first` for general website, corporate, museum, and visitor content.

That means further ISAweb work alone will not solve the open-ended problem. The next meaningful architecture work is:

1. candidate generation from real KB records, not hardcoded term maps
2. LLM router over grounded candidates
3. stronger website/corporate retrieval with better chunk selection
4. answer-mode expansion for trend, comparison, explanation, and navigation questions

## Why This Is Not Just "Plugging Holes"

The point of this eval set is not to hand-curate answers to 15 questions. It is to expose which subsystem fails for which class of question.

That gives a reliable development loop:

- if many structured questions fail at `routing`, improve the router
- if website questions fail at `retrieval`, improve general-content retrieval
- if mixed questions fail at `answering`, improve answer-mode orchestration
- if historically or corporately oriented questions fail at `coverage`, improve crawl scope or document grounding

This avoids false confidence from fixing one or two examples while the broader layer remains weak.

## Recommended Next Steps

1. Keep this eval set as a living regression fixture.
2. Add a small runner that executes the fixture against the current QA pipeline and stores outputs per case.
3. Split future workstreams by layer:
   - router
   - retrieval
   - answering
   - coverage
4. Use the open-ended set alongside the structured-statistics eval set, not instead of it.
