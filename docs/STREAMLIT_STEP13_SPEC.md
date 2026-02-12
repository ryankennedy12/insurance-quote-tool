# Phase 5: Streamlit UI — Step 13: Review & Edit Stage

> Place in `docs/`. Reference from CLAUDE.md.
> This replaces the Step 2 placeholder content in `app/ui/streamlit_app.py` with editable data tables for reviewing and correcting extracted insurance data.

---

## Overview

Step 13 builds out the Review stage where the agent:
1. Sees all extracted data organized by section (Premium Summary → Home → Auto → Umbrella)
2. Edits any incorrect values inline (coverage amounts, deductibles, premiums)
3. Reviews and edits endorsements, discounts, and AI-generated notes per carrier
4. Fills in missing current policy fields (especially auto/umbrella from PDF extraction)
5. Sees extraction warnings and validation issues inline
6. Clicks "Approve & Continue" to lock data and advance to Export

---

## Data Flow

```
Step 12 stores:
  st.session_state.carrier_bundles    → list[CarrierBundle]  (raw extraction)
  st.session_state.current_policy_data → CurrentPolicy or None
  st.session_state.extraction_warnings → list[str]

Step 13 works with:
  Deep copies of carrier_bundles → editable in UI
  Deep copy of current_policy_data → editable in UI

Step 13 stores on Approve:
  st.session_state.edited_bundles         → list[CarrierBundle]
  st.session_state.edited_current_policy  → CurrentPolicy or None
  st.session_state.review_complete = True
  st.session_state.current_step = 3
```

---

## UI Layout

### Extraction Warnings (top of Review stage)

```python
if st.session_state.extraction_warnings:
    with st.expander(f"⚠️ {len(warnings)} Extraction Warnings", expanded=True):
        for w in st.session_state.extraction_warnings:
            st.warning(w)
```

Show these first so the agent knows what needs attention.

---

### Current Policy Editor (if current_policy_data exists)

Only show if `st.session_state.current_policy_data` is not None.

```python
with st.expander("📋 Current Policy", expanded=True):
    cp = st.session_state.current_policy_data

    st.text_input("Current Carrier", value=cp.carrier_name, key="edit_cp_carrier_name")

    if "home" in sections:
        st.subheader("🏠 Home")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Premium", value=cp.home_premium or 0.0, key="edit_cp_home_premium")
            st.number_input("Dwelling", value=cp.home_dwelling or 0.0, key="edit_cp_home_dwelling")
            st.number_input("Other Structures", value=cp.home_other_structures or 0.0, key="edit_cp_home_other_structures")
            st.number_input("Personal Property", value=cp.home_personal_property or 0.0, key="edit_cp_home_personal_property")
        with col2:
            st.number_input("Liability", value=cp.home_liability or 0.0, key="edit_cp_home_liability")
            st.number_input("Loss of Use", value=cp.home_loss_of_use or 0.0, key="edit_cp_home_loss_of_use")
            st.number_input("Deductible", value=cp.home_deductible or 0.0, key="edit_cp_home_deductible")

    if "auto" in sections:
        st.subheader("🚗 Auto")
        st.info("💡 If current policy was extracted from PDF, auto fields may need manual entry.")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Premium", value=cp.auto_premium or 0.0, key="edit_cp_auto_premium")
            st.text_input("Liability Limits", value=cp.auto_limits or "", key="edit_cp_auto_limits")
        with col2:
            st.text_input("UM/UIM", value=cp.auto_um_uim or "", key="edit_cp_auto_um_uim")
            st.text_input("Comp Deductible", value=cp.auto_comp_deductible or "", key="edit_cp_auto_comp_deductible")
            st.number_input("Collision Deductible", value=cp.auto_collision_deductible or 0.0, key="edit_cp_auto_collision_deductible")

    if "umbrella" in sections:
        st.subheader("☂️ Umbrella")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Premium", value=cp.umbrella_premium or 0.0, key="edit_cp_umbrella_premium")
            st.text_input("Limits", value=cp.umbrella_limits or "", key="edit_cp_umbrella_limits")
        with col2:
            st.number_input("Deductible", value=cp.umbrella_deductible or 0.0, key="edit_cp_umbrella_deductible")
```

---

### Carrier Data Editors

One expander per carrier. Each shows the extracted data organized by section.

```python
for i, bundle in enumerate(st.session_state.carrier_bundles):
    with st.expander(f"📊 {bundle.carrier_name}", expanded=(i == 0)):
        _render_carrier_editor(i, bundle)
```

#### Per-Carrier Editor Layout

For each carrier, show sections based on what was extracted:

