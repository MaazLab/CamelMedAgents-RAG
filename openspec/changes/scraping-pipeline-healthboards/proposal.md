## Why

The existing scraping pipeline only covers `community.patient.info` (Discourse forum), limiting the diversity and volume of patient experience data for RAG retrieval. HealthBoards (`https://www.healthboards.com`) is a large vBulletin-based medical forum with 150+ disease-specific boards and years of patient discussions. Adding it as a second source broadens the corpus, improves semantic matching coverage, and validates the multi-source architecture already designed into the shared SQLite database and Qdrant collection.

## What Changes

- New `scrapers/healthboards/` module — a complete scraping pipeline for healthboards.com
- Patchright browser automation client to bypass Cloudflare + 403 blocks (healthboards blocks automated HTTP requests and standard headless Playwright; no JSON API available unlike Discourse)
- vBulletin HTML parser for board pages, thread pages, and post extraction (replacing Discourse JSON API parsing)
- Board-based topic discovery — healthboards uses flat boards (e.g., `forumdisplay.php?f=5` for Acne) instead of Discourse's tag+category system
- Disease-label-to-board mapping (`mappings.json`) for the same 20 disease labels used in `patient_info`
- vBulletin-specific content processor to clean HTML (quote blocks, signatures, smilies differ from Discourse's `cooked` HTML)
- Same 6-stage pipeline orchestration: query loading → board mapping → topic discovery → content scraping → embedding+Qdrant upsert → semantic query-post matching
- Reuses shared infrastructure: `scraper.db` (new source row), same Qdrant collection (distinguished by `source` payload field), same embedder, query loader, and query matcher
- New dependency: `patchright` (undetected Playwright fork — `pip install patchright`; bundles its own Chromium)

## Capabilities

### New Capabilities
- `healthboards-browser-client`: Playwright-based async browser client for healthboards.com with rate limiting, retry logic, and HTML parsing for board pages and thread pages
- `healthboards-board-mapping`: Disease label to vBulletin board ID/slug mapping for 20 disease labels
- `healthboards-content-processing`: vBulletin-specific HTML to clean text extraction (quote blocks, signatures, smilies, edit footers)
- `healthboards-topic-discovery`: Board-based topic discovery and thread content scraping with page-level resume via scrape_progress
- `healthboards-pipeline-orchestration`: 6-stage pipeline orchestration with Playwright client, CLI entry point, and graceful shutdown

### Modified Capabilities
<!-- No existing spec requirements are changing. The shared database, Qdrant, embedder,
     query loader, and query matcher are reused as-is via imports. -->

## Impact

- **New directory**: `scrapers/healthboards/` with ~11 files (config, models, client, mapper, content processor, topic discovery, pipeline, CLI, verify, mappings.json, __init__)
- **Shared database**: New source row `(name='healthboards', base_url='https://www.healthboards.com')` in existing `scraper.db`; all tables gain rows with this source_id
- **Qdrant**: Same collection `queries_relevant_scrape_data` gains points with `source="https://www.healthboards.com"`
- **Dependencies**: New `playwright` package; requires `playwright install chromium` post-install
- **Reused imports**: `scrapers.patient_info.database`, `scrapers.patient_info.embedder`, `scrapers.patient_info.vector_store`, `scrapers.patient_info.query_loader`, `scrapers.patient_info.query_matcher`, `scrapers.patient_info.logger`
- **No breaking changes** to existing `patient_info` pipeline or shared infrastructure
- **SQLite DB**: `DB_PATH = SCRAPERS_DIR / "data" / "scraper.db"` in `scrapers/healthboards/config.py` — same file as patient_info, segregated by `source_id`; no separate `healthboards_scraper.db`
