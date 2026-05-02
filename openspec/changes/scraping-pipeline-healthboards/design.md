## Context

The project already has a production scraping pipeline for `community.patient.info` (Discourse forum) in `scrapers/patient_info/`. It uses a shared SQLite database (`scrapers/data/scraper.db`) with source-segregated tables, Qdrant vector store for semantic search, and sentence-transformer embeddings. The architecture was explicitly designed for multi-source support: `sources` table, `source_id` FK on all data tables, `source` field in Qdrant payloads.

HealthBoards (`https://www.healthboards.com`) is a vBulletin 4.x forum with 150+ disease-specific boards. Unlike Discourse, it has **no JSON API** — all content is served as HTML pages. Additionally, the site returns **HTTP 403** for automated HTTP clients (e.g., httpx, requests), requiring browser automation via Playwright.

The existing pipeline modules — database, embedder, vector store, query loader, query matcher — are reusable as-is via imports. What needs to be built from scratch: the web client (Playwright replacing httpx), HTML parser (BeautifulSoup on vBulletin HTML replacing Discourse JSON parsing), board-based discovery (replacing tag/category dual discovery), and the pipeline orchestration wiring.

## Goals / Non-Goals

**Goals:**
- Scrape patient experience posts from healthboards.com for the same 20 disease labels as patient_info
- Store data in the shared `scraper.db` with a new source row, and in the same Qdrant collection with `source="https://www.healthboards.com"`
- Share the same SQLite database file (`scrapers/data/scraper.db`) as patient_info by setting `DB_PATH` in `config.py`; use local module copies (database, embedder, vector store, query loader, matcher) that all reference this shared path
- Support resumable scraping with page-level and topic-level checkpoints
- Handle vBulletin's HTML structure: board pages, thread pages, pagination, post extraction
- Bypass 403 blocks via Playwright headless browser

**Non-Goals:**
- Modifying the existing patient_info pipeline or shared modules
- Supporting vBulletin forums in general (this is healthboards-specific)
- Scraping boards beyond the 20 disease labels
- Authentication or login-based scraping (healthboards content is publicly readable)
- Real-time or incremental scraping (batch pipeline only, same as patient_info)

## Decisions

### #1 Patchright over Playwright/Selenium for browser automation
**Decision**: Use patchright (async Python API), an undetected Playwright fork that patches Chromium to evade Cloudflare bot detection.
**Rationale**: Standard Playwright (even with `playwright-stealth`) fails to bypass Cloudflare's JS challenge on healthboards.com. Patchright patches Chromium to remove WebDriver flags, CDP detection, and automation indicators, successfully resolving the challenge. It has the same API as Playwright (drop-in replacement) with native async/await support.
**Alternative rejected**: Selenium — synchronous by default, heavier setup, slower. Playwright + stealth — still blocked by Cloudflare. httpx with custom headers — returns 403.

### #2 Board-only discovery (no tag/category fallback)
**Decision**: Map each disease label directly to one or more vBulletin board IDs. No tag fallback needed.
**Rationale**: vBulletin doesn't have a tag system like Discourse. Each board is a dedicated topic (e.g., board 5 = Acne, board 45 = Diabetes). The mapping is simple and direct. Some labels share boards (e.g., angina and heart attack both map to Heart Disorders, board 65; cataract and conjunctivitis both map to Eye & Vision, board 54).
**Alternative rejected**: Search-based discovery — healthboards blocks `/search.php` for non-logged-in users and would be slower.

### #3 Conservative rate limiting (2s between requests)
**Decision**: Use 2-second delay between page navigations (vs 0.3s for Discourse JSON API).
**Rationale**: vBulletin forums are typically less tolerant of automated traffic than Discourse. Full page loads are heavier than JSON API calls. Starting conservative avoids IP blocks; can be tuned down after stability verification.
**Alternative rejected**: 0.3s (Discourse rate) — too aggressive for full browser page loads.

