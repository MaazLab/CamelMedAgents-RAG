# extraction_pipeline.py

import logging
from llm.structured_extractor import StructuredExtractor
from processors.postprocessing import apply_red_flag_guard

logger = logging.getLogger(__name__)


class ExtractionPipeline:

    def __init__(self):
        self.extractor = StructuredExtractor()

    def process(self, text, label, category):
        logger.info("▶ Starting ExtractionPipeline.process()")

        # Step 1: LLM Extraction
        logger.info("   → Executing StructuredExtractor")
        structured = self.extractor.extract(text)

        # Step 2: Attach metadata
        logger.info("   → Attaching metadata")
        structured["original_text"] = text
        structured["label"] = label
        structured["category"] = category

        # Step 3: Postprocessing
        logger.info("   → Executing Postprocessing")
        structured = apply_red_flag_guard(structured)        

        logger.info("✔ Finished processing query")

        return structured