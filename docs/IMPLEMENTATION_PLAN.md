# Implementation Plan — Build Order & Verification

> **For Claude Code in VS Code.** Work through phases sequentially. Each step includes what to build, how to verify, and what to do if it fails. Do not skip verification steps.

---

## Phase 1: Foundation (Evening 1)

### Step 1: Project Structure + Dependencies -- COMPLETE (2026-02-10)

**Build:**
- Create the full directory tree from PROJECT_SPEC.md
- Create `requirements.txt` with pinned minimum versions
- Create `.env.example` with all required variables
- Create `.gitignore` excluding: `.env`, `secrets/`, `data/`, `__pycache__/`, `*.pyc`, `.venv/`
- Create empty `__init__.py` in every Python package directory

**Verify:**
```bash
pip install -r requirements.txt
python -c "import streamlit, gspread, pymupdf4llm, google.genai, pydantic, jinja2; print('All imports OK')"
```

**If WeasyPrint fails on Windows:**
Remove `weasyprint` from requirements.txt. The PDF generator will use `fpdf2` fallback. Do NOT block progress on this.

---

### Step 2: Configuration Module -- COMPLETE (2026-02-10)

**Build:** `app/utils/config.py`

**Requirements:**
- Load `.env` using `python-dotenv`
- Export these constants:
  - `GEMINI_API_KEY` (required — print clear error if missing)
  - `OPENAI_API_KEY` (optional — backup model)
  - `GOOGLE_CREDS_PATH` (default: `./secrets/service_account.json`)
  - `SPREADSHEET_ID` (required for Sheets export)
  - `AGENCY_NAME` (default: `"Your Insurance Agency"`)
  - `AGENCY_PHONE` (default: `""`)
  - `AGENCY_LICENSE` (default: `""`)
  - `MAX_UPLOAD_FILES` (default: `6`)
  - `LOG_LEVEL` (default: `"INFO"`)
- Validate at import time: if `GEMINI_API_KEY` is None or empty, raise `ValueError` with message: `"GEMINI_API_KEY not found in .env file. Get your key at https://aistudio.google.com/apikey"`

**Verify:**
```bash
# Create a .env with a dummy key first
echo 'GEMINI_API_KEY=test-key-123' > .env
python -c "from app.utils.config import GEMINI_API_KEY, AGENCY_NAME; print(f'Key: {GEMINI_API_KEY}, Agency: {AGENCY_NAME}')"
# Should print: Key: test-key-123, Agency: Your Insurance Agency
```

---

### Step 3: Logging Configuration -- COMPLETE (2026-02-10)

**Build:** `app/utils/logging_config.py`

**Requirements:**
- Function `setup_logging()` that configures root logger
- `RotatingFileHandler` writing to `data/logs/app.log` (maxBytes=5MB, backupCount=5)
- `StreamHandler` for console output
- Format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
- Auto-create `data/logs/` directory if missing
- Return configured logger

**Verify:**
```bash
python -c "
from app.utils.logging_config import setup_logging
logger = setup_logging()
logger.info('Test log message')
print('Check data/logs/app.log')
"
```

---

## Phase 2: AI Extraction Engine (Evening 2)

### Step 4: Pydantic Data Models -- COMPLETE (2026-02-10)

**Build:** `app/extraction/models.py`

**Requirements:**
- Implement the `InsuranceQuote` model exactly as defined in PROJECT_SPEC.md
- Add a `QuoteExtractionResult` wrapper model:

```python
class QuoteExtractionResult(BaseModel):
    filename: str
    success: bool
    quote: Optional[InsuranceQuote] = None
    error: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
```

**Verify:**
```bash
python -c "
from app.extraction.models import InsuranceQuote
q = InsuranceQuote(
    carrier_name='Erie Insurance',
    policy_type='HO3',
    annual_premium=1200.00,
    deductible=500.0,
    coverage_limits={'dwelling': 300000, 'liability': 100000},
    endorsements=['Water backup'],
    exclusions=[],
    confidence='high'
)
print(q.model_dump_json(indent=2))
"
```

---

### Step 5: PDF Text Extraction -- COMPLETE (2026-02-10)

**Build:** `app/extraction/pdf_parser.py`

**Requirements:**
- Function `extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, bool]`
- Write bytes to a temp file, run `pymupdf4llm.to_markdown()`, delete temp file
- Calculate `is_digital`: average chars per page > 100
- Return `(markdown_text, is_digital)`
- On any exception, log the error and return `("", False)`
- Use `tempfile.NamedTemporaryFile` for the temp file