```python
def _render_carrier_editor(idx: int, bundle: CarrierBundle):
    sections = st.session_state.sections_included

    # --- Premium Summary ---
    st.markdown("**Premiums**")
    prem_cols = st.columns(len(sections))
    for j, section in enumerate(sections):
        quote = getattr(bundle, section)  # home, auto, or umbrella
        with prem_cols[j]:
            current_val = quote.annual_premium if quote else 0.0
            st.number_input(
                f"{section.title()} Premium",
                value=current_val,
                key=f"edit_carrier_{idx}_{section}_premium",
                step=100.0
            )

    # --- Home Details ---
    if "home" in sections and bundle.home:
        st.markdown("---")
        st.markdown("**🏠 Home Coverage**")
        _render_coverage_limits_editor(idx, "home", bundle.home)

    # --- Auto Details ---
    if "auto" in sections and bundle.auto:
        st.markdown("---")
        st.markdown("**🚗 Auto Coverage**")
        _render_coverage_limits_editor(idx, "auto", bundle.auto)

    # --- Umbrella Details ---
    if "umbrella" in sections and bundle.umbrella:
        st.markdown("---")
        st.markdown("**☂️ Umbrella Coverage**")
        _render_coverage_limits_editor(idx, "umbrella", bundle.umbrella)

    # --- Deductibles (home-level) ---
    if bundle.home:
        st.markdown("---")
        st.markdown("**Deductibles**")
        ded_cols = st.columns(2)
        with ded_cols[0]:
            st.number_input("All-Peril Deductible",
                          value=bundle.home.deductible or 0.0,
                          key=f"edit_carrier_{idx}_home_deductible", step=500.0)
        with ded_cols[1]:
            st.number_input("Wind/Hail Deductible",
                          value=bundle.home.wind_hail_deductible or 0.0,
                          key=f"edit_carrier_{idx}_wind_hail_deductible", step=500.0)

    # --- Endorsements ---
    st.markdown("---")
    st.markdown("**Endorsements**")
    all_endorsements = []
    for section in sections:
        quote = getattr(bundle, section)
        if quote and quote.endorsements:
            all_endorsements.extend(quote.endorsements)
    unique_endorsements = list(dict.fromkeys(all_endorsements))

    st.text_area(
        "Endorsements (one per line)",
        value="\n".join(unique_endorsements),
        key=f"edit_carrier_{idx}_endorsements",
        height=100
    )

    # --- Discounts ---
    st.markdown("**Discounts**")
    all_discounts = []
    for section in sections:
        quote = getattr(bundle, section)
        if quote and quote.discounts:
            all_discounts.extend(quote.discounts)
    unique_discounts = list(dict.fromkeys(all_discounts))

    st.text_area(
        "Discounts (one per line)",
        value="\n".join(unique_discounts),
        key=f"edit_carrier_{idx}_discounts",
        height=100
    )

    # --- AI Notes ---
    st.markdown("**Notes**")
    all_notes = []
    for section in sections:
        quote = getattr(bundle, section)
        if quote and quote.notes:
            all_notes.append(f"[{section.title()}] {quote.notes}")

    st.text_area(
        "Notes",
        value="\n".join(all_notes),
        key=f"edit_carrier_{idx}_notes",
        height=80
    )
```

#### Coverage Limits Editor Helper

```python
def _render_coverage_limits_editor(carrier_idx: int, section: str, quote: InsuranceQuote):
    """Render editable fields for coverage limits based on section type."""
    cl = quote.coverage_limits
    prefix = f"edit_carrier_{carrier_idx}_{section}"

    if section == "home":
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Dwelling", value=cl.dwelling or 0.0,
                          key=f"{prefix}_dwelling", step=10000.0)
            st.number_input("Other Structures", value=cl.other_structures or 0.0,
                          key=f"{prefix}_other_structures", step=1000.0)
            st.number_input("Personal Property", value=cl.personal_property or 0.0,
                          key=f"{prefix}_personal_property", step=1000.0)
        with col2:
            st.number_input("Loss of Use", value=cl.loss_of_use or 0.0,
                          key=f"{prefix}_loss_of_use", step=1000.0)
            st.number_input("Personal Liability", value=cl.personal_liability or 0.0,
                          key=f"{prefix}_personal_liability", step=50000.0)
            st.number_input("Medical Payments", value=cl.medical_payments or 0.0,
                          key=f"{prefix}_medical_payments", step=1000.0)

    elif section == "auto":
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("BI Per Person", value=cl.bi_per_person or 0.0,
                          key=f"{prefix}_bi_per_person", step=50000.0)
            st.number_input("BI Per Accident", value=cl.bi_per_accident or 0.0,
                          key=f"{prefix}_bi_per_accident", step=50000.0)
            st.number_input("PD Per Accident", value=cl.pd_per_accident or 0.0,
                          key=f"{prefix}_pd_per_accident", step=25000.0)
        with col2:
            st.number_input("CSL", value=cl.csl or 0.0,
                          key=f"{prefix}_csl", step=100000.0)
            st.number_input("UM/UIM BI Per Person", value=cl.um_bi_per_person or 0.0,
                          key=f"{prefix}_um_bi_per_person", step=50000.0)
            st.number_input("UM/UIM BI Per Accident", value=cl.um_bi_per_accident or 0.0,
                          key=f"{prefix}_um_bi_per_accident", step=50000.0)
        col3, col4 = st.columns(2)
        with col3:
            st.number_input("Comp Deductible", value=cl.comp_deductible or 0.0,
                          key=f"{prefix}_comp_deductible", step=100.0)
        with col4:
            st.number_input("Collision Deductible", value=cl.collision_deductible or 0.0,
                          key=f"{prefix}_collision_deductible", step=100.0)

    elif section == "umbrella":
        st.number_input("Umbrella Limit", value=cl.umbrella_limit or 0.0,
                      key=f"{prefix}_umbrella_limit", step=1000000.0)
```

