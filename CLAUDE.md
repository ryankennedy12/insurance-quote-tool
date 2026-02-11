# Insurance Quote Comparison Tool

Python tool: PDF quotes → AI structured extraction → comparison → Google Sheets + PDF reports.
Internal tool for a Columbus, Ohio insurance agency. Single agent, 10-30 quotes/day.

## Stack
Python 3.11+, Windows, VS Code. Libraries: google-genai (Gemini 2.5 Flash primary),
openai (GPT-4o-mini fallback), pymupdf4llm, pydantic v2, gspread + gspread-formatting,
fpdf2 (primary PDF output), jinja2, streamlit, python-dotenv, json-repair.

## Commands
- pip install -r requirements.txt
- pytest tests/ -v
- streamlit run app/main.py

## Architecture
See @PROJECT_SPEC.md for full specification.
See @IMPLEMENTATION_PLAN.md for current build progress.

- app/extraction/ — pymupdf4llm + Gemini structured extraction
- app/sheets/ — gspread Google Sheets output
- app/pdf_gen/ — fpdf2 PDF report generation with jinja2 templates
- app/ui/ — Streamlit interface (step-based routing)
- app/utils/ — Config, logging
- tests/ — pytest suite

## Code Style
- Type hints on ALL functions. Pydantic v2 syntax.
- Use python-dotenv + os.getenv() for all secrets. Never hardcode keys.
- All LLM calls: 3 retries with exponential backoff. Gemini primary, GPT-4o-mini fallback.
- Use json-repair on all LLM JSON responses before Pydantic parsing.
- Streamlit: use st.session_state for all persistent data. Script reruns top-to-bottom.
- Use callback-based navigation (on_click=handler) not inline if st.button().

## SDK Notes (CRITICAL)
- google-generativeai is DEPRECATED. Use google-genai package.
- Import: from google import genai; from google.genai import types
- Client: client = genai.Client() (reads GEMINI_API_KEY from env)
- Model string: gemini-2.5-flash (NOT the preview string)
- Pydantic models pass directly to response_schema
- response.parsed returns Pydantic object directly

## CRITICAL RULES
- NEVER read, display, or commit .env files or credential JSON files
- NEVER refactor working code unless explicitly asked
- Run pytest after every implementation change
- fpdf2 is PRIMARY for PDF generation (not WeasyPrint — Windows compatibility)