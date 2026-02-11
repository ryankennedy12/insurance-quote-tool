# Building an insurance quote comparison tool for under $10/month

**A small Columbus insurance agency can automate quote comparisons with a Python tool costing $1–9 per month to operate.** The core stack—a multimodal AI model for extraction, gspread for Google Sheets, WeasyPrint for branded PDFs, and Streamlit or NiceGUI for the interface—is entirely open-source, beginner-friendly, and production-capable for a single-user internal tool processing 10–30 quotes per day. This report provides the complete technical blueprint: specific library choices with reasoning, an architecture that separates concerns cleanly, security guidance grounded in Ohio's actual insurance data laws, and a step-by-step implementation roadmap designed for Claude Code in VS Code.

The most important design decisions come down to three things: which AI model to use for extraction (Gemini 2.5 Flash offers the best cost-accuracy tradeoff), how to handle the PII security question (the Gemini free tier is off-limits because Google trains on that data), and which web framework to build on (Streamlit works but NiceGUI fits multi-step workflows better). Everything else—Google Sheets integration, PDF generation, deployment—has clear best-practice answers that are straightforward to implement.

---

## 1. The AI extraction layer: what to use and why

### Gemini 2.5 Flash is the right primary model

At **$0.30 per million input tokens and $2.50 per million output tokens**, Gemini 2.5 Flash processes a typical 10-page insurance quote PDF for roughly **$0.007**. At 30 quotes per day across 22 working days, that's **$4.62 per month**. The model accepts PDFs natively as multimodal input (each page treated as an image at ~560 tokens), has a **1-million-token context window** that fits any insurance document without chunking, and supports JSON schema enforcement through `response_mime_type: "application/json"` with a defined schema. Its built-in "thinking" capability helps reason through ambiguous endorsement language and carrier-specific terminology.

The free tier offers 250 requests per day—technically sufficient for this volume—but **you must not use it for customer data**. Google's free-tier terms explicitly allow using inputs to improve products, meaning customer PII could enter training pipelines. The paid tier is governed by Google's Cloud Data Processing Addendum, which prohibits training on customer data.

| Model | Cost per quote | Monthly (600 quotes) | JSON reliability | Free tier for PII? |
|-------|---------------|---------------------|-----------------|-------------------|
| **Gemini 2.5 Flash** | $0.007 | $4.62 | Schema enforcement | ❌ Free tier trains on data |
| **GPT-4o-mini** | $0.002 | $1.31 | 100% via constrained decoding | N/A (no free tier) |
| **Claude Haiku 3.5** | $0.012 | $7.44 | Strong via tool use | N/A ($5 credits only) |
| **Gemini 2.5 Flash-Lite** | $0.002 | $1.10 | Schema enforcement | ❌ Same free tier issue |

**GPT-4o-mini** is the strongest backup option. It's the cheapest per-token model and has the **best structured output guarantee in the industry**—OpenAI's constrained decoding achieves 100% JSON schema compliance, meaning you'll never get malformed extraction results. At $0.15/$0.60 per million tokens, it costs roughly $1.31/month at maximum volume. The tradeoff is a smaller 128K context window (still plenty for insurance quotes) and no free tier.

**Claude Haiku 3.5** offers the strongest privacy posture—Anthropic's API retention dropped to **7 days** in September 2025, and API data is never used for training. It's the premium choice at ~$7.44/month but delivers excellent instruction-following for complex extraction tasks. The initial $5 free credit covers approximately 400 quotes.

### Skip dedicated document parsing services

AWS Textract, Google Document AI, and Azure Document Intelligence cost **$50–100 per thousand pages** for table extraction, translating to roughly **$0.05–0.10 per quote**—5 to 50 times more expensive than sending PDFs directly to a multimodal LLM. Worse, these services extract raw text and table structures but don't understand insurance semantics. You'd still need an LLM to interpret "BI/PD limits," map carrier-specific terminology, and produce structured output. Modern multimodal LLMs already include OCR capability, making dedicated parsing services an unnecessary expense and complexity layer at this volume.

### The extraction pipeline: text-first with multimodal fallback

