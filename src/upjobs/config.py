from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Resolve project root (repo root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_HTML_DIR = DATA_DIR / "raw_html"
PROCESSED_JSON_DIR = DATA_DIR / "processed" / "json"
TEMP_DIR = DATA_DIR / "temp"

SEARCH_URLS_FILE = CONFIG_DIR / "search_urls.yml"
WEBSCRAPBOOK_OPTIONS_FILE = CONFIG_DIR / "webscrapbook.options.20250808.json"


# Load environment
load_dotenv(PROJECT_ROOT / ".env", override=False)


# External services
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# OAuth-based Google auth (no service account)
GOOGLE_OAUTH_CLIENT_FILE = os.getenv(
    "GOOGLE_OAUTH_CLIENT_FILE", str(PROJECT_ROOT / "credentials" / "oauth_client_secret.json")
)
GOOGLE_OAUTH_TOKEN_FILE = os.getenv(
    "GOOGLE_OAUTH_TOKEN_FILE", str(PROJECT_ROOT / "credentials" / "oauth_token.json")
)

WEBSCRAPBOOK_BASE_DIR = os.getenv(
    "WEBSCRAPBOOK_BASE_DIR", os.path.expanduser("~/Downloads/WebScrapBook/Upwork")
)

# AI
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
