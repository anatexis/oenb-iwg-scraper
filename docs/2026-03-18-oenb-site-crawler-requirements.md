# OeNB Site Crawl Requirements for a Chatbot-Ready Knowledge Base

## Goal

This document summarizes what a rebuilt OeNB crawler must handle if its output is meant to become a high-quality knowledge base for a website chatbot.

Scope for the rebuild:

- Crawl the full `oenb.at` website.
- Preserve general website knowledge for chatbot answers.
- Detect and store all potentially relevant open-data resources.
- Treat `Statistik`, `Standardized Tables`, `ISAweb`, HTML tables and structured downloads as first-class sources.
- Prefer machine-readable acquisition paths over brittle UI scraping whenever possible.

More concretely, `full oenb.at website` should include:

- normal HTML content pages
- statistics and reporting sections
- downloadable assets under normal paths and `/dam/...`
- embedded or linked data applications
- OeNB-hosted Shiny applications
- OeNB-linked external Shiny deployments when they are part of the user journey
- ISAweb entry points, topic pages, chart pages, release pages and webservice-backed datasets
- relevant subdomains that are part of the OeNB web presence

Recommended scope rule:

- Treat `oenb.at` and OeNB-owned subdomains as primary crawl scope.
- Treat OeNB-linked third-party app hosts as secondary scope:
  - crawl them if they are clearly part of an OeNB product surface
  - mark them as externally hosted in metadata

## Research Method

I verified the current OeNB site structure on official OeNB pages and followed the relevant statistics and ISAweb paths as far as the available browsing tools allowed.

Confirmed directly on OeNB pages:

- `https://www.oenb.at/en/Statistics/Standardized-Tables.html`
- `https://www.oenb.at/en/Statistics/User-Defined-Tables/webservice.html`
- `https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/General-Overview-of-Inflation-Indicators.html`
- `https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/General-Overview-of-Inflation-Indicators/Selected-Inflation-Indicators.html`
- `https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1`
- `https://www.oenb.at/isawebstat/showReleaseForHierarchy?hierarchy=0&lang=EN`
- `https://www.oenb.at/dam/jcr%3A670b61d2-9c63-4ab3-ab5c-28c51ecc4948/quick-guide-webservice-de.pdf`

Confirmed from OeNB-hosted indexed ISAweb result pages:

- `https://www.oenb.at/isawebstat/dynabfrage`
- `https://www.oenb.at/isawebstat/dynabfrage/defineParams?...`

Where I make an inference from these sources, I mark it as such.

## Verified Site Structure

### 0. Legacy crawler coverage and what it already tells us

The existing spider already gives a useful picture of intended scope:

- seeds:
  - `https://www.oenb.at/`
  - `https://www.oenb.at/Service/Sitemap.html`
  - `https://finanzbildung.oenb.at/`
- allowed domains:
  - `oenb.at`
  - `www.oenb.at`
  - `finanzbildung.oenb.at`
- dedicated detectors for:
  - downloads
  - Shiny apps
  - interactive data portals
  - standardized tables
  - HTML pages with data tables
  - embedded data platforms

This is directionally right, but the current model is still too flat for the new goal. It collapses very different resource types into a single item model and does not yet turn ISAweb into a structured data acquisition pipeline.

Crawler implication:

- The rebuild should keep the broad discovery ambition of the legacy spider.
- The rebuild should replace the flat item model with resource-specific pipelines.

### 1. Statistics landing page is the main entry point for structured data

The OeNB `Data` page under `Statistics` is the canonical statistics landing page. It exposes nine top-level standardized-table sections:

1. OeNB, Eurosystem and monetary indicators
2. Interest rates and exchange rates
3. Financial institutions
4. Securities
5. Means of payment and payment systems
6. Prices, competitiveness
7. Economic and industry indicators
8. Financial accounts
9. External sector

The same page also links directly to:

- `User-defined query`
- `Web Service`
- `Release calendar`

Crawler implication:

- These statistics landing pages should be explicit seed URLs.
- Section hierarchy must be preserved as metadata, not reconstructed later from raw URLs only.

### 2. Standardized Tables pages follow a repeatable content pattern

A verified example is:

- `https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/General-Overview-of-Inflation-Indicators.html`

That page contains:

- a human-readable dataset or topic page
- a `Table` link
- an `Explanatory note` link
- a `Publication schedule` link
- a `Chart` link