The recommended approach uses a two-path strategy. For **digital-native PDFs** (the majority from major carriers), extract text first using **pymupdf4llm**, which produces clean Markdown preserving document hierarchy, headings, and table structure in about 0.12 seconds per document. Feed this Markdown to the LLM—text tokens are cheaper than image tokens, and structured text often yields better extraction accuracy.

For **scanned PDFs or complex multi-column layouts**, fall back to sending PDF pages directly as images to the multimodal LLM. Detection is automatic: if pymupdf4llm returns mostly empty or garbled text, switch to the image path.

```python
import pymupdf4llm

def extract_text_from_pdf(pdf_path: str) -> tuple[str, bool]:
    """Extract text; return (text, is_digital) tuple."""
    md_text = pymupdf4llm.to_markdown(pdf_path)
    # If less than 100 chars per page, likely scanned
    is_digital = len(md_text.strip()) > 100
    return md_text, is_digital
```

### Universal prompts with carrier-specific hints beat template-matching

Building separate extraction templates for each of 8–12 carriers creates a maintenance burden that doesn't pay off. Instead, use a **single well-crafted universal extraction prompt** with a carrier-specific hints section. First, have the LLM identify the carrier, then inject known terminology mappings.

Define your output schema using Pydantic (this becomes both your validation layer and your API schema):

```python
from pydantic import BaseModel
from typing import Optional

class InsuranceQuote(BaseModel):
    carrier_name: str
    policy_type: str  # "HO3", "Auto", "BOP", etc.
    effective_date: str  # ISO format
    annual_premium: float
    deductible: float
    coverage_limits: dict[str, float]  # {"dwelling": 300000, "liability": 100000}
    endorsements: list[str]
    exclusions: list[str]
    confidence: str  # "high", "medium", "low"
    notes: Optional[str] = None
```

Set temperature to 0 for extraction, include 1–2 few-shot examples in the system prompt, and add validation rules post-extraction: premiums must be positive and under $50,000, deductibles should be standard values ($250, $500, $1,000, $2,500, $5,000), and coverage limits should be reasonable increments. Flag anything that fails validation for human review rather than silently accepting bad data.

---

## 2. Google Sheets integration is simpler than you think

### gspread with a service account is the right setup

The **gspread** library (v6.2.1) is the clear winner for beginners—it wraps the Google Sheets API in a Pythonic interface that reads like pseudocode. Combined with **gspread-formatting** for cell styling, it handles everything this tool needs. The Google Sheets API is **completely free** at this volume, with limits of 60 write requests per minute per user—your tool will use roughly 3–5 API calls per quote, totaling 150 requests per day at most.

Authentication should use a **service account**—think of it as a "bot" Google account. You create it once in Google Cloud Console, download a JSON key file, and share your spreadsheet with the bot's email address (which looks like `quote-tool@your-project.iam.gserviceaccount.com`). No browser login flows, no token refresh headaches, and it runs unattended.

**Setup in five steps** (a "service account" is a special Google account for apps, not humans):

1. Go to console.cloud.google.com → create a new project named "Insurance Quote Tool"
2. Enable both the Google Sheets API and Google Drive API
3. Create credentials → Service Account → download the JSON key file
4. Rename to `service_account.json`, store it in a `secrets/` folder (never commit to Git)
5. Share your Google Sheet with the service account email as an Editor

### Duplicate the template sheet for each comparison

The most elegant pattern: maintain a "Template" worksheet inside your spreadsheet with all formatting, formulas, conditional formatting, merged cells, and branding pre-built. For each new comparison, call `template_ws.duplicate(new_sheet_name=f'Quote_{client_name}_{date}')`. This copies **everything**—colors, borders, fonts, column widths, formulas—and you only write the raw data values into the pre-formatted cells. Each comparison becomes a permanent historical record, and there's zero risk of accidentally destroying the template.

