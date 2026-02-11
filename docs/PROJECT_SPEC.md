# Insurance Quote Comparison Tool — Project Specification

## Purpose
Internal tool for a small Columbus, Ohio insurance agency. A single agent uploads 2–6 carrier quote PDFs, the tool extracts structured data via AI, presents an editable comparison table, then exports to Google Sheets and a branded PDF. Processes 10–30 quotes/day, ~600/month max.

---

## Tech Stack (Locked Decisions)

| Layer | Library | Version | Why |
|---|---|---|---|
| AI Extraction (primary) | `google-generativeai` | ≥0.8.0 | Gemini 2.5 Flash — $0.007/quote, native PDF, JSON schema enforcement |
| AI Extraction (backup) | `openai` | ≥1.0.0 | GPT-4o-mini — $0.002/quote, 100% JSON schema compliance via constrained decoding |
| PDF Text Extraction | `pymupdf4llm` | ≥0.0.17 | Extracts Markdown preserving tables/headings, 0.12s/doc |
| Data Validation | `pydantic` | ≥2.10.0 | Schema enforcement + validation in one layer |
| Google Sheets | `gspread` + `gspread-formatting` | ≥6.2.0 / ≥1.2.0 | Free API, service account auth, template duplication |
| PDF Generation | `weasyprint` | ≥62.0 | CSS Paged Media, @page rules. **Fallback:** `fpdf2` ≥2.8.0 if WeasyPrint install fails on Windows |
| HTML Templating | `jinja2` | ≥3.1.5 | Dynamic carrier columns in PDF template |
| Web UI | `streamlit` | ≥1.41.0 | Fastest to prototype. **Optional upgrade:** NiceGUI for event-driven model |
| Config | `python-dotenv` | ≥1.0.1 | .env file loading |
| JSON Fallback | `json-repair` | ≥0.30.0 | Recovers malformed LLM JSON responses |
| Error Tracking | `sentry-sdk` | ≥2.19.0 | Optional — production error monitoring |

---

## Architecture Overview

```
User uploads PDFs
        │
        ▼
┌─────────────────┐
│   Streamlit UI   │  (app/main.py)
│  Upload → Review │
│    → Export      │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│PDF Text│ │  AI    │
│Extract │→│Extract │  (app/extraction/)
│pymupdf │ │Gemini  │
└────────┘ └───┬────┘
               │
          ┌────┴────┐
          ▼         ▼
    ┌──────────┐ ┌──────────┐
    │  Google   │ │  PDF     │
    │  Sheets   │ │  Gen     │  (app/sheets/ + app/pdf_gen/)
    │  gspread  │ │WeasyPrint│
    └──────────┘ └──────────┘
```

**Critical Design Principle:** The `extraction/`, `sheets/`, and `pdf_gen/` modules must be pure Python functions callable from anywhere — independent of the UI framework. No Streamlit imports in business logic modules.

---

## File Structure

```
insurance-quote-tool/
├── .env                          # API keys — NEVER commit
├── .env.example                  # Template with placeholders
├── .gitignore
├── requirements.txt
├── README.md
├── run.bat                       # Windows launcher shortcut
├── app/
│   ├── __init__.py
│   ├── main.py                   # Streamlit entry point
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── upload_page.py        # File upload + extraction trigger
│   │   ├── review_page.py        # Editable data table + validation warnings
│   │   └── output_page.py        # PDF preview, Sheets link, download
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py         # pymupdf4llm text extraction
│   │   ├── ai_extractor.py       # LLM API calls + JSON parsing
│   │   ├── validator.py          # Post-extraction validation rules
│   │   └── models.py             # Pydantic data models (InsuranceQuote)
│   ├── sheets/
│   │   ├── __init__.py
│   │   └── sheets_client.py      # gspread service account operations
│   ├── pdf_gen/
│   │   ├── __init__.py
│   │   ├── generator.py          # WeasyPrint/FPDF2 PDF creation
│   │   └── templates/
│   │       └── comparison.html   # Jinja2 HTML template for branded PDF
│   └── utils/
│       ├── __init__.py
│       ├── config.py             # Settings from .env
│       └── logging_config.py     # RotatingFileHandler setup
├── secrets/
│   └── service_account.json      # Google credentials — gitignored
├── data/
│   ├── uploads/                  # Temporary PDF storage (delete after extraction)
│   ├── outputs/                  # Generated comparison PDFs
│   └── logs/                     # App logs (RotatingFileHandler, 5MB max, 5 files)
├── assets/
│   └── logo.png                  # Agency branding for PDF header
└── tests/
    ├── __init__.py
    ├── test_extraction.py
    └── fixtures/                 # Sample PDFs for testing
```

---

## Data Model (Pydantic)

This is the single source of truth for all extracted quote data. Used for AI extraction schema, validation, Sheets writing, and PDF generation.

```python
from pydantic import BaseModel, Field
from typing import Optional

class InsuranceQuote(BaseModel):
    carrier_name: str = Field(description="Insurance carrier name (e.g., 'Erie Insurance', 'State Farm')")
    policy_type: str = Field(description="Policy type code: HO3, HO5, Auto, BOP, etc.")
    effective_date: Optional[str] = Field(None, description="Policy effective date in ISO format YYYY-MM-DD")
    expiration_date: Optional[str] = Field(None, description="Policy expiration date in ISO format YYYY-MM-DD")
    annual_premium: float = Field(description="Total annual premium in USD")
    monthly_premium: Optional[float] = Field(None, description="Monthly premium if quoted separately")
    deductible: float = Field(description="Primary deductible in USD")
    wind_hail_deductible: Optional[float] = Field(None, description="Separate wind/hail deductible if applicable")
    coverage_limits: dict[str, float] = Field(
        description="Coverage type to limit amount mapping",
        examples=[{
            "dwelling": 300000,
            "other_structures": 30000,
            "personal_property": 150000,
            "loss_of_use": 60000,
            "personal_liability": 100000,
            "medical_payments": 5000
        }]
    )
    endorsements: list[str] = Field(default_factory=list, description="List of endorsements/riders included")
    exclusions: list[str] = Field(default_factory=list, description="List of notable exclusions")
    discounts_applied: list[str] = Field(default_factory=list, description="Discounts applied to this quote")
    confidence: str = Field(description="Extraction confidence: 'high', 'medium', or 'low'")
    notes: Optional[str] = Field(None, description="Any caveats, ambiguities, or extraction notes")
    raw_source: Optional[str] = Field(None, description="Which extraction path was used: 'text' or 'multimodal'")
```

