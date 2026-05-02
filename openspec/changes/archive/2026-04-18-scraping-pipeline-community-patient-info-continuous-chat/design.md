## Context

The project extracts medical parameters (symptoms, temporal data, patient context, clinical interpretation) from ~9,061 patient queries across 20 disease categories using an LLM-based extraction pipeline (`medical_parameter_extraction_pipeline/`). Each query is a first-person patient narrative with structured fields: `original_text`, `label` (disease), `category`, `symptoms` (with normalized names, anatomical location, severity), `duration`, `frequency`, `triggers`, `symptom_temporal_map`, `patient_context` (age, gender, comorbidities), and `clinical_interpretation` (intent, red flags).

These structured queries and their extracted parameters drive the data curation process for RAG: the scraper collects relevant medical forum discussions from `community.patient.info` and **maps each scraped post back to the query/queries it is relevant to**, so downstream RAG retrieval has curated, query-linked context.

The target site is a Discourse forum with a full JSON API (append `.json` to any URL), 30 medical categories, 289 disease/condition tags, and ~200K+ discussion topics. No authentication is needed for public content. The `/search` endpoint is disallowed by robots.txt, but category and tag browsing endpoints are allowed.

The scraper must be production-grade: resumable on failure, traceable (raw platform IDs stored for manual lookup), source-segregated (to support future data sources), and properly logged.

## Goals / Non-Goals

**Goals:**
- Load structured queries (with ALL extracted parameters: symptoms, duration, frequency, triggers, patient context, clinical interpretation) from the JSONL file into the database as the driving input for data curation
- Build a **parameter-enriched natural language representation** per query that combines all parameters (symptoms with location/severity, duration/onset, triggers, patient demographics, clinical intent) into a single text for embedding
- Scrape forum topics and posts relevant to the 20 disease labels using the Discourse JSON API (tag/category browsing — search endpoint is disallowed)
- **Compute semantic similarity** between query representations and scraped post texts using sentence embeddings, mapping each post to the query/queries it is relevant to at a semantic level — not just keyword overlap
- Store scraped posts in Qdrant with **real embedding vectors**, enabling both semantic search and payload-filtered retrieval
- Store raw data in SQLite with full platform IDs (topic_id, post_id, reply_to_post_number) for manual traceability
- Segregate data by source in the database to support multiple future scrapers; include `source` (datasource name) in every Qdrant payload
- Process content: HTML → clean text for storage alongside raw HTML
- Resume from any interruption point without re-processing completed work
- Provide structured logging at every pipeline stage

**Non-Goals:**
- Scraping data sources other than `community.patient.info` (future work, but architecture supports it)
- Using the `/search` endpoint (disallowed by robots.txt)
- Browser automation or JavaScript rendering (unnecessary — JSON API is sufficient)
- Real-time or scheduled scraping (one-time batch with resume, not a daemon)
- LLM-based re-ranking of query-post matches (future refinement — current phase uses embedding similarity)
- Training or fine-tuning models on scraped data (downstream concern)

## Decisions

### 1. JSON API over HTML scraping
**Choice**: Use Discourse's built-in JSON API (append `.json` to URLs)
**Rationale**: Returns structured JSON with every field we need (title, post HTML, tags, categories, timestamps, post IDs). Eliminates the need for HTML parsing of page layout, CSS selectors, or browser automation. More reliable and faster than scraping rendered HTML.
**Alternative considered**: Scrapy with HTML parsing — rejected as unnecessarily complex when structured data is available.

### 2. httpx async client over Scrapy
**Choice**: `httpx.AsyncClient` with manual rate limiting
**Rationale**: Scrapy is a full framework designed for large-scale web crawling with middleware, pipelines, and scheduling. For a JSON API consumer that just needs HTTP GET with rate limiting and retries, it's heavyweight. `httpx` provides async HTTP, connection pooling, and is lightweight.
**Alternative considered**: `aiohttp` — viable but `httpx` has a cleaner API and better type support.

