"""Application configuration — loads .env and exports constants."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Required ---
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found in .env file. "
        "Get your key at https://aistudio.google.com/apikey"
    )

# --- Optional API keys ---
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "")

# --- Google Sheets credentials ---
# .env.example uses GOOGLE_SERVICE_ACCOUNT_FILE; Python constant keeps the shorter name
GOOGLE_CREDS_PATH: str = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "./secrets/service_account.json"
)

# --- Agency branding ---
AGENCY_NAME: str = os.getenv("AGENCY_NAME", "Your Insurance Agency")
AGENCY_PHONE: str = os.getenv("AGENCY_PHONE", "")
AGENCY_LICENSE: str = os.getenv("AGENCY_LICENSE", "")

# --- App settings ---
MAX_UPLOAD_FILES: int = int(os.getenv("MAX_UPLOAD_FILES", "6"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
