# Phase 5: Streamlit UI — Step 12: Upload Stage (Real Logic)

> Place in `docs/`. Reference from CLAUDE.md.
> This replaces the Step 1 placeholder content in `app/ui/streamlit_app.py` with real upload, carrier grouping, and extraction logic.

---

## Overview

Step 12 builds out the Upload stage with:
1. Client name + section selection (already wired from Step 11)
2. Current policy entry — manual form OR PDF upload with Gemini extraction
3. Dynamic carrier grouping — add/remove carriers, upload PDFs per carrier per section
4. "Extract All" button that runs the Gemini pipeline on all uploaded PDFs

---

## Current Policy Section

### Three Modes (radio button, already in skeleton)

**Skip** — No current policy. `current_policy_data` stays None.

**Enter Manually** — Expandable form with fields matching `CurrentPolicy` model:

```python
with st.form("current_policy_form"):
    st.text_input("Current Carrier Name", key="cp_carrier_name")

    # Show fields based on selected sections
    if "home" in st.session_state.sections_included:
        st.subheader("Home")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Annual Home Premium", min_value=0.0, step=100.0, key="cp_home_premium")
            st.number_input("Dwelling Coverage", min_value=0.0, step=10000.0, key="cp_home_dwelling")
            st.number_input("Other Structures", min_value=0.0, step=1000.0, key="cp_home_other_structures")
            st.number_input("Personal Property", min_value=0.0, step=1000.0, key="cp_home_personal_property")
        with col2:
            st.number_input("Liability", min_value=0.0, step=50000.0, key="cp_home_liability")
            st.text_input("Loss of Use", key="cp_home_loss_of_use",
                         help="Dollar amount or 'ALS' for Actual Loss Sustained")
            st.number_input("Deductible", min_value=0.0, step=500.0, key="cp_home_deductible")

    if "auto" in st.session_state.sections_included:
        st.subheader("Auto")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Annual Auto Premium", min_value=0.0, step=100.0, key="cp_auto_premium")
            st.text_input("Liability Limits", key="cp_auto_limits",
                         help="e.g. '500/500/250' or '1M CSL'")
        with col2:
            st.text_input("UM/UIM", key="cp_auto_um_uim")
            st.text_input("Comp Deductible", key="cp_auto_comp_deductible")
            st.number_input("Collision Deductible", min_value=0.0, step=100.0, key="cp_auto_collision_deductible")

    if "umbrella" in st.session_state.sections_included:
        st.subheader("Umbrella")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Annual Umbrella Premium", min_value=0.0, step=100.0, key="cp_umbrella_premium")
            st.text_input("Umbrella Limits", key="cp_umbrella_limits", help="e.g. '1M CSL'")
        with col2:
            st.number_input("Umbrella Deductible", min_value=0.0, step=100.0, key="cp_umbrella_deductible")

    submitted = st.form_submit_button("Save Current Policy")
    if submitted:
        # Build CurrentPolicy from form fields
        # Store in st.session_state.current_policy_data
```

**Upload Dec Page PDF** — File uploader + extract button:

```python
uploaded_file = st.file_uploader("Upload Current Dec Page", type=["pdf"],
                                  key="current_policy_pdf")
if uploaded_file:
    if st.button("Extract Current Policy"):
        with st.spinner("Extracting current policy..."):
            # Call extract_and_validate(uploaded_file.read(), uploaded_file.name)
            # Convert InsuranceQuote → CurrentPolicy (map fields)
            # Store in st.session_state.current_policy_data
            # Show success message with extracted data summary
```

### CurrentPolicy Builder Helper

```python
def _build_current_policy_from_form() -> CurrentPolicy:
    """Build CurrentPolicy from manual entry form fields."""
    # Read all cp_* keys from session_state
    # Convert 0.0 values to None (user didn't fill them in)
    # Return CurrentPolicy object

def _build_current_policy_from_quote(quote: InsuranceQuote) -> CurrentPolicy:
    """Convert an extracted InsuranceQuote into a CurrentPolicy.

    Maps coverage_limits dict keys to CurrentPolicy fields.
    """
    return CurrentPolicy(
        carrier_name=quote.carrier_name,
        home_premium=quote.annual_premium,
        home_dwelling=quote.coverage_limits.get("dwelling"),
        home_other_structures=quote.coverage_limits.get("other_structures"),
        home_liability=quote.coverage_limits.get("personal_liability"),
        home_personal_property=quote.coverage_limits.get("personal_property"),
        home_loss_of_use=quote.coverage_limits.get("loss_of_use"),
        home_deductible=quote.deductible,
        # Auto and umbrella fields would need separate PDFs or manual entry
    )
```

