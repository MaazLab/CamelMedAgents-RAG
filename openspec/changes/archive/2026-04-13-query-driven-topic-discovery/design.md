## Context

The scraping pipeline has 5 stages: Load Queries (0), Topic Discovery (1), Content Scraping (2), Embed & Upsert (3), Semantic Matching (4). Currently Stages 0 and 1 are independent — discovery iterates all 20 labels from `mappings.json` regardless of queries. The Discourse API endpoint `/tag/{slug}.json` returns 404 for 8 of 20 tags; these labels have valid `category_slug`/`category_id` in mappings that can serve as fallback.

## Goals / Non-Goals

**Goals:**
- Pipeline aborts immediately if JSONL file is missing or yields 0 queries
- Topic discovery only runs for labels present in loaded queries
- Tag-based discovery automatically falls back to category-based discovery on HTTP 404
- Changes are minimal and backward-compatible with existing DB schema

**Non-Goals:**
- Using Discourse `/search` endpoint (blocked by robots.txt)
- Keyword-level topic filtering using query symptoms (Discourse tag/category endpoints only return topic listings; no full-text filtering is available server-side)
- Changing the embedding or matching logic in Stages 3-4

## Decisions

### 1. Fail-stop query loading
**Decision:** `load_queries()` raises `FileNotFoundError` when JSONL path doesn't exist, and a new `ValueError` when file parses to 0 valid queries. Pipeline catches these in `_stage_load_queries` and aborts.
**Rationale:** Silent continuation led to a full 90k-post embed run with zero query association — a waste of hours of compute. Fail-fast is the correct behavior for a required input.

### 2. Labels derived from queries table
**Decision:** After Stage 0, call `db.get_all_query_labels(source_id)` to get the set of labels. Pass these to Stage 1 instead of `mapper.get_all_labels()`. The `--labels` CLI flag continues to work as an additional filter (intersection).
**Rationale:** Only scraping labels that have associated queries ensures every scraped post has a potential query match. The `--labels` flag remains useful for debugging subsets.

### 3. Category fallback on tag 404
**Decision:** In `TopicDiscovery._discover_by_tag`, catch `httpx.HTTPStatusError` with status 404. When caught, log a warning and return a sentinel so `discover_topics_for_label` falls through to category-based discovery.
**Rationale:** 8 of 20 tags consistently 404. The category endpoint groups broader content but still covers the disease. This is better than skipping the label entirely.

## Risks / Trade-offs

- **Category discovery returns broader topics:** Category endpoints include all topics in that forum section, not just the specific disease tag. This increases noise but is mitigated by Stage 4's semantic matching which filters to `score_threshold=0.5`.
- **Existing `scrape_progress` entries for tag-based discovery remain in DB:** Tags already marked `completed=True` will continue to be skipped. Category fallback only triggers for tags that actually 404 (not already-completed tags). No migration needed.
