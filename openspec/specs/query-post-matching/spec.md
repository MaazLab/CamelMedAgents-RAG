## ADDED Requirements

### Requirement: Semantic query-post matching via embedding similarity
The query matcher SHALL match scraped posts to queries using sentence embedding similarity: (1) embed the query's `representation_text` using the configured sentence-transformer model, (2) search Qdrant for the top-K most similar posts filtered by the query's disease label, (3) store all matches above the similarity threshold in `query_post_mappings` with their cosine similarity scores.

#### Scenario: Single query semantic match
- **WHEN** query Q1 has `label = "acne"` and `representation_text = "Acne patient. Symptoms: mild bumps on face. Duration: 2 months..."`, and post P1 has `disease_label = "acne"` with semantically similar content about facial bumps
- **THEN** a Qdrant search SHALL return P1 with `similarity_score >= SIMILARITY_THRESHOLD`, and a mapping `(Q1, P1, score)` SHALL be stored

#### Scenario: Score-based filtering
- **WHEN** Qdrant returns 100 results for a query, 30 have `score >= 0.5` (threshold) and 70 have `score < 0.5`
- **THEN** only the 30 results above threshold SHALL be stored as mappings

#### Scenario: Top-K cap
- **WHEN** a query matches more than `TOP_K_MATCHES` (default 50) posts above threshold
- **THEN** only the top 50 by similarity score SHALL be stored

#### Scenario: Semantic understanding beyond keywords
- **WHEN** query representation mentions "chest tightness and difficulty breathing" and a post discusses "constriction in the thorax" and "struggling to get air"
- **THEN** the semantic similarity SHALL capture the match even though no exact keyword overlap exists

### Requirement: Many-to-many mapping
A single post MAY match multiple queries, and a single query MAY match multiple posts. All valid pairings above threshold SHALL be stored in `query_post_mappings` with their similarity scores.

#### Scenario: Post matches two queries
- **WHEN** post P1 about "facial bumps and redness" is semantically similar to both Q1 (symptoms=["bumps"]) and Q2 (symptoms=["bumps", "redness"]) under the same disease label
- **THEN** two mapping rows SHALL exist: `(Q1, P1, score_1)` and `(Q2, P1, score_2)`

#### Scenario: Query matches many posts
- **WHEN** query Q1 about "diabetes fatigue" semantically matches 45 posts above threshold
- **THEN** 45 mapping rows SHALL exist for Q1 (or up to TOP_K_MATCHES)

### Requirement: Configurable similarity parameters
The matching stage SHALL use configurable parameters: `SIMILARITY_THRESHOLD` (float, default 0.5) and `TOP_K_MATCHES` (int, default 50).

#### Scenario: Lower threshold yields more matches
- **WHEN** `SIMILARITY_THRESHOLD` is set to 0.3
- **THEN** more posts SHALL qualify as matches compared to the default 0.5

#### Scenario: Post-hoc threshold adjustment
- **WHEN** all matches are stored with their similarity scores
- **THEN** a higher threshold CAN be applied post-hoc by filtering the `query_post_mappings` table by `similarity_score >= new_threshold` without re-embedding

### Requirement: Idempotent re-runs
The matching stage SHALL be idempotent: re-running it SHALL not create duplicate mapping rows. Existing mappings SHALL be updated with new similarity scores if the embeddings change.

#### Scenario: Re-run matching after new posts scraped
- **WHEN** matching ran previously and new posts were scraped and embedded for the same label
- **THEN** only new `(query_id, post_id)` pairs SHALL be inserted; existing pairs SHALL be updated via `ON CONFLICT(query_id, post_id) DO UPDATE SET similarity_score = excluded.similarity_score`

### Requirement: Summary statistics
After matching, the matcher SHALL log summary statistics: total mappings created, queries with at least one match, queries with zero matches ("uncurated"), average/min/max similarity scores, average posts per query, and average queries per post.

#### Scenario: Summary log output
- **WHEN** matching completes
- **THEN** the log SHALL include e.g. `"Matching complete: 45,230 mappings, 8,540/9,061 queries curated, 521 uncurated, avg score=0.62, min=0.50, max=0.95, avg 5.3 posts/query, avg 2.1 queries/post"`