Crawler implication:

- A standardized-table topic is not one document. It is a bundle.
- The crawler should model these links as one logical dataset family with multiple related representations:
  - landing/topic page
  - explanatory note page
  - publication schedule
  - chart/table UI
  - downloadable structured data

### 3. Explanatory-note pages are high-value chatbot content

A verified explanatory-note page:

- `https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/General-Overview-of-Inflation-Indicators/Selected-Inflation-Indicators.html`

This page contains durable metadata-like content such as:

- description
- source
- legal basis
- reporting institutions
- index keywords

Crawler implication:

- These pages are not secondary decoration. They are core knowledge-base documents.
- The chatbot will need them to answer definition, methodology and provenance questions.
- These pages should be extracted into structured text documents with dedicated fields for:
  - `description`
  - `source`
  - `legal_basis`
  - `reporting_institutions`
  - `keywords`

### 4. Chart pages expose structured export affordances

A verified chart page:

- `https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1`

Observed on the page:

- `CSV (all indicators)`
- `CSV (selected indicators)`
- `EXCEL (all indicators)`
- `EXCEL (selected indicators)`
- period editing controls

Crawler implication:

- For standardized tables, chart pages are often a more useful acquisition point than rendered HTML tables.
- The crawler should detect and persist export affordances even if it does not yet follow every UI action.
- When structured export is available, downloads should be preferred over scraping rendered cells.

### 5. The release calendar is a distinct crawl target

Verified endpoint:

- `https://www.oenb.at/isawebstat/showReleaseForHierarchy?hierarchy=0&lang=EN`

The `Data` landing page also describes the release calendar as daily updated and relevant for standardized tables.

Crawler implication:

- Publication schedules should be crawled into a separate entity type, not mixed into normal page text.
- These dates can drive incremental refreshes for the future crawler.

## Verified ISAweb Behavior

### 6. ISAweb is not just content, it is a query system

The `User-defined query` landing page states that users can:

- customize tables
- define their own layout
- save table settings
- reapply saved settings

Crawler implication:

- ISAweb must be treated as an application surface with query semantics, not just a set of pages.
- A crawler that only follows HTML links will miss the actual structured data model.

### 7. ISAweb queries require mandatory selections

From verified indexed `defineParams` pages, ISAweb exposes:

- indicator selection
- fixed dimensions
- optional or additional dimensions depending on hierarchy
- period selection
- sort order

Verified examples on OeNB-hosted pages:

- `Fixe Dimensionen`
- `Periodenauswahl`
- dimensions like `Produzent`, `Datentyp`, `Status`, `Region / partner`
- sector selectors such as `Volkswirtschaftlicher Sektor Schuldner` and `Volkswirtschaftlicher Sektor Gläubiger`
- warning message when selection is incomplete:
  - `Es wurde nicht in allen Bereichen eine Auswahl getroffen!`

Crawler implication:

- UI replay against session-bound ISAweb pages is fragile.
- Any automated extraction must understand that a valid query needs:
  - one or more indicators
  - all required dimensions
  - a valid period selection
- The crawler should not treat `showResult` pages as stable identifiers of a dataset.

### 8. ISAweb uses session-bound navigation that should not be the primary crawl API

Verified and indexed URLs include patterns like:

- `/isawebstat/dynabfrage/defineParams;jsessionid=...?...`
- `/isawebstat/dynabfrage/showResult?...`

Inference:

- These URLs are session-shaped UI routes, not good canonical identifiers for the knowledge base.

Crawler implication:

- Do not use `jsessionid` URLs as canonical dataset keys.
- Strip session fragments during normalization.
- Prefer stable identifiers derived from hierarchy, indicator code, dimensions and language.

### 9. Language is a first-class parameter

Verified across OeNB statistics and ISAweb pages:

- `lang=EN`
- German and English page variants

Crawler implication:

- Store language explicitly per document, dataset and extracted series.
- Canonicalization must decide whether `DE` and `EN` pages are:
  - separate knowledge documents
  - linked translations of the same conceptual resource

Recommended approach:

- Keep both.
- Link them through a shared canonical resource ID.

## Verified Web Service Model

### 10. OeNB provides a machine-readable statistics API

Verified official page:

- `https://www.oenb.at/en/Statistics/User-Defined-Tables/webservice.html`

