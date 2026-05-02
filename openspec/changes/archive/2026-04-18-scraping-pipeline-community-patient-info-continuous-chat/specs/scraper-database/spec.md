## ADDED Requirements

### Requirement: Source-segregated schema
The database SHALL have a `sources` table that registers each data source. All other tables SHALL reference `source_id` as a foreign key to segregate data by source.

#### Scenario: Register a new source
- **WHEN** a scraper starts for a new data source (e.g., "patient_info")
- **THEN** a row SHALL be inserted into `sources` with the source name and base URL, or the existing row SHALL be returned if it already exists

#### Scenario: Data isolation between sources
- **WHEN** querying topics or posts
- **THEN** filtering by `source_id` SHALL return only data from that specific source

### Requirement: Queries table for structured query storage with representation text
The database SHALL have a `queries` table that stores structured queries loaded from the JSONL file. Each row SHALL include: `id`, `source_id`, `original_text`, `label` (disease label), `category`, `symptoms_json` (full symptom list as JSON array), `duration_json`, `frequency`, `triggers_json`, `patient_context_json`, `clinical_interpretation_json`, `representation_text` (parameter-enriched natural language text for sentence embedding), `loaded_at`.

#### Scenario: Load a query with representation
- **WHEN** a structured query `{"original_text": "I've had bumps for 2 months...", "label": "acne", "symptoms": [{"name": "bumps", "normalized_name": "bumps"}], ...}` is loaded
- **THEN** a row SHALL be inserted with `label = "acne"`, `symptoms_json` containing the full symptom array, and `representation_text` containing the parameter-enriched natural language representation

#### Scenario: Query with all parameters produces rich representation
- **WHEN** an enriched query has symptoms with location/severity, duration, patient_context (age, gender), clinical_interpretation (intent)
- **THEN** `representation_text` SHALL include all parameter sections in natural language form

#### Scenario: Query with partial parameters produces adapted representation
- **WHEN** a non-enriched query has only symptoms, duration, and triggers (no patient_context, no clinical_interpretation)
- **THEN** `representation_text` SHALL include only available sections, omitting patient context and clinical interpretation

#### Scenario: Skip duplicate queries on re-load
- **WHEN** the same query text is loaded twice (same `source_id` + `original_text` hash)
- **THEN** the second insert SHALL be skipped via `UNIQUE(source_id, text_hash)` constraint

### Requirement: Query-post mappings table with similarity scores
The database SHALL have a `query_post_mappings` table that stores the many-to-many semantic relevance mapping between queries and scraped posts. Each row SHALL include: `id`, `query_id` (FK → queries), `post_id` (FK → posts), `similarity_score` (REAL, cosine similarity from Qdrant vector search), `created_at`. Unique constraint on `(query_id, post_id)`.

#### Scenario: Map a post to a query via semantic similarity
- **WHEN** a Qdrant similarity search for a query's embedding returns a post with cosine similarity 0.73
- **THEN** a mapping row SHALL be inserted with `similarity_score = 0.73`

#### Scenario: Post matches multiple queries
- **WHEN** a post about "acne bumps" is semantically similar to queries Q1 (score=0.82) and Q2 (score=0.65)
- **THEN** two mapping rows SHALL exist: `(Q1, post, 0.82)` and `(Q2, post, 0.65)`

#### Scenario: Prevent duplicate mappings
- **WHEN** the matching stage re-runs
- **THEN** the `UNIQUE(query_id, post_id)` constraint SHALL handle conflicts via `ON CONFLICT DO UPDATE SET similarity_score = excluded.similarity_score`

### Requirement: Topics table with platform IDs
The `topics` table SHALL store one row per discovered forum topic, including the raw `platform_topic_id` from the Discourse API, the topic title, category info, tags (as JSON array), disease label, medical category, post count, view count, source creation date, and scrape status.

#### Scenario: Insert a discovered topic
- **WHEN** a topic is discovered during tag/category browsing
- **THEN** a row SHALL be inserted with `scrape_status = 'discovered'` and the raw `platform_topic_id`

#### Scenario: Unique constraint on platform topic ID per source
- **WHEN** the same topic is discovered via multiple tags
- **THEN** the `UNIQUE(source_id, platform_topic_id)` constraint SHALL prevent duplicate rows

### Requirement: Posts table with platform IDs, reply tracking, embedding hash, and Qdrant linkback
The `posts` table SHALL store one row per post/reply, including `platform_post_id`, `platform_topic_id`, `post_number`, `reply_to_post_number`, `is_original_post`, username, cleaned text, raw HTML, word count, source creation date, `qdrant_point_id`, `embedding_hash`, and `upserted_at`. The `embedding_hash` tracks the hash of post text content used for the current embedding, enabling detection of when re-embedding is needed.

#### Scenario: Store a post with reply reference
- **WHEN** a post that is a reply to post #3 is scraped
- **THEN** the row SHALL have `reply_to_post_number = 3` and `is_original_post = FALSE`

#### Scenario: Manual traceability via platform IDs
- **WHEN** a post row has `platform_topic_id = 532536` and `post_number = 5`
- **THEN** the original post SHALL be viewable at `https://community.patient.info/t/532536/5`

#### Scenario: Unique constraint on platform post ID per source
- **WHEN** the same post is encountered during re-scraping
- **THEN** the `UNIQUE(source_id, platform_post_id)` constraint SHALL prevent duplicate rows

#### Scenario: Qdrant linkback after upsert
- **WHEN** a post is embedded and upserted to Qdrant
- **THEN** `posts.qdrant_point_id` SHALL be written with the deterministic UUID, `posts.embedding_hash` SHALL be set to the hash of the post text used for embedding, and `posts.upserted_at` SHALL be set

### Requirement: Multi-level checkpoint resume
The database SHALL support resume at three levels: page-level (via `scrape_progress`), topic-level (via `topics.scrape_status`), and embedding-level (via `posts.embedding_hash`).

#### Scenario: Skip already-scraped topics
- **WHEN** the pipeline restarts and a topic has `scrape_status = 'scraped'`
- **THEN** the pipeline SHALL skip the API call to fetch that topic's posts
