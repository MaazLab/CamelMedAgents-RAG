## 1. Project Setup

- [x] 1.1 Create directory structure: `scrapers/patient_info/`, `scrapers/data/community.patient.info/cache/`, `scrapers/logs/community.patient.info/`, `scrapers/__init__.py`, `scrapers/patient_info/__init__.py` — data and logs are at the shared `scrapers/` level, namespaced by source slug
- [x] 1.2 Create `scrapers/patient_info/config.py` with settings: `DISCOURSE_BASE_URL` defined first; source slug derived as `DISCOURSE_BASE_URL.split("://", 1)[-1]`; `DATA_DIR`, `LOGS_DIR`, `CACHE_DIR`, `DB_PATH`, `LOG_FILE` all rooted at `SCRAPERS_DIR / {data|logs} / _SOURCE_SLUG`; Qdrant config (URL, Docker volume path, collection name); embedding config; JSONL input path
- [x] 1.3 Create `scrapers/patient_info/logger.py` with centralized logging: console handler (INFO), rotating file handler (DEBUG, 10MB × 5 backups), named loggers per module, format `[TIMESTAMP] [LEVEL] [module] message`

## 2. Pydantic Models

- [x] 2.1 Create `scrapers/patient_info/models.py` with Pydantic models: `ForumCategory`, `ForumTag`, `TopicSummary`, `Topic`, `Post` matching Discourse JSON API response shapes

## 3. Database Layer

- [x] 3.1 Create `scrapers/patient_info/database.py` with SQLite schema: `sources`, `queries`, `topics`, `posts`, `query_post_mappings`, `scrape_progress` tables with all columns, constraints, and foreign keys as specified
- [x] 3.2 Implement DB helper methods: `get_or_create_source()`, `insert_topic()`, `insert_post()`, `update_topic_status()`, `update_scrape_progress()`, `get_pending_topics()`
- [x] 3.3 Add `qdrant_point_id`, `embedding_hash`, and `upserted_at` columns to `posts` table; add `update_post_qdrant_id()` and `get_posts_pending_upsert()` helper methods; `embedding_hash` tracks content hash to detect when re-embedding is needed
- [x] 3.4 Add `queries` table: `id`, `source_id`, `original_text`, `label` (disease), `category`, `symptoms_json` (full symptom list as JSON), `duration_json`, `frequency`, `triggers_json`, `patient_context_json`, `clinical_interpretation_json`, `representation_text` (parameter-enriched natural language text for embedding), `loaded_at`
- [x] 3.5 Add `query_post_mappings` table: `id`, `query_id` (FK → queries), `post_id` (FK → posts), `similarity_score` (REAL, cosine similarity from Qdrant search), `created_at`; UNIQUE on `(query_id, post_id)`
- [x] 3.6 Implement query helper methods: `insert_query()`, `get_queries_by_label()`, `insert_query_post_mapping()`, `get_mappings_for_query()`, `get_mapping_stats()`, `get_queries_pending_matching()`

## 4. Category & Tag Mapping

- [x] 4.1 Create `scrapers/patient_info/mappings.json` with the static mapping of all 20 disease labels to tag IDs, tag slugs, and category IDs
- [x] 4.2 Create `scrapers/patient_info/category_tag_mapper.py` with methods: `load_mappings()`, `get_tag_slugs(label)`, `get_category_id(label)`, and API fetch + cache logic for `/categories.json` and `/tags.json`

## 5. Discourse API Client

- [x] 5.1 Create `scrapers/patient_info/discourse_client.py` with `httpx.AsyncClient`, rate limiter (300ms delay), exponential backoff retry (3 retries, factor 2, on 429/5xx), User-Agent header
- [x] 5.2 Implement API methods: `get_categories()`, `get_tags()`, `get_category_topics(id, page)`, `get_tag_topics(tag_slug, page)`, `get_topic(topic_id)`, `get_topic_posts(topic_id, post_ids)`
- [x] 5.3 Add robots.txt compliance: block requests to `/search` endpoint

## 6. Topic Discovery

