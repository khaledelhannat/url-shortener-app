"""
Centralized application configuration.

Loads environment variables once and exposes typed settings.
"""

from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

ENABLE_DOCS = (
    os.getenv("ENABLE_DOCS", "true").lower() == "true"
)

SHORT_CODE_LENGTH = int(
    os.getenv("SHORT_CODE_LENGTH", "6")
)