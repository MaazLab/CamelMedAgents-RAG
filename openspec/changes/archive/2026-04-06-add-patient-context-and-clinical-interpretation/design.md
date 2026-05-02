## Context

The intelligent_scraping pipeline extracts structured medical signals from patient forum descriptions. It currently runs two sequential LLM stages:

1. **Stage 1 — Symptom Extraction**: Extracts symptoms with normalized names, anatomical locations, and severity
2. **Stage 2 — Temporal Extraction**: Extracts duration, frequency, triggers, and per-symptom temporal mappings

The architecture follows a consistent pattern per stage: Pydantic model → system prompt → retry-wrapped extractor method → pipeline orchestration → JSONL output validated against `StructuredQuery`. An unused `Demographics` model already exists in the schema.

The project's own `medical_signal_extraction_steps.md` defines a 4-stage pipeline. Stages 3 (Patient Context) and 4 (Clinical Interpretation) are planned but unimplemented.

## Goals / Non-Goals

**Goals:**
- Add Patient Context extraction (age, age_group, gender, pregnancy_status, comorbidities) as Stage 3
- Add Clinical Interpretation (intent classification, red-flag detection with reasons) as Stage 4
- Follow the exact same architectural patterns as existing stages for consistency
- Maintain backward compatibility with existing JSONL output
- Provide a batch runner for retroactive enrichment of already-processed records

**Non-Goals:**
- Postprocessing or complexity scoring (`apply_red_flag_guard` remains out of scope)
- Prompt optimization or evaluation metrics for the new stages
- Negation detection (e.g., "no history of diabetes")
- Changes to the existing Symptom or Temporal extraction logic
- UI or API integration

## Decisions

### 1. Nest new fields as objects rather than flattening into top-level

New data goes under `patient_context` and `clinical_interpretation` keys in the output, not as top-level fields.

**Rationale:** The schema already has 8+ top-level fields. Flattening would cause naming collisions (e.g., `intent` is generic) and make the schema harder to reason about as it grows. Nesting groups related fields logically.

**Alternative considered:** `structured.update(result)` like temporal does — rejected because temporal's fields (`duration`, `frequency`, `triggers`) are inherently top-level concepts, while demographics and interpretation are cohesive groups.

### 2. Extend existing `Demographics` model → rename to `PatientContext`

Reuse the existing `Demographics` class (already has `age`, `age_group`, `gender`, `pregnancy_status`) and add `comorbidities: List[str]`. Rename the class to `PatientContext`.

**Rationale:** Avoids duplicating an existing model. The user confirmed this approach. `PatientContext` is a more accurate name since it now includes comorbidities.

**Alternative considered:** Create a brand-new `PatientContext` model from scratch — rejected as unnecessary duplication.

### 3. Patient Context takes raw text only; Clinical Interpretation takes text + symptoms

Stage 3 (Patient Context) receives only the patient query — demographics are independent of extracted symptoms. Stage 4 (Clinical Interpretation) receives patient query + extracted symptoms list — intent and red-flag detection benefit from knowing what symptoms were found.

**Rationale:** Matches the dependency chain. Patient context doesn't need symptom data. Clinical interpretation needs symptom context to detect patterns like "chest pain + shortness of breath" as a red flag.

### 4. Red flag as boolean + explainable reasons list

`red_flag: bool` + `red_flag_reasons: List[str]` rather than just a boolean.

**Rationale:** Production medical systems need audit trails. A bare boolean provides no insight into why a case was flagged. The reasons list makes the detection transparent and debuggable.

**Alternative considered:** Boolean only — rejected because it's opaque and hard to evaluate/debug.

### 5. All new StructuredQuery fields are Optional with None default

Ensures existing JSONL records (without the new fields) still pass Pydantic validation.

**Rationale:** The batch runner retroactively enriches existing data. During the transition period, records at different enrichment stages coexist. Optional fields prevent validation failures.

## Risks / Trade-offs

**[Doubled LLM calls per record]** → Each pipeline run now makes 4 LLM calls instead of 2, increasing API cost and latency by ~2x. Mitigation: The two new stages are independent of each other (both depend only on Stage 1 output), so they could be parallelized in a future optimization. Current sequential execution is acceptable for batch processing.

**[Comorbidity vs symptom boundary]** → The LLM may struggle distinguishing between a comorbidity ("I have diabetes") and a symptom ("I have pain"). Mitigation: The patient context prompt explicitly defines comorbidities as pre-existing diagnosed conditions, not current symptoms. Include examples in the prompt to reinforce the boundary.

**[Red flag false positives]** → Overly sensitive red-flag detection could mark too many records as emergencies. Mitigation: The prompt defines a specific list of high-confidence red flag patterns. The `red_flag_reasons` field makes false positives auditable and correctable.

**[Intent classification ambiguity]** → Many patient descriptions contain mixed intents (seeking both diagnosis and treatment). Mitigation: The prompt will classify the primary/dominant intent. Future work could support multiple intents.
