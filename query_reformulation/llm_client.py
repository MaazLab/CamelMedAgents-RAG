# llm_client.py

from openai import OpenAI
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

class OpenRouterClient:

    def __init__(self):
        self.client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL
        )

    def generate_structured(self, model: str, system_prompt: str, user_prompt: str):
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}  # enforce JSON output
        )

        return response.choices[0].message.content