## Why

The project has extracted structured medical queries (with symptoms, temporal data, patient context, clinical interpretation) from patient narratives across 20 disease categories. To implement RAG, each query needs curated context — relevant medical forum discussions that are semantically relevant to the query's specific symptoms, patient profile, and clinical intent — not just topically related to the disease. `community.patient.info` is a Discourse-based medical forum with 30 categories, 289 disease tags, and ~200K+ topics of patient discussions — an ideal source. A production-grade scraper is needed to collect this data, **semantically match each scraped post to its relevant query/queries** using ALL extracted parameters, and store the curated mappings for downstream RAG retrieval.

## What Changes

- Add a new top-level `scrapers/` directory with a `patient_info/` sub-folder (separate from `medical_parameter_extraction_pipeline/`, which handles parameter extraction)
- **Load structured queries** (with extracted parameters: symptoms with location/severity, duration, triggers, patient context, clinical interpretation) from the JSONL file into a `queries` table in SQLite
- **Build a parameter-enriched natural language representation** per query from ALL available parameters (symptoms, anatomical locations, severity, duration, onset type, frequency, triggers, age, gender, comorbidities, clinical intent) for semantic embedding
- **Fail-stop on query loading**: If the JSONL file is missing or yields zero valid queries, the pipeline raises an error and stops instead of silently continuing
- **Query-driven label selection**: Stage 1 (Topic Discovery) only discovers topics for labels that exist in the loaded queries, not all 20 labels from `mappings.json`
- **Category fallback on tag 404**: When tag-based discovery returns HTTP 404, automatically fall back to category-based discovery using the `category_slug` and `category_id` from `mappings.json`
- Build an async Discourse JSON API client with rate limiting and retry logic, targeting `community.patient.info`
- Create a disease-label-to-tag/category mapping engine that maps the 20 extracted disease labels to the forum's tag and category IDs
- Implement a SQLite database schema with `sources`, `queries`, `topics`, `posts`, `query_post_mappings`, and `scrape_progress` tables, designed to segregate data by source and store raw platform post/topic IDs for manual traceability; posts table stores `qdrant_point_id` and `embedding_hash` for cross-reference
- Build a content extraction pipeline: HTML → clean text (stored alongside raw HTML in the posts table)
- **Embed both query representations and post texts** using a sentence-transformer model; store real embedding vectors in Qdrant
- **Compute semantic query-to-post relevance** via Qdrant vector similarity search (filtered by disease label); store mappings with similarity scores in `query_post_mappings` table
- Upsert each scraped post to Qdrant with: **real sentence embedding vector**, full metadata payload including `source` (datasource name), `disease_label`, `post_text`, platform IDs, reply info, and `matched_query_ids`; payload indexes enable filtered queries per datasource and per query
- Build a resumable pipeline orchestrator: on interruption or error, restarts from where it left off using multi-level DB checkpoints (page-level, topic-level, embedding-level)
- Add centralized structured logging with rotating file handler and console handler
- Provide CLI entry point with filtering, dry-run, and resume options
- Add a verification tool to check DB integrity, coverage, and semantic mapping quality stats

## Capabilities

### New Capabilities
- `query-loading`: Load structured queries from the JSONL file into a `queries` table with all extracted parameters (symptoms, duration, patient context, clinical interpretation); assign stable query IDs for mapping
- `query-representation`: Build a parameter-enriched natural language representation per query from ALL available parameters — symptoms (name, normalized name, anatomical location, severity), duration (value, normalized days, onset type), frequency, triggers, patient context (age, age group, gender, comorbidities), clinical interpretation (intent, red flags) — for sentence embedding
- `embedder`: Sentence-transformer embedding module — embeds query representations and post texts into fixed-size vectors; configurable model (default: `all-MiniLM-L6-v2` 384-dim; alternative: `pritamdeka/S-PubMedBert-MS-MARCO` for medical domain); batch encoding for efficiency
- `discourse-api-client`: Async HTTP client for the Discourse JSON API with rate limiting, exponential backoff, and robots.txt compliance
- `scraper-database`: SQLite database with source-segregated schema storing raw platform IDs (post_id, topic_id, reply_to_post_number); `queries` table for structured queries with representation text; `query_post_mappings` table for query-to-post semantic relevance links with similarity scores; posts table tracks `qdrant_point_id` for cross-reference
- `category-tag-mapping`: Static + cacheable mapping from 20 disease labels to patient.info tag IDs and category IDs
- `query-driven-discovery`: Topic discovery is driven by loaded queries — only labels present in the queries table are discovered. Category fallback on tag 404. Pipeline fails fast when no queries are loaded.
- `topic-discovery`: Paginated topic collection by tag/category with deduplication and page-level resume tracking
- `content-processing`: HTML-to-text extraction and cleanup for storing clean text alongside raw HTML
- `query-post-matching`: Semantic relevance engine — for each query, searches Qdrant by embedding similarity (filtered by disease label) to find semantically relevant posts; stores many-to-many mappings with similarity scores and top-K cap
- `vector-storage`: Qdrant Docker server vector store — one point per post with real sentence embedding and full metadata payload (including `source` datasource name, `matched_query_ids`); deterministic point IDs; payload indexes on `source`, `disease_label`, `is_original_post`, `matched_query_ids`, and platform IDs; accessible via web UI at `http://localhost:6333/dashboard`
- `scraper-pipeline-orchestration`: Resumable multi-stage pipeline with CLI, structured logging, and stage-level checkpoint resume

### Modified Capabilities
<!-- No existing capabilities are being modified -->

## Impact

- **New directory**: `scrapers/patient_info/` with ~15 Python files
- **New dependencies**: `httpx`, `beautifulsoup4`, `aiosqlite`, `qdrant-client`, `sentence-transformers`
- **New database file**: SQLite DB at `scrapers/patient_info/data/scraper.db`
- **New log files**: Rotating logs at `scrapers/patient_info/logs/scraper.log`
- **Embedding model**: ~80MB model download on first run (cached in `~/.cache/torch/sentence_transformers/`)
- **External system**: Reads from `community.patient.info` JSON API (public, no auth); writes to Qdrant Docker server at `http://localhost:6333` (start with `docker run -d --name qdrant -p 6333:6333 -p 6334:6334 -v <host_path>:/qdrant/storage qdrant/qdrant`; `QDRANT_URL` env var defaults to `http://localhost:6333`, override to point to remote instance)
- **Input dependency**: Reads JSONL file from `medical_parameter_extraction_pipeline/` for structured queries with extracted parameters. Supports both enriched (204 records, all parameters) and non-enriched (9,061 records, symptoms/duration/triggers) formats — adapts representation to available parameters
- **New DB tables**: `queries` (structured query storage with representation text), `query_post_mappings` (query-to-post semantic relevance links with similarity scores)
- **No changes** to existing `medical_parameter_extraction_pipeline/`, `query_reformulation/`, or `dataset/` directories
