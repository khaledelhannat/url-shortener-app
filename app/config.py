"""
Central configuration module.
Single source of truth for environment variables.
Fail-fast design: app must crash early if config is invalid.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _get_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).lower() == "true"


# ---------------------------------------------------------------------------
# Core services (REQUIRED)
# ---------------------------------------------------------------------------

DATABASE_URL = _require("DATABASE_URL")
REDIS_URL = _require("REDIS_URL")


# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENABLE_DOCS = _get_bool("ENABLE_DOCS", "true")

SHORT_CODE_LENGTH = int(os.getenv("SHORT_CODE_LENGTH", "6"))
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "3600"))