```python
import gspread

gc = gspread.service_account(filename='secrets/service_account.json')
sh = gc.open('Insurance Comparisons')
template_ws = sh.worksheet('Template')

# Create new comparison from template
new_ws = template_ws.duplicate(new_sheet_name=f'Quote_Smith_2026-02-10')

# Write extracted data (formatting is preserved from template)
quote_data = [
    ["State Farm", "$1,200", "$500", "$300K"],
    ["Progressive", "$1,050", "$1,000", "$300K"],
    ["Erie", "$1,150", "$500", "$250K"],
]
new_ws.update(quote_data, 'B3')  # Batch write - single API call
```

---

## 3. Branded PDF generation with HTML and CSS

### WeasyPrint + Jinja2 produces the best output

For creating polished, branded comparison documents, the **HTML/CSS-to-PDF** approach is clearly superior to building PDFs programmatically. You design the document as a web page using familiar HTML tables and CSS styling, then convert to PDF. This means you can iterate on the design by editing CSS and refreshing—no recompiling, no coordinate math, no learning a PDF-specific layout language.

**WeasyPrint** (v68.1, released February 2026) is the best HTML-to-PDF converter for this use case. It supports CSS Paged Media (`@page` rules for headers, footers, margins, page numbers), renders HTML tables beautifully, and produces print-quality output. Combined with **Jinja2** templating, dynamic content handling is trivial—a `{% for carrier in carriers %}` loop naturally generates the right number of columns whether comparing 2 or 6 carriers.

The one downside is **Windows installation**. WeasyPrint requires system-level libraries (Pango, Cairo) that aren't native to Windows. Installation requires either MSYS2 (a Unix-like environment for Windows) or using WeasyPrint's standalone executable. If this proves too frustrating, **FPDF2** (v2.8.5) is the fallback—it's pure Python (`pip install fpdf2` and done), handles tables well with its built-in `pdf.table()` context manager, and requires zero system dependencies. The output is less visually refined than WeasyPrint's CSS-driven layouts, but still professional.

| Factor | WeasyPrint | FPDF2 |
|--------|-----------|-------|
| Output quality | ★★★★★ Excellent | ★★★☆☆ Good |
| Windows install | ★★☆☆☆ Requires MSYS2 | ★★★★★ `pip install` only |
| Design approach | HTML/CSS templates | Python code + basic HTML |
| Dynamic columns | CSS handles automatically | Manual width calculation |
| Branding support | Full CSS (fonts, colors, logos) | Manual positioning |
| Page breaks | CSS `break-inside: avoid` | Automatic built-in |

### What makes a professional insurance comparison PDF

Key design elements for credibility: a header with agency logo and contact info, client name and date, a clean comparison table with carriers as columns and coverage types as rows, **green highlighting on best-value cells**, consistent currency formatting, a bold premium summary row, an optional agent recommendation section, and a footer with the agency's license number and disclaimer. Use a navy/dark blue primary color (#2c5aa0) for trust, green (#28a745) for best-value highlights, and light gray (#f8f9fa) for alternating table rows.

---

## 4. Streamlit works, but NiceGUI fits this workflow better

### Why the script-rerun model creates friction

Streamlit's core design—the entire script re-executes on every user interaction—creates state management headaches for a multi-step workflow like upload → extract → review → edit → export. Every button click, every table edit, every dropdown change triggers a full re-run. You manage this with `st.session_state`, but it adds complexity and can cause confusing behavior (progress indicators resetting, uploads re-triggering).

