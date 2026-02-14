"""Application configuration — loads .env and exports constants."""

import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Streamlit secrets fallback ---
try:
    import streamlit as _st
    _secrets = dict(_st.secrets)
except Exception:
    _secrets = {}

# --- Required ---
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "") or _secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found in .env or st.secrets. "
        "Get your key at https://aistudio.google.com/apikey"
    )

# --- Optional API keys ---
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY") or _secrets.get("OPENAI_API_KEY")
SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "") or _secrets.get("SPREADSHEET_ID", "")

# --- Google Sheets credentials ---
GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "./secrets/service_account.json"
)
if not Path(GOOGLE_SERVICE_ACCOUNT_FILE).exists():
    _sa_json = _secrets.get("GOOGLE_SERVICE_ACCOUNT")
    if _sa_json:
        _tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        if isinstance(_sa_json, str):
            _tmp.write(_sa_json)
        else:
            json.dump(dict(_sa_json), _tmp)
        _tmp.close()
        GOOGLE_SERVICE_ACCOUNT_FILE = _tmp.name

LOGO_DRIVE_FILE_ID: str = os.getenv("LOGO_DRIVE_FILE_ID", "") or _secrets.get("LOGO_DRIVE_FILE_ID", "")

# --- Agency branding ---
AGENCY_NAME: str = os.getenv("AGENCY_NAME", "Your Insurance Agency")
AGENCY_PHONE: str = os.getenv("AGENCY_PHONE", "")
AGENCY_LICENSE: str = os.getenv("AGENCY_LICENSE", "")

# --- App settings ---
MAX_UPLOAD_FILES: int = int(os.getenv("MAX_UPLOAD_FILES", "6"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
