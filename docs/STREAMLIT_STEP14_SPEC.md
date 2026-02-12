# Phase 5: Streamlit UI — Step 14: Export Stage

> Place in `docs/`. Reference from CLAUDE.md.
> This replaces the Step 3 placeholder content in `app/ui/streamlit_app.py` with real PDF generation and Google Sheets export.

---

## Overview

Step 14 builds out the Export stage where the agent:
1. Enters optional agent notes (already wired from Step 11)
2. Clicks "Generate PDF" to create the comparison PDF using `pdf_gen/generator.py`
3. Downloads the generated PDF
4. Clicks "Export to Google Sheets" to create a formatted spreadsheet
5. Gets a link to the created Google Sheet

---

## Data Flow

```
Step 13 stores:
  st.session_state.edited_bundles         → list[CarrierBundle]
  st.session_state.edited_current_policy  → CurrentPolicy or None

Step 14 reads those + agent_notes to build:
  ComparisonSession → passed to PDF generator and Sheets client

Step 14 stores:
  st.session_state.export_pdf_path  → str (path to generated PDF)
  st.session_state.export_sheet_url → str (URL to Google Sheet)
```

---

## Building the ComparisonSession

Before either export, build the `ComparisonSession` object from edited data:

```python
def _build_comparison_session() -> ComparisonSession:
    """Build ComparisonSession from edited data for export."""
    return ComparisonSession(
        client_name=st.session_state.client_name,
        sections_included=st.session_state.sections_included,
        carriers=st.session_state.edited_bundles,
        current_policy=st.session_state.edited_current_policy,
        agent_notes=st.session_state.get("agent_notes", "").strip() or None,
    )
```

**Important:** Verify the `ComparisonSession` constructor fields match the model. Grep `models.py` before coding.

---

## PDF Generation

```python
st.subheader("📄 PDF Comparison Report")

col1, col2 = st.columns([1, 3])
with col1:
    generate_pdf_btn = st.button("📄 Generate PDF", type="primary")

if generate_pdf_btn:
    with st.spinner("Generating PDF..."):
        try:
            session = _build_comparison_session()

            # Generate to temp output path
            output_dir = Path("data/outputs")
            output_dir.mkdir(parents=True, exist_ok=True)

            safe_name = session.client_name.replace(" ", "_")
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_path = str(output_dir / f"{safe_name}_comparison_{date_str}.pdf")

            logo_path = "assets/logo_transparent.png"
            if not Path(logo_path).exists():
                logo_path = None

            result_path = generate_comparison_pdf(
                session=session,
                output_path=output_path,
                logo_path=logo_path,
                date_str=date_str,
                agent_notes=session.agent_notes,
            )

            st.session_state.export_pdf_path = result_path
            st.success("PDF generated successfully!")

        except Exception as e:
            st.error(f"PDF generation failed: {e}")
            logger.error("PDF generation error", exc_info=True)

# Show download button if PDF exists
if st.session_state.get("export_pdf_path"):
    pdf_path = st.session_state.export_pdf_path
    if Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        st.download_button(
            label="⬇️ Download PDF",
            data=pdf_bytes,
            file_name=Path(pdf_path).name,
            mime="application/pdf",
        )
```

---

## Google Sheets Export

```python
st.markdown("---")
st.subheader("📊 Google Sheets Export")

col1, col2 = st.columns([1, 3])
with col1:
    generate_sheets_btn = st.button("📊 Export to Google Sheets", type="primary")

if generate_sheets_btn:
    with st.spinner("Exporting to Google Sheets..."):
        try:
            session = _build_comparison_session()

            sheets_client = SheetsClient()
            sheet_url = sheets_client.create_comparison_sheet(session)

            st.session_state.export_sheet_url = sheet_url
            st.success("Google Sheet created!")

        except Exception as e:
            st.error(f"Sheets export failed: {e}")
            logger.error("Sheets export error", exc_info=True)

# Show link if Sheet was created
if st.session_state.get("export_sheet_url"):
    st.markdown(f"[📎 Open Google Sheet]({st.session_state.export_sheet_url})")
```

---

## Full render_export_stage() Implementation

```python
def render_export_stage():
    # Agent Notes
    st.text_area(
        "Agent Notes (optional — appears on PDF and Sheet)",
        key="agent_notes",
        height=100,
        placeholder="Add any notes for the client..."
    )

    st.markdown("---")

    # PDF Section
    st.subheader("📄 PDF Comparison Report")
    # ... (PDF generation code above)

    st.markdown("---")

    # Sheets Section
    st.subheader("📊 Google Sheets Export")
    # ... (Sheets export code above)

    st.markdown("---")

    # Re-export info
    st.info("You can re-generate exports after making changes. Go back to Review to edit data.")
```

---

## Imports Needed

Add to top of `streamlit_app.py` (some may already be there):

```python
from datetime import datetime
from pathlib import Path
import logging

from app.pdf_gen.generator import generate_comparison_pdf
from app.sheets.sheets_client import SheetsClient
```

**Note:** `SheetsClient` requires Google Sheets API credentials. If credentials aren't configured, the Sheets export button should fail gracefully with a helpful error message, not crash the app. The PDF export has no external dependencies beyond what's already installed.

---

## Edge Cases

1. **No Google credentials** — `SheetsClient()` may raise on init if `credentials.json` is missing. Wrap in try/except and show a clear message: "Google Sheets credentials not configured. See README for setup."

2. **Re-export** — Agent can click Generate PDF multiple times. Each click overwrites the previous file. Same for Sheets — creates a new sheet each time (doesn't update existing).

3. **Agent notes changes** — If the agent edits notes and re-generates, the new PDF/Sheet should include updated notes. No cache invalidation needed since we rebuild ComparisonSession each time.

4. **Large PDFs** — The comparison PDF shouldn't be large (a few pages), but wrap generation in try/except regardless.

5. **File path on Windows** — Use `Path()` for cross-platform compatibility. The `data/outputs/` directory may not exist — create it.

---

## What This Step Does NOT Include

- ❌ No email sending
- ❌ No Sheet update (always creates new)
- ❌ No PDF preview in browser
- ❌ No export history or versioning

---

## Verification

1. Run: `python -m streamlit run app/ui/streamlit_app.py`
2. Complete Steps 1-2 (Upload → Extract → Review → Approve)
3. Step 3 unlocks:
   - Enter agent notes
   - Click Generate PDF → spinner → success message → download button appears
   - Download PDF → opens correctly with all carrier data and agent notes
   - Click Export to Google Sheets → spinner → success or graceful error
   - If successful, link appears → opens in browser
4. Edit agent notes → re-generate PDF → new PDF includes updated notes
5. Go back to Step 2, change data, re-approve → re-export works with new data
