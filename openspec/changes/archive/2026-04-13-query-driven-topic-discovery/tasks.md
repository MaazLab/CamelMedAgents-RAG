## 1. Fail-stop query loading

- [x] 1.1 In `query_loader.py`, raise `FileNotFoundError` when JSONL path does not exist (instead of returning 0)
- [x] 1.2 In `query_loader.py`, raise `ValueError` when file parses but yields 0 valid queries
- [x] 1.3 In `pipeline.py`, catch exceptions from `_stage_load_queries` and abort the pipeline with a clear error message

## 2. Query-driven label selection

- [x] 2.1 In `pipeline.py`, after Stage 0, fetch unique labels from the queries table via `db.get_all_query_labels()`
- [x] 2.2 If `--labels` CLI flag is set, compute intersection of query labels and CLI labels
- [x] 2.3 Pass the resulting label list to Stages 1 and 2 instead of `mapper.get_all_labels()`

## 3. Category fallback on tag 404

- [x] 3.1 In `topic_discovery.py`, catch `httpx.HTTPStatusError` with status 404 in `_discover_by_tag`
- [x] 3.2 On 404, return a sentinel value (e.g. -1) so `discover_topics_for_label` knows to try category fallback
- [x] 3.3 In `discover_topics_for_label`, when tag discovery returns the 404 sentinel, fall back to `_discover_by_category` using mapper's `category_slug` and `category_id`
- [x] 3.4 Log a warning when falling back from tag to category discovery
