import json
import logging
from typing import Dict, Any


from pydantic import ValidationError
from llm.client import OpenRouterClient
# from config import QUERY_FORMULATION_MODEL_NAME
from prompts.symptom_extraction import SYMPTOM_EXTRACTION_PROMPT
from prompts.temporal_extraction_prompt import TEMPORAL_EXTRACTION_PROMPT
from prompts.patient_context_prompt import PATIENT_CONTEXT_PROMPT
from prompts.clinical_interpretation_prompt import CLINICAL_INTERPRETATION_PROMPT


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class StructuredExtractor:
    """
    LLM-based medical signal extraction engine.
    Uses OpenRouter client with enforced JSON output.
    """

    def __init__(self, max_retries: int = 2):
        self.client = OpenRouterClient()
        self.model_name = "openai/gpt-4o" #QUERY_FORMULATION_MODEL_NAME
        self.max_retries = max_retries

    def extract_symptoms(self, text: str):

        for attempt in range(self.max_retries + 1):
            try:

                raw_output = self.client.generate_structured(
                    model=self.model_name,
                    system_prompt=SYMPTOM_EXTRACTION_PROMPT,
                    user_prompt=text
                )

                structured = self._safe_json_parse(raw_output)

                return structured

            except Exception as e:
                logger.warning(
                    f"Extraction attempt {attempt + 1} failed: {str(e)}"
                )

                if attempt == self.max_retries:
                    raise RuntimeError(
                        f"Structured extraction failed after {self.max_retries + 1} attempts"
                    )


    def extract_temporal(self, text: str, symptoms: list):

        payload = {
            "patient_query": text,
            "extracted_symptoms": symptoms
        }

        for attempt in range(self.max_retries + 1):
            try:

                raw_output = self.client.generate_structured(
                    model=self.model_name,
                    system_prompt=TEMPORAL_EXTRACTION_PROMPT,
                    user_prompt=json.dumps(payload)
                )

                structured = self._safe_json_parse(raw_output)

                return structured

            except Exception as e:
                logger.warning(
                    f"Temporal extraction attempt {attempt + 1} failed: {str(e)}"
                )

                if attempt == self.max_retries:
                    raise RuntimeError(
                        "Temporal extraction failed"
                    )


    def extract_patient_context(self, text: str):

        for attempt in range(self.max_retries + 1):
            try:

                raw_output = self.client.generate_structured(
                    model=self.model_name,
                    system_prompt=PATIENT_CONTEXT_PROMPT,
                    user_prompt=text
                )

                structured = self._safe_json_parse(raw_output)

                return structured

            except Exception as e:
                logger.warning(
                    f"Patient context extraction attempt {attempt + 1} failed: {str(e)}"
                )

                if attempt == self.max_retries:
                    raise RuntimeError(
                        "Patient context extraction failed"
                    )


    def extract_clinical_interpretation(self, text: str, symptoms: list):

        payload = {
            "patient_query": text,
            "extracted_symptoms": symptoms
        }

        for attempt in range(self.max_retries + 1):
            try:

                raw_output = self.client.generate_structured(
                    model=self.model_name,
                    system_prompt=CLINICAL_INTERPRETATION_PROMPT,
                    user_prompt=json.dumps(payload)
                )

                structured = self._safe_json_parse(raw_output)

                return structured

            except Exception as e:
                logger.warning(
                    f"Clinical interpretation attempt {attempt + 1} failed: {str(e)}"
                )

                if attempt == self.max_retries:
                    raise RuntimeError(
                        "Clinical interpretation extraction failed"
                    )


    @staticmethod
    def _safe_json_parse(raw_output: str) -> Dict[str, Any]:
        """
        Ensures LLM output is valid JSON.
        """

        try:
            return json.loads(raw_output)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON returned by LLM: {e}")