---

## Carrier Upload Section

### Dynamic Carrier List

Carriers are stored in `st.session_state.carriers` as a list of dicts:

```python
# Each carrier dict:
{
    "name": "Erie Insurance",      # Text input
    "home_pdf": None,              # UploadedFile or None
    "auto_pdf": None,              # UploadedFile or None
    "umbrella_pdf": None,          # UploadedFile or None
}
```

### UI Structure

```python
def render_carrier_uploads():
    st.subheader("Carrier Quotes")

    # Ensure at least 2 carriers
    if len(st.session_state.carriers) < 2:
        st.session_state.carriers = [
            {"name": "", "home_pdf": None, "auto_pdf": None, "umbrella_pdf": None},
            {"name": "", "home_pdf": None, "auto_pdf": None, "umbrella_pdf": None},
        ]

    for i, carrier in enumerate(st.session_state.carriers):
        with st.container(border=True):
            col_name, col_remove = st.columns([4, 1])
            with col_name:
                carrier["name"] = st.text_input(
                    f"Carrier {i + 1} Name",
                    value=carrier["name"],
                    key=f"carrier_name_{i}"
                )
            with col_remove:
                if len(st.session_state.carriers) > 2:
                    if st.button("🗑️", key=f"remove_carrier_{i}"):
                        st.session_state.carriers.pop(i)
                        st.rerun()

            # Only show uploaders for selected sections
            upload_cols = st.columns(len(st.session_state.sections_included))
            for j, section in enumerate(st.session_state.sections_included):
                with upload_cols[j]:
                    uploaded = st.file_uploader(
                        f"{section.title()} PDF",
                        type=["pdf"],
                        key=f"carrier_{i}_{section}_pdf"
                    )
                    if uploaded:
                        carrier[f"{section}_pdf"] = uploaded

    # Add carrier button (max 6)
    if len(st.session_state.carriers) < 6:
        if st.button("➕ Add Another Carrier"):
            st.session_state.carriers.append(
                {"name": "", "home_pdf": None, "auto_pdf": None, "umbrella_pdf": None}
            )
            st.rerun()
```

---

## Extract All Button

### Validation Before Extraction

```python
def _validate_upload_stage() -> list[str]:
    """Check that required fields are filled before extraction."""
    errors = []

    if not st.session_state.client_name.strip():
        errors.append("Client name is required")

    if not st.session_state.sections_included:
        errors.append("Select at least one section to compare")

    carriers = st.session_state.carriers
    named_carriers = [c for c in carriers if c["name"].strip()]
    if len(named_carriers) < 2:
        errors.append("At least 2 carriers with names are required")

    # Check that each named carrier has at least one PDF uploaded
    for carrier in named_carriers:
        has_pdf = any(
            carrier.get(f"{section}_pdf") is not None
            for section in st.session_state.sections_included
        )
        if not has_pdf:
            errors.append(f"Carrier '{carrier['name']}' needs at least one PDF")

    return errors
```

### Extraction Logic

