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

Your task:
- Remove conversational filler.
- Preserve only clinically relevant content.
- Detect user uncertainty or concern.
- Do NOT infer diseases.
- Do NOT add new information.
- Do NOT interpret beyond explicit text.

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