- [x] 6.1 Create `scrapers/patient_info/topic_discovery.py` with tag-based pagination: for each disease label, paginate through mapped tag(s) to discover all topics
- [x] 6.2 Implement category-based fallback discovery for labels without exact tag matches
- [x] 6.3 Implement cross-tag/category deduplication using `UNIQUE(source_id, platform_topic_id)` constraint
- [x] 6.4 Implement page-level resume using `scrape_progress` table (read `last_page`, resume from next page, mark completed when done)

## 7. Content Scraping

- [x] 7.1 Implement full topic content scraping: fetch topic JSON, handle post pagination for topics >20 posts, write all posts to `posts` table with platform IDs and reply references
- [x] 7.2 Update `topics.scrape_status` to `'scraped'` on success, `'failed'` on error after retries

## 8. Content Processing

- [x] 8.1 Create `scrapers/patient_info/content_processor.py` with HTML-to-text extraction: strip HTML tags, remove quoted reply blocks (`<aside class="quote">`), remove images/emoji/formatting artifacts using BeautifulSoup

## 9. Query Loading & Representation

- [x] 9.1 Create `scrapers/patient_info/query_loader.py`: read the JSONL file (enriched or non-enriched), parse each line into a structured query record with all available parameters
- [x] 9.2 Implement `load_queries(db, source_id, jsonl_path)`: for each query, extract `original_text`, `label`, `category`, `symptoms` (full list as JSON), `duration`, `frequency`, `triggers`, `patient_context` (if available), `clinical_interpretation` (if available); insert into `queries` table; skip duplicates (by `original_text` hash)
- [x] 9.3 Implement `build_query_representation(query_row)`: build a parameter-enriched natural language text from ALL available parameters — include symptoms with anatomical location and severity, duration with normalized days and onset type, frequency, triggers, **symptom_temporal_map** (per-symptom duration and onset), patient context (age, age_group, gender, pregnancy_status, comorbidities), clinical interpretation (intent, red_flag, red_flag_reasons), and original query text; store in `representation_text` column
- [x] 9.4 Handle both JSONL formats: enriched (204 records, all parameters including patient_context/clinical_interpretation) and non-enriched (9,061 records, symptoms/duration/triggers only) — adapt representation to available fields, omit sections for null parameters
- [x] 9.5 Log summary: total queries loaded, count per disease label, representation text sample for verification

## 10. Embedder Module

- [x] 10.1 Create `scrapers/patient_info/embedder.py`: wrapper around `sentence-transformers` library for encoding text to embedding vectors
- [x] 10.2 Implement `Embedder` class: load configurable model (default: `all-MiniLM-L6-v2` 384-dim; alternative: `pritamdeka/S-PubMedBert-MS-MARCO` 768-dim); expose `encode(texts: list[str]) -> np.ndarray` for batch encoding; log model name, dimension, and device on init
- [x] 10.3 Add embedding model config to `scrapers/patient_info/config.py`: `EMBEDDING_MODEL` (model name string), `EMBEDDING_DIM` (int, must match model), `EMBEDDING_BATCH_SIZE` (default 64)

## 11. Semantic Query-Post Matching

- [x] 11.1 Create `scrapers/patient_info/query_matcher.py`: semantic matching engine using Qdrant vector similarity search
- [x] 11.2 Implement `match_queries_to_posts(db, vector_store, embedder, source_id)`: for each query, embed `representation_text` using the embedder; search Qdrant for top-K similar posts filtered by the query's disease label; store mappings in `query_post_mappings` with `similarity_score`
- [x] 11.3 Add matching config to `config.py`: `SIMILARITY_THRESHOLD` (default 0.5, minimum cosine similarity to store a mapping), `TOP_K_MATCHES` (default 50, maximum posts per query)
- [x] 11.4 Handle edge cases: posts with no query matches (still stored, just unmapped); queries with no post matches above threshold (logged as "uncurated queries"); store all scores so threshold is adjustable post-hoc without re-embedding

## 12. Vector Storage (Qdrant — real embeddings)

