from pathlib import Path
import os

# -- Paths --
BASE_DIR = Path(__file__).resolve().parent       # scrapers/healthboards/
SCRAPERS_DIR = BASE_DIR.parent                   # scrapers/

# -- HealthBoards site --
BASE_URL = "https://www.healthboards.com"
SOURCE_NAME = "healthboards"

_SOURCE_SLUG = BASE_URL.split("://", 1)[-1]     # "www.healthboards.com"

DATA_DIR = SCRAPERS_DIR / "data" / _SOURCE_SLUG  # scrapers/data/www.healthboards.com/
LOGS_DIR = SCRAPERS_DIR / "logs" / _SOURCE_SLUG  # scrapers/logs/www.healthboards.com/
CACHE_DIR = DATA_DIR / "cache"                   # scrapers/data/www.healthboards.com/cache/
LOG_FILE = LOGS_DIR / "scraper.log"              # scrapers/logs/www.healthboards.com/scraper.log

# SQLite database — shared with all scrapers, segregated by source_id.
DB_PATH = SCRAPERS_DIR / "data" / "scraper.db"

# -- Patchright / Browser --
# Per official Patchright best practice: use launch_persistent_context with
# channel="chrome", headless=False, no_viewport=True, and NO custom user-agent
# or viewport injection. See: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python
HEADLESS = False  # headed mode is far more reliable against Cloudflare
BROWSER_CHANNEL = "chrome"  # use real Google Chrome, not Chromium
BROWSER_TIMEOUT = 90_000  # page load timeout in ms
# Persistent user data dir preserves cf_clearance cookies across runs
USER_DATA_DIR = str(DATA_DIR / "chrome_profile")

# -- Rate limiting & retry --
RATE_LIMIT_DELAY = 3.0  # seconds between page navigations
REQUEST_TIMEOUT = 90     # seconds
RETRY_MAX_ATTEMPTS = 5
RETRY_BACKOFF_FACTOR = 2  # exponential: 2s, 4s, 8s, 16s, 32s

# -- Cloudflare handling --
CF_CHALLENGE_WAIT = 45          # seconds to wait for a single CF challenge
CF_CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive CF failures to trigger cooldown
CF_CIRCUIT_BREAKER_COOLDOWN = 120  # seconds to wait when circuit breaker trips
CF_WARMUP_URL = BASE_URL + "/"  # landing page for cookie warmup

# -- Qdrant --
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION_NAME = "queries_relevant_scrape_data"
QDRANT_MAX_REQUEST_SIZE_MB: int = int(os.getenv("QDRANT__SERVICE__MAX_REQUEST_SIZE_MB", "32"))

# -- Embedding --
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
EMBEDDING_BATCH_SIZE = 64

# -- Semantic Matching --
SIMILARITY_THRESHOLD = 0.5
TOP_K_MATCHES = 50

# -- Input data --
JSONL_INPUT_PATH = Path(__file__).resolve().parent.parent.parent / "medical_parameter_extraction_pipeline" / "structured_queries_symptoms_temporal.jsonl"

# -- Logging --
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