**Verify:**
```bash
python -c "
from app.extraction.pdf_parser import extract_text_from_pdf
# Test with any PDF you have available
with open('test.pdf', 'rb') as f:
    text, is_digital = extract_text_from_pdf(f.read())
print(f'Digital: {is_digital}, Length: {len(text)} chars')
print(text[:500])
"
```

---

### Step 6: AI Extraction Module -- COMPLETE (2026-02-10)

**Build:** `app/extraction/ai_extractor.py`

**This is the most critical module.** Reference `EXTRACTION_PROMPT.md` for the complete system prompt and carrier hints.

**Requirements:**
- Function `extract_quote_data(pdf_bytes: bytes, filename: str = "") -> InsuranceQuote`
- Step 1: Call `extract_text_from_pdf()` to get markdown text and digital flag
- Step 2: If digital (text path), send markdown as text to Gemini
- Step 3: If not digital (multimodal path), send raw PDF bytes as document to Gemini
- Configure Gemini:
  - Model: `gemini-2.5-flash-preview-05-20`
  - `temperature=0`
  - `response_mime_type="application/json"`
  - `response_schema=InsuranceQuote` (pass Pydantic model for schema enforcement)
- Parse response JSON into `InsuranceQuote`
- If JSON parsing fails, try `json_repair.repair_json()` before raising
- Log: carrier name, confidence level, extraction path (text vs multimodal)
- Set `raw_source` field to `"text"` or `"multimodal"` based on path used

**Error handling:**
- API timeout → raise with clear message
- JSON parse failure after repair → raise with raw response snippet
- Empty/garbled extraction → return InsuranceQuote with confidence="low" and notes explaining the issue

**Verify:**
```bash
python -c "
from app.extraction.ai_extractor import extract_quote_data
with open('sample_quote.pdf', 'rb') as f:
    quote = extract_quote_data(f.read(), 'sample_quote.pdf')
print(quote.model_dump_json(indent=2))
"
# Manually check: carrier name, premium, deductible match the PDF
```

---

### Step 7: Validation Module -- COMPLETE (2026-02-11)

**Build:** `app/extraction/validator.py`

**Requirements:**
- Function `validate_quote(quote: InsuranceQuote) -> tuple[InsuranceQuote, list[str]]`
- Returns the quote unchanged + a list of warning strings
- Validation rules (from PROJECT_SPEC.md):
  - `annual_premium` > 0 and < 50,000
  - `deductible` in [250, 500, 1000, 2500, 5000, 10000] or warn "Non-standard deductible"
  - All `coverage_limits` values > 0
  - `carrier_name` is not empty — this is the only hard error
  - `effective_date` is valid ISO format if present
  - `confidence` in ["high", "medium", "low"] — default to "low" if not
- **Never reject a quote. Only add warnings.**

**Verify:**
```bash
python -c "
from app.extraction.models import InsuranceQuote
from app.extraction.validator import validate_quote
bad = InsuranceQuote(
    carrier_name='Test',
    policy_type='HO3',
    annual_premium=999999,
    deductible=777,
    coverage_limits={'dwelling': -100},
    endorsements=[], exclusions=[],
    confidence='maybe'
)
quote, warnings = validate_quote(bad)
for w in warnings:
    print(f'⚠️  {w}')
# Should produce warnings for premium, deductible, coverage limit, and confidence
"
```

---

## Phase 3: Google Sheets Integration (Evening 3)

### Step 8: Sheets Client

**Build:** `app/sheets/sheets_client.py`

**Prerequisites:** Service account JSON must exist and spreadsheet must be shared with the service account email. A "Template" worksheet must exist in the spreadsheet.

**Requirements:**
- Class `SheetsClient` with `__init__(self)` that authenticates via `gspread.service_account()`
- Method `create_comparison(self, client_name: str, quotes: list[InsuranceQuote]) -> str`
  - Opens spreadsheet by `SPREADSHEET_ID` from config
  - Duplicates "Template" worksheet → `Quote_{client_name}_{YYYY-MM-DD}`
  - If duplicate name exists, append `_2`, `_3`, etc.
  - Builds data grid: carriers as columns, coverage types as rows
  - Row layout:
    - Row 1-2: Headers (from template)
    - Row 3: Carrier names
    - Row 4: Policy type
    - Row 5: Effective date
    - Row 6: Annual premium
    - Row 7: Monthly premium
    - Row 8: Deductible
    - Rows 9+: Coverage limits (dwelling, other structures, personal property, loss of use, liability, medical payments)
    - Next rows: Endorsements (comma-separated)
    - Next rows: Exclusions (comma-separated)
    - Next rows: Discounts (comma-separated)
    - Last data row: Confidence level
  - Uses `new_ws.update(data, 'B3')` for batch write (single API call)
  - Returns the worksheet URL: `f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={new_ws.id}"`
