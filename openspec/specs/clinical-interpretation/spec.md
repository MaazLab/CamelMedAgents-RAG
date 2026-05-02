# clinical-interpretation Specification

## Purpose
TBD - created by archiving change add-patient-context-and-clinical-interpretation. Update Purpose after archive.
## Requirements
### Requirement: Classify patient intent
The system SHALL classify the primary intent of the patient query into one of: diagnosis, treatment, reassurance, emergency, prognosis.

#### Scenario: Diagnosis intent
- **WHEN** the patient text contains "What could be causing my chest pain and dizziness?"
- **THEN** the system SHALL return `intent: "diagnosis"`

#### Scenario: Treatment intent
- **WHEN** the patient text contains "What medication should I take for my migraines?"
- **THEN** the system SHALL return `intent: "treatment"`

#### Scenario: Reassurance intent
- **WHEN** the patient text contains "I have a small bump on my arm, is this something to worry about?"
- **THEN** the system SHALL return `intent: "reassurance"`

#### Scenario: Emergency intent
- **WHEN** the patient text describes an acute dangerous situation such as "I'm having crushing chest pain and can't breathe"
- **THEN** the system SHALL return `intent: "emergency"`

#### Scenario: Prognosis intent
- **WHEN** the patient text contains "Will my condition get worse over time?"
- **THEN** the system SHALL return `intent: "prognosis"`

### Requirement: Detect red-flag emergency indicators
The system SHALL detect red-flag emergency patterns in the patient description and set `red_flag: true` when any are present. Red-flag patterns include but are not limited to: chest pain with shortness of breath, sudden severe headache, loss of consciousness, suicidal ideation, signs of stroke (facial drooping, slurred speech, sudden one-sided weakness), and severe uncontrolled bleeding.

#### Scenario: Red flag detected
- **WHEN** the patient text contains "I have severe chest pain and I can't breathe"
- **THEN** the system SHALL return `red_flag: true`

#### Scenario: No red flag
- **WHEN** the patient text contains "I've had mild acne for a few weeks"
- **THEN** the system SHALL return `red_flag: false`

### Requirement: Provide explainable red-flag reasons
When `red_flag` is true, the system SHALL populate `red_flag_reasons` with a list of specific reasons explaining why the case was flagged. Each reason SHALL describe the pattern detected.

#### Scenario: Red flag with reasons
- **WHEN** the patient text triggers a red flag due to "chest pain and shortness of breath"
- **THEN** the system SHALL return `red_flag_reasons: ["chest pain combined with shortness of breath — possible cardiac emergency"]`

#### Scenario: No red flag means empty reasons
- **WHEN** `red_flag` is false
- **THEN** the system SHALL return `red_flag_reasons: []`

### Requirement: Clinical interpretation receives symptoms context
The clinical interpretation stage SHALL receive both the raw patient text and the list of previously extracted symptoms as input. This allows the LLM to detect red-flag patterns based on symptom combinations.

#### Scenario: Symptoms passed to clinical interpretation
- **WHEN** the pipeline has extracted symptoms in Stage 1 (e.g., ["chest pain", "shortness of breath"])
- **THEN** the clinical interpretation stage SHALL receive these symptoms alongside the patient text

### Requirement: Clinical interpretation output follows schema
The system SHALL return clinical interpretation as a JSON object matching the ClinicalInterpretation Pydantic model with fields: intent, red_flag, red_flag_reasons.

#### Scenario: Valid clinical interpretation output
- **WHEN** the patient text is processed through the clinical interpretation stage
- **THEN** the output SHALL be a valid JSON object conforming to the ClinicalInterpretation schema

### Requirement: Clinical interpretation integrated into pipeline as Stage 4
The clinical interpretation extraction SHALL execute after patient context extraction (Stage 3) in the pipeline. The result SHALL be stored under the `clinical_interpretation` key in the output.

#### Scenario: Pipeline executes Stage 4
- **WHEN** the extraction pipeline processes a patient description
- **THEN** the pipeline SHALL call the clinical interpretation extractor after patient context extraction and store the result under the `clinical_interpretation` key

### Requirement: Backward compatibility for clinical interpretation
The `clinical_interpretation` field in `StructuredQuery` SHALL be Optional with a default of None so that existing JSONL records without this field remain valid.

#### Scenario: Old record without clinical interpretation
- **WHEN** an existing JSONL record without `clinical_interpretation` is validated against `StructuredQuery`
- **THEN** validation SHALL pass with `clinical_interpretation` defaulting to None

### Requirement: Retroactive enrichment of existing records
A batch runner script SHALL read existing JSONL output, extract patient context and clinical interpretation for each record, and write enriched records to a new JSONL file. It SHALL skip records already processed using the same deduplication pattern as existing runners.

#### Scenario: Enrich existing JSONL
- **WHEN** the batch runner is executed against `structured_queries_symptoms_temporal.jsonl`
- **THEN** it SHALL produce `structured_queries_symptoms_temporal_enriched.jsonl` with `patient_context` and `clinical_interpretation` fields added to each record

#### Scenario: Skip already enriched records
- **WHEN** a record's `original_text` already exists in the output file
- **THEN** the batch runner SHALL skip that record