- [x] 12.1 Create `scrapers/patient_info/vector_store.py`: connect to Qdrant Docker server (default `http://localhost:6333`, configurable via `QDRANT_URL` env var), create collection with `VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)` and payload indexes on `source`, `disease_label`, `medical_category`, `is_original_post`, `platform_topic_id`, `platform_post_id`; no local file storage fallback
- [x] 12.2 Implement `upsert_post(post_row, topic_row, embedding_vector, matched_queries, thread_post_count, thread_point_ids)`: build payload with all post + topic metadata including `source` (base URL), `matched_queries` (list of full query parameter dicts), `thread_post_count`, and `thread_point_ids`; use real embedding vector from embedder; deterministic point ID via `uuid5(namespace, "{DISCOURSE_BASE_URL}:{platform_post_id}")`
- [x] 12.3 Implement batch embed + upsert: embed post texts in batches using `embedder.encode()`, upsert to Qdrant, write `qdrant_point_id` and `embedding_hash` back to `posts` table; skip posts already upserted with matching `embedding_hash`
- [x] 12.4 Implement `search_similar(query_vector, disease_label, top_k, score_threshold)`: search Qdrant collection filtered by `disease_label` payload field, return top-K results above score threshold with similarity scores

## 13. Pipeline Orchestration & CLI

- [x] 13.1 Update `scrapers/patient_info/pipeline.py`: Stage 0 — load queries from JSONL + build representations; Stage 1 — discover topics; Stage 2 — scrape posts; Stage 3 — embed posts + upsert to Qdrant (real vectors); Stage 4 — embed query representations + semantic search → store mappings; skip already-completed stages via DB checkpoints; graceful shutdown saves progress before exit
- [x] 13.2 Implement error handling: per-topic failure isolation (log + mark failed + continue), graceful shutdown on Ctrl+C (save progress before exit)
- [x] 13.3 Update `scrapers/patient_info/run_scraper.py` CLI: add `--qdrant-url` argument (default: `http://localhost:6333` from config, override via `QDRANT_URL` env var or CLI flag), add `--jsonl-path` argument (default: JSONL path from config), add `--embedding-model` argument (default: `all-MiniLM-L6-v2`); Qdrant Docker server must be running before pipeline starts

## 14. Verification

- [x] 14.1 Update `scrapers/patient_info/verify.py`: add Qdrant point count per datasource (`source` payload filter) alongside existing SQLite coverage and duplicate detection; add query mapping stats (queries with matches, queries without matches, avg posts per query, avg queries per post, avg/min/max similarity scores); add embedding dimension check (verify Qdrant collection dimension matches configured model)

## 15. Thread Context in Qdrant Payload

- [x] 15.1 Add `get_thread_context(source_id)` method to `database.py`: returns mapping of `platform_topic_id → list[platform_post_id]` for all posts in the source, enabling per-post thread context computation
- [x] 15.2 Add `thread_post_count` (int) and `thread_point_ids` (list[str]) to `_build_payload()` in `vector_store.py`; update payload docstring
- [x] 15.3 Update `upsert_post()` and `upsert_batch()` in `vector_store.py`: accept `thread_post_count`, `thread_point_ids` (single post) or `thread_contexts` (batch) parameters; fix point ID generation to use `DISCOURSE_BASE_URL` consistently
- [x] 15.4 Update `pipeline.py` `_stage_embed_and_upsert()`: pre-compute thread context map from SQLite before chunk loop; build per-post `thread_contexts` list; pass to `upsert_batch()` for each chunk

## 16. Full Query Parameters in Qdrant Payload (`matched_queries`)

- [x] 16.1 Add `symptom_temporal_map_json TEXT` column to `queries` table in `database.py` schema; add schema migration in `connect()` for existing databases; update `insert_query()` to accept and persist `symptom_temporal_map_json`
- [x] 16.2 Update `query_loader.py`: pass `symptom_temporal_map_json` (from JSONL `symptom_temporal_map` field) to `insert_query()` during query loading
- [x] 16.3 Replace `matched_query_ids` (list[int]) with `matched_queries` (list[dict]) in `_build_payload()` payload; each dict contains: `query_id`, `original_text`, `label`, `category`, `symptoms`, `duration`, `frequency`, `triggers`, `symptom_temporal_map`, `patient_context`, `clinical_interpretation`, `representation_text`, `similarity_score`
- [x] 16.4 Add `_build_matched_query_entry()` helper to `query_matcher.py`: deserialize JSON fields from SQLite query row, build full parameter dict with similarity score
- [x] 16.5 Update `match_queries_to_posts()` in `query_matcher.py`: collect full query entries (not just IDs) per Qdrant point; deduplicate by `query_id`; call renamed `update_matched_queries()` method
- [x] 16.6 Rename `update_matched_query_ids()` → `update_matched_queries()` in `vector_store.py`; accept `list[dict]` payload; remove `matched_query_ids` INTEGER index from `ensure_collection()`
- [x] 16.7 Update openspec design.md payload field reference table: replace `matched_query_ids` row with `thread_post_count`, `thread_point_ids`, and `matched_queries` rows with full schema documentation
- [x] 16.8 Fix `build_query_representation()` in `query_loader.py`: add `symptom_temporal_map` (per-symptom duration/onset) section; include `age_group` and `pregnancy_status` from patient_context; fix `clinical_interpretation` to read `red_flag` (bool) + `red_flag_reasons` (list) instead of non-existent `red_flags` key