- Error handling for: spreadsheet not found, permission denied, template worksheet missing, API quota exceeded

**Verify:**
```bash
python -c "
from app.sheets.sheets_client import SheetsClient
from app.extraction.models import InsuranceQuote
client = SheetsClient()
quotes = [
    InsuranceQuote(carrier_name='State Farm', policy_type='HO3', annual_premium=1200, deductible=500, coverage_limits={'dwelling': 300000}, endorsements=[], exclusions=[], confidence='high'),
    InsuranceQuote(carrier_name='Erie', policy_type='HO3', annual_premium=1050, deductible=1000, coverage_limits={'dwelling': 300000}, endorsements=[], exclusions=[], confidence='high'),
]
url = client.create_comparison('TestClient', quotes)
print(f'Sheet created: {url}')
"
# Check that a new tab appeared in Google Sheets with correct data
```

---

## Phase 4: PDF Generation (Evening 4)

### Step 9: HTML Template

**Build:** `app/pdf_gen/templates/comparison.html`

**Requirements:**
- Jinja2 template that renders a complete HTML document
- Design per PROJECT_SPEC.md (navy header, green best-value, gray alternating rows)
- Template variables: `agency_name`, `agency_phone`, `agency_license`, `client_name`, `date`, `quotes` (list), `best_premium_index` (int)
- `{% for quote in quotes %}` generates dynamic carrier columns (2–6)
- `@page` CSS rules for Letter size, 0.75" margins, page numbers in footer
- Coverage rows: dwelling, other structures, personal property, loss of use, liability, medical payments, deductible
- Bold premium summary row
- Footer with license number and disclaimer: "This comparison is for informational purposes only. Coverage details should be verified with the carrier."
- All CSS embedded in `<style>` tag (no external stylesheets)

---

### Step 10: PDF Generator

**Build:** `app/pdf_gen/generator.py`

**Requirements:**
- Function `generate_comparison_pdf(quotes: list[InsuranceQuote], client_name: str, output_path: str) -> str`
- Determine `best_premium_index` (index of quote with lowest `annual_premium`)
- Load and render Jinja2 template with quote data + agency info from config
- Try WeasyPrint first: `weasyprint.HTML(string=html).write_pdf(output_path)`
- If WeasyPrint `ImportError`, fall back to FPDF2:
  - Create table with `pdf.table()` context manager
  - Carriers as columns, coverage types as rows
  - Apply basic styling (colors, bold headers)
- Return the `output_path`
- Auto-create output directory if missing

**Verify:**
```bash
python -c "
from app.pdf_gen.generator import generate_comparison_pdf
from app.extraction.models import InsuranceQuote
quotes = [
    InsuranceQuote(carrier_name='State Farm', policy_type='HO3', annual_premium=1200, deductible=500, coverage_limits={'dwelling': 300000, 'personal_property': 150000, 'personal_liability': 100000}, endorsements=['Water backup'], exclusions=[], confidence='high'),
    InsuranceQuote(carrier_name='Erie', policy_type='HO3', annual_premium=1050, deductible=1000, coverage_limits={'dwelling': 300000, 'personal_property': 150000, 'personal_liability': 100000}, endorsements=[], exclusions=[], confidence='high'),
    InsuranceQuote(carrier_name='Progressive', policy_type='HO3', annual_premium=1350, deductible=500, coverage_limits={'dwelling': 300000, 'personal_property': 150000, 'personal_liability': 100000}, endorsements=[], exclusions=[], confidence='medium'),
]
path = generate_comparison_pdf(quotes, 'Smith Family', 'data/outputs/test_comparison.pdf')
print(f'PDF created: {path}')
"
# Open the PDF and visually inspect
```

---

## Phase 5: Web UI (Weekend Session)

### Step 11: Streamlit Application

**Build:** `app/main.py` (can also split into `app/ui/upload_page.py`, `review_page.py`, `output_page.py` and import)

**Requirements:**
- `st.set_page_config(page_title="Quote Comparison Tool", layout="wide")`
- Sidebar: Agency name, tool description, help text
- Client name input (required — disable processing until filled)
- Workflow managed via `st.session_state.workflow_stage`

