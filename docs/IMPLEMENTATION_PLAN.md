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

### Step 9: HTML Template -- SKIPPED (2026-02-11)

**Status:** SKIPPED — fpdf2 implementation does not require HTML templates

**Rationale:** The PDF generator uses fpdf2 for programmatic PDF generation with full control over layout, fonts, and styling. No Jinja2 HTML templates or WeasyPrint needed.

---

### Step 10: PDF Generator -- COMPLETE (2026-02-11)

**Build:** `app/pdf_gen/generator.py`

**Requirements (Updated per PDF_GEN_SPEC.md):**
- Function `generate_comparison_pdf(session: ComparisonSession, output_path: str, ...) -> str`
- Multi-section layout: Premium Summary → Home Details → Auto Details → Umbrella Details
- Current Policy column with blue-gray styling (not green highlighting)
- Responsive portrait/landscape based on total data columns (current + carriers)
- No "best value" green highlighting or ★ star markers
- Footer: page number + disclaimer only (no license number)
- Two-part notes section: per-carrier AI notes + optional agent notes
- Value formatting: `-` for None, currency strings for numbers, pass-through for text values

**Verify:**
```bash
python -c "from app.pdf_gen.generator import generate_comparison_pdf; print('PDF generator imports OK')"
```

**Verification Result:** ✅ PDF generator imports OK

---

## Phase 5: Web UI (Weekend Session)

### Step 11: Streamlit Wizard Skeleton -- COMPLETE (2026-02-11)

**Build:** `app/ui/streamlit_app.py` (wizard skeleton with session state management)

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

### 2026-02-11 — Phase 4, Steps 9-10: PDF Generator

**Status:** COMPLETE (Step 9 skipped, Step 10 complete)

**Built:** `app/pdf_gen/generator.py` — Branded PDF generator with multi-policy comparison layout

**Details:**
- **Model update:** Added `agent_notes: Optional[str]` field to `ComparisonSession` in `app/extraction/models.py:120`
- **Class:** `SciotoComparisonPDF(FPDF)` — Custom FPDF subclass with Scioto Insurance Group branding
- **Public API:** `generate_comparison_pdf(session: ComparisonSession, output_path, logo_path, date_str, agent_notes) -> str`
- **Brand constants updated:**
  - Primary color: `(135, 28, 48)` — maroon #871c30 (was deep crimson)
  - Removed: `best_value_bg`, `best_value_border` (no green highlighting)
  - Added: `current_bg` (230, 240, 248), `current_header` (180, 200, 220) — light blue-gray for Current Policy column
- **Layout logic:** Dynamic `_get_layout(num_carriers, has_current)` function
  - Total data columns = num_carriers + (1 if has_current else 0)
  - Portrait: 2-5 data columns (responsive font/row scaling)
  - Landscape: 6-7 data columns (tighter fonts for 6+ carriers)
- **Multi-section table structure:**
  - Table header: Label | Current | Carrier 1 | ... | Carrier N
  - Premium Summary section (always shown): Home, Auto, Umbrella, Total rows
  - Home Details section (if "home" in sections_included): 8 rows (Dwelling through Wind/Hail Deductible)
  - Auto Details section (if "auto" in sections_included): 4 rows (Limits, UM/UIM, Comp/Collision Deductibles)
  - Umbrella Details section (if "umbrella" in sections_included): 2 rows (Limits, Deductible)
- **Current Policy column:** Blue-gray background distinguishes baseline from carrier quotes
- **Removed features:**
  - No green "best value" highlighting
  - No ★ star markers
  - No `agency_license` in footer (page number + disclaimer only)
- **Two-part notes section:**
  - Part A: Per-carrier notes from `InsuranceQuote.notes` (AI-generated caveats)
  - Part B: General agent notes from `session.agent_notes` parameter (freeform text)
