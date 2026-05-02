## ADDED Requirements

### Requirement: Qdrant collection with real sentence embeddings
The vector store SHALL create a Qdrant collection using real sentence embedding vectors from the configured sentence-transformer model (default: `all-MiniLM-L6-v2` at 384 dimensions, `Distance.COSINE`). The collection SHALL have payload indexes to support filtered similarity search.

#### Scenario: Create collection if not exists
- **WHEN** the vector store initialises and the collection does not exist
- **THEN** it SHALL create the collection with `VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)` where `EMBEDDING_DIM` matches the configured model (384 for `all-MiniLM-L6-v2`, 768 for `pritamdeka/S-PubMedBert-MS-MARCO`)

#### Scenario: Payload indexes created on collection creation
- **WHEN** the collection is created
- **THEN** payload indexes SHALL be created on: `source` (keyword), `disease_label` (keyword), `medical_category` (keyword), `is_original_post` (bool), `platform_topic_id` (integer), `platform_post_id` (integer), `matched_query_ids` (integer)

#### Scenario: Support local file and server modes
- **WHEN** no Qdrant URL is configured
- **THEN** the vector store SHALL use Qdrant local file storage (no server required)
- **WHEN** a Qdrant URL is configured
- **THEN** the vector store SHALL connect to the remote Qdrant server

### Requirement: Embed and upsert posts with real vectors
Each scraped post SHALL be embedded using the sentence-transformer model and stored as a Qdrant point with its real embedding vector. The embedding SHALL be computed from the post's cleaned text.

#### Scenario: Embed a post
- **WHEN** a post with `post_text = "I've had bumps on my face for 2 months now..."` is processed
- **THEN** the embedder SHALL encode the text into a 384-dimensional vector (or model-configured dimension) which SHALL be stored as the point's vector in Qdrant

#### Scenario: Batch embedding for efficiency
- **WHEN** 100 posts are pending upsert
- **THEN** the embedder SHALL encode them in batches (configurable batch size, default 64) rather than one-by-one

#### Scenario: Track embedding content hash
- **WHEN** a post is embedded and upserted
- **THEN** an `embedding_hash` (hash of the post text used for embedding) SHALL be stored in the `posts` table to detect when re-embedding is needed (e.g., after content reprocessing)

#### Scenario: Skip re-embedding unchanged posts
- **WHEN** a post already has a `qdrant_point_id` and its `embedding_hash` matches the current text hash
- **THEN** the post SHALL be skipped (no re-embedding or re-upsert needed)

### Requirement: One point per post with datasource and query linkage in payload
Each scraped post SHALL be stored as one Qdrant point. The payload SHALL include the `source` field (datasource name, e.g., `"patient_info"`) and `matched_query_ids` (list of query DB IDs from the semantic matching stage) to enable multi-source filtering and query-level retrieval.

#### Scenario: Payload fields per post
- **WHEN** a post is upserted
- **THEN** the Qdrant payload SHALL contain: `source`, `platform_topic_id`, `platform_post_id`, `post_number`, `reply_to_post_number`, `is_original_post`, `title`, `post_text`, `username`, `disease_label`, `medical_category`, `category_name`, `tags`, `created_at`, `word_count`, `matched_query_ids`

#### Scenario: Filter by datasource
- **WHEN** a query filter `source = "patient_info"` is applied
- **THEN** only points from that datasource SHALL be returned

#### Scenario: Filter by matched query ID
- **WHEN** a filter `matched_query_ids` contains query ID 42 is applied
- **THEN** only posts mapped to query 42 SHALL be returned

### Requirement: Similarity search for query matching
The vector store SHALL support similarity search: given a query embedding vector, find the top-K most similar posts filtered by disease label, returning results with similarity scores.

#### Scenario: Search by query embedding
- **WHEN** a query embedding and `disease_label = "acne"` filter are provided with `top_k = 50` and `score_threshold = 0.5`
- **THEN** the vector store SHALL return up to 50 points with `disease_label = "acne"` that have cosine similarity >= 0.5, ordered by similarity score descending

#### Scenario: No results above threshold
- **WHEN** no posts for the given disease label have similarity >= threshold
- **THEN** an empty result list SHALL be returned

### Requirement: Deterministic point IDs
Point IDs SHALL be generated deterministically via `uuid5(namespace, "{source}:{platform_post_id}")` to prevent duplicates on re-runs.

#### Scenario: Same post produces same point ID
- **WHEN** post with `source="patient_info"` and `platform_post_id=12345` is upserted twice
- **THEN** the same UUID SHALL be generated both times, resulting in an update rather than a duplicate

### Requirement: Linkback to SQLite
After upserting a post to Qdrant, the vector store SHALL write the `qdrant_point_id` and `embedding_hash` back to the `posts` table in SQLite.

#### Scenario: Write qdrant_point_id to database
- **WHEN** a post is successfully upserted to Qdrant
- **THEN** `posts.qdrant_point_id` SHALL be set to the point UUID, `posts.embedding_hash` SHALL be set to the content hash, and `posts.upserted_at` SHALL be set to the current timestamp

### Requirement: Skip already-upserted posts on resume
The upsert stage SHALL skip posts that already have a `qdrant_point_id` set in SQLite with a matching `embedding_hash`.

#### Scenario: Resume after interruption
- **WHEN** the pipeline restarts and some posts already have `qdrant_point_id` set with matching `embedding_hash`
- **THEN** those posts SHALL be skipped and only posts with `qdrant_point_id IS NULL` or mismatched `embedding_hash` SHALL be embedded and upserted