```python
if st.button("🔍 Extract All", type="primary"):
    errors = _validate_upload_stage()
    if errors:
        for error in errors:
            st.error(error)
    else:
        carrier_bundles = []
        all_warnings = []

        progress = st.progress(0)
        status = st.status("Extracting quotes...", expanded=True)

        named_carriers = [c for c in st.session_state.carriers if c["name"].strip()]
        total_pdfs = sum(
            1 for c in named_carriers
            for s in st.session_state.sections_included
            if c.get(f"{s}_pdf") is not None
        )
        pdf_count = 0

        for carrier_dict in named_carriers:
            home_quote = None
            auto_quote = None
            umbrella_quote = None

            for section in st.session_state.sections_included:
                pdf_file = carrier_dict.get(f"{section}_pdf")
                if pdf_file is None:
                    continue

                pdf_count += 1
                progress.progress(pdf_count / total_pdfs)
                status.write(f"Extracting {carrier_dict['name']} — {section.title()}...")

                result = extract_and_validate(pdf_file.read(), pdf_file.name)

                if result.success and result.quote:
                    if section == "home":
                        home_quote = result.quote
                    elif section == "auto":
                        auto_quote = result.quote
                    elif section == "umbrella":
                        umbrella_quote = result.quote

                    if result.warnings:
                        all_warnings.extend(
                            [f"{carrier_dict['name']} ({section}): {w}" for w in result.warnings]
                        )
                else:
                    all_warnings.append(
                        f"⚠️ {carrier_dict['name']} ({section}): {result.error or 'Extraction failed'}"
                    )

            bundle = CarrierBundle(
                carrier_name=carrier_dict["name"],
                home=home_quote,
                auto=auto_quote,
                umbrella=umbrella_quote,
            )
            carrier_bundles.append(bundle)

        progress.progress(1.0)
        status.update(label="Extraction complete!", state="complete")

        # Store results
        st.session_state.carrier_bundles = carrier_bundles
        st.session_state.extraction_warnings = all_warnings
        st.session_state.extraction_complete = True
        st.session_state.current_step = 2

        # Show summary
        st.success(f"Extracted {pdf_count} PDFs across {len(carrier_bundles)} carriers")
        if all_warnings:
            with st.expander(f"⚠️ {len(all_warnings)} warnings"):
                for w in all_warnings:
                    st.warning(w)

        st.rerun()
```

---

## Imports Needed

Add to top of `streamlit_app.py`:

```python
from app.extraction.models import (
    ComparisonSession, CarrierBundle, CurrentPolicy, InsuranceQuote
)
from app.extraction.ai_extractor import extract_and_validate
```

---

## Session State Updates

Add to initialization (if not already present):

```python
# These should already exist from Step 11, but verify:
"current_policy_mode": "skip",
"current_policy_data": None,
"current_policy_pdf": None,
"carriers": [],
"extraction_complete": False,
"carrier_bundles": [],
"extraction_warnings": [],
```

---

## Edge Cases to Handle

1. **File uploader key stability** — Streamlit file uploaders reset on rerun. Use unique keys per carrier index. If a carrier is removed, indices shift — keys must account for this (use carrier index, not a persistent ID for v1).

2. **Large PDFs** — Gemini has upload limits. The extraction pipeline already handles this with error returns. Surface the error in the warnings list.

3. **Re-extraction** — If the agent goes back to Step 1 and clicks Extract again, reset Steps 2 and 3:
```python
st.session_state.review_complete = False
st.session_state.edited_bundles = []
st.session_state.edited_current_policy = None
st.session_state.export_pdf_path = None
st.session_state.export_sheet_url = None
```

4. **Section changes after carrier upload** — If the agent changes sections_included after uploading PDFs, some PDFs may become irrelevant. Don't delete them — just ignore sections not in `sections_included` during extraction.

5. **Empty carrier slots** — Skip carriers with no name during extraction. Don't error on them.

---

## What This Step Does NOT Include

- ❌ No editable review tables (Step 13)
- ❌ No export functionality (Step 14)
- ❌ No PDF preview
- ❌ No drag-and-drop reordering of carriers
- ❌ No saved sessions or history

---

## Verification

1. Run: `streamlit run app/ui/streamlit_app.py`
2. Enter a client name, select Home + Auto sections
3. Choose "Enter Manually" for current policy — form fields appear for Home and Auto only
4. Switch to "Upload Dec Page PDF" — file uploader appears
5. Add 3 carriers with names, upload a PDF for each
6. Click Extract All — progress bar shows, extraction runs
7. If no real PDFs available, verify the UI flow works (extraction will fail gracefully with warnings)
8. Verify warnings display correctly
9. Verify Step 2 unlocks after extraction
10. Verify Reset clears everything including uploaded files
