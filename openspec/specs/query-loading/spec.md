## ADDED Requirements

### Requirement: Load structured queries from JSONL
The query loader SHALL read a JSONL file (enriched or non-enriched) and insert each structured query into the `queries` table in SQLite, supporting both formats: enriched (with patient_context and clinical_interpretation) and non-enriched (symptoms, duration, triggers only).

#### Scenario: Parse a single enriched query record
- **WHEN** a JSONL line is `{"original_text": "I've had bumps...", "label": "acne", "category": "Dermatology", "symptoms": [{"name": "bumps", "normalized_name": "bumps", "anatomical_location": "", "severity": ""}], "duration": {"value": "2 months", "normalized_days": 60, "onset_type": "chronic"}, "frequency": "off and on", "triggers": [], "symptom_temporal_map": [...], "patient_context": {"age": 20, ...}, "clinical_interpretation": {"intent": "diagnosis", ...}}`
- **THEN** the loader SHALL insert a row with `label = "acne"`, `category = "Dermatology"`, `symptoms_json` containing the full symptoms array, and all other parameters stored as JSON columns

#### Scenario: Parse a non-enriched query record
- **WHEN** a JSONL line has symptoms, duration, frequency, triggers, and symptom_temporal_map but no patient_context or clinical_interpretation
- **THEN** the loader SHALL insert a row with available fields populated and `patient_context_json = null`, `clinical_interpretation_json = null`

#### Scenario: Handle queries without patient context or clinical interpretation
- **WHEN** a query has `"patient_context": null` or the field is absent
- **THEN** the corresponding JSON columns SHALL be stored as `null` and the representation SHALL omit those sections

### Requirement: Build parameter-enriched query representation
The query loader SHALL build a natural language representation text per query from ALL available parameters, stored in the `representation_text` column for sentence embedding.

#### Scenario: Full representation with all parameters
- **WHEN** a query has label="acne", symptoms=[{normalized_name: "bumps", anatomical_location: "face", severity: "mild"}], duration={value: "2 months", onset_type: "chronic"}, frequency="daily", triggers=["stress"], patient_context={age: 25, gender: "female"}, clinical_interpretation={intent: "diagnosis", red_flags: []}
- **THEN** `representation_text` SHALL be approximately: `"Acne patient. Symptoms: mild bumps on face. Duration: 2 months (chronic onset). Frequency: daily. Triggers: stress. Patient: 25 year old female. Seeking diagnosis. Original query: [original_text]"`

#### Scenario: Representation with partial parameters (non-enriched)
- **WHEN** a query has label="diabetes", symptoms=[{normalized_name: "fatigue"}, {normalized_name: "increased thirst"}], duration={value: "3 weeks"}, patient_context=null, clinical_interpretation=null
- **THEN** `representation_text` SHALL include only available sections: `"Diabetes patient. Symptoms: fatigue, increased thirst. Duration: 3 weeks. Original query: [original_text]"` (patient context and clinical interpretation sections omitted)

#### Scenario: Representation handles empty/null symptom fields
- **WHEN** a symptom has `anatomical_location = ""` and `severity = ""`
- **THEN** the representation SHALL include only the symptom name without location or severity qualifiers

### Requirement: Skip duplicates on re-load
The query loader SHALL use a hash of `original_text` (per source) to detect duplicates and skip them on re-runs.

#### Scenario: Re-run after partial load
- **WHEN** the loader previously loaded 5,000 queries before interruption
- **THEN** on re-run, those 5,000 SHALL be skipped (via `UNIQUE(source_id, text_hash)`) and only the remaining queries SHALL be inserted

### Requirement: Summary logging
The query loader SHALL log: total queries loaded, queries skipped (duplicates), count per disease label, and a sample representation text for verification.

#### Scenario: Log summary after loading
- **WHEN** all queries are loaded
- **THEN** the log SHALL include e.g. `"Loaded 9061 queries (0 skipped). Labels: acne=523, diabetes=412, ..."` and print one sample representation text

### Requirement: Pipeline SHALL fail when query loading fails
The pipeline SHALL raise an error and stop execution if the JSONL input file does not exist or if zero valid queries are loaded from the file.

#### Scenario: JSONL file does not exist
- **WHEN** the pipeline runs with a `--jsonl-path` pointing to a non-existent file
- **THEN** `load_queries()` SHALL raise `FileNotFoundError` and the pipeline SHALL log the error and terminate before Stage 1

#### Scenario: JSONL file yields zero valid queries
- **WHEN** the JSONL file exists but contains no parseable queries (empty file, all invalid JSON, or all missing `original_text`)
- **THEN** `load_queries()` SHALL raise `ValueError` with a message indicating zero queries were loaded, and the pipeline SHALL terminate before Stage 1