### 3. SQLite over PostgreSQL
**Choice**: SQLite via `aiosqlite` for all state management. A single shared database lives at `scrapers/data/scraper.db` — **not** per-source. Multi-source segregation is handled at the schema level via the `sources` table and `source_id` foreign key on every data table (`topics`, `posts`, `queries`, `query_post_mappings`, `scrape_progress`).
**Rationale**: Zero-dependency setup (no server process), file-based, sufficient for the data volumes (~30K topics, ~hundreds of thousands of posts). A single database makes cross-source queries trivial (e.g., "all posts matched to diabetes queries regardless of source") and avoids managing multiple DB files. The existing `sources` table already provides strong data isolation — every row in every data table carries a `source_id` FK, so adding a second scraper never risks mixing data. Easy to inspect with any SQLite client for manual verification.
**Alternative considered**: (1) PostgreSQL — would require a running server, adds operational complexity for a batch pipeline with no concurrency requirements beyond async HTTP. (2) Per-source SQLite files at `scrapers/data/{source_slug}/scraper.db` — rejected because it duplicates the schema, complicates cross-source analysis, and the `sources` table already provides the same isolation at the schema level.

### 4. Qdrant Docker server with real sentence embeddings
**Choice**: Run Qdrant as a Docker container (`qdrant/qdrant`) accessible at `http://localhost:6333`. Store each scraped post as a Qdrant point with a real sentence embedding vector. Use a sentence-transformer model (default: `all-MiniLM-L6-v2`, 384-dim; configurable to medical models like `pritamdeka/S-PubMedBert-MS-MARCO`). Query representations are also embedded and used for vector similarity search.
**Rationale**: The core goal is semantic-level matching between structured queries and scraped posts. Real embeddings capture semantic meaning — "breaking out badly" matches "acne flare-up" even without shared keywords. Qdrant's vector search combined with payload filters (disease label) makes this efficient. Running Qdrant as a Docker server (rather than the embedded Python local client) enables UI access via the dashboard at `http://localhost:6333/dashboard`, supports larger collections without performance degradation, and uses the proper server storage format (binary segments) which is compatible with the web UI. The `QDRANT_URL` environment variable defaults to `http://localhost:6333` and can be overridden to point to a remote Qdrant instance.
**Alternative considered**: (1) Qdrant local Python client (`QdrantClient(path=...)`) — rejected because it stores data in SQLite format that is incompatible with the Qdrant server and web UI, and the library itself warns against using it for collections >20,000 points. (2) Placeholder vectors with keyword matching — rejected because keyword overlap misses semantic relationships and ignores parameters like duration, severity, triggers, patient context. (3) LLM-based pairwise scoring — too expensive for the cross-product of queries × posts; better suited as a future re-ranking step on top of embedding results.

### 5. Source URL in every Qdrant payload
**Choice**: Include `source` field set to the forum base URL (e.g., `"https://community.patient.info"`) in every Qdrant point payload.
**Rationale**: Multiple scrapers will feed the same Qdrant collection. Without `source` in the payload, there is no way to filter or attribute data by datasource. Using the base URL (rather than a short name) is self-documenting and enables queries like "all posts from community.patient.info with disease_label=diabetes".

### Qdrant Point Payload Field Reference
Every point in the `queries_relevant_scrape_data` collection has the following payload fields. When adding new fields in future scrapers, add an entry here with the same format.

