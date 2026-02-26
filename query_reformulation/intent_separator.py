# intent_separator.py

import json
from query_reformulation.schemas import IntentSeparationOutput
from query_reformulation.llm_client import OpenRouterClient
from config import QUERY_FORMULATION_MODEL_NAME


class IntentSeparator:

    def __init__(self):
        self.llm = OpenRouterClient()

        self.system_prompt = """
You are a medical text preprocessing module.

STRICT OUTPUT RULES:
- cleaned_text must be a string.
- uncertainty must be a boolean (true or false only).
- emotional_context must be a short string or null.

uncertainty = true ONLY if the user explicitly expresses doubt,
concern, fear, or uncertainty.
Otherwise return false.

Do NOT return text inside the uncertainty field.
Do NOT explain anything.
Return strictly valid JSON.
"""

    def process(self, raw_query: str) -> IntentSeparationOutput:

        user_prompt = f"""
Extract cleaned clinical text and uncertainty signals from:

"{raw_query}"

Return JSON with keys:
- cleaned_text
- uncertainty
- emotional_context
"""

        result = self.llm.generate_structured(
            model=QUERY_FORMULATION_MODEL_NAME,
            system_prompt=self.system_prompt,
            user_prompt=user_prompt
        )

        parsed = json.loads(result)
        return IntentSeparationOutput(**parsed)