**NiceGUI** uses an event-driven model where state persists naturally and user interactions trigger specific callbacks rather than full re-runs. This maps cleanly to a multi-step business workflow. It provides built-in editable tables (based on Quasar's QTable), multi-file upload with progress callbacks, professional Tailwind CSS styling, and it's built on FastAPI so you can add API endpoints later. It also offers a "native" mode that opens the app in a desktop-like window—useful if the agent prefers a desktop feel.

**The pragmatic recommendation**: If the Streamlit prototype is mostly working and you're comfortable with it, **stay with Streamlit**—it has the largest community, the most tutorials, and the easiest cloud deployment. Use `st.data_editor` for editable tables and `st.session_state` carefully for workflow state. If you're willing to refactor, NiceGUI will produce a cleaner, more maintainable application for this specific type of multi-step tool.

### Required UI components checklist

- **Multi-file upload**: `st.file_uploader(accept_multiple_files=True)` in Streamlit, `ui.upload(multiple=True)` in NiceGUI
- **Progress indicators**: `st.progress()` + `st.spinner()`, or NiceGUI's `ui.linear_progress`
- **Editable data table**: `st.data_editor` (Streamlit) or `ui.table` with editing enabled (NiceGUI)—both support inline cell editing
- **PDF preview/download**: `st.download_button` for downloads; PDF preview via embedded iframe or a "Download & Open" button
- **Google Sheets link**: Simple clickable hyperlink displayed after sheet creation

---

## 5. Architecture that a beginner can maintain

### Project structure

```
insurance-quote-tool/
├── .env                          # API keys (NEVER commit to Git)
├── .env.example                  # Template showing required variables
├── .gitignore
├── requirements.txt              # Pinned dependencies
├── README.md
├── app/
│   ├── main.py                   # Entry point — starts web UI
│   ├── ui/
│   │   ├── upload_page.py        # File upload + extraction trigger
│   │   ├── review_page.py        # Editable data table
│   │   └── output_page.py        # PDF preview, Sheets link, download
│   ├── extraction/
│   │   ├── pdf_parser.py         # pymupdf4llm text extraction
│   │   ├── ai_extractor.py       # LLM API calls + JSON parsing
│   │   ├── validator.py          # Post-extraction validation rules
│   │   └── models.py             # Pydantic data models
│   ├── sheets/
│   │   └── sheets_client.py      # gspread read/write operations
│   ├── pdf_gen/
│   │   ├── generator.py          # WeasyPrint/FPDF2 PDF creation
│   │   └── templates/
│   │       └── comparison.html   # Jinja2 HTML template
│   └── utils/
│       ├── config.py             # Settings loaded from .env
│       └── logging_config.py
├── secrets/
│   └── service_account.json      # Google credentials (gitignored)
├── data/
│   ├── uploads/                  # Temporary PDF storage
│   └── outputs/                  # Generated comparison PDFs
├── assets/
│   └── logo.png                  # Agency branding
└── tests/
    ├── test_extraction.py
    └── fixtures/                 # Sample PDFs for testing
```

The key principle: **the extraction, sheets, and pdf_gen modules should work as pure Python functions callable from anywhere**, independent of the UI framework. This means you can test extraction from the command line, swap Streamlit for NiceGUI without rewriting business logic, and debug components individually.

### Configuration management

Use a `.env` file with `python-dotenv` for simplicity. A `.env` file is a plain text file storing settings as key-value pairs—it sits in your project root and is read by your app at startup. **Never commit it to Git** (add `.env` to `.gitignore`).

```python
# .env file
GEMINI_API_KEY=your-key-here
GOOGLE_SERVICE_ACCOUNT_FILE=./secrets/service_account.json
SPREADSHEET_ID=your-spreadsheet-id
AGENCY_NAME=Columbus Insurance Group
```

```python
# app/utils/config.py
from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
AGENCY_NAME = os.getenv("AGENCY_NAME", "Your Insurance Agency")
```

### File-based storage is sufficient—no database needed

At 10–30 quotes per day, Google Sheets **is** your persistent storage. Local storage only holds temporary files during processing. Store uploaded PDFs in `data/uploads/{date}/` and generated PDFs in `data/outputs/{date}/`. Delete uploaded PDFs after extraction completes to minimize PII retention. SQLite becomes worth considering only if you later want to search historical quotes or track processing metrics.

### Error recovery for partial failures

When extracting data from 5 PDFs and one fails, the tool should continue processing the rest and clearly show what happened:

```python
results = []
for pdf in uploaded_files:
    try:
        data = extract_quote_data(pdf)
        results.append({"file": pdf.name, "success": True, "data": data})
    except Exception as e:
        results.append({"file": pdf.name, "success": False, "error": str(e)})

# UI shows: "4/5 PDFs processed successfully"
# Failed file gets a "Retry" button and option for manual entry
```

---

## 6. Security posture grounded in Ohio law

### Ohio's insurance data security law has a small-agency exemption

Ohio Revised Code Chapter 3965 (SB 273), enacted in 2019, requires insurance licensees to maintain written information security programs, conduct risk assessments, and implement cybersecurity controls. However, **agencies with fewer than 20 employees, less than $5 million in gross annual revenue, or less than $10 million in assets are exempt from most requirements**. A small independent agency in Columbus almost certainly qualifies for this exemption.

The exemption does **not** cover breach notification obligations. If a data breach affects Ohio consumers, notification within 3 business days to the Ohio Superintendent of Insurance is still required, along with 45-day notification to affected individuals.

### The free AI tier is the biggest security risk

The single most important security decision: **never send customer PII through an AI provider's free tier**. Google's Gemini free tier explicitly allows using inputs to improve products. The paid tier ($0.007 per quote) is governed by the Cloud Data Processing Addendum and prohibits training on customer data. At roughly **$5 per month**, this is the cheapest possible insurance against a data handling violation.

Among paid tiers, **Anthropic's Claude API has the strongest privacy posture**: 7-day data retention (reduced from 30 days in September 2025), no training on API data by default, and zero-data-retention agreements available for enterprise customers. OpenAI's API also doesn't train on data by default (since March 2023) but retains data for 30 days. Google's paid Gemini tier doesn't train on data and offers enterprise-grade compliance through Vertex AI.

### Minimum security checklist for this tool

- **Encryption in transit**: Automatic—all AI API calls and Google Sheets API calls use HTTPS/TLS. Cloud hosting platforms (Render, Cloud Run) provide free SSL certificates. If running locally, access only via `localhost`.
- **Encryption at rest**: Enable BitLocker on the Windows machine where the tool runs. This encrypts the hard drive, protecting any locally stored PDFs.
- **API key storage**: `.env` file added to `.gitignore`, or platform environment variables for cloud deployment. Never hardcode keys in source code.
- **Data minimization**: Delete uploaded PDFs after extraction. Write only structured comparison data to Google Sheets—not raw PDF contents. Implement a clear lifecycle: upload → extract → write to Sheets → delete local copy.
- **Access control**: For a single-user tool, the operating system login is your access control. If deploying to the cloud, use the platform's private app settings rather than a public URL.

---

## 7. Monthly costs are remarkably low

### Full cost breakdown at maximum volume (600 quotes/month)

| Component | Cheapest viable | Recommended |
|-----------|----------------|-------------|
| AI extraction | Gemini 2.5 Flash paid: **$4.62** | Claude Haiku 3.5: **$7.44** |
| Google Sheets API | Free: **$0** | Free: **$0** |
| Hosting | Run locally: **$0** | Render: **$7.00** |
| PDF generation libs | Open-source: **$0** | Open-source: **$0** |
| Domain / SSL | Platform URL: **$0** | Platform URL: **$0** |
| **Monthly total** | **$4.62** | **$14.44** |

The **cheapest viable stack** uses Gemini 2.5 Flash on the paid tier (mandatory for PII safety) and runs the tool locally on the agency's existing computer. Total: under $5/month. The **recommended stack** adds Claude Haiku for stronger privacy guarantees and Render hosting ($7/month) so the agent can access the tool from any computer without keeping a specific PC running. Total: under $15/month.

For comparison, even the recommended stack costs less per month than a single hour of manual data entry. At 600 quotes per month with an estimated 15 minutes saved per quote, the tool saves roughly **150 hours of manual work monthly**.

---

## 8. Step-by-step implementation roadmap for Claude Code

This roadmap is designed for working in VS Code with Claude Code (an AI coding assistant). Each step includes what to build, a suggested prompt for Claude Code, how to verify it works, and what to do if it doesn't. Work through these sequentially—**each step builds on the previous one**.

### Phase 1: Foundation (Evening 1)

**Step 1: Create project structure and install dependencies**

Open VS Code, open a new terminal, and create your project folder. Then ask Claude Code:

> "Create a Python project structure for an insurance quote comparison tool. Create the folder structure with app/extraction/, app/sheets/, app/pdf_gen/, app/ui/, app/utils/, data/uploads/, data/outputs/, secrets/, assets/, and tests/fixtures/ directories. Create a requirements.txt with: streamlit, gspread, gspread-formatting, google-auth, pymupdf4llm, google-generativeai, python-dotenv, pydantic, jinja2, fpdf2, weasyprint. Create a .env.example with GEMINI_API_KEY, GOOGLE_SERVICE_ACCOUNT_FILE, SPREADSHEET_ID, and AGENCY_NAME placeholders. Create a .gitignore that excludes .env, secrets/, data/, __pycache__."

**Test**: Run `pip install -r requirements.txt` in your terminal. All packages should install successfully. If WeasyPrint fails on Windows, remove it from requirements.txt for now—you'll use FPDF2 as the PDF engine instead.

**If it fails**: WeasyPrint's Windows installation is the most likely issue. Install MSYS2 from msys2.org, then in the MSYS2 terminal run `pacman -S mingw-w64-x86_64-pango`. If still failing, comment out weasyprint and proceed with fpdf2 only.

**Step 2: Build the configuration module**

> "Create app/utils/config.py that loads settings from a .env file using python-dotenv. Include settings for: GEMINI_API_KEY, GOOGLE_SERVICE_ACCOUNT_FILE (default: './secrets/service_account.json'), SPREADSHEET_ID, AGENCY_NAME (default: 'Your Insurance Agency'), MAX_UPLOAD_FILES (default: 6). Include validation that prints a clear error message if GEMINI_API_KEY is missing."

**Test**: Create a `.env` file with a dummy API key, then run `python -c "from app.utils.config import *; print(AGENCY_NAME)"`. It should print your agency name.

**Step 3: Set up Google Cloud service account**

This step is manual—no Claude Code needed:
1. Go to console.cloud.google.com and create a project called "Insurance Quote Tool"
2. Enable the Google Sheets API and Google Drive API
3. Go to Credentials → Create Credentials → Service Account
4. Download the JSON key → save as `secrets/service_account.json`
5. Create a Google Sheet called "Insurance Comparisons"
6. Share it with the service account email (from the JSON file's `client_email` field)
7. Copy the spreadsheet ID from the URL and add it to your `.env` file

### Phase 2: AI extraction engine (Evening 2)

**Step 4: Build the PDF text extraction module**

> "Create app/extraction/pdf_parser.py with a function extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, bool] that uses pymupdf4llm to extract text from a PDF file provided as bytes. Return a tuple of (markdown_text, is_digital). A PDF is considered 'digital' (not scanned) if the extracted text has more than 100 characters per page on average. Include error handling that returns ('', False) if extraction fails."

**Test**: Download any PDF from the internet, then run:
```python
from app.extraction.pdf_parser import extract_text_from_pdf
with open("test.pdf", "rb") as f:
    text, is_digital = extract_text_from_pdf(f.read())
print(f"Digital: {is_digital}, Length: {len(text)}")
```

**Step 5: Build the AI extraction module**

> "Create app/extraction/models.py with a Pydantic model called InsuranceQuote with fields: carrier_name (str), policy_type (str), effective_date (str, optional), annual_premium (float), deductible (float), coverage_limits (dict of str to float), endorsements (list of str), exclusions (list of str), confidence (str: high/medium/low), notes (optional str).
>
> Then create app/extraction/ai_extractor.py that uses the Google Generative AI library (google.generativeai) with model 'gemini-2.5-flash-preview-05-20' to extract structured data from insurance quote text. The function extract_quote_data(pdf_bytes: bytes) should: (1) extract text using pdf_parser, (2) send text to Gemini with a system prompt instructing it to extract insurance quote data into the InsuranceQuote schema, (3) use response_mime_type='application/json' with the schema, (4) set temperature=0, (5) parse the response into an InsuranceQuote model, (6) return the model. Include a good system prompt that tells the AI to extract only explicitly stated information, return null for missing fields, use standard formats for dates and currencies, and include carrier-specific hints for Erie, Progressive, Safeco, Nationwide, Allstate, and State Farm."

**Test**: Get a real insurance quote PDF (or use a sample), then:
```python
from app.extraction.ai_extractor import extract_quote_data
with open("sample_quote.pdf", "rb") as f:
    quote = extract_quote_data(f.read())
print(quote.model_dump_json(indent=2))
```
Verify the extracted carrier name, premium, and deductible match the PDF.

**If it fails**: Check your GEMINI_API_KEY in `.env`. If you get JSON parsing errors, ask Claude Code to add the `json-repair` library as a fallback parser.

**Step 6: Add validation**

> "Create app/extraction/validator.py with a function validate_quote(quote: InsuranceQuote) -> tuple[InsuranceQuote, list[str]] that checks: premium is between 0 and 50000, deductible is a standard value (250, 500, 1000, 2500, 5000, 10000) or flag it, coverage limits are positive numbers, carrier_name is not empty. Return the quote and a list of warning strings for any issues found. Don't reject the quote—just flag warnings for user review."

**Test**: Create a quote with a $999,999 premium and verify it returns a warning.

### Phase 3: Google Sheets integration (Evening 3)

**Step 7: Build the Sheets client**

> "Create app/sheets/sheets_client.py with a class SheetsClient that: (1) authenticates with gspread using a service account JSON file path from config, (2) has a method create_comparison(client_name: str, quotes: list[InsuranceQuote]) that opens the spreadsheet by ID from config, duplicates the 'Template' worksheet with name 'Quote_{client_name}_{today's date}', writes the quote data into the sheet starting at row 3 with carriers as columns and coverage types as rows, and returns the URL of the new sheet. Use batch updates for efficiency. Include error handling for common issues like sheet not found or permission denied."

**Test**: Run the function with dummy data and check that a new tab appears in your Google Sheet with the correct data and preserved formatting from the template.

**Before this works**: You need to create a "Template" tab in your Google Sheet with your desired formatting—header row with colors, column widths set, any formulas in place. The code will duplicate this tab for each new comparison.

### Phase 4: PDF generation (Evening 4)

**Step 8: Create the comparison PDF template**

> "Create app/pdf_gen/templates/comparison.html as a Jinja2 HTML template for an insurance quote comparison PDF. Include: an agency header with logo placeholder and agency name, client name and date, a comparison table with carriers as columns (dynamic—works for 2 to 6 carriers) and coverage types as rows, a bold premium summary row, and a footer with a disclaimer. Style with embedded CSS: navy blue header (#2c5aa0), white header text, alternating gray rows (#f8f9fa), green highlight class for best values (#d4edda), professional sans-serif font. Use @page CSS rules for letter-size paper with 0.75-inch margins and page numbers."

> "Then create app/pdf_gen/generator.py with a function generate_comparison_pdf(quotes: list[InsuranceQuote], client_name: str, output_path: str) that renders the Jinja2 template with the quote data and converts to PDF using WeasyPrint. If WeasyPrint is not installed, fall back to FPDF2 with a simpler table layout. The function should determine the best value (lowest premium) and mark it for highlighting."

**Test**: Generate a PDF with 3 sample quotes and open it. Verify it looks professional with correct data, branding colors, and the lowest premium highlighted.

### Phase 5: Web UI (Weekend session)

**Step 9: Build the Streamlit interface**

> "Create app/main.py as a Streamlit app with three main sections using st.session_state to manage workflow state:
>
> Section 1 - Upload: st.file_uploader accepting multiple PDFs (max 6), a 'Process Quotes' button that calls extract_quote_data on each uploaded file with a progress bar, stores results in session_state, and handles failures gracefully (shows which files succeeded/failed with retry option).
>
> Section 2 - Review: Only shows after extraction. Display extracted data in st.data_editor (an editable table) so the user can correct any extraction errors. Show validation warnings from the validator. Include 'Save to Google Sheets' and 'Generate PDF' buttons.
>
> Section 3 - Output: Show a success message with a clickable link to the Google Sheet, a download button for the comparison PDF, and a summary of what was created.
>
> Add a sidebar with the agency name, a brief description, and a help section. Use st.set_page_config for a professional title and layout."

**Test**: Run `streamlit run app/main.py` and walk through the entire workflow: upload PDFs → verify extraction → edit data → save to Sheets → download PDF.

**Step 10: Polish the UI**

> "Update the Streamlit app to add: (1) client name input field at the top, (2) error messages that are helpful and non-technical (e.g., 'We couldn't read this file clearly—please check the PDF is not password-protected'), (3) a spinner with status messages during extraction ('Reading State Farm quote... Extracting coverage details...'), (4) formatting for the editable table (currency formatting for premiums, highlighting for lowest premium), (5) a 'Start New Comparison' button that clears session state."

### Phase 6: Testing and hardening (One more evening)

**Step 11: Test with real carrier PDFs**

Collect one sample quote PDF from each carrier you work with (Erie, Progressive, Safeco, Nationwide, Allstate, State Farm, etc.). Process each one through the tool and note:
- Which carriers extract perfectly?
- Which carriers have extraction errors?
- What specific fields are commonly wrong?

For carriers with issues, ask Claude Code:

> "The AI extraction is getting [specific field] wrong for [carrier name] PDFs. Here's what the PDF says: [paste the relevant text]. Here's what the AI extracted: [paste the wrong output]. Update the system prompt in ai_extractor.py to add a carrier-specific hint that fixes this."

**Step 12: Add logging**

> "Create app/utils/logging_config.py that sets up Python logging with a RotatingFileHandler writing to data/logs/app.log (max 5MB, keep 5 files) and a console handler. Add logging calls throughout the application: INFO level for successful extractions, WARNING for validation issues, ERROR for failures. In ai_extractor.py, log the carrier name and confidence level for each extraction."

**Test**: Process a quote, then check `data/logs/app.log` to see if events were recorded.

### Phase 7: Deployment (Final session)

**Step 13: Deploy for daily use**

**Option A—Run locally (simplest, free):**

> "Create a run.bat file in the project root that activates the Python environment and runs 'streamlit run app/main.py --server.port 8501'. Add a shortcut on the desktop that runs this .bat file. The agent double-clicks the shortcut and the app opens in their browser."

**Option B—Deploy to Render ($7/month):**
1. Push your code to a GitHub repository (excluding .env and secrets/)
2. Create a Render account at render.com
3. New Web Service → connect your GitHub repo
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `streamlit run app/main.py --server.port $PORT --server.address 0.0.0.0`
6. Add environment variables in Render's dashboard (all your .env values)
7. Upload the service account JSON as a secret file
8. Deploy—future Git pushes auto-redeploy

**Test**: Access the deployed URL from a different computer. Walk through the full workflow.

### Quick-reference dependency list

```
# requirements.txt
streamlit>=1.41.0
gspread>=6.2.0
gspread-formatting>=1.2.0
google-auth>=2.36.0
pymupdf4llm>=0.0.17
google-generativeai>=0.8.0
python-dotenv>=1.0.1
pydantic>=2.10.0
jinja2>=3.1.5
fpdf2>=2.8.0
weasyprint>=62.0      # Remove if Windows install fails
json-repair>=0.30.0
sentry-sdk>=2.19.0    # Optional: error tracking
```

---

## Conclusion

This tool is buildable in a week of evenings by a beginner using Claude Code, and the entire operating cost sits between **$5 and $15 per month**. The most consequential decisions aren't about which library is marginally better—they're about PII handling. Use the paid Gemini tier or Claude Haiku API (never the free tier for customer data), delete PDFs after extraction, and document your data handling practices even though Ohio's small-agency exemption likely applies. The technical stack—Gemini 2.5 Flash for extraction, gspread for Sheets, WeasyPrint or FPDF2 for PDFs, and Streamlit for the UI—is mature, well-documented, and proven at this scale. Start with the extraction module (Step 5), because if the AI can't reliably read the PDFs your agency uses, nothing else matters. Once extraction works on real quotes from your carriers, the rest is straightforward plumbing.