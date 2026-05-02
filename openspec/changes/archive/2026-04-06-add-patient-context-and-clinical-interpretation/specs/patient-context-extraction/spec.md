## ADDED Requirements

### Requirement: Extract patient age from description
The system SHALL extract the patient's numeric age from the description text when explicitly stated or clearly inferable (e.g., "30-year-old", "I'm 45").

#### Scenario: Explicit age mentioned
- **WHEN** the patient text contains "I am a 30 year old male"
- **THEN** the system SHALL return `age: 30`

#### Scenario: No age mentioned
- **WHEN** the patient text contains no age information
- **THEN** the system SHALL return `age: null`

### Requirement: Classify patient age group
The system SHALL classify the patient into an age group (infant / child / adolescent / adult / elderly) when exact age is unavailable but age range is inferable from context.

#### Scenario: Age group inferred from context
- **WHEN** the patient text contains "my toddler has been" with no numeric age
- **THEN** the system SHALL return `age_group: "child"` and `age: null`

#### Scenario: Age group derived from exact age
- **WHEN** the patient text contains an explicit age
- **THEN** the system SHALL also populate `age_group` based on the age value

### Requirement: Extract patient gender
The system SHALL extract the patient's gender from the description text. Valid values: male, female, other, unknown.

#### Scenario: Gender explicitly stated
- **WHEN** the patient text contains "I'm a 25 year old female"
- **THEN** the system SHALL return `gender: "female"`

#### Scenario: Gender not mentioned
- **WHEN** the patient text contains no gender indicators
- **THEN** the system SHALL return `gender: null`

### Requirement: Extract patient comorbidities
The system SHALL extract pre-existing diagnosed medical conditions mentioned in the patient text. Comorbidities are conditions the patient already has, not the symptoms they are currently describing.

#### Scenario: Comorbidities mentioned
- **WHEN** the patient text contains "I have diabetes and high blood pressure, and now I'm getting headaches"
- **THEN** the system SHALL return `comorbidities: ["diabetes", "hypertension"]` and SHALL NOT include "headaches" as a comorbidity

#### Scenario: No comorbidities mentioned
- **WHEN** the patient text contains no pre-existing conditions
- **THEN** the system SHALL return `comorbidities: []`

#### Scenario: Distinguish comorbidities from symptoms
- **WHEN** the patient text describes a condition as the reason for the consultation (e.g., "I think I have diabetes")
- **THEN** the system SHALL NOT include it as a comorbidity since it is not a confirmed pre-existing condition

### Requirement: Retain pregnancy status
The system SHALL extract pregnancy status from the patient text when mentioned. Valid values: pregnant, not_pregnant, postpartum, null.

#### Scenario: Pregnancy mentioned
- **WHEN** the patient text contains "I am 6 months pregnant and having back pain"
- **THEN** the system SHALL return `pregnancy_status: "pregnant"`

#### Scenario: No pregnancy context
- **WHEN** the patient text contains no pregnancy-related information
- **THEN** the system SHALL return `pregnancy_status: null`

### Requirement: Patient context uses only explicit information
The system SHALL extract patient context only from information explicitly stated or clearly implied in the patient text. The system SHALL NOT infer demographics not supported by the text.

#### Scenario: Minimal text with no demographics
- **WHEN** the patient text contains "I have a terrible headache"
- **THEN** the system SHALL return all patient context fields as null or empty

### Requirement: Patient context output follows schema
The system SHALL return patient context as a JSON object matching the PatientContext Pydantic model with fields: age, age_group, gender, pregnancy_status, comorbidities.

#### Scenario: Complete patient context extraction
- **WHEN** the patient text is processed through the patient context stage
- **THEN** the output SHALL be a valid JSON object conforming to the PatientContext schema

### Requirement: Patient context integrated into pipeline as Stage 3
The patient context extraction SHALL execute after temporal extraction (Stage 2) and before clinical interpretation (Stage 4) in the pipeline. It SHALL receive only the raw patient text as input.

#### Scenario: Pipeline executes Stage 3
- **WHEN** the extraction pipeline processes a patient description
- **THEN** the pipeline SHALL call the patient context extractor after temporal extraction and store the result under the `patient_context` key

### Requirement: Backward compatibility for patient context
The `patient_context` field in `StructuredQuery` SHALL be Optional with a default of None so that existing JSONL records without this field remain valid.

#### Scenario: Old record without patient context
- **WHEN** an existing JSONL record without `patient_context` is validated against `StructuredQuery`
- **THEN** validation SHALL pass with `patient_context` defaulting to None