**Stage: UPLOAD**
- `st.file_uploader(accept_multiple_files=True, type=["pdf"], key="pdf_upload")`
- Limit to `MAX_UPLOAD_FILES`
- "Process Quotes" button (disabled if no files or no client name)
- On click: transition to EXTRACTING

**Stage: EXTRACTING**
- Show `st.progress()` bar updating per file
- Show `st.spinner()` with carrier-aware messages: "Reading quote 2 of 4..."
- Call `extract_quote_data()` for each file in a loop
- Call `validate_quote()` on each result
- Store results in `st.session_state.extracted_quotes` and warnings in `st.session_state.validation_warnings`
- Handle partial failures: "3 of 4 PDFs processed successfully"
- Failed files get a warning message with the error + "Retry" button
- Transition to REVIEW

**Stage: REVIEW**
- Display `st.data_editor` with extracted quote data as an editable DataFrame
- Show validation warnings above the table with `st.warning()`
- Columns: Carrier, Policy Type, Annual Premium, Deductible, Dwelling, Other Structures, Personal Property, Loss of Use, Liability, Medical Payments, Endorsements, Confidence
- Currency formatting for dollar amounts
- Highlight lowest premium
- Two buttons: "Save to Google Sheets" and "Generate PDF"
- Both can be clicked independently or sequentially

**Stage: COMPLETE**
- Success message
- Clickable Google Sheets link (if exported)
- `st.download_button` for PDF (if generated)
- "Start New Comparison" button → clears all session state, returns to UPLOAD

**Error UX:**
- Non-technical error messages: "We couldn't read this file clearly — please check the PDF is not password-protected"
- Never show raw stack traces to user
- Log full errors to `data/logs/app.log`

**Verify:**
```bash
streamlit run app/main.py
# Walk through: upload 2-3 PDFs → verify extraction → edit a cell → export to Sheets → download PDF
```

---

## Phase 6: Testing & Hardening (One More Evening)

### Step 12: Test with Real Carrier PDFs

Collect one sample PDF from each carrier: Erie, Progressive, Safeco, Nationwide, Allstate, State Farm, and any others the agency uses.

For each carrier, document:
- ✅ Fields that extract correctly
- ❌ Fields that extract incorrectly
- ⚠️ Fields that are missing

For any extraction errors, add carrier-specific hints to the system prompt in `ai_extractor.py` (see EXTRACTION_PROMPT.md for the hints framework).

### Step 13: Add Logging Throughout

Add to every module:
```python
import logging
logger = logging.getLogger(__name__)
```

Log levels:
- `INFO`: Successful extraction (carrier, confidence), Sheets export, PDF generation
- `WARNING`: Validation issues, non-standard values, fallback to multimodal path
- `ERROR`: Extraction failures, API errors, file I/O errors

---

## Phase 7: Deployment (Final Session)

### Step 14: Local Deployment (Free)

**Build:** `run.bat`
```batch
@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
streamlit run app/main.py --server.port 8501
```

Create a desktop shortcut pointing to `run.bat`.

### Step 15: Cloud Deployment (Optional, $7/month on Render)

1. Push code to GitHub (verify `.env` and `secrets/` are NOT committed)
2. Render.com → New Web Service → connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `streamlit run app/main.py --server.port $PORT --server.address 0.0.0.0`
5. Add all `.env` variables in Render dashboard
6. Upload `service_account.json` as a secret file
7. Deploy

**Verify from a different computer/device** — full workflow must complete.

---

## Progress Log

### 2026-02-10 — Phase 1, Step 1: Project Structure + Dependencies

**Status:** COMPLETE

**Created (26 files):**
- Root configs: `.gitignore`, `requirements.txt`, `.env.example`, `run.bat`
- Package inits: `app/pdf_gen/__init__.py`, `app/utils/__init__.py`
- Stub source files: `app/main.py`, `app/pdf_gen/generator.py`, `app/pdf_gen/templates/comparison.html`, `app/utils/config.py`, `app/utils/logging_config.py`, `app/extraction/pdf_parser.py`, `app/extraction/ai_extractor.py`, `app/extraction/validator.py`, `app/extraction/models.py`, `app/sheets/sheets_client.py`, `app/ui/upload_page.py`, `app/ui/review_page.py`, `app/ui/output_page.py`, `tests/test_extraction.py`
- Directory placeholders: `data/uploads/.gitkeep`, `data/outputs/.gitkeep`, `data/logs/.gitkeep`, `assets/.gitkeep`, `tests/fixtures/.gitkeep`, `tests/__init__.py`