---

## Approve & Continue Button

### Build Edited Models from Session State

```python
def _build_edited_bundles() -> list[CarrierBundle]:
    """Reconstruct CarrierBundle objects from edited session state values."""
    edited = []
    sections = st.session_state.sections_included

    for i, original_bundle in enumerate(st.session_state.carrier_bundles):
        home_quote = None
        auto_quote = None
        umbrella_quote = None

        if "home" in sections and original_bundle.home:
            home_quote = _build_edited_quote(i, "home", original_bundle.home)
        if "auto" in sections and original_bundle.auto:
            auto_quote = _build_edited_quote(i, "auto", original_bundle.auto)
        if "umbrella" in sections and original_bundle.umbrella:
            umbrella_quote = _build_edited_quote(i, "umbrella", original_bundle.umbrella)

        edited.append(CarrierBundle(
            carrier_name=original_bundle.carrier_name,
            home=home_quote,
            auto=auto_quote,
            umbrella=umbrella_quote,
        ))

    return edited


def _build_edited_quote(carrier_idx: int, section: str, original: InsuranceQuote) -> InsuranceQuote:
    """Reconstruct an InsuranceQuote from edited session state values."""
    prefix = f"edit_carrier_{carrier_idx}_{section}"

    # Read coverage limits from session state
    cl_fields = {}
    if section == "home":
        for field in ["dwelling", "other_structures", "personal_property",
                      "loss_of_use", "personal_liability", "medical_payments"]:
            val = st.session_state.get(f"{prefix}_{field}", 0.0)
            cl_fields[field] = val if val != 0.0 else None
    elif section == "auto":
        for field in ["bi_per_person", "bi_per_accident", "pd_per_accident",
                      "csl", "um_bi_per_person", "um_bi_per_accident",
                      "comp_deductible", "collision_deductible"]:
            val = st.session_state.get(f"{prefix}_{field}", 0.0)
            cl_fields[field] = val if val != 0.0 else None
    elif section == "umbrella":
        val = st.session_state.get(f"{prefix}_umbrella_limit", 0.0)
        cl_fields["umbrella_limit"] = val if val != 0.0 else None

    coverage_limits = CoverageLimits(**cl_fields)

    # Read premium
    premium = st.session_state.get(f"edit_carrier_{carrier_idx}_{section}_premium", 0.0)

    # Read deductibles (home only)
    deductible = None
    wind_hail_deductible = None
    if section == "home":
        deductible = st.session_state.get(f"edit_carrier_{carrier_idx}_home_deductible", 0.0)
        deductible = deductible if deductible != 0.0 else None
        wind_hail_deductible = st.session_state.get(f"edit_carrier_{carrier_idx}_wind_hail_deductible", 0.0)
        wind_hail_deductible = wind_hail_deductible if wind_hail_deductible != 0.0 else None

    # Read endorsements/discounts/notes from text areas
    endorsements_raw = st.session_state.get(f"edit_carrier_{carrier_idx}_endorsements", "")
    endorsements = [e.strip() for e in endorsements_raw.split("\n") if e.strip()]

    discounts_raw = st.session_state.get(f"edit_carrier_{carrier_idx}_discounts", "")
    discounts = [d.strip() for d in discounts_raw.split("\n") if d.strip()]

    notes_raw = st.session_state.get(f"edit_carrier_{carrier_idx}_notes", "")

    return InsuranceQuote(
        carrier_name=original.carrier_name,
        annual_premium=premium if premium != 0.0 else None,
        coverage_limits=coverage_limits,
        deductible=deductible,
        wind_hail_deductible=wind_hail_deductible,
        endorsements=endorsements,
        discounts=discounts,
        notes=notes_raw.strip() or None,
        # Preserve fields we don't edit in UI
        policy_type=original.policy_type,
        policy_number=original.policy_number,
        effective_date=original.effective_date,
        expiration_date=original.expiration_date,
    )


def _build_edited_current_policy() -> CurrentPolicy | None:
    """Reconstruct CurrentPolicy from edited session state values."""
    if st.session_state.current_policy_data is None:
        return None

    def clean_float(key: str) -> float | None:
        val = st.session_state.get(key, 0.0)
        return val if val != 0.0 else None

    def clean_str(key: str) -> str | None:
        val = st.session_state.get(key, "")
        return val.strip() if val.strip() else None

    return CurrentPolicy(
        carrier_name=st.session_state.get("edit_cp_carrier_name", "").strip(),
        home_premium=clean_float("edit_cp_home_premium"),
        home_dwelling=clean_float("edit_cp_home_dwelling"),
        home_other_structures=clean_float("edit_cp_home_other_structures"),
        home_personal_property=clean_float("edit_cp_home_personal_property"),
        home_liability=clean_float("edit_cp_home_liability"),
        home_loss_of_use=clean_float("edit_cp_home_loss_of_use"),
        home_deductible=clean_float("edit_cp_home_deductible"),
        auto_premium=clean_float("edit_cp_auto_premium"),
        auto_limits=clean_str("edit_cp_auto_limits"),
        auto_um_uim=clean_str("edit_cp_auto_um_uim"),
        auto_comp_deductible=clean_str("edit_cp_auto_comp_deductible"),
        auto_collision_deductible=clean_float("edit_cp_auto_collision_deductible"),
        umbrella_premium=clean_float("edit_cp_umbrella_premium"),
        umbrella_limits=clean_str("edit_cp_umbrella_limits"),
        umbrella_deductible=clean_float("edit_cp_umbrella_deductible"),
    )
```

