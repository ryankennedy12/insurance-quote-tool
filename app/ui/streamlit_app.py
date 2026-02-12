"""
Streamlit UI — Insurance Quote Comparison Tool
Phase 5, Step 12: Upload Stage with real logic (current policy entry + carrier uploads + extraction)

Entry point: streamlit run app/ui/streamlit_app.py
"""

import streamlit as st
from pathlib import Path
from typing import Optional

from app.extraction.models import ComparisonSession, CarrierBundle, CurrentPolicy, InsuranceQuote
from app.extraction.ai_extractor import extract_and_validate

# Future imports (not needed yet):
# from app.sheets.sheets_client import SheetsClient
# from app.pdf_gen.generator import generate_comparison_pdf


def init_session_state() -> None:
    """Initialize all session state keys with defaults."""
    defaults = {
        # ── Wizard Navigation ──
        "current_step": 1,

        # ── Step 1: Upload Data ──
        "client_name": "",
        "sections_included": ["home"],
        "current_policy_mode": "Skip",
        "current_policy_data": None,
        "current_policy_pdf": None,

        # ── Carrier Data ──
        "carriers": [],

        # ── Extraction Results ──
        "extraction_complete": False,
        "carrier_bundles": [],
        "extraction_warnings": [],

        # ── Step 2: Review Data ──
        "review_complete": False,
        "edited_bundles": [],
        "edited_current_policy": None,

        # ── Step 3: Export ──
        "agent_notes": "",
        "export_pdf_path": None,
        "export_sheet_url": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions for Upload Stage
# ═══════════════════════════════════════════════════════════════════════════════

def _build_current_policy_from_form() -> CurrentPolicy:
    """Build CurrentPolicy from manual entry form session state (cp_* keys)."""
    carrier_name = st.session_state.get("cp_carrier_name", "").strip()
    if not carrier_name:
        raise ValueError("Current carrier name is required")

    def clean_float(key: str) -> Optional[float]:
        """Convert 0.0 to None (Streamlit number_input default is not a real value)."""
        value = st.session_state.get(key, 0.0)
        return None if value == 0.0 else value

    def clean_str(key: str) -> Optional[str]:
        """Convert empty string to None."""
        value = st.session_state.get(key, "")
        return None if not value.strip() else value.strip()

    # Special handling for loss_of_use: can be numeric or "ALS"
    loss_of_use_raw = st.session_state.get("cp_home_loss_of_use", "")
    loss_of_use = None
    if loss_of_use_raw:
        try:
            loss_of_use = float(loss_of_use_raw)
        except ValueError:
            # "ALS" or other text → store as None (user can edit in Review stage)
            loss_of_use = None

    return CurrentPolicy(
        carrier_name=carrier_name,
        home_premium=clean_float("cp_home_premium"),
        home_dwelling=clean_float("cp_home_dwelling"),
        home_other_structures=clean_float("cp_home_other_structures"),
        home_liability=clean_float("cp_home_liability"),
        home_personal_property=clean_float("cp_home_personal_property"),
        home_loss_of_use=loss_of_use,
        home_deductible=clean_float("cp_home_deductible"),
        auto_premium=clean_float("cp_auto_premium"),
        auto_limits=clean_str("cp_auto_limits"),
        auto_um_uim=clean_str("cp_auto_um_uim"),
        auto_comp_deductible=clean_str("cp_auto_comp_deductible"),
        auto_collision_deductible=clean_float("cp_auto_collision_deductible"),
        umbrella_premium=clean_float("cp_umbrella_premium"),
        umbrella_limits=clean_str("cp_umbrella_limits"),
        umbrella_deductible=clean_float("cp_umbrella_deductible"),
    )


def _build_current_policy_from_quote(quote: InsuranceQuote) -> CurrentPolicy:
    """Convert InsuranceQuote to CurrentPolicy (home fields only per spec)."""
    cl = quote.coverage_limits

    return CurrentPolicy(
        carrier_name=quote.carrier_name,
        home_premium=quote.annual_premium,
        home_dwelling=cl.dwelling,
        home_other_structures=cl.other_structures,
        home_personal_property=cl.personal_property,
        home_liability=cl.personal_liability,
        home_loss_of_use=cl.loss_of_use,
        home_deductible=quote.deductible if quote.deductible else None,
        # Auto and umbrella fields left as None (user fills in Review stage)
    )


def _validate_upload_stage() -> list[str]:
    """Validate upload stage before extraction. Returns list of error messages."""
    errors = []

    if not st.session_state.client_name.strip():
        errors.append("Client name is required")

    if not st.session_state.sections_included:
        errors.append("Select at least one policy section")

    named_carriers = [c for c in st.session_state.carriers if c.get("name", "").strip()]

    if len(named_carriers) < 2:
        errors.append("At least 2 carriers are required")

    # Check for duplicate carrier names
    names = [c["name"].strip() for c in named_carriers]
    duplicates = [n for n in names if names.count(n) > 1]
    if duplicates:
        errors.append(f"Duplicate carrier names found: {', '.join(set(duplicates))}. Please use unique names.")

    # Check each named carrier has at least one PDF
    for carrier in named_carriers:
        has_pdf = any(
            carrier.get(f"{section}_pdf") is not None
            for section in st.session_state.sections_included
        )
        if not has_pdf:
            errors.append(f"Carrier '{carrier['name']}' needs at least one PDF uploaded")

    return errors


def _add_carrier_callback() -> None:
    """Callback to add a new carrier slot."""
    if len(st.session_state.carriers) < 6:
        st.session_state.carriers.append({
            "name": "",
            "home_pdf": None,
            "auto_pdf": None,
            "umbrella_pdf": None
        })


def _remove_carrier_callback(index: int) -> None:
    """Callback to remove a carrier slot."""
    if len(st.session_state.carriers) > 2:
        st.session_state.carriers.pop(index)


def _render_current_policy_manual_form() -> None:
    """Render expandable manual entry form for current policy."""
    with st.expander("📝 Enter Current Policy Details", expanded=True):
        with st.form("current_policy_form"):
            # Carrier name (always visible)
            st.text_input(
                "Current Carrier Name",
                key="cp_carrier_name",
                help="Name of your current insurance carrier",
                placeholder="e.g., Erie Insurance, State Farm"
            )

            sections = st.session_state.sections_included

            # Home section
            if "home" in sections:
                st.subheader("🏠 Home Insurance")
                col1, col2 = st.columns(2)
                with col1:
                    st.number_input(
                        "Annual Home Premium ($)",
                        min_value=0.0,
                        step=100.0,
                        key="cp_home_premium",
                        format="%.2f"
                    )
                    st.number_input(
                        "Dwelling Coverage ($)",
                        min_value=0.0,
                        step=10000.0,
                        key="cp_home_dwelling",
                        format="%.0f"
                    )
                    st.number_input(
                        "Other Structures ($)",
                        min_value=0.0,
                        step=1000.0,
                        key="cp_home_other_structures",
                        format="%.0f"
                    )
                    st.number_input(
                        "Personal Property ($)",
                        min_value=0.0,
                        step=1000.0,
                        key="cp_home_personal_property",
                        format="%.0f"
                    )
                with col2:
                    st.number_input(
                        "Liability ($)",
                        min_value=0.0,
                        step=50000.0,
                        key="cp_home_liability",
                        format="%.0f"
                    )
                    st.text_input(
                        "Loss of Use",
                        key="cp_home_loss_of_use",
                        help="Dollar amount or 'ALS' for Actual Loss Sustained",
                        placeholder="e.g., 20000 or ALS"
                    )
                    st.number_input(
                        "Deductible ($)",
                        min_value=0.0,
                        step=500.0,
                        key="cp_home_deductible",
                        format="%.0f"
                    )

            # Auto section
            if "auto" in sections:
                st.subheader("🚗 Auto Insurance")
                col1, col2 = st.columns(2)
                with col1:
                    st.number_input(
                        "Annual Auto Premium ($)",
                        min_value=0.0,
                        step=100.0,
                        key="cp_auto_premium",
                        format="%.2f"
                    )
                    st.text_input(
                        "Liability Limits",
                        key="cp_auto_limits",
                        help="e.g., '500/500/250' or '1M CSL'",
                        placeholder="e.g., 500/500/250"
                    )
                    st.text_input(
                        "UM/UIM",
                        key="cp_auto_um_uim",
                        help="Uninsured/Underinsured Motorist coverage",
                        placeholder="e.g., 500/500"
                    )
                with col2:
                    st.text_input(
                        "Comp Deductible",
                        key="cp_auto_comp_deductible",
                        help="Comprehensive deductible and terms",
                        placeholder="e.g., $500"
                    )
                    st.number_input(
                        "Collision Deductible ($)",
                        min_value=0.0,
                        step=100.0,
                        key="cp_auto_collision_deductible",
                        format="%.0f"
                    )

            # Umbrella section
            if "umbrella" in sections:
                st.subheader("☂️ Umbrella Insurance")
                col1, col2 = st.columns(2)
                with col1:
                    st.number_input(
                        "Annual Umbrella Premium ($)",
                        min_value=0.0,
                        step=100.0,
                        key="cp_umbrella_premium",
                        format="%.2f"
                    )
                    st.text_input(
                        "Umbrella Limits",
                        key="cp_umbrella_limits",
                        help="e.g., '1M CSL', '2M CSL'",
                        placeholder="e.g., 1M CSL"
                    )
                with col2:
                    st.number_input(
                        "Umbrella Deductible ($)",
                        min_value=0.0,
                        step=100.0,
                        key="cp_umbrella_deductible",
                        format="%.0f"
                    )

            # Form submit button
            submitted = st.form_submit_button(
                "💾 Save Current Policy",
                type="primary",
                use_container_width=True
            )

            if submitted:
                try:
                    current_policy = _build_current_policy_from_form()
                    st.session_state.current_policy_data = current_policy
                    st.success(f"✅ Saved current policy for {current_policy.carrier_name}")
                except ValueError as e:
                    st.error(f"❌ {str(e)}")


def _render_current_policy_upload() -> None:
    """Render file upload + extraction for current policy dec page."""
    uploaded_file = st.file_uploader(
        "Upload Current Dec Page",
        type=["pdf"],
        key="current_policy_pdf"
    )

    st.info("ℹ️ Note: Extraction will only populate Home insurance fields. Auto and Umbrella fields can be added manually in the Review stage.")

    if uploaded_file:
        if st.button("Extract Current Policy", type="secondary"):
            with st.spinner("Extracting current policy..."):
                result = extract_and_validate(uploaded_file.read(), uploaded_file.name)

                if result.success and result.quote:
                    current_policy = _build_current_policy_from_quote(result.quote)
                    st.session_state.current_policy_data = current_policy

                    # Show what was extracted
                    st.success(f"✅ Extracted current policy from {result.quote.carrier_name}")

                    if "auto" in st.session_state.sections_included or "umbrella" in st.session_state.sections_included:
                        st.info("💡 Only Home fields were populated. You can add Auto/Umbrella data in the Review stage.")

                    # Show warnings if any
                    if result.warnings:
                        with st.expander("⚠️ Extraction Warnings", expanded=False):
                            for warning in result.warnings:
                                st.warning(warning)
                else:
                    st.error(f"❌ Extraction failed: {result.error}")


def _render_carrier_uploads() -> None:
    """Render dynamic carrier upload section with add/remove."""
    st.subheader("📋 Carrier Quotes")

    # Initialize with minimum 2 carriers
    if not st.session_state.carriers or len(st.session_state.carriers) < 2:
        st.session_state.carriers = [
            {"name": "", "home_pdf": None, "auto_pdf": None, "umbrella_pdf": None},
            {"name": "", "home_pdf": None, "auto_pdf": None, "umbrella_pdf": None},
        ]

    # Render each carrier
    for i, carrier in enumerate(st.session_state.carriers):
        with st.container(border=True):
            # Header row: name input + remove button
            col_name, col_remove = st.columns([5, 1])

            with col_name:
                carrier_name = st.text_input(
                    f"Carrier {i + 1} Name",
                    value=carrier.get("name", ""),
                    key=f"carrier_name_{i}",
                    placeholder="e.g., Erie Insurance, State Farm",
                    label_visibility="collapsed"
                )
                # Update carrier dict (Streamlit doesn't auto-update nested dicts)
                st.session_state.carriers[i]["name"] = carrier_name

            with col_remove:
                # Only allow removal if more than 2 carriers
                if len(st.session_state.carriers) > 2:
                    st.button(
                        "🗑️",
                        key=f"remove_carrier_{i}",
                        help="Remove this carrier",
                        on_click=_remove_carrier_callback,
                        args=(i,)
                    )
                else:
                    # Placeholder to maintain alignment
                    st.write("")

            # File uploaders (only for selected sections)
            sections = st.session_state.sections_included
            if sections:
                upload_cols = st.columns(len(sections))
                for j, section in enumerate(sections):
                    with upload_cols[j]:
                        uploaded_file = st.file_uploader(
                            f"{section.title()} PDF",
                            type=["pdf"],
                            key=f"carrier_{i}_{section}_pdf",
                            label_visibility="visible"
                        )
                        # Store file in carrier dict
                        st.session_state.carriers[i][f"{section}_pdf"] = uploaded_file
            else:
                st.info("👆 Select at least one policy section above to upload quotes")

    # Add carrier button (max 6)
    if len(st.session_state.carriers) < 6:
        st.button(
            "➕ Add Another Carrier",
            key="add_carrier_btn",
            on_click=_add_carrier_callback,
            use_container_width=False
        )
    else:
        st.info("Maximum 6 carriers reached")


def render_upload_stage() -> None:
    """Step 1: Upload & Extract — Full implementation with real logic."""
    # Client Name
    st.text_input("Client Name", key="client_name")

    # Section Selection
    st.multiselect(
        "Policy Sections to Compare",
        options=["home", "auto", "umbrella"],
        default=["home"],
        key="sections_included"
    )

    # Current Policy Mode
    st.radio(
        "Current Policy",
        options=["Skip", "Enter Manually", "Upload Dec Page PDF"],
        key="current_policy_mode",
        horizontal=True
    )

    # Current Policy Entry (3 modes)
    if st.session_state.current_policy_mode == "Enter Manually":
        _render_current_policy_manual_form()

    elif st.session_state.current_policy_mode == "Upload Dec Page PDF":
        _render_current_policy_upload()

    # Carrier Uploads
    _render_carrier_uploads()

    # Extract All Button with validation and extraction pipeline
    st.markdown("---")

    if st.button("🔍 Extract All Quotes", type="primary", use_container_width=True):
        # Validation
        errors = _validate_upload_stage()

        if errors:
            st.error("**Cannot extract - please fix the following:**")
            for error in errors:
                st.markdown(f"- {error}")
        else:
            # Initialize results
            carrier_bundles = []
            all_warnings = []

            # Filter to named carriers only
            named_carriers = [
                c for c in st.session_state.carriers
                if c.get("name", "").strip()
            ]

            # Count total PDFs for progress tracking
            total_pdfs = sum(
                1 for c in named_carriers
                for s in st.session_state.sections_included
                if c.get(f"{s}_pdf") is not None
            )

            # Create progress tracking widgets
            progress_bar = st.progress(0.0, text="Starting extraction...")
            status_container = st.status("Extracting quotes...", expanded=True)

            pdf_count = 0

            # Extract each carrier's PDFs
            for carrier_dict in named_carriers:
                home_quote = None
                auto_quote = None
                umbrella_quote = None

                with status_container:
                    st.write(f"**Processing {carrier_dict['name']}...**")

                for section in st.session_state.sections_included:
                    pdf_file = carrier_dict.get(f"{section}_pdf")
                    if pdf_file is None:
                        continue

                    pdf_count += 1
                    progress_pct = pdf_count / total_pdfs
                    progress_bar.progress(
                        progress_pct,
                        text=f"Extracting {pdf_count}/{total_pdfs}: {carrier_dict['name']} - {section.title()}"
                    )

                    with status_container:
                        st.write(f"  → Extracting {section.title()} quote...")

                    # Call extraction API
                    result = extract_and_validate(pdf_file.read(), pdf_file.name)

                    if result.success and result.quote:
                        # Store quote in appropriate slot
                        if section == "home":
                            home_quote = result.quote
                        elif section == "auto":
                            auto_quote = result.quote
                        elif section == "umbrella":
                            umbrella_quote = result.quote

                        # Collect warnings
                        if result.warnings:
                            for w in result.warnings:
                                all_warnings.append(f"**{carrier_dict['name']}** ({section}): {w}")

                        with status_container:
                            st.write(f"    ✅ Success (confidence: {result.quote.confidence})")
                    else:
                        # Extraction failed - log as warning
                        error_msg = result.error or "Extraction failed"
                        all_warnings.append(f"❌ **{carrier_dict['name']}** ({section}): {error_msg}")
                        with status_container:
                            st.write(f"    ⚠️ Failed: {error_msg}")

                # Build carrier bundle (even if some quotes failed)
                bundle = CarrierBundle(
                    carrier_name=carrier_dict["name"],
                    home=home_quote,
                    auto=auto_quote,
                    umbrella=umbrella_quote,
                )
                carrier_bundles.append(bundle)

            # Finalize progress
            progress_bar.progress(1.0, text=f"✅ Extraction complete - {pdf_count} PDFs processed")
            status_container.update(label="Extraction complete!", state="complete", expanded=False)

            # Store results in session state
            st.session_state.carrier_bundles = carrier_bundles
            st.session_state.extraction_warnings = all_warnings
            st.session_state.extraction_complete = True
            st.session_state.current_step = 2

            # Reset downstream state (re-extraction invalidates edits/exports)
            st.session_state.review_complete = False
            st.session_state.edited_bundles = []
            st.session_state.edited_current_policy = None
            st.session_state.export_pdf_path = None
            st.session_state.export_sheet_url = None

            # Show success summary
            st.success(f"🎉 Successfully extracted {pdf_count} PDFs across {len(carrier_bundles)} carriers")

            # Show warnings in expandable section
            if all_warnings:
                with st.expander(f"⚠️ {len(all_warnings)} warnings/errors - click to review", expanded=True):
                    for warning in all_warnings:
                        st.warning(warning, icon="⚠️")

            # Auto-advance to review stage
            st.rerun()


def render_review_stage() -> None:
    """Step 2: Review & Edit — placeholder UI."""
    st.info("Editable data tables will go here (Step 13)")

    # Approve & Continue button
    col1, col2 = st.columns([1, 4])
    with col1:
        approve_btn = st.button("✅ Approve & Continue", type="primary")

    if approve_btn:
        st.session_state.review_complete = True
        st.session_state.current_step = 3
        st.rerun()


def render_export_stage() -> None:
    """Step 3: Export — placeholder UI."""
    # Agent Notes
    st.text_area(
        "Agent Notes (optional — appears on PDF)",
        key="agent_notes",
        height=100
    )

    st.info("Export buttons will go here (Step 14)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("📄 Generate PDF", disabled=True)
    with col2:
        st.button("📊 Export to Google Sheets", disabled=True)


def render_sidebar() -> None:
    """Sidebar with logo, session info, and reset button."""
    with st.sidebar:
        # Logo
        logo_path = Path("assets/logo_transparent.png")
        if logo_path.exists():
            st.image(str(logo_path), width=200)

        st.markdown("---")

        # Session Info
        if st.session_state.client_name:
            st.markdown(f"**Client:** {st.session_state.client_name}")

        if st.session_state.carriers:
            st.markdown(f"**Carriers:** {len(st.session_state.carriers)}")

        if st.session_state.sections_included:
            st.markdown(f"**Sections:** {', '.join(st.session_state.sections_included)}")

        st.markdown("---")

        # Reset Button
        if st.button("🔄 Reset Session"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def main() -> None:
    """Main application entry point."""
    st.set_page_config(
        page_title="Scioto Insurance — Quote Comparison",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize session state
    init_session_state()

    # Title
    st.title("🏠 Scioto Insurance Group — Quote Comparison")

    # Sidebar
    render_sidebar()

    # ── Step 1: Upload & Extract ──
    step1_expanded = (st.session_state.current_step == 1)
    step1_title = "Step 1: Upload & Extract ✅" if st.session_state.extraction_complete else "Step 1: Upload & Extract"

    with st.expander(step1_title, expanded=step1_expanded):
        render_upload_stage()

    # ── Step 2: Review & Edit ──
    if st.session_state.extraction_complete:
        step2_expanded = (st.session_state.current_step == 2)
        step2_title = "Step 2: Review & Edit ✅" if st.session_state.review_complete else "Step 2: Review & Edit"

        with st.expander(step2_title, expanded=step2_expanded):
            render_review_stage()

    # ── Step 3: Export ──
    if st.session_state.review_complete:
        step3_expanded = (st.session_state.current_step == 3)

        with st.expander("Step 3: Export", expanded=step3_expanded):
            render_export_stage()


if __name__ == "__main__":
    main()
