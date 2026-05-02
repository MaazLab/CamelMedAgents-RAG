## Why

The intelligent_scraping extraction pipeline currently performs only 2 stages: Symptom Extraction and Temporal Extraction. The project's own architecture document (`medical_signal_extraction_steps.md`) defines a 4-stage pipeline, with Stage 3 (Patient Context) and Stage 4 (Clinical Interpretation) still unimplemented. Without patient demographics and clinical intent, the downstream retrieval system cannot filter by age/gender/comorbidities or prioritize emergency cases — both critical for production-grade medical information retrieval.

## What Changes

- Extend the existing `Demographics` Pydantic model with `comorbidities` and rename it to `PatientContext`
- Add a new `ClinicalInterpretation` Pydantic model with `intent`, `red_flag`, and `red_flag_reasons` fields
- Update `StructuredQuery` to include the two new nested objects as Optional fields (backward-compatible)
- Create two new LLM system prompts: patient context extraction and clinical interpretation
- Add two new extractor methods to `StructuredExtractor` following the existing retry-and-parse pattern
- Wire Stage 3 and Stage 4 into `ExtractionPipeline.process()` after the existing temporal step
- Create a batch runner script for retroactive enrichment of existing JSONL data

## Capabilities

### New Capabilities
- `patient-context-extraction`: Extracts patient demographics (age, age_group, gender, pregnancy_status) and comorbidities from patient description text via LLM
- `clinical-interpretation`: Classifies patient intent (diagnosis / treatment / reassurance / emergency / prognosis) and detects red-flag emergency indicators with explainable reasons from patient text + extracted symptoms

### Modified Capabilities

## Impact

- `intelligent_scraping/medical_schema.py` — Schema changes (extend Demographics → PatientContext, add ClinicalInterpretation, update StructuredQuery)
- `intelligent_scraping/llm/structured_extractor.py` — Two new extractor methods + prompt imports
- `intelligent_scraping/extraction_pipeline.py` — Two new pipeline stages in process()
- `intelligent_scraping/prompts/` — Two new prompt files
- `intelligent_scraping/run_context_interpretation_extraction.py` — New batch runner script
- Output JSONL schema grows with two new nested objects; existing records remain valid (Optional fields)
- Each pipeline run now makes 4 LLM calls per record instead of 2 (increased API cost and latency)