The page states that the web service allows:

- search by user-defined criteria
- download in XML format
- search by indicator code in the browser address bar
- access to metadata
- access to publication schedules

Crawler implication:

- The new crawler should have a dedicated `ISAWebServiceClient`.
- This should be the primary acquisition path for structured statistical data.

### 11. The quick guide exposes concrete endpoint types

Verified from the OeNB quick guide PDF:

- `isadataservice/content`
- `isadataservice/meta`
- `isadataservice/datafrequency`
- `isadataservice/data`

Verified parameter model from the guide:

- `lang`
- `hierid`
- `mode`
- `pos`
- `starttime`
- `endtime`
- `freq`
- `dval1` to `dval10`

Verified examples in the guide include:

- fetching hierarchy content
- retrieving metadata for an indicator
- retrieving available frequencies
- retrieving data for one or more positions with dimension values

Crawler implication:

- ISAweb extraction should not start from browser automation.
- It should start from the web service model:
  - discover hierarchy
  - enumerate positions
  - fetch metadata
  - determine available frequencies
  - materialize data series

### 12. Indicator codes and dimensions are the durable keys

Verified from the quick guide:

- `pos` selects indicator positions
- `dval*` parameters constrain dimensions
- `hierid` selects hierarchy

Inference:

- For chatbot-grade facts, the durable identity of a time series is closer to:
  - `hierid`
  - `pos`
  - chosen dimension values
  - frequency
  - language
than to any UI page URL.

Crawler implication:

- Persist these fields in normalized form.
- Build dataset and series IDs from them.

## What the Rebuilt Crawler Must Respect

### 13. Full-site crawling and statistics crawling must be separate concerns

The full OeNB site includes:

- normal HTML content pages
- news and publications
- downloads in `/dam/...`
- dynamic statistics applications
- explanatory notes
- release calendars

Crawler implication:

- Build separate pipelines or resource handlers for:
  - HTML pages
  - binary assets
  - structured statistics pages
  - ISAweb API-backed resources
  - release schedules

Do not force all of them into one generic page parser.

### 14. PDFs should be handled selectively, not ignored

Your preferred strategy is the hybrid approach:

- keep the full website crawl
- keep open-data resources
- do not let PDFs dominate the corpus

Recommended crawler behavior:

- always record PDF metadata and provenance
- extract text only when at least one of the following is true:
  - linked from statistics sections
  - linked from explanatory notes or methodology pages
  - contains tables or clear statistical relevance
  - is necessary for definitions or methodological context

Crawler implication:

- PDF extraction should be a scoring-based secondary step, not the default for every file.

### 15. HTML tables matter, even outside ISAweb

The OeNB site contains explanatory and statistics pages that are useful even when they are not part of ISAweb downloads.

Crawler implication:

- Detect substantial HTML tables on normal pages.
- Persist table structure separately from body text when possible.
- Link each table back to:
  - page URL
  - section
  - heading context
  - crawl timestamp

### 16. Provenance is mandatory for chatbot trustworthiness

For questions like `aktueller Leitzins`, the chatbot should not answer with an unqualified number.

Crawler implication:

- Every extracted fact-like record should carry:
  - source URL
  - source type
  - title
  - language
  - crawl timestamp
  - data period
  - publication schedule if available
  - extraction method

Recommended chatbot contract:

- respond with the value plus the data vintage, for example:
  - `Stand Wissensbasis: Crawl vom 2026-03-18`

### 16a. Source attribution must be extracted explicitly, not as an accidental text by-product

For the later chatbot, source visibility is not optional. The crawler should extract and persist source attributions as first-class metadata.

The existing spider already partially supports this through:

- explicit parsing of `Quelle:`, `Source:` and `Datenquelle:`
- CSS selectors such as `.quelle`, `.source`, `.data-source`
- a Shiny-specific fallback for footer source labels

That is a useful starting point, but the rebuild should make source extraction much more systematic.

Required extraction behavior:

- search case-insensitively for:
  - `Quelle:`
  - `Quellen:`
  - `Source:`
  - `Sources:`
  - `Datenquelle:`
  - `Data source:`
  - `Reporting institutions:`
  - `Reporting institutions`
- accept optional whitespace around the colon
- parse multiple sources separated by:
  - comma
  - semicolon
  - slash
  - `und`
  - `and`