## 17. Source-Namespaced Data and Logs Directory Structure

- [x] 17.1 Restructure `config.py`: move `DISCOURSE_BASE_URL` definition before path constants; derive `_SOURCE_SLUG = DISCOURSE_BASE_URL.split("://", 1)[-1]` (e.g. `"community.patient.info"`); set `DATA_DIR = SCRAPERS_DIR / "data" / _SOURCE_SLUG`, `LOGS_DIR = SCRAPERS_DIR / "logs" / _SOURCE_SLUG`; expose `SCRAPERS_DIR` for other shared resources
- [x] 17.2 Migrate existing artefacts: move `scrapers/patient_info/data/scraper.db` → `scrapers/data/community.patient.info/scraper.db`; move `scrapers/patient_info/data/cache/` → `scrapers/data/community.patient.info/cache/`; move `scrapers/patient_info/logs/scraper.log` → `scrapers/logs/community.patient.info/scraper.log`
- [x] 17.3 No changes required in `database.py`, `logger.py`, or `category_tag_mapper.py` — all consume `DATA_DIR`, `LOGS_DIR`, `DB_PATH`, `CACHE_DIR`, `LOG_FILE` from config; path changes propagate automatically

## 18. Shared SQLite Database (Single DB, Schema-Level Segregation)

- [x] 18.1 Update `config.py`: change `DB_PATH` from per-source (`DATA_DIR / "scraper.db"`) to shared (`SCRAPERS_DIR / "data" / "scraper.db"`); `DATA_DIR` now only governs per-source cache, not the database
- [x] 18.2 Update `database.py` `connect()`: replace `DATA_DIR.mkdir()` with `Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)` so the shared `scrapers/data/` directory is created regardless of per-source paths; remove unused `DATA_DIR` import
- [x] 18.3 Update openspec design.md: rewrite Decision #3 to document single shared DB with schema-level segregation via `sources` table + `source_id` FK; rewrite Decision #7 to document the four-store architecture (SQLite shared, Qdrant shared, Cache per-source, Logs per-source) with clear table and updated directory layout

## 19. Query-Driven Topic Discovery & Fail-Stop Query Loading

- [x] 19.1 In `query_loader.py`, raise `FileNotFoundError` when JSONL path does not exist (instead of returning 0)
- [x] 19.2 In `query_loader.py`, raise `ValueError` when file parses but yields 0 valid queries
- [x] 19.3 In `pipeline.py`, catch exceptions from `_stage_load_queries` and abort the pipeline with a clear error message
- [x] 19.4 In `pipeline.py`, after Stage 0, fetch unique labels from the queries table via `db.get_all_query_labels()`
- [x] 19.5 If `--labels` CLI flag is set, compute intersection of query labels and CLI labels
- [x] 19.6 Pass the resulting label list to Stages 1 and 2 instead of `mapper.get_all_labels()`
- [x] 19.7 In `topic_discovery.py`, catch `httpx.HTTPStatusError` with status 404 in `_discover_by_tag`
- [x] 19.8 On 404, return a sentinel value (e.g. -1) so `discover_topics_for_label` knows to try category fallback
- [x] 19.9 In `discover_topics_for_label`, when tag discovery returns the 404 sentinel, fall back to `_discover_by_category` using mapper's `category_slug` and `category_id`
- [x] 19.10 Log a warning when falling back from tag to category discovery
