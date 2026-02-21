# symptom_extractor.py

import json
from query_reformulation.schemas import SymptomAttributeOutput
from query_reformulation.llm_client import OpenRouterClient
from config import QUERY_FORMULATION_MODEL_NAME


class SymptomAttributeExtractor:

    def __init__(self):
        self.llm = OpenRouterClient()
        self.system_prompt = """
You are a clinical information extraction module.

STRICT RULES:
- Extract only explicitly mentioned information.
- Do NOT infer diseases.
- Do NOT add assumptions.
- Do NOT rewrite the text globally.
- Normalize symptom terminology using standard clinical phrasing.
- Each symptom must include:
    - original: exact phrase from text
    - normalized: standardized clinical term

Examples:
    "really tired" → {"original": "really tired", "normalized": "fatigue"}
    "chest feels tight" → {"original": "chest feels tight", "normalized": "chest tightness"}

- Severity must be one of: ["mild", "moderate", "severe"]
- If severity not explicitly stated using these words → null.
- Duration must be short phrase (e.g., "2 days", "recent", "3 weeks").
- Trigger should be short normalized phrase (e.g., "climbing stairs", "after eating").
- If something is not mentioned → return null.

Return strictly valid JSON.
"""

    def process(self, cleaned_text: str) -> SymptomAttributeOutput:

        user_prompt = f"""
Extract structured clinical information from:

"{cleaned_text}"

Return JSON with keys:
- symptoms (list of objects with keys: original, normalized)
- duration
- severity
- frequency
- trigger
"""

        result = self.llm.generate_structured(
            model=QUERY_FORMULATION_MODEL_NAME,
            system_prompt=self.system_prompt,
            user_prompt=user_prompt
        )

        parsed = json.loads(result)
        return SymptomAttributeOutput(**parsed)