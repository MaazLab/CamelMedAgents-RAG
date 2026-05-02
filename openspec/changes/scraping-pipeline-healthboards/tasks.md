## 1. Project Setup

- [x] 1.1 Create directory structure: `scrapers/healthboards/`, `scrapers/healthboards/__init__.py`, `scrapers/data/www.healthboards.com/cache/`, `scrapers/logs/www.healthboards.com/`
- [x] 1.2 Create `scrapers/healthboards/config.py` with settings: `BASE_URL = "https://www.healthboards.com"`, `_SOURCE_SLUG = "www.healthboards.com"`, `SOURCE_NAME = "healthboards"`, patchright browser settings (headless=True, viewport, user-agent), `RATE_LIMIT_DELAY = 2.0`, `REQUEST_TIMEOUT = 60`, `RETRY_MAX_ATTEMPTS = 3`, `RETRY_BACKOFF_FACTOR = 2`, `DATA_DIR`, `LOGS_DIR`, `CACHE_DIR` rooted at `SCRAPERS_DIR / {data|logs} / _SOURCE_SLUG`; `DB_PATH = SCRAPERS_DIR / "data" / "scraper.db"` (shared SQLite database — same file used by patient_info, NOT a separate file); `QDRANT_URL`, `QDRANT_COLLECTION_NAME`, `EMBEDDING_MODEL` defined locally (not imported from patient_info)
- [x] 1.3 Add `patchright` (undetected Playwright fork) to project dependencies and document `pip install patchright` setup step

## 2. Pydantic Models

- [x] 2.1 Create `scrapers/healthboards/models.py` with Pydantic models: `Board` (id, name, slug), `ThreadSummary` (thread_id, title, author, reply_count, view_count, last_post_date), `ThreadPost` (post_id, post_number, author, post_date, html_content, reply_to_post_number), `ThreadPage` (thread_id, title, page_number, total_pages, posts: list[ThreadPost])

## 3. Board Mapping

- [x] 3.1 Create `scrapers/healthboards/mappings.json` with the static mapping of all 20 disease labels to board IDs, board slugs, board names, and medical categories (acne→5, angina→65, appendicitis→46, arthritis→15, b12-deficiency→14, cancer→22, cataract→54, conjunctivitis→54, diabetes→45, headache→62, heart-attack→65, hepatitis→66, hernia→46, hypertension→61, otitis-media→164, piles→20, renal-failure→78, stroke-and-tia→119, urinary-tract-infection→124, urticarial-rash→138)
- [x] 3.2 Create `scrapers/healthboards/board_mapper.py` with `BoardMapper` class: `load_mappings()`, `get_board_id(label)`, `get_board_slug(label)`, `get_board_name(label)`, `get_medical_category(label)`

## 4. Playwright Browser Client

- [x] 4.1 Create `scrapers/healthboards/healthboards_client.py` with `HealthBoardsClient` class as async context manager: launch patchright Chromium (undetected fork), configure realistic User-Agent and viewport, implement `__aenter__`/`__aexit__` with robust cleanup for browser lifecycle
- [x] 4.2 Implement rate limiting: enforce 2-second minimum delay between consecutive page navigations using asyncio timestamp tracking
- [x] 4.3 Implement retry with exponential backoff: retry page loads on timeout or navigation error up to 3 times with backoff factor 2 (2s, 4s, 8s); no retry on 404
- [x] 4.4 Implement `get_board_threads(board_id, page=1)` method: navigate to `forumdisplay.php?f={board_id}&page={page}`, extract page HTML via `page.content()`, parse with BeautifulSoup to extract list of `ThreadSummary` objects (thread_id, title, author, reply_count, view_count, last_post_date), detect whether more pages exist from pagination element
- [x] 4.5 Implement `get_thread_page(thread_id, page=1)` method: navigate to `showthread.php?t={thread_id}&page={page}`, extract page HTML, parse with BeautifulSoup to extract list of `ThreadPost` objects (post_id, post_number, author, post_date, html_content), extract thread title from page heading
- [x] 4.6 Implement `get_thread_page_count(thread_id)` method: navigate to thread page 1, extract total page count from pagination element (return 1 if no pagination)

