from pathlib import Path
import os


# -- Paths --
BASE_DIR = Path(__file__).resolve().parent   # scrapers/patient_info/
SCRAPERS_DIR = BASE_DIR.parent               # scrapers/

# -- Discourse API --
DISCOURSE_BASE_URL = "https://community.patient.info"
USER_AGENT = "CamelMedAgents-RAG-Scraper/1.0 (research; +https://github.com/camelmedagents)"

RATE_LIMIT_DELAY = 0.3  # seconds between requests
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 2  # exponential: 1s, 2s, 4s
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT = 30  # seconds

# -- Source --
SOURCE_NAME = "patient_info"

# Derive a path-safe source slug from the base URL (strip protocol prefix).
# Used to namespace data and logs per source so future scrapers don't collide.
# "https://community.patient.info" → "community.patient.info"
_SOURCE_SLUG = DISCOURSE_BASE_URL.split("://", 1)[-1]

DATA_DIR = SCRAPERS_DIR / "data" / _SOURCE_SLUG    # scrapers/data/community.patient.info/
LOGS_DIR = SCRAPERS_DIR / "logs" / _SOURCE_SLUG    # scrapers/logs/community.patient.info/
CACHE_DIR = DATA_DIR / "cache"                     # scrapers/data/community.patient.info/cache/

# SQLite is a single shared database for ALL datasources.
# Different sources are segregated at schema level via the `sources` table
# and `source_id` FK on every data table (topics, posts, queries, etc.).
DB_PATH = SCRAPERS_DIR / "data" / "scraper.db"     # scrapers/data/scraper.db (shared)
LOG_FILE = LOGS_DIR / "scraper.log"                # scrapers/logs/community.patient.info/scraper.log

# -- Qdrant --
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")  # Docker server
QDRANT_DOCKER_VOLUME_PATH = str(BASE_DIR.parent / "qdrant_server")  # mount to /qdrant/storage in Docker
QDRANT_COLLECTION_NAME = "queries_relevant_scrape_data"
# Must match the Qdrant server's `service.max_request_size_mb` setting (default: 32).
# The client uses 80 % of this value as its safe upsert budget.
# To raise the limit on the server side, set QDRANT__SERVICE__MAX_REQUEST_SIZE_MB=<value>
# and update this constant to match.
QDRANT_MAX_REQUEST_SIZE_MB: int = int(os.getenv("QDRANT__SERVICE__MAX_REQUEST_SIZE_MB", "32"))

# -- Embedding --
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # alternative: "pritamdeka/S-PubMedBert-MS-MARCO" (768-dim)
EMBEDDING_DIM = 384  # must match model; 768 for S-PubMedBert-MS-MARCO
EMBEDDING_BATCH_SIZE = 64

# -- Semantic Matching --
SIMILARITY_THRESHOLD = 0.5  # minimum cosine similarity to store a mapping
TOP_K_MATCHES = 50  # maximum posts per query

# -- Input data --
JSONL_INPUT_PATH = Path(__file__).resolve().parent.parent.parent / "medical_parameter_extraction_pipeline" / "structured_queries_symptoms_temporal.jsonl"

# -- Logging --
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
