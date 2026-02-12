# Phase 5: Streamlit UI — Step 11: Session State & Wizard Skeleton

> Place in `docs/`. Reference from CLAUDE.md.
> This is the navigation shell only — no extraction logic, no Sheets/PDF export. Just the page structure and state management.

---

## Overview

Single-page Streamlit app with a wizard-style flow. Three stages expand sequentially — the agent completes each stage before the next unlocks. All state lives in `st.session_state`.

File: `app/ui/streamlit_app.py` (main entry point, run with `streamlit run app/ui/streamlit_app.py`)

---

## Session State Schema

```python
# Initialize in st.session_state if not present:

# ── Wizard Navigation ──
"current_step": 1,              # 1=Upload, 2=Review, 3=Export

# ── Step 1: Upload Data ──
"client_name": "",
"sections_included": [],        # ["home", "auto", "umbrella"]
"current_policy_mode": "skip",  # "skip", "manual", "upload"
"current_policy_data": None,    # CurrentPolicy object or None
"current_policy_pdf": None,     # Uploaded PDF bytes (if mode="upload")

# ── Carrier Data ──
"carriers": [],                 # List of dicts:
                                # [{"name": "Erie", "home_pdf": bytes|None,
                                #   "auto_pdf": bytes|None, "umbrella_pdf": bytes|None}]

# ── Extraction Results ──
"extraction_complete": False,
"carrier_bundles": [],          # List of CarrierBundle objects (after extraction)
"extraction_warnings": [],      # List of warning strings

# ── Step 2: Review Data ──
"review_complete": False,
"edited_bundles": [],           # CarrierBundle objects after agent edits
"edited_current_policy": None,  # CurrentPolicy after agent edits

# ── Step 3: Export ──
"agent_notes": "",
"export_pdf_path": None,
"export_sheet_url": None,
```

---

## Page Layout

```
┌─────────────────────────────────────────────────┐
│  🏠 Scioto Insurance Group — Quote Comparison   │  ← st.title + branding
│                                                   │
│  ┌─ Step 1: Upload & Extract ──────────── ✅ ──┐ │  ← st.expander (expanded when active)
│  │  [Client name, sections, current policy,    │ │
│  │   carrier uploads, Extract button]          │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ┌─ Step 2: Review & Edit ──────────── 🔒 ────┐ │  ← st.expander (collapsed/disabled)
│  │  [Editable tables, validation warnings,     │ │
│  │   endorsement corrections]                  │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ┌─ Step 3: Export ────────────────── 🔒 ────┐  │  ← st.expander (collapsed/disabled)
│  │  [Agent notes, PDF download, Sheets link]  │  │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ── Sidebar ──                                    │
│  [Reset Session] button                           │
│  Session info (client name, carrier count)        │
└─────────────────────────────────────────────────┘
```

---

## Wizard Logic

### Step Progression
- **Step 1 → Step 2:** Unlocks when `extraction_complete == True`
- **Step 2 → Step 3:** Unlocks when `review_complete == True`
- Agent can always go back to earlier steps (expanders stay clickable)
- Going back to Step 1 and re-extracting resets Steps 2 and 3

### Expander Behavior
```python
# Step 1: Always expanded on first load, collapsible after completion
step1_expanded = (st.session_state.current_step == 1)
with st.expander("Step 1: Upload & Extract ✅" if extraction_complete else "Step 1: Upload & Extract",
                  expanded=step1_expanded):
    render_upload_stage()

# Step 2: Only rendered if extraction is complete
if st.session_state.extraction_complete:
    step2_expanded = (st.session_state.current_step == 2)
    with st.expander("Step 2: Review & Edit ✅" if review_complete else "Step 2: Review & Edit",
                      expanded=step2_expanded):
        render_review_stage()

# Step 3: Only rendered if review is complete
if st.session_state.review_complete:
    step3_expanded = (st.session_state.current_step == 3)
    with st.expander("Step 3: Export", expanded=step3_expanded):
        render_export_stage()
```

---

## Step 1 Skeleton (Upload Stage — placeholder content)

For this step, just build the UI structure with placeholder widgets. Real logic comes in Step 12.

