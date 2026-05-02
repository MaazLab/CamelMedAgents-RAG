## 1. Schema Layer

- [x] 1.1 Rename `Demographics` to `PatientContext` in `intelligent_scraping/medical_schema.py` and add `comorbidities: List[str] = Field(default_factory=list)`
- [x] 1.2 Add `ClinicalInterpretation` Pydantic model with `intent: Optional[str]`, `red_flag: bool = False`, `red_flag_reasons: List[str] = Field(default_factory=list)`
- [x] 1.3 Update `StructuredQuery` — add `patient_context: Optional[PatientContext] = None` and `clinical_interpretation: Optional[ClinicalInterpretation] = None`; remove old commented-out fields (`demographics`, `intent`, `red_flag`, `comorbidities`)

## 2. Prompt Engineering

- [x] 2.1 Create `intelligent_scraping/prompts/patient_context_prompt.py` with system prompt for extracting age, age_group, gender, pregnancy_status, comorbidities from raw patient text
- [x] 2.2 Create `intelligent_scraping/prompts/clinical_interpretation_prompt.py` with system prompt for intent classification (diagnosis/treatment/reassurance/emergency/prognosis) and red-flag detection with reasons, accepting patient query + extracted symptoms

## 3. Extractor Methods

- [x] 3.1 Add `extract_patient_context(text: str)` method to `StructuredExtractor` in `intelligent_scraping/llm/structured_extractor.py` — import prompt, retry loop, generate_structured, _safe_json_parse
- [x] 3.2 Add `extract_clinical_interpretation(text: str, symptoms: list)` method to `StructuredExtractor` — same retry pattern, payload as `{"patient_query": text, "extracted_symptoms": symptoms}`

## 4. Pipeline Orchestration

- [x] 4.1 Add Stage 3 (patient context) call in `ExtractionPipeline.process()` after temporal extraction — store result under `structured["patient_context"]`
- [x] 4.2 Add Stage 4 (clinical interpretation) call in `ExtractionPipeline.process()` after patient context — store result under `structured["clinical_interpretation"]`

## 5. Batch Runner for Retroactive Enrichment

- [x] 5.1 Create `intelligent_scraping/run_context_interpretation_extraction.py` — reads `structured_queries_symptoms_temporal.jsonl`, extracts patient context + clinical interpretation per record, writes to `structured_queries_symptoms_temporal_enriched.jsonl` with deduplication via `original_text`

## 6. Verification

- [x] 6.1 Validate backward compatibility — confirm existing JSONL records without new fields pass `StructuredQuery` validation
- [x] 6.2 Run pipeline on 2-3 sample patient descriptions and verify output contains correctly structured `patient_context` and `clinical_interpretation` fields