## 5. Content Processing

- [x] 5.1 Create `scrapers/healthboards/content_processor.py` with `extract_text_from_vbulletin_html(html)` function: parse with BeautifulSoup, remove `<div class="bbcode_container">` / `<div class="bbcode_quote">` quoted reply blocks, remove `<div class="signaturecontainer">` signatures, remove `<img>` tags (smilies, avatars, attachments), remove "Last edited by..." footers, extract text with `get_text(separator="\n")`, collapse multiple blank lines, strip per-line whitespace

## 6. Topic Discovery

- [x] 6.1 Create `scrapers/healthboards/topic_discovery.py` with `TopicDiscovery(client, db, mapper, source_id)` class
- [x] 6.2 Implement `discover_topics_for_label(label, max_topics=None)`: get board_id from mapper, check `scrape_progress` for resume (scope_type='board', scope_id=str(board_id)), paginate through board pages via `client.get_board_threads()`, insert each thread into `topics` table with `scrape_status='discovered'` and disease_label/category_name/medical_category from mapper, update `scrape_progress.last_page` after each page, stop when no more pages or max_topics reached, set `completed=TRUE` when all pages exhausted
- [x] 6.3 Implement `scrape_topic(topic_row)`: fetch total page count via `client.get_thread_page_count()`, fetch all pages via `client.get_thread_page()`, for each post call `content_processor.extract_text_from_vbulletin_html()` and insert into `posts` table with clean text + raw HTML, update `topics.scrape_status` to 'scraped' on success or 'failed' on error. Per-page checkpointing via `scrape_progress` (scope_type='topic', scope_id=str(platform_topic_id)) so interrupted topics resume from last completed page.
- [x] 6.4 Handle topic deduplication: rely on `UNIQUE(source_id, platform_topic_id)` constraint; skip insert on conflict for shared boards (e.g., cataract and conjunctivitis both from board 54)

## 7. Pipeline Orchestration

- [x] 7.1 Create `scrapers/healthboards/pipeline.py` with `Pipeline` class accepting CLI options: `labels`, `max_topics_per_label`, `dry_run`, `qdrant_url`, `jsonl_path`, `embedding_model`, `headless`, `browser_timeout`. Always executes all stages sequentially (identical to patient.info); each stage queries the DB to find only pending work, so resume is automatic with no manual stage override needed.
- [x] 7.2 Implement Stage 0 — Load queries: import and call `query_loader.load_queries(db, source_id, jsonl_path)` from `scrapers.patient_info.query_loader`; fail-stop on `FileNotFoundError` or `ValueError`
- [x] 7.3 Implement Stage 1 — Load board mappings: initialize `BoardMapper`, load `mappings.json`
- [x] 7.4 Implement Stage 2 — Discover topics: derive label list from `db.get_all_query_labels(source_id)`, intersect with `--labels` CLI filter, call `discovery.discover_topics_for_label()` for each label
- [x] 7.5 Implement Stage 3 — Scrape thread content: get pending topics via `db.get_pending_topics(source_id)`, call `discovery.scrape_topic()` for each; skip if `--dry-run`
- [x] 7.6 Implement Stage 4 — Embed posts + upsert to Qdrant: import `Embedder` from `scrapers.patient_info.embedder` and `VectorStore` from `scrapers.patient_info.vector_store`; get posts pending upsert, embed in batches (default 64), compute thread context, upsert with `source="https://www.healthboards.com"` and deterministic point IDs via `uuid5(namespace, "https://www.healthboards.com:{platform_post_id}")`; write `qdrant_point_id` and `embedding_hash` back to posts table; skip if `--dry-run`
- [x] 7.7 Implement Stage 5 — Semantic query-post matching: import and call `query_matcher.match_queries_to_posts(db, vector_store, embedder, source_id)` from `scrapers.patient_info.query_matcher`; use `get_queries_pending_matching()` to skip already-matched queries on resume; skip if `--dry-run`
- [x] 7.8 Implement graceful shutdown: register SIGINT/SIGTERM handlers, finish current operation, commit database, close Playwright browser, exit cleanly
- [x] 7.9 Implement structured logging: import logger setup from `scrapers.patient_info.logger`, configure log file at `scrapers/logs/www.healthboards.com/scraper.log` with 10MB rotation and 5 backups

