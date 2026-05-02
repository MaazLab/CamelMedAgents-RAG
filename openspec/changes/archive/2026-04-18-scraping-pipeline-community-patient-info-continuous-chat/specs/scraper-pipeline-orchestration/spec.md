## ADDED Requirements

### Requirement: Multi-stage pipeline orchestration
The pipeline SHALL execute stages in order: (0) load structured queries from JSONL + build parameter-enriched representations, (1) load category/tag mapping, (2) discover topics by tag/category, (3) scrape topic content (with HTML-to-text processing), (4) embed posts using sentence-transformer + upsert to Qdrant with real vectors, (5) embed query representations + semantic similarity search in Qdrant → store mappings with similarity scores. Each stage SHALL check database state before executing to support resume.

#### Scenario: Full pipeline execution
- **WHEN** the pipeline runs for disease label "acne"
- **THEN** it SHALL load queries and build representations, discover topics via tag "acne", scrape each topic, embed post texts and upsert to Qdrant with real vectors, then embed query representations and search Qdrant for semantically similar posts, storing mappings with similarity scores

#### Scenario: Resume skips completed stages
- **WHEN** the pipeline restarts and queries are already loaded, topics for "acne" are already discovered and some are scraped
- **THEN** query loading SHALL skip duplicates, discovery SHALL resume from the last incomplete page, already-scraped topics SHALL be skipped, already-embedded posts (with matching `embedding_hash`) SHALL be skipped in Stage 4, and existing query-post mappings SHALL be preserved (UNIQUE constraint prevents duplicates)

### Requirement: Topic discovery SHALL only discover labels present in loaded queries
Stage 1 (Topic Discovery) SHALL derive its label list from the `queries` table instead of from `mappings.json`. Only disease labels that have at least one loaded query SHALL be discovered.

#### Scenario: Queries exist for a subset of labels
- **WHEN** the JSONL file contains queries for labels `acne`, `diabetes`, and `headache` only
- **THEN** Stage 1 SHALL discover topics only for those 3 labels, not all 20 from mappings

#### Scenario: CLI --labels flag narrows further
- **WHEN** queries exist for labels `acne`, `diabetes`, `headache` and `--labels acne diabetes` is passed
- **THEN** Stage 1 SHALL discover topics only for `acne` and `diabetes` (intersection of queries and CLI filter)

### Requirement: Query loading from JSONL with representation building
The pipeline SHALL load all structured queries from the specified JSONL file into the `queries` table as Stage 0. Each query's available parameters SHALL be converted into a parameter-enriched natural language `representation_text` for semantic embedding. Both enriched (with patient_context, clinical_interpretation) and non-enriched (symptoms, duration, triggers only) JSONL formats SHALL be supported.

#### Scenario: Load queries on first run
- **WHEN** the pipeline runs for the first time with the non-enriched JSONL
- **THEN** all 9,061 queries SHALL be inserted into the `queries` table with their extracted parameters and generated representation texts

#### Scenario: Load enriched queries
- **WHEN** the pipeline runs with the enriched JSONL (204 records)
- **THEN** all 204 queries SHALL be inserted with full parameters including patient_context and clinical_interpretation, producing richer representation texts

#### Scenario: Skip already-loaded queries on restart
- **WHEN** the pipeline restarts and queries are already loaded
- **THEN** duplicate queries SHALL be skipped via the unique constraint

### Requirement: Post embedding and Qdrant upsert stage
After scraping, the pipeline SHALL embed all post texts using the configured sentence-transformer model and upsert them to Qdrant with real embedding vectors (Stage 4). Posts SHALL be embedded in batches for efficiency.

#### Scenario: Embed and upsert new posts
- **WHEN** 500 new posts have been scraped and are pending embedding
- **THEN** the pipeline SHALL embed their texts in batches (default 64), upsert to Qdrant with the real vectors and full metadata payload, and write `qdrant_point_id` and `embedding_hash` back to the posts table

#### Scenario: Skip already-embedded posts
- **WHEN** a post has `qdrant_point_id` set and `embedding_hash` matches its current text
- **THEN** the post SHALL be skipped in Stage 4

### Requirement: Semantic query-post matching stage
After posts are embedded and upserted to Qdrant, the pipeline SHALL embed each query's `representation_text` and search Qdrant for semantically similar posts filtered by disease label (Stage 5). Matches above the similarity threshold SHALL be stored in `query_post_mappings` with similarity scores.