- **Helper methods (12 new):**
  - Section builders: `_add_table_header`, `_add_premium_section`, `_add_home_section`, `_add_auto_section`, `_add_umbrella_section`, `_add_total_row`
  - Data extractors: `_extract_premium_row`, `_extract_home_row`, `_extract_auto_row`, `_extract_umbrella_row`
  - Value formatters: `_get_auto_limits` (BI/BI/PD or CSL), `_get_umbrella_limits` (XM CSL)
- **Updated helpers:**
  - `_add_section_divider_row`: Now accepts `current_policy` and `carriers` for dynamic column count calculation
  - `_add_data_row`: Removed `best_idx`, added Current column blue-gray styling logic
  - `_fmt_currency`: Returns `"-"` instead of `"—"` for None values (consistency with Sheets client)
  - `add_endorsements_section`: Pulls from `CarrierBundle.home/auto/umbrella`, deduplicates across policies
  - `add_notes_section`: Two-part rendering (carrier notes + agent notes)
- **Preserved from existing code:**
  - `_register_fonts()`: DejaVu with Helvetica fallback (Windows compatible)
  - `_draw_branded_header()`, `_draw_continuation_header()`: Full crimson banner on page 1, slim header on subsequent pages
  - `add_client_section()`: "Prepared for" + date banner with cream background
  - `add_section_title()`: Crimson accent bar with uppercase title
  - `_ensure_space()`, `_space_remaining()`: Auto page breaks before footer zone

**Verification:** `python -c "from app.pdf_gen.generator import generate_comparison_pdf; print('PDF generator imports OK')"` — PDF generator imports OK

**Bug Fix:** Line 343 — Replaced Unicode ellipsis "…" with ASCII "..." for Helvetica/Latin-1 compatibility (Windows encoding issue)

**Visual Testing:**
- Created `tests/test_pdf_visual.py` — Standalone test script that generates 4 sample PDFs with realistic Ohio insurance data
- Test scenarios:
  - `test_2carriers_current.pdf`: 2 carriers + current policy, home only (portrait)
  - `test_3carriers_current.pdf`: 3 carriers + current policy, home + auto (portrait)
  - `test_5carriers_current.pdf`: 5 carriers + current policy, home + auto + umbrella (landscape)
  - `test_3carriers_no_current.pdf`: 3 carriers, no current policy, home + auto, with agent notes
- Uses realistic carriers: Erie Insurance, Westfield, State Farm, Nationwide, Grange Insurance, Progressive
- Includes endorsements, discounts, per-carrier notes, mix of numeric and text coverage values (e.g., "ALS" for Actual Loss Sustained)
- All PDFs output to `data/outputs/` directory

**Logo Asset Creation:**
- Created `scripts/make_logo_transparent.py` — Pillow-based background removal script
- Samples corner pixels to detect maroon background color RGB(120, 34, 39)
- Replaces similar-colored pixels (tolerance=30) with transparency
- Generated `assets/logo_transparent.png` — 90.2% of pixels made transparent
- Visual test suite now uses transparent logo for seamless header integration

### 2026-02-11 — Phase 5, Step 11: Streamlit Wizard Skeleton

**Status:** COMPLETE

**Built:** `app/ui/streamlit_app.py` — Streamlit wizard skeleton with progressive stage unlocking

**Details:**
- **Session state schema:** 17 state keys across 5 categories (wizard navigation, upload data, carrier data, extraction results, review data, export)
- **Three-stage wizard flow:**
  - Step 1 (Upload & Extract): Client name input, sections multiselect, current policy mode radio, placeholder carrier uploads, Extract button
  - Step 2 (Review & Edit): Locked until `extraction_complete == True`, placeholder for editable tables
  - Step 3 (Export): Locked until `review_complete == True`, agent notes textarea, disabled export buttons
- **Progressive unlocking:** Step 2 only renders when extraction complete, Step 3 only renders when review complete
- **Expander-based UI:** Each step is an expandable section with checkmark (✅) when completed
- **Sidebar:** Logo display, session info (client name, carrier count, sections), Reset Session button
- **State management:** Single `init_session_state()` function initializes all 17 keys with defaults
- **Navigation:** Extract button sets `extraction_complete = True` and advances to Step 2; Approve button sets `review_complete = True` and advances to Step 3
- **Reset functionality:** Reset Session button clears all state and returns to Step 1