| Field | Type | Source | Description |
|---|---|---|---|
| `source` | string | `DISCOURSE_BASE_URL` in config | Base URL of the forum (e.g. `https://community.patient.info`). Identifies datasource across all scrapers sharing this collection. |
| `platform_topic_id` | int | `posts.platform_topic_id` | Discourse thread ID. Reconstructs URL: `{source}/t/{platform_topic_id}`. |
| `platform_post_id` | int | `posts.platform_post_id` | Discourse individual reply ID. Used to generate deterministic Qdrant point ID via `uuid5(namespace, "{source}:{platform_post_id}")`. |
| `post_number` | int | `posts.post_number` | Sequential position within thread (1 = original question). |
| `reply_to_post_number` | int\|null | `posts.reply_to_post_number` | `post_number` this reply responds to; null = general thread reply. |
| `is_original_post` | bool | `posts.is_original_post` | True only when `post_number == 1`. Indexed for filtering original posts vs. replies. |
| `title` | string | `topics.title` | Thread title — shared by all posts in the same thread. |
| `post_text` | string | `posts.post_text` | Clean plain text after HTML stripping. **This is the text that was embedded to produce the vector.** |
| `username` | string | `posts.username` | Anonymised Discourse username of the post author (e.g. `nh_user_46005`). |
| `disease_label` | string | `topics.disease_label` | One of the 20 disease labels (e.g. `hypertension`). **Primary filter field in semantic search** — queries only search within their own label. |
| `medical_category` | string | `topics.medical_category` | Broad medical category from `mappings.json` (e.g. `Heart health and blood vessels`). |
| `category_name` | string | `topics.category_name` | Discourse forum's own category name. Empty when discovered via tag browsing. |
| `tags` | list[string] | `topics.tags` (JSON → list) | Discourse tags on the thread (e.g. `["Hypertension"]`). |
| `created_at` | string | `posts.created_at_source` | ISO 8601 timestamp of when the post was made on the forum. |
| `word_count` | int | `posts.word_count` | Word count of `post_text`. Useful for filtering very short/noisy posts. |
| `thread_post_count` | int | Computed from SQLite `posts` table | Total number of posts in the same thread (topic). Enables retrieval of the full conversation context for RAG. |
| `thread_point_ids` | list[string] | Computed via `generate_point_id()` for all posts in thread | Qdrant point IDs for every post in the same thread. Enables fetching the complete thread from Qdrant in a single call. |
| `matched_queries` | list[object] | Set in Stage 4 by `query_matcher.py` | Full query parameter dicts for queries semantically matched to this post (cosine ≥ threshold). Each entry contains: `query_id`, `original_text`, `label`, `category`, `symptoms` (list of {name, normalized_name, anatomical_location, severity}), `duration` ({value, normalized_days, onset_type}), `frequency`, `triggers`, `symptom_temporal_map` (list of {symptom, duration_days, onset_type}), `patient_context` ({age, age_group, gender, pregnancy_status, comorbidities}), `clinical_interpretation` ({intent, red_flag, red_flag_reasons}), `representation_text`, `similarity_score`. Empty until Stage 4 runs. Self-contained payload enables RAG retrieval without SQLite joins. |

### 6. Multi-level resume strategy
**Choice**: Two checkpoint levels: page-level (`scrape_progress`), topic-level (`topics.scrape_status`)
**Rationale**: A scrape of ~30K topics over days will inevitably be interrupted. Page-level resume means topic discovery restarts from the last completed page. Topic-level means already-scraped topics are skipped. This avoids any redundant API calls or re-processing.

### 7. Four-store architecture with shared and per-source artefacts
**Choice**: Runtime artefacts are split across four storage systems with clear shared vs. per-source boundaries:

| Store | Scope | Path / Location | Segregation mechanism |
|---|---|---|---|
| **SQLite** | Shared | `scrapers/data/scraper.db` | `sources` table + `source_id` FK on all data tables |
| **Qdrant** | Shared | `scrapers/qdrant_server/` (Docker volume), `http://localhost:6333` | `source` field in every point payload |
| **Cache** | Per-source | `scrapers/data/{source_slug}/cache/` | Source slug directory (e.g., `community.patient.info`) |
| **Logs** | Per-source | `scrapers/logs/{source_slug}/` | Source slug directory |

