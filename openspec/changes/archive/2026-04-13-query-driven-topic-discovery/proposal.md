## Why

The scraping pipeline currently runs topic discovery independently of loaded queries — it discovers topics for all 20 disease labels regardless of whether any queries exist. This means: (1) the pipeline silently proceeds even when the JSONL file is missing or invalid, resulting in empty `queries` and `query_post_mappings` tables with no indication of failure; (2) topics are discovered for labels that have no corresponding queries, wasting API calls and scraping effort; (3) several tag slugs return HTTP 404 from the Discourse API with no fallback to category-based discovery.

## What Changes

- **Fail-stop on query loading**: If the JSONL file is missing or yields zero valid queries, the pipeline raises an error and stops instead of silently continuing.
- **Query-driven label selection**: Stage 1 (Topic Discovery) only discovers topics for labels that exist in the loaded queries, not all 20 labels from `mappings.json`.
- **Category fallback on tag 404**: When tag-based discovery returns HTTP 404, automatically fall back to category-based discovery using the `category_slug` and `category_id` from `mappings.json`.
- **Query-topic association tracking**: Track which query labels and categories drove the discovery of each topic, enabling downstream traceability from queries through to discovered topics and matched posts.

## Capabilities

### New Capabilities
- `query-driven-discovery`: Topic discovery is driven by loaded queries — only labels present in the queries table are discovered. Category fallback on tag 404. Pipeline fails fast when no queries are loaded.

### Modified Capabilities

## Impact

- `scrapers/patient_info/pipeline.py`: Stage 0 becomes a hard gate; Stage 1 receives labels from queries instead of mapper.
- `scrapers/patient_info/query_loader.py`: Raises exception on file-not-found or zero queries loaded.
- `scrapers/patient_info/topic_discovery.py`: Adds category fallback when tag discovery returns 404.
- `scrapers/patient_info/database.py`: New method to retrieve unique labels/categories from queries.