**Also created:**
- `.streamlit/config.toml` — Scioto maroon theme (#871c30), cream secondary background, 25MB max upload size
- `app/ui/components/__init__.py` — Placeholder for future component modules

**Key patterns:**
- Uses `key=` parameter on all input widgets for automatic session_state binding
- Uses `st.rerun()` for navigation after state changes (not deprecated experimental version)
- All render functions separated: `render_upload_stage()`, `render_review_stage()`, `render_export_stage()`, `render_sidebar()`

**What this step does NOT include:**
- No real PDF extraction logic (placeholder Extract button just flips state)
- No manual entry forms for current policy
- No carrier add/remove dynamic UI
- No editable data tables
- No real export functionality
- Real logic deferred to Steps 12-14

**Verification:** `python app/ui/streamlit_app.py` — All imports OK, script executes without errors (ScriptRunContext warnings expected when running directly)

---

### 2026-02-11 — Phase 5, Step 12: Upload Stage + Extraction Pipeline Fixes

**Status:** COMPLETE

**Modified files:**
- `app/ui/streamlit_app.py` — Upload stage UI with real extraction logic
- `app/extraction/models.py` — `CoverageLimits` sub-model replacing `dict[str, float | str]`
- `app/extraction/ai_extractor.py` — Gemini schema fixes, mkstemp temp files, dict-to-Pydantic conversion
- `app/extraction/pdf_parser.py` — Eliminated temp files (in-memory PDF open)
- `app/extraction/validator.py` — Adapted to CoverageLimits model
- `app/sheets/sheets_client.py` — Dict `.get()` changed to dot notation
- `app/pdf_gen/generator.py` — Dict `.get()` changed to dot notation / `getattr()`
- `tests/test_pdf_visual.py` — Test data updated for CoverageLimits fields

**Upload Stage UI:**
- 7 helpers: `_build_current_policy_from_form/quote()`, `_validate_upload_stage()`, `_add/remove_carrier_callback()`, `_render_current_policy_manual_form/upload()`
- Current Policy: Skip / Enter Manually / Upload Dec Page PDF
- Dynamic Carrier Upload: 2-6 carriers, section-responsive file uploaders
- Extract All: validation, progress bar, non-blocking failures, auto-rerun

**Bug Fix — Windows temp file locking (WinError 32):**
- `pdf_parser.py`: Eliminated temp files. Uses `fitz.open(stream=pdf_bytes, filetype="pdf")` + `pymupdf4llm.to_markdown(doc)` in memory.
- `ai_extractor.py _call_gemini_multimodal()`: `tempfile.mkstemp()` with `os.write()` + `os.close()` before `client.files.upload()`, cleanup in `finally`.

**Bug Fix — Gemini structured output schema compatibility:**
- `CoverageLimits(BaseModel)`: 14 explicit `Optional[float]` fields (6 home, 7 auto incl. `csl`, 1 umbrella). Replaces `dict[str, float | str]` which Gemini cannot enforce.
- `_clean_schema_for_gemini()`: Recursively strips `additionalProperties`, `examples`, `title`, `default` from Pydantic JSON schema before passing to Gemini config.
- Dict-to-Pydantic conversion: `response.parsed` returns `dict` when using dict schema. Both Gemini call functions check `isinstance(response.parsed, dict)` and convert via `InsuranceQuote.model_validate()`.
- All downstream code updated from `.get("key")` to dot notation or `getattr()`.

**Verified:** Erie and Progressive home quotes extracted successfully through Streamlit UI on Windows.

**Next:** Step 13 (Review Stage) per `docs/STREAMLIT_STEP13_SPEC.md`

---

### 2026-02-12 — Phase 5, Step 13: Review & Edit Stage

**Status:** COMPLETE

**Modified files:**
- `app/ui/streamlit_app.py` — Review stage with editable carrier data and current policy forms

**Review Stage UI (6 new helper functions):**
- `_render_coverage_limits_editor(carrier_idx, section, quote)` — Section-specific coverage fields (home: 6 fields, auto: 7 fields, umbrella: 1 field)
- `_render_carrier_editor(idx, bundle)` — Complete carrier editor: premiums, coverage limits, deductibles, endorsements, discounts, notes
- `_build_edited_quote(carrier_idx, section, original)` — Reconstruct InsuranceQuote from session state values
- `_build_edited_bundles()` — Reconstruct list[CarrierBundle] from all edited session state
- `_build_edited_current_policy()` — Reconstruct CurrentPolicy from edited session state
- `render_review_stage()` — Replaced placeholder with full implementation

**UI Features:**
- Extraction warnings displayed at top (expandable, auto-expanded if present)
- Current Policy editor (if exists): editable fields for home/auto/umbrella with 0.0 → None conversion
- Per-carrier editors: one expander per carrier (first expanded by default)
  - Premium inputs for each policy section
  - Coverage limits with section-specific field sets
  - Home deductibles: All-Peril + Wind/Hail
  - Endorsements: Deduplicated across sections, multi-line text area
  - Discounts: Deduplicated across sections, multi-line text area
  - Notes: Combined from all sections with [Section] prefixes
- Approve & Continue button: Builds edited models, stores in session state, advances to Step 3

**Field Name Corrections (actual model fields used):**
- `InsuranceQuote.discounts_applied` (NOT `discounts`)
- `CoverageLimits` auto: `comprehensive`, `collision`, `um_uim` (NOT `comp_deductible`, `collision_deductible`, `um_bi_per_person`, etc.)
- Preserves non-editable fields: `policy_type`, `effective_date`, `expiration_date`, `confidence`, `raw_source`, `exclusions`, `monthly_premium`

**Session State Keys:**
- Current policy: `edit_cp_{field_name}` (e.g., `edit_cp_home_premium`)
- Carrier premiums: `edit_carrier_{idx}_{section}_premium`
- Coverage limits: `edit_carrier_{idx}_{section}_{field}` (e.g., `edit_carrier_0_home_dwelling`)
- Shared text areas: `edit_carrier_{idx}_endorsements`, `edit_carrier_{idx}_discounts`, `edit_carrier_{idx}_notes`

**Data Flow:**
- Step 12 stores: `carrier_bundles`, `current_policy_data`, `extraction_warnings`
- Step 13 works with: Deep copies via session state widgets
- Step 13 stores on Approve: `edited_bundles`, `edited_current_policy`, `review_complete = True`, `current_step = 3`

**Import Updates:**
- Added `CoverageLimits` to imports from `app.extraction.models`

**Verification:** `python -c "from app.ui.streamlit_app import main; print('Streamlit app syntax check passed')"` — All imports successful, syntax valid

**Next:** Step 14 (Export Stage) — PDF generation and Google Sheets export with real functionality

---

### 2026-02-12 — Phase 5, Step 14: Export Stage

**Status:** COMPLETE

**Modified files:**
- `app/ui/streamlit_app.py` — Export stage with real PDF generation and Google Sheets export
- `app/utils/config.py` — Renamed `GOOGLE_CREDS_PATH` → `GOOGLE_SERVICE_ACCOUNT_FILE` (Python constant now matches `.env` variable name)
- `app/sheets/sheets_client.py` — Updated all references from `GOOGLE_CREDS_PATH` to `GOOGLE_SERVICE_ACCOUNT_FILE`

**Export Stage UI (2 new helper functions):**
- `_build_comparison_session()` — Builds `ComparisonSession` from edited data, including required `date` field (ISO format)
- `render_export_stage()` — Replaced placeholder with full implementation

**PDF Generation:**
- "Generate PDF" button → builds `ComparisonSession` → calls `generate_comparison_pdf()` → stores path in session state
- Download button appears after successful generation
- Output path: `data/outputs/{client_name}_comparison_{date}.pdf`
- Logo auto-detected from `assets/logo_transparent.png`

**Google Sheets Export:**
- "Export to Google Sheets" button → builds `ComparisonSession` → calls `SheetsClient().create_comparison()` → stores URL
- Clickable link to Google Sheet appears after successful export
- Graceful error handling if credentials not configured

**Config rename:**
- `.env` variable `GOOGLE_SERVICE_ACCOUNT_FILE` now matches Python constant `GOOGLE_SERVICE_ACCOUNT_FILE` (was previously aliased as `GOOGLE_CREDS_PATH`)
- All 3 references in `sheets_client.py` updated (import, `__init__`, error message)

**Imports added to streamlit_app.py:**
- `datetime`, `logging`, `Path`
- `generate_comparison_pdf` from `app.pdf_gen.generator`
- `SheetsClient` from `app.sheets.sheets_client`

**Verification:** `python -c "from app.ui.streamlit_app import main; print('OK')"` — All imports successful

---

### Phase 5 Summary

**Status:** ALL STEPS COMPLETE (Steps 11-14)

Full Streamlit wizard is working end-to-end: Upload → Extract → Review & Edit → Export (PDF + Google Sheets).

**Pending:** ~~Google Sheets export currently requires a pre-existing "Template" worksheet. Next task is a template-free rewrite of `sheets_client.py` to build sheets programmatically with formatting via `gspread` batch API. See `docs/SHEETS_REWRITE_PLAN.md` for the full plan.~~ **Done — see Phase 6 below.**

---

## Phase 6: Google Sheets Rewrite (2026-02-12)

### Step 16: Template-Free Programmatic Sheets — COMPLETE

**Plan:** `docs/SHEETS_REWRITE_PLAN.md`

**Modified files:**
- `app/sheets/sheets_client.py` — Full rewrite per plan
- `app/utils/config.py` — Added `LOGO_DRIVE_FILE_ID` env var
- `scripts/test_sheets_live.py` — Live smoke test script (new file)

**What was removed:**
- `TemplateNotFoundError` exception class (no template = no template error)
- `WorksheetNotFound` import (no longer caught)
- `_duplicate_template()` method — replaced by `_create_worksheet()`
- `_build_data_grid()` method — replaced by `_build_full_grid()`
- Template dependency: no more "Template" worksheet prerequisite

**What was added:**

**Module-level formatting constants:**
- `MAROON_BG` — `{"red": 0.529, "green": 0.110, "blue": 0.188}` (RGB 135,28,48 / #871c30)
- `WHITE_TEXT` — `{"red": 1.0, "green": 1.0, "blue": 1.0}`
- `LIGHT_GRAY_BG` — `{"red": 0.973, "green": 0.973, "blue": 0.973}` (#f8f8f8)
- `CURRENT_COL_BG` — `{"red": 1.0, "green": 0.973, "blue": 0.941}` (#FFF8F0 light cream)
- `CURRENT_HEADER_BG` — `{"red": 0.961, "green": 0.902, "blue": 0.827}` (#F5E6D3 dark cream)
- `ROW_LABELS` — 25-element list of column A labels (index 0 = row 1)
- `HEADER_ROWS` — `[1, 3, 9, 17, 23]` (maroon background rows)
- `CURRENCY_ROWS` — `[4, 5, 6, 7, 10, 11, 12, 13, 14, 15]` (premium + home coverage rows)
- `LABEL_COL_WIDTH` = 140, `DATA_COL_WIDTH` = 120

**New methods:**
- `_get_num_data_columns(session)` — Returns `len(carriers[:6]) + (1 if current_policy else 0)`
- `_create_worksheet(client_name, date, num_data_cols)` — Creates blank worksheet via `add_worksheet(title, rows=25, cols=1+num_data_cols)` with same `_2`/`_3` dedup naming
- `_build_full_grid(session, num_data_cols)` — Builds all 25 rows at A1: row 1 title, row 2 date, row 3 carrier names, rows 4-25 labels + data from existing helpers. Inner `pad_row()` trims helper rows to actual column count; strips current policy column when absent
- `_apply_formatting(worksheet, num_data_cols, *, has_current_policy)` — Single `batch_format()` call (one API request) for all cell formatting + `spreadsheet.batch_update()` (one API request) for column widths and merges

**Formatting applied by `_apply_formatting()`:**

| Rule | Range | Format |
|------|-------|--------|
| Maroon headers | Rows 1 (B1+), 3, 9, 17, 23 | Maroon BG #871c30, white bold text, centered |
| Bold total | Row 7 | Bold |
| Currency | Rows 4-7, 10-15 (B through last col) | `"$"#,##0` |
| Alternating shading | Even data rows (4,6,10,12,14,18,20,24) | Light gray #f8f8f8 BG |
| Current Policy column | B4:B25 | Cream #FFF8F0 BG (overrides gray) |
| Current Policy header | B3 | Dark cream #F5E6D3 BG, bold (overrides maroon) |
| Borders | A3 through last-col:25 | Thin solid all sides |
| Data alignment | B4 through last-col:25 | Center |
| Label alignment | A4:A25 | Left |
| Date row | B2 through last-col:2 | Italic, left |
| Column A width | Col A | 140px |
| Data column widths | B through last | 120px |
| Logo cell merge | A1:A2 | Merged for logo placeholder |
| Title merge | B1 through last-col:1 | Merged for title text |

**Logo support:**
- Title moved from A1 to B1; date moved from A2 to B2
- A1:A2 merged vertically as logo placeholder
- If `LOGO_DRIVE_FILE_ID` env var is set, writes `=IMAGE("https://drive.google.com/uc?id={ID}", 2)` into A1
- Google Sheets REST API has no `addImage`/`insertImage` request type — `=IMAGE()` formula with public Google Drive URL is the only programmatic option from gspread/Python
- Setup: Upload logo to Google Drive, share as "Anyone with the link", set `LOGO_DRIVE_FILE_ID` in `.env`

**Modified methods:**
- `_write_to_worksheet()` — Writes at `A1` instead of `B4`
- `create_comparison()` — New flow: `_create_worksheet` → `_build_full_grid` → `_write_to_worksheet` → `_apply_formatting` → logo insert → URL. Removed `WorksheetNotFound`/`TemplateNotFoundError` catch block

**Unchanged (11 helper methods):**
`_format_cell_value`, `_get_auto_limits`, `_get_umbrella_limits`, `_build_premium_row`, `_build_total_row`, `_build_home_section`, `_build_auto_section`, `_build_umbrella_section`, `_build_coverage_row`, `_build_auto_limits_row`, `_build_umbrella_limits_row`

**Config change:**
- `app/utils/config.py` — Added `LOGO_DRIVE_FILE_ID: str = os.getenv("LOGO_DRIVE_FILE_ID", "")` under Google Sheets credentials section

**Smoke test:**
- `scripts/test_sheets_live.py` — Standalone script that creates a real worksheet with 3 fake carriers (Erie, Progressive, Nationwide) + State Farm current policy, all three sections populated. Prints the Google Sheets URL for visual verification.

**Verification:**
- `python -c "from app.sheets.sheets_client import SheetsClient; print('Import OK')"` — Pass
- `python -c "from app.ui.streamlit_app import main; print('Streamlit import OK')"` — Pass
- `python -m pytest tests/ -v` — No test regressions (0 collected, exit 5)
- `python scripts/test_sheets_live.py` — Creates formatted worksheet in Google Sheets

**Commits:**
1. `feat: template-free programmatic Google Sheets with dynamic formatting`
2. `feat: distinct current policy column color and logo support in Sheets`
3. `feat: auto-insert logo via =IMAGE() formula from LOGO_DRIVE_FILE_ID env var`
4. `fix: Sheets layout — logo row height, uniform maroon headers, Premium Breakout label`

### Step 18: Sheets Visual Polish — COMPLETE

**Changes:** `app/sheets/sheets_client.py`

- **Logo row height:** Added `updateDimensionProperties` for rows 1-2, setting `pixelSize: 45` (default was ~21px). Logo now has 140×90px of space in merged A1:A2.
- **Uniform maroon headers on current policy column:** Removed the dark cream override on B3 and replaced the blanket `B4:B25` cream range with four targeted data-only ranges (`B4:B7`, `B10:B15`, `B18:B21`, `B24:B25`). Section header rows 3, 9, 17, 23 now render maroon uniformly across all columns.
- **"Premium Breakout" label in A3:** Changed A3 from `""` to `"Premium Breakout"` in the carrier header row, rendered as white bold text on maroon.

---

## Phase 7: UI Polish (2026-02-12)

### Step 19: Streamlit Professional Restyling — COMPLETE

**Modified files:**
- `app/ui/streamlit_app.py` — CSS injection, branded header, step indicator (+369 lines, -16 lines)

**No business logic changed.** All modifications are presentation-only.

**New functions (3):**
- `inject_custom_css()` — Injects ~200 lines of CSS via `st.markdown(unsafe_allow_html=True)` at start of `main()`
- `render_step_indicator()` — HTML/CSS step progress bar: Upload → Review → Export with active/completed/pending states
- `_reset_session_callback()` — Extracted from inline lambda for callback-based navigation pattern

**Branding:**
- Branded header with `assets/logo_rgb.png` inline as base64 + "Scioto Insurance Group" title + "Quote Comparison Tool" subtitle
- Maroon `#871c30` accent color applied to: headings (h1/h2/h3), primary buttons, secondary button outlines, radio dots, multiselect pills, progress bars, expander left borders, input focus rings, download buttons
- `page_icon` set to `assets/logo_rgb.png` (browser tab favicon)
- Sidebar updated from `logo_transparent.png` → `logo_rgb.png` at 220px width
- Sidebar section names now title-cased (e.g., "Home" not "home")

**Hidden Streamlit defaults (CSS):**
- `#MainMenu` (hamburger menu) — `visibility: hidden`
- `footer` (Made with Streamlit) — `visibility: hidden`
- `[data-testid="stHeader"]` — `display: none` (removes fixed header bar entirely)
- `[data-testid="stToolbar"]` — `display: none`
- `[data-testid="stDecoration"]` — `display: none`
- Heading anchor links (`h1 a, h2 a, h3 a`) — `display: none`

**Step progress indicator:**
- Three-step horizontal bar: Upload → Review → Export
- Active step: maroon circle with shadow + maroon label
- Completed step: maroon circle with checkmark
- Pending step: gray circle + muted label
- Connecting lines fill maroon as steps complete
- Styled container with cream gradient background and subtle border

**Button styling:**
- Primary: maroon background, white text, darkens on hover with box-shadow, subtle press animation
- Secondary: maroon outline and text, subtle fill on hover
- Download: same maroon treatment as primary
- Full-width consistency on sidebar buttons

**Card/container styling:**
- Expanders: left 4px maroon accent border, cream header background, rounded corners, subtle box-shadow
- Carrier upload containers: 8px border-radius, subtle shadow
- File uploaders: dashed border that highlights maroon on hover

**Typography & spacing:**
- h2: bottom border for visual separation, adjusted margins
- h3: darker maroon (#5a1220), tighter margins
- `block-container`: max-width 1100px, reduced top padding
- Expander content: tightened vertical gap (0.6rem)
- Sidebar: gradient background (cream to slightly darker cream)
- Input focus states: maroon border + maroon box-shadow

**Expander labels updated:**
- "Step 1: Upload & Extract" → "Upload & Extract" (step numbers now in progress indicator)
- "Step 2: Review & Edit" → "Review & Edit"
- "Step 3: Export" → "Export Results"

**Import added:** `base64` (for inline logo embedding)

**Verification:** Syntax check passed. Streamlit app loads and renders correctly at `http://localhost:8501`. Visual verification via Playwright screenshots confirmed: branded header, step indicator, hidden defaults, maroon buttons, card layouts, clean spacing.

---

## Phase 8: Bug Fixes & Hardening (2026-02-12)

### Step 20: PDF Unicode Sanitizer — COMPLETE

**Bug:** `FPDFUnicodeEncodingException: Character "\u2013" at index 268 in text is outside the range of characters supported by the font used: "helveticaI".`

**Root cause:** AI-extracted text from Gemini contains Unicode characters (en dashes, smart quotes, bullets, ellipsis) that Helvetica's Latin-1 encoding cannot render. The crash occurred specifically in italic font (`helveticaI`) when rendering endorsements and discounts.

**Modified files:**
- `app/pdf_gen/generator.py` — Added `_sanitize_text()` function + wrapped all 28 `cell()`/`multi_cell()` call sites

**New files:**
- `tests/test_pdf_unicode.py` — 18 tests (12 unit + 6 integration) reproducing and preventing the crash

**Fix — `_sanitize_text()` function (module-level):**

| Unicode Character | Code Point | Replacement |
|-------------------|------------|-------------|
| En dash | `\u2013` | `-` |
| Em dash | `\u2014` | `-` |
| Left single quote | `\u2018` | `'` |
| Right single quote | `\u2019` | `'` |
| Left double quote | `\u201c` | `"` |
| Right double quote | `\u201d` | `"` |
| Bullet | `\u2022` | `-` |
| Ellipsis | `\u2026` | `...` |
| Non-breaking space | `\u00a0` | ` ` |
| Unicode hyphen | `\u2010` | `-` |
| Non-breaking hyphen | `\u2011` | `-` |
| Figure dash | `\u2012` | `-` |
| Middle dot | `\u00b7` | `-` |

**Two-layer defense:**
1. **Safety-net overrides:** `cell()` and `multi_cell()` overridden on `SciotoComparisonPDF` to sanitize any text argument automatically
2. **Explicit call-site wrapping:** All 28 `cell()`/`multi_cell()` calls explicitly wrap their text argument with `_sanitize_text()` — no exceptions

**Additional sanitization point:**
- `_fmt_currency()` fallback path: `str(value)` wrapped with `_sanitize_text()` for AI-extracted pass-through text values

**Test coverage (`tests/test_pdf_unicode.py`):**

*Unit tests (12) — `TestSanitizeText`:*
- Individual replacement for each of the 13 mapped characters
- Multiple replacements in one string + verification that zero non-ASCII characters remain in output
- ASCII passthrough (no modification to clean strings)
- Non-string passthrough (int/None returned unchanged)

*Integration tests (6) — `TestPDFUnicodeGeneration`:*
- `test_full_comparison_with_unicode` — Full session with Unicode in every text field (client name, carrier names, endorsements, discounts, notes, agent notes) across home + auto + umbrella
- `test_unicode_in_agent_notes_only` — Smart quotes and en dashes in agent notes (multi_cell path)
- `test_unicode_in_carrier_name` — En dash + non-breaking space in carrier name (table header cells)
- `test_unicode_in_client_name` — Smart apostrophe in client name (bold font path)
- `test_endorsements_italic_font_crash` — Direct reproduction of the exact bug: en dash in endorsement text rendered in `helveticaI`
- `test_all_unicode_chars_at_once` — Stress test with every mapped character in a single string

**Verification:**
- `python -m pytest tests/test_pdf_unicode.py -v` — 18 passed in 1.66s
- `python tests/test_pdf_visual.py` — All 4 visual test PDFs generate successfully
- Unicode test PDF generated at `data/outputs/unicode_test.pdf` — visual confirmation of clean ASCII output