## 8. CLI Entry Point

- [x] 8.1 Create `scrapers/healthboards/run_scraper.py` with argparse CLI: `--labels` (nargs='+'), `--max-topics-per-label` (int), `--dry-run` (flag), `--resume` (flag, default True), `--qdrant-url` (str), `--jsonl-path` (str), `--embedding-model` (str), `--headless` (bool, default True), `--browser-timeout` (int, default 60)
- [x] 8.2 Wire CLI args to `Pipeline` class initialization and `pipeline.run()` async execution via `asyncio.run()`

## 9. Verification

- [x] 9.1 Create `scrapers/healthboards/verify.py`: DB integrity checks filtered to healthboards source_id (topic counts by status, post counts, orphaned FK detection), Qdrant point count with `source="https://www.healthboards.com"` filter, coverage report per disease label (topics discovered, scraped, posts, Qdrant points), query mapping stats (queries with/without matches, avg/min/max scores)

## 10. Testing & Validation

> **RESOLVED:** Cloudflare JS challenge handling significantly improved with multi-layered
> approach: (1) cookie warmup on startup to acquire `cf_clearance`, (2) challenge detection
> on ALL status codes + page body inspection (not just HTTP 403), (3) response HTML validation
> to catch soft challenges served with HTTP 200, (4) client-level circuit breaker that pauses
> and restarts browser context after 3 consecutive failures, (5) pipeline-level circuit breaker
> that aborts after 3/5 consecutive CF blocks per stage, (6) jittered rate limiting (3-4.5s),
> (7) default headed mode (`HEADLESS=False`) which is far more reliable against CF Bot Management.
> Original approach only checked HTTP 403 status and used a 30s wait with 3 retries — this failed
> 100% of the time against modern Cloudflare. The `patchright` undetected fork is still used
> for baseline stealth.

- [x] 10.1 Verify patchright can load healthboards.com in headless mode without 403 (Cloudflare challenge resolved via patchright)
- [ ] 10.2 Validate HTML parsing: fetch one board page + one thread page, verify extracted thread list and post list match expected structure
- [ ] 10.3 Dry-run test: `python -m scrapers.healthboards.run_scraper --labels acne --max-topics-per-label 2 --dry-run` — verify topic discovery writes to DB without scraping
- [ ] 10.4 End-to-end smoke test: `python -m scrapers.healthboards.run_scraper --labels acne --max-topics-per-label 3` — verify full pipeline with 3 topics (scrape, embed, match)
- [ ] 10.5 Cross-source verification: confirm healthboards query_post_mappings only reference healthboards posts (not patient_info posts), confirm Qdrant points have correct `source` field

## 11. Resilience Improvements

- [x] 11.1 Switch from `playwright` to `patchright` for Cloudflare bypass in `healthboards_client.py`
- [x] 11.2 ~~Add `--start-stage` CLI flag (0-5) for resuming pipeline from any stage~~ **REMOVED**: Resume is automatic — each stage queries the DB for pending work (identical to patient.info). Manual stage override was redundant and fragile.
- [x] 11.3 Add `exc_info=True` to all error logging for full tracebacks
- [x] 11.4 Implement per-page topic scrape checkpointing using `scrape_progress` table (scope_type='topic')
- [x] 11.5 Use `get_queries_pending_matching()` in query_matcher to skip already-matched queries on resume
- [x] 11.6 Update DB_PATH to shared `scraper.db` (was using separate `healthboards_scraper.db`)
- [x] 11.7 Refactor pipeline into stage methods with timing, matching patient.info stage architecture

