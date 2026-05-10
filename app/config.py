"""
Central configuration module for the application.
All environment variables must live here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Core services
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

REDIS_URL = os.getenv("REDIS_URL")

# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

ENABLE_DOCS = os.getenv("ENABLE_DOCS", "true").lower() == "true"

SHORT_CODE_LENGTH = int(os.getenv("SHORT_CODE_LENGTH", "6"))

# IMPORTANT: missing in your system — this caused the crash
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "3600"))