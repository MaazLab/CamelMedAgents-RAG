import json
import logging
from typing import Dict, Any

from llm.client import OpenRouterClient
# from config import QUERY_FORMULATION_MODEL_NAME
from prompts.extraction_prompt import SYSTEM_PROMPT


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

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extract structured medical representation from raw query text.
        Includes retry logic and strict JSON validation.
        """

        for attempt in range(self.max_retries + 1):
            try:
                raw_output = self.client.generate_structured(
                    model=self.model_name,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=text
                )

                structured = self._safe_json_parse(raw_output)

                self._validate_minimum_fields(structured)

                return structured

            except Exception as e:
                logger.warning(
                    f"Extraction attempt {attempt + 1} failed: {str(e)}"
                )

                if attempt == self.max_retries:
                    raise RuntimeError(
                        f"Structured extraction failed after {self.max_retries + 1} attempts"
                    )

        raise RuntimeError("Unexpected extraction failure")

    @staticmethod
    def _safe_json_parse(raw_output: str) -> Dict[str, Any]:
        """
        Ensures LLM output is valid JSON.
        """

        try:
            return json.loads(raw_output)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON returned by LLM: {e}")

    @staticmethod
    def _validate_minimum_fields(structured: Dict[str, Any]):
        """
        Ensures essential fields exist.
        This prevents silent schema corruption.
        """

        required_fields = [
            "symptoms",
            "duration",
            "intent",
            "red_flag",
            "query_complexity_score"
        ]

        for field in required_fields:
            if field not in structured:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(structured["symptoms"], list):
            raise ValueError("Field 'symptoms' must be a list")

        if not isinstance(structured["red_flag"], bool):
            raise ValueError("Field 'red_flag' must be boolean")

        if not isinstance(structured["query_complexity_score"], int):
            raise ValueError("Field 'query_complexity_score' must be integer")