### Approve Button Logic

```python
if st.button("✅ Approve & Continue", type="primary"):
    st.session_state.edited_bundles = _build_edited_bundles()
    st.session_state.edited_current_policy = _build_edited_current_policy()
    st.session_state.review_complete = True
    st.session_state.current_step = 3
    st.rerun()
```

---

## Important Implementation Notes

1. **CoverageLimits field names** — Before writing code, `grep` the actual `CoverageLimits` class in `models.py` to confirm exact field names. The spec above uses field names from the Step 12 refactor but these MUST be verified.

2. **InsuranceQuote fields** — Also verify which fields exist on InsuranceQuote (policy_type, policy_number, effective_date, expiration_date, etc.) to preserve them when reconstructing.

3. **0.0 → None conversion** — Same pattern as Step 12. Streamlit number_input defaults to 0.0; convert back to None for the model.

4. **Endorsements/Discounts are shared across sections** — The UI shows one combined endorsements text area per carrier (deduplicated from home/auto/umbrella). When rebuilding, apply the edited endorsements list to ALL section quotes in the bundle.

5. **Notes prefix stripping** — The display prepends `[Home]`, `[Auto]`, `[Umbrella]` prefixes. When rebuilding, store the full text as-is on the first non-None quote in the bundle.

6. **No new session state keys needed** — All editable values are stored via widget `key=` parameters. The `edited_bundles` and `edited_current_policy` are only built when Approve is clicked.

---

## What This Step Does NOT Include

- ❌ No export functionality (Step 14)
- ❌ No side-by-side comparison view (could add later as polish)
- ❌ No drag-and-drop carrier reordering
- ❌ No "undo" for edits (can re-extract from Step 1 if needed)
- ❌ No inline validation (e.g. "dwelling seems low") — just show extraction warnings at top

---

## Verification

1. Run: `python -m streamlit run app/ui/streamlit_app.py`
2. Complete Step 1: Upload PDFs, Extract All
3. Step 2 unlocks — verify:
   - Extraction warnings displayed at top (if any)
   - Current policy fields editable (if present)
   - Each carrier has an expander with premiums, coverage limits, deductibles, endorsements, discounts, notes
   - Coverage limit fields match the section type (home fields for home, auto fields for auto)
   - Edit a value → click Approve → verify edited_bundles contains the changed value
4. Step 3 unlocks after Approve
5. Go back to Step 1, re-extract → Step 2 resets (old edits cleared)