Resulting directory layout:
```
scrapers/
  data/
    scraper.db                 ← single shared SQLite database (all sources)
    community.patient.info/    ← source slug from "https://community.patient.info"
      cache/
        categories.json
        tags.json
  logs/
    community.patient.info/
      scraper.log
  qdrant_server/               ← shared Qdrant Docker volume (all sources)
  patient_info/                ← source-specific Python modules and config
```
The source slug is computed once in `config.py` as `DISCOURSE_BASE_URL.split("://", 1)[-1]` and used to build `DATA_DIR` (per-source cache root), `LOGS_DIR`, `CACHE_DIR`, and `LOG_FILE`. The shared `DB_PATH` is at `SCRAPERS_DIR / "data" / "scraper.db"` — independent of the source slug.
**Rationale**: SQLite and Qdrant are shared because they benefit from cross-source queries and unified schema. Cache and logs are per-source because they are source-specific artefacts (API response caches, scraper run logs) with no cross-source value. Placing all artefacts under `scrapers/` (above individual source module folders like `patient_info/`) keeps the workspace clean. A second scraper (e.g., `reddit.com/r/medical`) writes cache to `scrapers/data/reddit.com/r/medical/cache/` and logs to `scrapers/logs/reddit.com/r/medical/` while sharing the same `scraper.db` and Qdrant collection.
**Alternative considered**: (1) Per-source SQLite files — rejected because the `sources` table already isolates data at the schema level. (2) Keep data inside source module folders (`scrapers/patient_info/data/`) — rejected because it provides no source identifier in the path and creates parallel top-level directories per scraper.

### 8. Tag-based discovery over full category sweep
**Choice**: Primary discovery via disease-specific tags, fallback to category pagination
**Rationale**: Tags are precise (e.g., tag "Acne" has 255 topics vs. category "Skin, nail and hair health" has 7,149 topics). Using tags first gives higher signal-to-noise. Category fallback covers cases without exact tag matches (e.g., Conjunctivitis).

### 9. Query-driven data curation (queries table + semantic relevance mapping)
**Choice**: Load all structured queries from the JSONL file into a `queries` table. Build a parameter-enriched text representation per query. After scraping, compute query-to-post semantic relevance via embedding similarity, stored in a `query_post_mappings` table with similarity scores.
**Rationale**: The scraping purpose is data curation for RAG — each scraped post must be traceable to the query/queries it serves. Semantic matching using ALL query parameters (not just disease label) ensures that the curated data is truly relevant to each query's specific symptoms, patient profile, and clinical intent.
**Alternative considered**: Store only query hashes — rejected because downstream processes need the full parameter set for representation building and verification.

### 10. Parameter-enriched query representation for semantic matching
**Choice**: Convert each query's structured parameters into a natural language text that combines: disease label, all symptoms (with anatomical location and severity), duration and onset type, frequency, triggers, **symptom temporal map** (per-symptom duration and onset), patient demographics (age, age_group, gender, pregnancy_status, comorbidities), and clinical interpretation (intent, red_flag, red_flag_reasons). This representation is embedded for semantic similarity search.
**Rationale**: A sentence embedding model needs a single text input. By aggregating ALL parameters into a structured natural language representation, we capture the full semantic context of each query in one embedding. The `symptom_temporal_map` is particularly important because it captures per-symptom timing that the overall `duration` field cannot represent (e.g., a patient with chronic redness for 3 years but acute acne lesions for 2 weeks). Example output: `"Acne patient. Symptoms: redness on cheeks, acne lesions on chin. Duration: about 3 years (chronic onset). Symptom timeline: redness for 1095 days (chronic), acne lesions for 1095 days (chronic). Patient: 16 year old adolescent male. Seeking diagnosis."` — this captures ALL 10 JSONL parameters at the semantic level.
**Alternative considered**: Embed `original_text` directly — rejected because the original text contains noise (emotional language, tangential details) while the extracted parameters are structured and clinically focused.

### 11. Sentence-transformer model for embeddings
**Choice**: Use `sentence-transformers` library with a configurable model name. Default: `all-MiniLM-L6-v2` (384-dim, fast, good quality). Alternative: `pritamdeka/S-PubMedBert-MS-MARCO` (768-dim, medical IR tasks) for better medical domain accuracy.
**Rationale**: Sentence-transformer models are designed for semantic similarity tasks. They produce fixed-size embeddings that capture meaning, not just surface-level keywords. The `all-MiniLM-L6-v2` model is lightweight (runs on CPU), fast (~100ms per encoding), and has good benchmark performance. For production, a medical-domain model can be swapped in via config without code changes.
**Alternative considered**: (1) OpenAI embeddings API — adds cost and external dependency. (2) TF-IDF/BM25 — better than pure keyword but still surface-level, misses synonyms and paraphrases. (3) LLM-based pairwise scoring — most accurate but O(queries × posts) LLM calls is prohibitively expensive.