#### Scenario: Match queries to posts by semantic similarity
- **WHEN** query Q1 (label="acne") has representation text about "mild bumps on face for 2 months" and Qdrant contains embedded posts about acne
- **THEN** the pipeline SHALL embed Q1's representation, search Qdrant filtered by `disease_label = "acne"`, and store mappings for the top-K posts with `similarity_score >= SIMILARITY_THRESHOLD`

#### Scenario: Post matches no queries above threshold
- **WHEN** a post with label "acne" has low similarity to all acne queries (all scores below threshold)
- **THEN** no mapping rows SHALL be created for that post (it remains in the DB and Qdrant, just unmapped)

#### Scenario: Log uncurated queries
- **WHEN** a query has zero post matches above threshold after the matching stage
- **THEN** the pipeline SHALL log it as an "uncurated query" in the summary

### Requirement: CLI entry point
The pipeline SHALL provide a CLI via `run_scraper.py` with the following options: `--labels` (filter to specific disease labels), `--max-topics-per-label` (cap topics per label for testing), `--dry-run` (discover topics without scraping), `--resume` (continue from checkpoint, default behavior), `--qdrant-url` (Qdrant server URL; default: local file storage), `--jsonl-path` (path to JSONL file; default: from config), `--embedding-model` (sentence-transformer model name; default: `all-MiniLM-L6-v2`).

#### Scenario: Filter by labels
- **WHEN** `--labels acne diabetes` is passed
- **THEN** the pipeline SHALL only scrape topics for acne and diabetes

#### Scenario: Dry run mode
- **WHEN** `--dry-run` is passed
- **THEN** the pipeline SHALL load queries and discover topics in the database but SHALL NOT scrape content, compute mappings, or upsert to Qdrant

#### Scenario: Cap topics per label
- **WHEN** `--max-topics-per-label 5` is passed
- **THEN** the pipeline SHALL stop discovering topics for a label after 5 topics are recorded

### Requirement: Structured logging
The pipeline SHALL use Python's `logging` module with centralized configuration. Two handlers SHALL be active: a console handler at INFO level with human-readable format, and a rotating file handler at DEBUG level (10MB max, 5 backups) writing to `scrapers/patient_info/logs/scraper.log`.

#### Scenario: Console output at INFO level
- **WHEN** the pipeline runs
- **THEN** INFO-level messages (stage start/end, topic counts, progress summaries) SHALL appear on the console

#### Scenario: Debug logs in rotating file
- **WHEN** the pipeline runs
- **THEN** DEBUG-level messages (rate limit waits, retry attempts, individual API calls) SHALL be written to the rotating log file

#### Scenario: Named loggers per module
- **WHEN** the Discourse client logs a rate limit wait
- **THEN** the log entry SHALL include the module name (e.g., `patient_info.client`)

#### Scenario: Log format
- **WHEN** any log entry is written
- **THEN** it SHALL follow the format `[TIMESTAMP] [LEVEL] [module] message`

### Requirement: Error handling and graceful shutdown
The pipeline SHALL handle errors gracefully: individual topic failures SHALL be logged and the topic marked as `failed` in the database, but the pipeline SHALL continue with the next topic. On keyboard interrupt (Ctrl+C), the pipeline SHALL save current progress to the database before exiting.

#### Scenario: Individual topic failure
- **WHEN** scraping topic 12345 fails after all retries
- **THEN** the topic SHALL be marked as `failed` in the database and the pipeline SHALL continue with the next topic

#### Scenario: Graceful shutdown on Ctrl+C
- **WHEN** the user presses Ctrl+C during scraping
- **THEN** the pipeline SHALL save the current scrape progress and exit cleanly

### Requirement: Verification tool
A verification script (`verify.py`) SHALL query both the SQLite database and Qdrant, check for duplicate topics/posts, and produce a coverage report.

#### Scenario: Coverage report
- **WHEN** `verify.py` is run
- **THEN** it SHALL report topics and posts per disease label in SQLite AND point counts per `source` in Qdrant

#### Scenario: Integrity check
- **WHEN** `verify.py` is run
- **THEN** it SHALL check for duplicate topic and post platform IDs and verify Qdrant point count matches upserted posts in SQLite