Crawler implication:

- source extraction should become its own reusable module
- source names should be stored as arrays
- raw matched source text should also be stored for traceability

### 16b. Highcharts and accessibility descriptions must be scanned for hidden source text

Some OeNB pages expose source attributions inside chart accessibility text rather than as visible captions.

Crawler implication:

- do not limit source extraction to visible paragraph text
- inspect at least:
  - `aria-label`
  - `aria-describedby`
  - Highcharts-generated accessibility descriptions
  - hidden descriptive blocks associated with charts

Recommended output fields for chart-like resources:

- `sources`
- `source_urls`
- `source_text_raw`
- `source_extraction_method`
- `chart_accessibility_text`

### 16c. Source links must be preserved separately from source names

Often, source organizations are linked directly, for example to Statistics Austria, Eurostat, AMS or related portals.

Crawler implication:

- store both the normalized source label and the linked source URL
- keep the source link relation even if the visible label is ambiguous

Recommended structure:

- `sources`: normalized organization names
- `source_links`: list of `{label, url}`

### 16d. Related provenance fields must be harvested alongside source labels

On statistics and explanatory pages, provenance may appear not only under `Quelle:` or `Source:` but also in nearby fields such as:

- `Reporting institutions`
- `Legal basis`
- `Description`
- `Metadata`

Crawler implication:

- these fields should be extracted together so the chatbot can explain not only who provided the data, but also under which reporting context or legal framework.

## How Linked ISAweb Pages Should Be Handled

### 16a. Linked ISAweb pages must be discovered, but not treated as canonical knowledge records by default

The legacy spider currently detects ISAweb links as `interactive_data` and then follows them recursively.

That discovery behavior is useful, but it is not sufficient as a storage model.

Recommended handling:

1. Discover every ISAweb link encountered on normal OeNB pages.
2. Store the linkage itself:
   - source page URL
   - anchor text
   - section heading
   - surrounding page section
3. Normalize the ISAweb URL:
   - strip `jsessionid`
   - remove fragments
   - normalize language
4. Classify the link target:
   - landing page
   - `dynabfrage`
   - `defineParams`
   - `showResult`
   - chart page
   - release schedule
   - export link
5. Hand the normalized target to an ISAweb-specific processing pipeline.

Important rule:

- A link to ISAweb is evidence of relevance and navigation context.
- It is not, by itself, the final dataset identity.

### 16b. Frequent ISAweb linking should increase priority, not duplicate storage

ISAweb pages are often linked from many statistics pages.

Recommended behavior:

- count incoming links from different OeNB pages
- preserve all parent-child relations
- store one canonical ISAweb resource record per normalized target
- enrich that record with:
  - all referring pages
  - both languages when available
  - section distribution
  - crawl frequency priority

This means:

- many links to the same ISAweb resource should strengthen confidence and priority
- they should not create many duplicate dataset records

### 16c. `showResult` and session-shaped URLs should be treated as transient query views

When the crawler encounters links like:

- `/isawebstat/dynabfrage/showResult?...`
- `/isawebstat/dynabfrage/defineParams;jsessionid=...?...`

it should:

- keep them as evidence of discoverability
- extract any stable parameters
- avoid using them as long-term canonical dataset IDs

Preferred canonicalization order:

1. explicit webservice identifier set
   - `hierid`
   - `pos`
   - `dval*`
   - `freq`
   - `lang`
2. stable chart or report identifier
3. normalized ISAweb page URL

### 16d. Linked ISAweb pages should create two outputs, not one

For every relevant linked ISAweb page, the crawler should ideally produce:

- a `navigation/document` record
  - where it was linked
  - how users reach it
  - human-readable label
- a `structured dataset` record
  - metadata
  - dimensions
  - frequencies
  - observations

That separation is important because the chatbot needs both:

- website navigation knowledge
- reliable numeric/statistical facts

## Recommended Resource Model for the New Crawler

### 17. Use separate entity types in the knowledge base

Recommended core entities:

- `PageDocument`
  - normal HTML content page
- `AssetDocument`
  - binary resource such as PDF, XLSX, CSV, ZIP
- `DatasetFamily`
  - logical statistics topic or standardized-table topic
- `DatasetMetadata`
  - explanatory note, source, legal basis, reporting institutions
- `TimeSeriesDataset`
  - normalized ISAweb/webservice dataset definition