### #4 Local module copies sharing the same SQLite database file
**Decision**: Create local copies of `database.py`, `embedder.py`, `vector_store.py`, `query_loader.py`, `query_matcher.py`, and `logger.py` inside `scrapers/healthboards/`. All of them import `DB_PATH` from `scrapers.healthboards.config`, which points to the shared `scrapers/data/scraper.db` — the same file used by `scrapers/patient_info/`.
**Rationale**: The modules are functionally identical to their patient_info counterparts. Local copies avoid cross-package import coupling and allow healthboards-specific divergence without touching the patient_info pipeline. Data sharing (the actual goal) is achieved at the database-file level via `DB_PATH`, not at the module level. All tables use `source_id` FK for segregation, so both pipelines coexist safely in the same SQLite file.
**Alternative rejected**: Import directly from `scrapers.patient_info.*` — creates tight cross-package coupling; any patient_info change could silently break healthboards. Using a separate `healthboards_scraper.db` file — defeats the multi-source shared-database design and prevents cross-source queries.

### #5 vBulletin HTML parsing with BeautifulSoup
**Decision**: After Playwright loads a page, extract `page.content()` and parse with BeautifulSoup. Don't use Playwright selectors for data extraction.
**Rationale**: BeautifulSoup is faster and more reliable for static HTML parsing. Playwright selectors are designed for interaction (clicking, typing), not bulk data extraction. This separates concerns: Playwright handles browser automation + page loading, BeautifulSoup handles data extraction.

### #6 vBulletin URL patterns
**Decision**: Use canonical URL patterns:
- Board listing: `https://www.healthboards.com/boards/forumdisplay.php?f={board_id}&page={page}`
- Thread: `https://www.healthboards.com/boards/showthread.php?t={thread_id}&page={page}`
**Rationale**: The `forumdisplay.php?f=` and `showthread.php?t=` patterns are the canonical vBulletin URLs. While healthboards uses SEO-friendly URLs (e.g., `/boards/acne/`), these redirect to the canonical form. Using canonical URLs is more reliable for scraping.

### #7 Thread ID as platform_topic_id, Post ID as platform_post_id
**Decision**: Map vBulletin thread IDs to `platform_topic_id` and vBulletin post IDs to `platform_post_id` in the existing schema. These are extracted from HTML attributes (e.g., `id="post_12345"`, thread ID from URL parameter `t=`).
**Rationale**: Maintains 1:1 mapping with the existing schema. URL reconstruction: `https://www.healthboards.com/boards/showthread.php?t={platform_topic_id}&p={platform_post_id}`.

### #8 Same Qdrant collection, source-distinguished
**Decision**: Store healthboards posts in the same `queries_relevant_scrape_data` Qdrant collection, distinguished by `source="https://www.healthboards.com"` payload field.
**Rationale**: The existing architecture already supports multi-source via the `source` payload field. Same collection enables cross-source semantic search if needed. Separate collections would require collection management logic.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| **IP blocking on sustained Playwright scraping** | Conservative 2s rate limit, proper User-Agent, headless browser mimics real user. If blocked, increase delay or add random jitter. |
| **vBulletin HTML structure changes across themes/versions** | Use robust CSS selectors with fallbacks. Test against archived pages first. |
| **Playwright resource consumption (memory/CPU)** | Single browser context, reuse pages where possible, process topics serially. Playwright is lighter than Selenium. |
| **Some boards shared by multiple labels (e.g., board 65 for both angina and heart-attack)** | Same topic may be discovered twice for different labels. Deduplication via `UNIQUE(source_id, platform_topic_id)` prevents duplicate DB rows. First label wins for `disease_label` assignment. |
| **Thread pagination unknown (posts per page varies)** | Parse pagination element to discover total pages. Fetch all pages sequentially. |
| **403 block may extend to Playwright headless** | Resolved: switched to patchright which patches Chromium to evade Cloudflare detection. CF_CHALLENGE_WAIT increased to 30s with title keyword detection. |
| **New dependency (patchright) adds setup complexity** | Document `pip install patchright` in README. Patchright bundles its own Chromium. |
| **Scraping healthboards may violate Terms of Service** | Research use only, respectful rate limiting, no redistribution of raw content. |