**Fixes applied:**
- Renamed `secrets/service_account.json.json` → `service_account.json` (double extension)
- Cleaned up `CLAUDE.md` (removed leftover unclosed code block lines 48-60)
- Initialized git repository

**SDK correction:** `requirements.txt` uses `google-genai>=1.0.0` (not deprecated `google-generativeai`). WeasyPrint commented out; fpdf2 is primary.

**Verification:** `import streamlit, gspread, pymupdf4llm, google.genai, pydantic, jinja2` — All imports OK.

### 2026-02-10 — Phase 1, Step 2: Configuration Module

**Status:** COMPLETE

**Built:** `app/utils/config.py` — loads `.env` via python-dotenv, exports 9 module-level constants.

**Details:**
- `GEMINI_API_KEY` validated at import time; raises `ValueError` if missing/empty
- Env var `GOOGLE_SERVICE_ACCOUNT_FILE` maps to Python constant `GOOGLE_CREDS_PATH` (matched `.env.example` naming)
- `MAX_UPLOAD_FILES` cast to `int`; all others are strings with sensible defaults

**Verification:** `from app.utils.config import GEMINI_API_KEY, AGENCY_NAME` — Key loaded, Agency: Scioto Insurance Group.

### 2026-02-10 — Phase 1, Step 3: Logging Configuration

**Status:** COMPLETE

**Built:** `app/utils/logging_config.py` — `setup_logging()` configures root logger.

**Details:**
- `RotatingFileHandler` → `data/logs/app.log` (5MB max, 5 backups, UTF-8 encoding)
- `StreamHandler` → console output
- Format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
- Auto-creates `data/logs/` directory; guard against duplicate handlers on repeated calls
- Uses `LOG_LEVEL` from config module

**Verification:** `logger.info('Test message')` — written to both console and `data/logs/app.log`.

### 2026-02-10 — Phase 2, Step 4: Pydantic Data Models

**Status:** COMPLETE

**Built:** `app/extraction/models.py` — two Pydantic v2 models.

**Details:**
- `InsuranceQuote`: 15 fields matching PROJECT_SPEC.md exactly, all with `Field(description=...)` for Gemini schema enforcement
- `QuoteExtractionResult`: wrapper with filename, success, optional quote/error, warnings list
- No `Literal` on confidence — validator handles bad values instead of rejecting at parse time

**Verification:** `InsuranceQuote` instantiates and serializes to JSON correctly with `model_dump_json()`.

### 2026-02-10 — Phase 2, Step 5: PDF Text Extraction

**Status:** COMPLETE

**Built:** `app/extraction/pdf_parser.py` — single function `extract_text_from_pdf()`.

**Details:**
- Writes bytes to `tempfile.NamedTemporaryFile`, runs `pymupdf4llm.to_markdown()`, deletes temp file in `finally`
- Uses `fitz.open()` for page count; `is_digital = (chars / pages) > 100`
- On any exception: logs error with traceback, returns `("", False)`

**Verification:** Invalid bytes test returns `("", False)` cleanly with logged traceback.

### 2026-02-10 — Phase 2, Step 6: AI Extraction Module

**Status:** COMPLETE

**Built:** `app/extraction/ai_extractor.py` — Gemini 2.5 Flash extraction via `google-genai` SDK.

**Details:**
- Uses correct SDK: `from google import genai`, `client = genai.Client(api_key=...)`, `client.models.generate_content()`
- Model string: `gemini-2.5-flash` (per CLAUDE.md, not the preview string in EXTRACTION_PROMPT.md)
- `SYSTEM_PROMPT` verbatim from EXTRACTION_PROMPT.md with `{carrier_hints}` placeholder
- `CARRIER_HINTS` dict: 8 carriers (erie, state farm, progressive, safeco, nationwide, allstate, westfield, grange) + default
- `response_schema=InsuranceQuote` passed directly; `response.parsed` returns Pydantic object
- Fallback: `_parse_response()` with `json-repair` if `.parsed` is None
- `tenacity` added to requirements.txt: `@retry(stop=3, wait=exponential(min=2, max=10))`
- Text path (`_call_gemini_text`) and multimodal path (`_call_gemini_multimodal` via `client.files.upload()`)
- `extract_and_validate()` wired up with lazy import of `validate_quote` (Step 7)

**Deferred to Phase 6:**
- OpenAI GPT-4o-mini backup
- Two-phase carrier identification