- `TimeSeriesObservation`
  - period/value/unit observation rows
- `ReleaseEvent`
  - publication schedule item

Why this matters:

- A chatbot needs narrative context and hard numbers.
- One flattened JSON blob per URL will not be enough.

### 18. Preserve lineage between pages, datasets and files

Example lineage that the crawler should retain:

- standardized-table topic page
- explanatory-note page
- chart/table UI page
- CSV/XLSX export
- webservice metadata
- webservice observations

Crawler implication:

- Each derived artifact should know its parent topic and source page.
- This is required for:
  - traceability
  - deduplication
  - source citation in chatbot answers

## Recommended Architecture for the Rebuild

### 19. Minimum module split

Recommended modules for the new crawler:

- `site_discovery`
  - seeds, sitemap, internal-link traversal, canonicalization
- `page_extraction`
  - clean text, headings, navigation context, language
- `asset_discovery`
  - download detection and typing
- `html_table_extraction`
  - table detection and structure capture
- `statistics_catalog`
  - standardized-tables landing pages and section hierarchy
- `isaweb_discovery`
  - identify relevant hierarchies, topics and metadata pages
- `isaweb_service_client`
  - `content`, `meta`, `datafrequency`, `data`
- `release_calendar`
  - publication schedules
- `document_storage`
  - normalized output for the knowledge base

### 20. Recommended crawl strategy order

Recommended order:

1. Crawl the normal website and collect page and asset inventory.
2. Promote statistics sections to dedicated structured processing.
3. Build standardized-table dataset families from statistics landing pages.
4. Harvest explanatory notes and publication schedules.
5. Use the ISAweb web service to enumerate positions and metadata.
6. Materialize selected series and observations for chatbot-relevant statistics.
7. Score PDFs and only then extract relevant ones deeply.

This order keeps the whole-site crawl intact while preventing ISAweb from degenerating into unreliable browser replay.

## Anti-Patterns to Avoid

- Scraping rendered ISAweb tables as the primary source of truth.
- Using `jsessionid` URLs as canonical identifiers.
- Mixing explanatory-note text, downloads and observations into one flat record.
- Extracting every PDF deeply before scoring relevance.
- Losing the relation between a series and its parent statistics topic.
- Storing numeric values without period, unit and crawl provenance.

## Concrete Build Decisions That Follow From This Research

### 21. Architecture decisions already justified

Based on the verified OeNB structure, the following decisions are now well supported:

- Full-site crawl: yes.
- Hybrid resource strategy: yes.
- ISAweb structured extraction: yes.
- Web service as primary statistics acquisition path: yes.
- Explanatory notes as first-class knowledge documents: yes.
- Release calendar as structured refresh signal: yes.
- Selective PDF deep extraction instead of full extraction: yes.

## Open Questions for the Implementation Phase

These are not blockers for the rebuild direction, but they should be tested explicitly during implementation:

- Which ISAweb hierarchies can be enumerated fully through `isadataservice/content` without browser state?
- Which chart and standardized-table exports can be fetched directly from stable URLs versus requiring UI-generated requests?
- Whether units and value formatting need additional normalization beyond the `data` endpoint output.
- Whether `DE` and `EN` metadata are fully symmetric for all hierarchies.
- How often release calendar updates should trigger incremental recrawls.

## Source Links

Official OeNB pages used for this document:

- https://www.oenb.at/en/Statistics/Standardized-Tables.html
- https://www.oenb.at/en/Statistics/User-Defined-Tables/webservice.html
- https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/General-Overview-of-Inflation-Indicators.html
- https://www.oenb.at/en/Statistics/Standardized-Tables/Prices--Competitiveness/General-Overview-of-Inflation-Indicators/Selected-Inflation-Indicators.html
- https://www.oenb.at/isawebstat/createChart?lang=EN&report=1.1.1
- https://www.oenb.at/isawebstat/showReleaseForHierarchy?hierarchy=0&lang=EN
- https://www.oenb.at/dam/jcr%3A670b61d2-9c63-4ab3-ab5c-28c51ecc4948/quick-guide-webservice-de.pdf

OeNB-hosted ISAweb pages that were used as indexed evidence for dynamic query behavior:

- https://www.oenb.at/isawebstat/dynabfrage
- https://www.oenb.at/isawebstat/dynabfrage/defineParams
