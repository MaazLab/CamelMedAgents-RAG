# config.py

import os
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

QUERY_FORMULATION_MODEL_NAME = "openai/gpt-4o-mini"  
# You can switch to:
# "openai/gpt-4o"
# "anthropic/claude-3.5-sonnet"
# etc.