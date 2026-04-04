# extraction_pipeline.py

import logging
from llm.structured_extractor import StructuredExtractor
# from processors.postprocessing import apply_red_flag_guard

logger = logging.getLogger(__name__)


class ExtractionPipeline:

    def __init__(self):
        self.extractor = StructuredExtractor()

    def process(self, text, label, category):
        logger.info("▶ Starting ExtractionPipeline.process()")

        # Step 1: Symptom Extraction
        logger.info("   → Executing StructuredExtractor")
        structured = self.extractor.extract_symptoms(text)
        
        # Step 2: Temporal Extraction
        temporal = self.extractor.extract_temporal(
            text=text,
            symptoms=structured["symptoms"]
        )
        
        structured.update(temporal)

        # Step 3: Patient Context Extraction
        logger.info("   → Executing Patient Context Extraction")
        patient_context = self.extractor.extract_patient_context(text=text)
        structured["patient_context"] = patient_context

        # Step 4: Clinical Interpretation
        logger.info("   → Executing Clinical Interpretation")
        clinical = self.extractor.extract_clinical_interpretation(
            text=text,
            symptoms=structured["symptoms"]
        )
        structured["clinical_interpretation"] = clinical

        # Step 5: Attach metadata
        logger.info("   → Attaching metadata")
        structured["original_text"] = text
        structured["label"] = label
        structured["category"] = category

        # Step 6: Postprocessing
        logger.info("   → Executing Postprocessing")
        # structured = apply_red_flag_guard(structured)        

        logger.info("✔ Finished processing query")

        return structured