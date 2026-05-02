## ADDED Requirements

### Requirement: Multi-stage pipeline orchestration
The pipeline SHALL execute stages in order: (0) load structured queries from JSONL + build parameter-enriched representations, (1) load board mappings from `mappings.json`, (2) discover topics by board pagination, (3) scrape thread content (with vBulletin HTML-to-text processing), (4) embed posts using sentence-transformer + upsert to Qdrant with real vectors, (5) embed query representations + semantic similarity search in Qdrant → store mappings with similarity scores. Each stage SHALL check database state before executing to support resume.

#### Scenario: Full pipeline execution
- **WHEN** the pipeline runs for disease label "acne"
- **THEN** it SHALL load queries and build representations, discover threads from board 5, scrape each thread across all its pages, embed post texts and upsert to Qdrant with real vectors and `source="https://www.healthboards.com"`, then embed query representations and search Qdrant for semantically similar posts, storing mappings with similarity scores

#### Scenario: Resume skips completed stages
- **WHEN** the pipeline restarts and queries are already loaded, topics for "acne" are already discovered and some are scraped
- **THEN** query loading SHALL skip duplicates, discovery SHALL resume from the last incomplete page, already-scraped topics SHALL be skipped, already-embedded posts (with matching `embedding_hash`) SHALL be skipped in Stage 4, and existing query-post mappings SHALL be preserved

### Requirement: Topic discovery SHALL only discover labels present in loaded queries
Stage 2 (Topic Discovery) SHALL derive its label list from the `queries` table. Only disease labels that have at least one loaded query SHALL be discovered.

#### Scenario: Queries exist for a subset of labels
- **WHEN** the JSONL file contains queries for labels `acne`, `diabetes`, and `headache` only
- **THEN** Stage 2 SHALL discover topics only for those 3 labels, not all 20 from mappings

#### Scenario: CLI --labels flag narrows further
- **WHEN** queries exist for labels `acne`, `diabetes`, `headache` and `--labels acne diabetes` is passed
- **THEN** Stage 2 SHALL discover topics only for `acne` and `diabetes` (intersection of queries and CLI filter)

### Requirement: Shared SQLite database
The pipeline SHALL store all data in the shared `scrapers/data/scraper.db` database (same as patient_info), segregated by `source_id`. The pipeline SHALL NOT use a separate database file.

#### Scenario: Shared database with new source row
- **WHEN** the pipeline initializes
- **THEN** it SHALL call `db.get_or_create_source(name='healthboards', base_url='https://www.healthboards.com')` to register the source and obtain a `source_id`

#### Scenario: Same Qdrant collection
- **WHEN** posts are upserted to Qdrant
- **THEN** they SHALL be stored in the same `queries_relevant_scrape_data` collection with `source="https://www.healthboards.com"` in the payload

#### Scenario: Deterministic Qdrant point IDs
- **WHEN** a healthboards post is upserted
- **THEN** the point ID SHALL be generated as `uuid5(namespace, "https://www.healthboards.com:{platform_post_id}")`

### Requirement: Query loading from JSONL with representation building
The pipeline SHALL load all structured queries from the specified JSONL file into the `queries` table as Stage 0, reusing the existing `query_loader.load_queries()` function. The pipeline SHALL fail-stop if the JSONL file is missing or yields zero queries.

#### Scenario: Load queries on first run
- **WHEN** the pipeline runs for the first time with the JSONL file
- **THEN** all queries SHALL be inserted into the `queries` table with their extracted parameters and generated representation texts, associated with the healthboards `source_id`

#### Scenario: Fail-stop on missing JSONL
- **WHEN** the JSONL file path does not exist
- **THEN** the pipeline SHALL raise `FileNotFoundError` and abort before Stage 1

#### Scenario: Fail-stop on zero queries
- **WHEN** the JSONL file yields zero valid queries
- **THEN** the pipeline SHALL raise `ValueError` and abort before Stage 1

### Requirement: Post embedding and Qdrant upsert stage
After scraping, the pipeline SHALL embed all post texts using the configured sentence-transformer model and upsert them to Qdrant with real embedding vectors (Stage 4). Posts SHALL be embedded in batches for efficiency.

#### Scenario: Embed and upsert new posts
- **WHEN** 500 new posts have been scraped and are pending embedding
- **THEN** the pipeline SHALL embed their texts in batches (default 64), upsert to Qdrant with the real vectors and full metadata payload, and write `qdrant_point_id` and `embedding_hash` back to the posts table

#### Scenario: Skip already-embedded posts
- **WHEN** a post has `qdrant_point_id` set and `embedding_hash` matches its current text
- **THEN** the post SHALL be skipped in Stage 4

### Requirement: Semantic query-post matching stage with resumability
After posts are embedded and upserted to Qdrant, the pipeline SHALL embed each query's `representation_text` and search Qdrant for semantically similar posts filtered by disease label (Stage 5). Matches above the similarity threshold SHALL be stored in `query_post_mappings` with similarity scores. Queries that already have mappings SHALL be skipped on resume to avoid redundant re-matching.