---

## Extraction Pipeline Logic

```
PDF bytes received
       │
       ▼
pymupdf4llm.to_markdown()
       │
       ├── chars/page > 100 → TEXT PATH (cheaper, often more accurate)
       │       │
       │       ▼
       │   Send Markdown text to Gemini as text prompt
       │
       └── chars/page ≤ 100 → MULTIMODAL PATH (scanned PDFs)
               │
               ▼
           Send PDF pages as images to Gemini
       │
       ▼
Parse JSON response → InsuranceQuote model
       │
       ▼
Run validator → Return (quote, warnings[])
```

**Temperature:** Always 0 for extraction.
**JSON enforcement:** Use `response_mime_type="application/json"` with `response_schema` in Gemini.
**Fallback parsing:** If JSON parse fails, use `json-repair` library before raising error.

---

## Validation Rules

| Field | Rule | Action |
|---|---|---|
| `annual_premium` | Must be > 0 and < 50,000 | Warning if outside range |
| `deductible` | Should be standard: 250, 500, 1000, 2500, 5000, 10000 | Warning if non-standard |
| `coverage_limits` values | Must be > 0 | Warning if zero or negative |
| `carrier_name` | Must not be empty | Error — require manual entry |
| `effective_date` | Must be valid ISO date if present | Warning if malformed |
| `confidence` | Must be "high", "medium", or "low" | Default to "low" if missing |

**Never silently reject data.** Flag warnings for human review. The editable table is the correction mechanism.

---

## Google Sheets Strategy

1. Authenticate via service account (JSON key file, shared as Editor on spreadsheet)
2. Maintain a "Template" worksheet with pre-built formatting, colors, formulas, column widths
3. For each comparison: `template_ws.duplicate(new_sheet_name=f'Quote_{client_name}_{date}')`
4. Write extracted data via batch update starting at cell B3
5. Carriers as columns, coverage types as rows
6. Return the sheet URL for the user

**API limits:** 60 write requests/min. Tool uses 3–5 calls per quote — no throttling needed.

---

## PDF Design Specification

| Element | Value |
|---|---|
| Page size | US Letter (8.5" × 11") |
| Margins | 0.75" all sides |
| Primary color (header, borders) | Navy blue `#2c5aa0` |
| Best-value highlight | Green background `#d4edda` |
| Alternating row background | Light gray `#f8f9fa` |
| Font | Sans-serif system font stack |
| Header | Agency logo (left) + agency name + contact info (right) |
| Body | Client name, date, comparison table (carriers = columns, coverages = rows) |
| Summary row | Bold, total premium per carrier |
| Footer | Agency license number, disclaimer text, page numbers |

---

## Security Requirements (Non-Negotiable)

1. **NEVER use Gemini free tier for customer data.** Google trains on free-tier inputs. Paid tier is mandatory ($0.007/quote).
2. **Delete uploaded PDFs after extraction.** `data/uploads/` is temporary only.
3. **API keys in `.env` only.** Never hardcode. `.env` must be in `.gitignore`.
4. **Service account JSON in `secrets/`.** Also gitignored.
5. **HTTPS only** for all API calls (automatic with Google/OpenAI SDKs).
6. **No raw PDF content in Sheets.** Only structured extracted data.
7. **Ohio SB 273 (ORC 3965):** Small agency exemption likely applies (<20 employees, <$5M revenue). Breach notification (3 business days to Superintendent, 45 days to individuals) still required.

---

## Cost Budget

| Component | Monthly Cost |
|---|---|
| Gemini 2.5 Flash (paid tier, 600 quotes) | $4.62 |
| Google Sheets API | $0.00 |
| PDF generation | $0.00 |
| Local hosting | $0.00 |
| **Total (local)** | **~$5/month** |
| Optional: Render hosting | +$7.00 |
| Optional: Claude Haiku instead of Gemini | +$2.82 |

---

## UI Workflow (Streamlit)

### State Machine
```
UPLOAD → EXTRACTING → REVIEW → EXPORTING → COMPLETE
```

### Session State Keys
```python
st.session_state.workflow_stage     # "upload" | "extracting" | "review" | "exporting" | "complete"
st.session_state.uploaded_files     # list of UploadedFile objects
st.session_state.extracted_quotes   # list of InsuranceQuote dicts
st.session_state.extraction_errors  # list of {file, error} dicts
st.session_state.validation_warnings # list of {file, warnings} dicts
st.session_state.client_name        # str
st.session_state.sheets_url         # str (after export)
st.session_state.pdf_path           # str (after export)
```

### UI Components
- `st.text_input` — Client name (required before processing)
- `st.file_uploader(accept_multiple_files=True, type=["pdf"])` — Max 6 files
- `st.progress()` + `st.spinner()` — During extraction
- `st.data_editor` — Editable comparison table for review/correction
- `st.download_button` — PDF download
- Clickable hyperlink — Google Sheets URL
- `st.button("Start New Comparison")` — Clears session state