```python
def render_upload_stage():
    # Client Name
    st.text_input("Client Name", key="client_name")

    # Section Selection
    st.multiselect("Policy Sections to Compare",
                   options=["home", "auto", "umbrella"],
                   default=["home"],
                   key="sections_included")

    # Current Policy Mode
    st.radio("Current Policy",
             options=["Skip", "Enter Manually", "Upload Dec Page PDF"],
             key="current_policy_mode",
             horizontal=True)

    if st.session_state.current_policy_mode == "Enter Manually":
        st.info("Manual entry form will go here (Step 12)")

    elif st.session_state.current_policy_mode == "Upload Dec Page PDF":
        st.file_uploader("Upload Current Dec Page", type=["pdf"],
                         key="current_policy_pdf")

    # Carrier Uploads
    st.subheader("Carrier Quotes")
    st.info("Carrier upload section will go here (Step 12)")

    # Extract Button (placeholder)
    col1, col2 = st.columns([1, 4])
    with col1:
        extract_btn = st.button("🔍 Extract All", type="primary",
                                disabled=not st.session_state.client_name)
    if extract_btn:
        st.session_state.extraction_complete = True
        st.session_state.current_step = 2
        st.rerun()
```

---

## Step 2 Skeleton (Review Stage — placeholder content)

```python
def render_review_stage():
    st.info("Editable data tables will go here (Step 13)")

    # Approve & Continue button
    col1, col2 = st.columns([1, 4])
    with col1:
        approve_btn = st.button("✅ Approve & Continue", type="primary")
    if approve_btn:
        st.session_state.review_complete = True
        st.session_state.current_step = 3
        st.rerun()
```

---

## Step 3 Skeleton (Export Stage — placeholder content)

```python
def render_export_stage():
    # Agent Notes
    st.text_area("Agent Notes (optional — appears on PDF)",
                 key="agent_notes",
                 height=100)

    st.info("Export buttons will go here (Step 14)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("📄 Generate PDF", disabled=True)
    with col2:
        st.button("📊 Export to Google Sheets", disabled=True)
```

---

## Sidebar

```python
with st.sidebar:
    st.image("assets/logo_transparent.png", width=200)
    st.markdown("---")

    if st.session_state.client_name:
        st.markdown(f"**Client:** {st.session_state.client_name}")

    if st.session_state.carriers:
        st.markdown(f"**Carriers:** {len(st.session_state.carriers)}")

    if st.session_state.sections_included:
        st.markdown(f"**Sections:** {', '.join(st.session_state.sections_included)}")

    st.markdown("---")

    if st.button("🔄 Reset Session"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
```

---

## File Structure

```
app/ui/
├── __init__.py          # Already exists (empty)
├── streamlit_app.py     # Main entry point (THIS FILE)
└── components/          # Create this directory for future component modules
    └── __init__.py
```

---

## Streamlit Config

Create `.streamlit/config.toml` in project root:

```toml
[theme]
primaryColor = "#871c30"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f8f0e8"
textColor = "#282828"
font = "sans serif"

[server]
maxUploadSize = 25
```

---

## What This Step Does NOT Include

- ❌ No actual PDF extraction logic (Step 12)
- ❌ No manual entry form fields for current policy (Step 12)
- ❌ No carrier add/remove dynamic UI (Step 12)
- ❌ No editable data tables (Step 13)
- ❌ No real export functionality (Step 14)
- ❌ No error handling for extraction failures (Step 12)

The Extract button just flips `extraction_complete = True` for now. The Approve button just flips `review_complete = True`. These get replaced with real logic in later steps.

---

## Verification

1. Run: `streamlit run app/ui/streamlit_app.py`
2. Confirm: Page loads with title and Step 1 expanded
3. Confirm: Type a client name, click Extract → Step 2 appears
4. Confirm: Click Approve → Step 3 appears
5. Confirm: Sidebar shows client info and Reset button works
6. Confirm: Reset clears all state and returns to Step 1
7. Confirm: Maroon theme applied (primary color #871c30)

---

## Imports

```python
import streamlit as st
from pathlib import Path

# Future imports (not needed yet):
# from app.extraction.models import ComparisonSession, CarrierBundle, CurrentPolicy
# from app.extraction.ai_extractor import extract_and_validate
# from app.sheets.sheets_client import SheetsClient
# from app.pdf_gen.generator import generate_comparison_pdf
```

---

## Key Patterns for Streamlit

- **Use `key=` on all input widgets** — Streamlit binds widget values to session_state keys automatically
- **Use `st.rerun()`** after state changes that should update the UI (not `st.experimental_rerun()` — deprecated)
- **Guard against missing keys** with `st.session_state.get("key", default)`
- **Initialize state once** with a helper function called at top of main()