## 12. Cloudflare Resilience Improvements

- [x] 12.1 Add cookie warmup: on browser launch, navigate to the site landing page to acquire `cf_clearance` cookie before any scraping requests
- [x] 12.2 Detect Cloudflare challenges on ANY HTTP status (not just 403) — also inspect page title and body content for challenge markers (e.g. `cf-browser-verification`, `challenge-platform`, `turnstile`)
- [x] 12.3 Add response HTML validation: after receiving a response, check that the HTML is not a Cloudflare challenge page that slipped through with HTTP 200 (heuristic check for short responses and challenge keywords)
- [x] 12.4 Implement client-level circuit breaker: after N consecutive CF failures (default 3), pause for a cooldown period (default 120s), then restart the browser context with a fresh cookie jar and re-run warmup
- [x] 12.5 Implement pipeline-level circuit breaker for Stage 2 (discovery): abort after 3 consecutive label-level CF blocks instead of wasting ~3 minutes per label on futile retries
- [x] 12.6 Implement pipeline-level circuit breaker for Stage 3 (scraping): abort after 5 consecutive topic-level CF blocks
- [x] 12.7 Add jittered rate limiting: add 0-50% random extra delay between navigations to reduce detection of fixed-interval request patterns
- [x] 12.8 Update default config: `HEADLESS=False` (headed mode far more reliable against CF), `RATE_LIMIT_DELAY=3.0`, `RETRY_MAX_ATTEMPTS=5`, `BROWSER_TIMEOUT=90_000`, `CF_CHALLENGE_WAIT=45`, updated Chrome User-Agent to v131, viewport to 1366x768
- [x] 12.9 Add `CloudflareBlockError` exception class to distinguish CF blocks from other errors in pipeline-level error handling
- [x] 12.10 ~~Set browser context locale (`en-US`) and timezone (`America/New_York`) for more realistic fingerprint~~ **REVERTED in 13.6** — per Patchright best practice, injecting locale/timezone creates a detectable mismatch
- [x] 12.11 Update CLI `--headless` default to `false` and `--browser-timeout` default to 90s

## 13. Patchright Best-Practice Alignment (Undetectable Configuration)

Per the official Patchright documentation (https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python#best-practice), the browser client was fully rewritten to follow every recommendation:

- [x] 13.1 Switch from `pw.chromium.launch()` + `browser.new_context()` to `pw.chromium.launch_persistent_context()` — persistent context is the only recommended launch mode
- [x] 13.2 Add `channel="chrome"` to use real Google Chrome instead of Chromium — "We recommend using Google Chrome instead of Chromium"
- [x] 13.3 Add `no_viewport=True` — let Chrome use OS-native window sizing instead of injected viewport dimensions
- [x] 13.4 Remove custom `user_agent` injection from config and context creation — "do NOT add custom browser headers or user_agent"
- [x] 13.5 Remove custom `viewport` injection from config and context creation — injecting viewport creates a detectable fingerprint mismatch
- [x] 13.6 Remove forced `locale="en-US"` and `timezone_id="America/New_York"` — these can mismatch the client's actual geolocation and trigger detection
- [x] 13.7 Remove `--disable-blink-features=AutomationControlled` from launch args — patchright already patches this internally; adding it redundantly signals bot activity
- [x] 13.8 Add persistent `USER_DATA_DIR` config (`scrapers/data/www.healthboards.com/chrome_profile/`) to preserve cookies (including `cf_clearance`) across runs
- [x] 13.9 Update circuit breaker to close + relaunch the persistent context (new browser process, same profile dir) instead of creating a new ephemeral context
- [x] 13.10 Remove `USER_AGENT` and `VIEWPORT` constants from `config.py` (no longer used)
- [x] 13.11 Add `BROWSER_CHANNEL` constant to `config.py` for Chrome channel selection
- [x] 13.12 Update openspec browser-client spec to reflect persistent context architecture and best-practice requirements