**Verification:** Module imports successfully; `CARRIER_HINTS` has 9 keys; `get_carrier_hints("Erie Insurance")` matches erie entry.

### 2026-02-11 — Phase 2, Step 7: Validation Module

**Status:** COMPLETE

**Built:** `app/extraction/validator.py` — single function `validate_quote()` with 5 validation rules.

**Details:**
- `validate_quote(quote) -> tuple[InsuranceQuote, list[str]]` — never rejects, only adds warnings
- Rule 1: `carrier_name` not empty/whitespace
- Rule 2: `annual_premium` > 0 and < 50,000
- Rule 3: `deductible` in standard set [250, 500, 1000, 2500, 5000, 10000] or warn "Non-standard deductible"
- Rule 4: All `coverage_limits` values > 0
- Rule 5: `effective_date` valid ISO format if present
- Rule 6: `confidence` in ["high", "medium", "low"] — auto-corrects invalid values to "low" via `model_copy(update=...)`
- Logging: WARNING for quotes with issues, INFO for clean quotes

**Verification:** Bad-data test produced 4 expected warnings (premium, deductible, coverage limit, confidence). Confidence corrected from "maybe" to "low".

### 2026-02-11 — Pre-Phase 3: SPEC_UPDATE.md Model Updates

**Status:** COMPLETE

**Context:** `docs/SPEC_UPDATE.md` introduced multi-policy bundled quotes and current-policy baseline columns. Models and validator updated before starting Phase 3 (Sheets).

**Updated:** `app/extraction/models.py`
- `InsuranceQuote.coverage_limits`: `dict[str, float]` → `dict[str, float | str]` (supports text values like "ALS" / Actual Loss Sustained)
- Added `CarrierBundle` — groups home/auto/umbrella `InsuranceQuote`s per carrier, with `total_premium` and `policy_types_present` properties
- Added `CurrentPolicy` — customer's existing coverage baseline (15 optional home/auto/umbrella fields, `total_premium` property)
- Added `ComparisonSession` — top-level container: `client_name`, `date`, optional `CurrentPolicy`, list of `CarrierBundle`, `sections_included`

**Updated:** `app/extraction/validator.py`
- Coverage limits validation now uses `isinstance(value, (int, float))` guard — string values like "ALS" skip the positivity check

**Verification:** `InsuranceQuote` with `coverage_limits={'dwelling': 300000, 'loss_of_use': 'ALS'}` serializes correctly and produces zero validation warnings. `CarrierBundle.total_premium` and `CurrentPolicy.total_premium` sum correctly. `ComparisonSession` wires all models together.

### 2026-02-11 — Phase 3, Step 8: Google Sheets Client

**Status:** COMPLETE

**Built:** `app/sheets/sheets_client.py` — Google Sheets output module with multi-policy bundled layout

**Details:**
- `SheetsClient` class authenticates via `gspread.service_account(filename=GOOGLE_CREDS_PATH)`
- `create_comparison(session: ComparisonSession) -> str` transforms session into 25-row fixed template layout
- Fixed row structure (rows 1-25): Header (1-3), Premium Summary (4-7), Home Details (9-15), Auto Details (17-21), Umbrella Details (23-25)
- Column mapping: A = row labels, B = Current Policy, C-H = up to 6 CarrierBundles
- Data grid: 22 rows x 7 columns (rows 4-25, columns B-H), written via single batch update at B4
- **Value formatting:** Raw numeric values (floats/ints) for currency and coverage limits — Google Sheets template formatting handles display. Strings only for text values ("ALS"), compound values ("500/500/250", "1M CSL"), and missing data ("-")
- gspread v6.1+ API verified: `worksheet.update(grid, 'B4')` (values first, then range)
- Worksheet naming: `Quote_{client_name}_{date}` with `_2`, `_3` suffixes for duplicates
- 5 custom exceptions: `SheetsClientError`, `SpreadsheetNotFoundError`, `TemplateNotFoundError`, `PermissionDeniedError`, `QuotaExceededError`
- Helper methods: `_build_premium_row`, `_build_total_row`, `_build_home_section`, `_build_auto_section`, `_build_umbrella_section`
- Special formatting methods: `_get_auto_limits` (constructs "500/500/250" or "1M CSL"), `_get_umbrella_limits`
- Conditional section population: Only writes data if section in `sections_included`, otherwise leaves blank

**Verification:** `from app.sheets.sheets_client import SheetsClient, TemplateNotFoundError, SpreadsheetNotFoundError; print('Sheets client imports OK')` — All imports successful.