#### Scenario: Match queries to healthboards posts
- **WHEN** query Q1 (label="acne") has representation text about "mild bumps on face for 2 months" and Qdrant contains embedded healthboards posts about acne
- **THEN** the pipeline SHALL embed Q1's representation, search Qdrant filtered by `disease_label = "acne"`, and store mappings for the top-K posts with `similarity_score >= SIMILARITY_THRESHOLD`

#### Scenario: Skip already-matched queries on resume
- **WHEN** the pipeline restarts and query Q1 already has entries in `query_post_mappings`
- **THEN** Q1 SHALL be skipped (identified via `get_queries_pending_matching()`) and only unmatched queries SHALL be processed

#### Scenario: Only match posts from healthboards source
- **WHEN** semantic matching is performed
- **THEN** the search SHALL be scoped to posts with `source="https://www.healthboards.com"` so patient_info posts are not included in healthboards mappings

### Requirement: CLI entry point
The pipeline SHALL provide a CLI via `run_scraper.py` with the following options: `--labels` (filter to specific disease labels), `--max-topics-per-label` (cap topics per label for testing), `--dry-run` (discover topics without scraping), `--resume` (continue from checkpoint, default behavior), `--qdrant-url` (Qdrant server URL), `--jsonl-path` (path to JSONL file), `--embedding-model` (sentence-transformer model name), `--headless` (run browser in headless mode, default True), `--browser-timeout` (page load timeout in seconds). The pipeline SHALL NOT expose a `--start-stage` option — resume point is determined automatically from DB state.

#### Scenario: Filter by labels
- **WHEN** `--labels acne diabetes` is passed
- **THEN** the pipeline SHALL only discover and scrape topics for acne and diabetes

#### Scenario: Dry run mode
- **WHEN** `--dry-run` is passed
- **THEN** the pipeline SHALL load queries and discover topics in the database but SHALL NOT scrape content, compute embeddings, or upsert to Qdrant

#### Scenario: Automatic resume from DB state
- **WHEN** the pipeline restarts after a partial run
- **THEN** each stage SHALL query the DB to determine pending work: Stage 0 skips duplicate queries via `UNIQUE(source_id, text_hash)`, Stage 2 resumes discovery from `scrape_progress.last_page`, Stage 3 skips topics with `scrape_status='scraped'`, Stage 4 skips posts with `qdrant_point_id IS NOT NULL` and matching `embedding_hash`, Stage 5 skips queries already in `query_post_mappings` — no manual stage flag required

#### Scenario: Cap topics per label
- **WHEN** `--max-topics-per-label 5` is passed
- **THEN** the pipeline SHALL stop discovering topics for a label after 5 topics are recorded

#### Scenario: Headed browser mode
- **WHEN** `--headless false` is passed (or the default is used)
- **THEN** the Playwright browser SHALL launch in visible (headed) mode, which is more reliable against Cloudflare

#### Scenario: Headless browser mode
- **WHEN** `--headless true` is explicitly passed
- **THEN** the Playwright browser SHALL launch in headless mode (less reliable against Cloudflare)

### Requirement: Pipeline-level circuit breaker for Cloudflare
The pipeline SHALL detect persistent Cloudflare blocking at the stage level and abort early rather than wasting time on futile retries.

#### Scenario: Discovery stage circuit breaker
- **WHEN** 3 consecutive disease labels fail with `CloudflareBlockError` during Stage 2
- **THEN** the pipeline SHALL abort Stage 2 and log an actionable error message suggesting headed mode, different network, or waiting

#### Scenario: Scraping stage circuit breaker
- **WHEN** 5 consecutive topics fail with `CloudflareBlockError` during Stage 3
- **THEN** the pipeline SHALL abort Stage 3 and log an actionable error message

#### Scenario: Circuit breaker resets on success
- **WHEN** a label or topic succeeds after CF failures
- **THEN** the consecutive failure counter SHALL reset to 0

### Requirement: Graceful shutdown
The pipeline SHALL handle SIGINT and SIGTERM signals by finishing the current operation, saving progress to the database, and exiting cleanly.

#### Scenario: Ctrl+C during scraping
- **WHEN** the user presses Ctrl+C while scraping thread posts
- **THEN** the pipeline SHALL finish the current post insert, commit the database, and exit with a message indicating interrupted state

### Requirement: Structured logging with full tracebacks
The pipeline SHALL log to both console (INFO level) and a rotating log file (DEBUG level) at `scrapers/logs/www.healthboards.com/scraper.log`. All error logging SHALL include `exc_info=True` to capture full stack traces in the log file.

#### Scenario: Log file location
- **WHEN** the pipeline starts
- **THEN** logs SHALL be written to `scrapers/logs/www.healthboards.com/scraper.log` with 10MB rotation and 5 backups

#### Scenario: Stage progress logging
- **WHEN** each stage starts and completes
- **THEN** the pipeline SHALL log the stage name, items processed, and elapsed time

#### Scenario: Error tracebacks in logs
- **WHEN** any error occurs during discovery, scraping, or matching
- **THEN** the full Python traceback SHALL be logged via `exc_info=True` (visible in log file at DEBUG level)