### 12. Fail-stop query loading
**Choice**: `load_queries()` raises `FileNotFoundError` when JSONL path doesn't exist, and `ValueError` when the file parses to 0 valid queries. The pipeline catches these in `_stage_load_queries` and aborts.
**Rationale**: Silent continuation led to a full 90k-post embed run with zero query association — a waste of hours of compute. Fail-fast is the correct behavior for a required input.

### 13. Labels derived from queries table
**Choice**: After Stage 0, call `db.get_all_query_labels(source_id)` to get the set of labels. Pass these to Stage 1 instead of `mapper.get_all_labels()`. The `--labels` CLI flag continues to work as an additional filter (intersection).
**Rationale**: Only scraping labels that have associated queries ensures every scraped post has a potential query match. The `--labels` flag remains useful for debugging subsets.

### 14. Category fallback on tag HTTP 404
**Choice**: In `TopicDiscovery._discover_by_tag`, catch `httpx.HTTPStatusError` with status 404. When caught, log a warning and return a sentinel so `discover_topics_for_label` falls through to category-based discovery using `category_slug` and `category_id` from `mappings.json`.
**Rationale**: 8 of 20 tags consistently return 404 from the Discourse API. The category endpoint groups broader content but still covers the disease. This is better than skipping the label entirely. Broader results are mitigated by Stage 4's semantic matching (similarity threshold).

## Risks / Trade-offs

- **[Rate limiting]** Discourse's anonymous rate limit (~200 req/min) means a full scrape is slow → Mitigation: 300ms inter-request delay, exponential backoff on 429s, resume support so progress is never lost
- **[IP blocking]** Sustained scraping could trigger IP bans → Mitigation: respectful rate limiting, proper User-Agent header, compliance with robots.txt
- **[Data volume]** ~30K topics × N posts per topic generates significant data → Mitigation: SQLite handles this well; Qdrant handles real vectors efficiently; can filter with `--max-topics-per-label` for testing
- **[API response changes]** Discourse API is not versioned; response shapes could change → Mitigation: Pydantic models with strict validation will surface breaking changes immediately
- **[Tag mapping gaps]** Some disease labels don't have exact tag matches (Conjunctivitis, Heart Attack, Otitis-Media) → Mitigation: Fallback to broader tags (Eye problems, Cardiovascular disorders, Ear problems) plus category browsing
- **[Embedding model quality]** General-purpose sentence-transformers may not capture medical nuance perfectly → Mitigation: Model is configurable; can swap to medical-specific model (`S-PubMedBert-MS-MARCO`) without code changes; disease-label pre-filtering ensures only same-domain comparisons
- **[Similarity threshold tuning]** Choosing the right cosine similarity threshold determines match quality (too low = noise, too high = missed matches) → Mitigation: Configurable threshold with a sensible default (0.5); store similarity scores in mappings table so threshold can be adjusted post-hoc without re-embedding
- **[Embedding compute time]** Embedding thousands of posts takes time on CPU → Mitigation: Batch encoding, GPU support (optional), resume from last embedded post
- **[Many-to-many mapping volume]** Queries × posts can produce a large mapping table → Mitigation: Disease label pre-filter + similarity threshold + top-K cap per query keeps mappings manageable
- **[Partial parameter coverage]** The non-enriched JSONL (9,061 queries) lacks `patient_context` and `clinical_interpretation`; the enriched file (204 queries) has all parameters → Mitigation: Query representation builder adapts to available parameters — uses what's present, omits what's null. Results improve as more queries get enriched
- **[Category fallback yields broader results]** Category endpoints include all topics in a forum section, not just the specific disease tag. This increases noise → Mitigation: Stage 4's semantic matching filters results to `score_threshold=0.5`, keeping only semantically relevant matches
- **[Silent query-loading failure]** If the JSONL path is invalid, the pipeline previously ran all expensive stages (embedding 90k posts) with zero queries → Mitigation: Fail-stop behavior now raises an exception and aborts before Stage 1
