## ADDED Requirements

### Requirement: Pipeline SHALL fail when query loading fails
The pipeline SHALL raise an error and stop execution if the JSONL input file does not exist or if zero valid queries are loaded from the file.

#### Scenario: JSONL file does not exist
- **WHEN** the pipeline runs with a `--jsonl-path` pointing to a non-existent file
- **THEN** `load_queries()` SHALL raise `FileNotFoundError` and the pipeline SHALL log the error and terminate before Stage 1

#### Scenario: JSONL file yields zero valid queries
- **WHEN** the JSONL file exists but contains no parseable queries (empty file, all invalid JSON, or all missing `original_text`)
- **THEN** `load_queries()` SHALL raise `ValueError` with a message indicating zero queries were loaded, and the pipeline SHALL terminate before Stage 1

### Requirement: Topic discovery SHALL only discover labels present in loaded queries
Stage 1 (Topic Discovery) SHALL derive its label list from the `queries` table instead of from `mappings.json`. Only disease labels that have at least one loaded query SHALL be discovered.

#### Scenario: Queries exist for a subset of labels
- **WHEN** the JSONL file contains queries for labels `acne`, `diabetes`, and `headache` only
- **THEN** Stage 1 SHALL discover topics only for those 3 labels, not all 20 from mappings

#### Scenario: CLI --labels flag narrows further
- **WHEN** queries exist for labels `acne`, `diabetes`, `headache` and `--labels acne diabetes` is passed
- **THEN** Stage 1 SHALL discover topics only for `acne` and `diabetes` (intersection of queries and CLI filter)

### Requirement: Tag discovery SHALL fall back to category discovery on HTTP 404
When tag-based topic discovery receives an HTTP 404 response, the system SHALL automatically attempt category-based discovery using the `category_slug` and `category_id` from `mappings.json`.

#### Scenario: Tag returns 404 with valid category mapping
- **WHEN** `/tag/pernicious-anaemia.json` returns HTTP 404
- **AND** `mappings.json` has `category_slug: "allergies-blood-and-immune-system"` and `category_id: 4` for label `b12-deficiency`
- **THEN** the system SHALL log a warning about the tag 404, attempt category-based discovery using `/c/allergies-blood-and-immune-system/4.json`, and proceed normally

#### Scenario: Both tag and category fail
- **WHEN** tag discovery returns 404 and category discovery also fails
- **THEN** the system SHALL log an error for that label and continue to the next label without aborting the pipeline
