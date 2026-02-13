"""
Streamlit UI — Insurance Quote Comparison Tool
Phase 5, Steps 12-14: Upload, Review & Edit, Export Stages

Entry point: streamlit run app/ui/streamlit_app.py
"""

import base64
import streamlit as st
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.extraction.models import ComparisonSession, CarrierBundle, CurrentPolicy, InsuranceQuote, CoverageLimits
from app.extraction.ai_extractor import extract_and_validate
from app.pdf_gen.generator import generate_comparison_pdf
from app.sheets.sheets_client import SheetsClient

logger = logging.getLogger(__name__)


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


def _render_coverage_limits_editor(carrier_idx: int, section: str, quote: InsuranceQuote) -> None:
    """Render editable fields for coverage limits based on section type."""
    cl = quote.coverage_limits
    prefix = f"edit_carrier_{carrier_idx}_{section}"

    if section == "home":
        col1, col2 = st.columns(2)
        with col1:
            st.number_input(
                "Dwelling",
                value=cl.dwelling or 0.0,
                key=f"{prefix}_dwelling",
                step=10000.0,
                format="%.0f"
            )
            st.number_input(
                "Other Structures",
                value=cl.other_structures or 0.0,
                key=f"{prefix}_other_structures",
                step=1000.0,
                format="%.0f"
            )
            st.number_input(
                "Personal Property",
                value=cl.personal_property or 0.0,
                key=f"{prefix}_personal_property",
                step=1000.0,
                format="%.0f"
            )
        with col2:
            st.number_input(
                "Loss of Use",
                value=cl.loss_of_use or 0.0,
                key=f"{prefix}_loss_of_use",
                step=1000.0,
                format="%.0f"
            )
            st.number_input(
                "Personal Liability",
                value=cl.personal_liability or 0.0,
                key=f"{prefix}_personal_liability",
                step=50000.0,
                format="%.0f"
            )
            st.number_input(
                "Medical Payments",
                value=cl.medical_payments or 0.0,
                key=f"{prefix}_medical_payments",
                step=1000.0,
                format="%.0f"
            )

    elif section == "auto":
        col1, col2 = st.columns(2)
        with col1:
            st.number_input(
                "BI Per Person",
                value=cl.bi_per_person or 0.0,
                key=f"{prefix}_bi_per_person",
                step=50000.0,
                format="%.0f"
            )
            st.number_input(
                "BI Per Accident",
                value=cl.bi_per_accident or 0.0,
                key=f"{prefix}_bi_per_accident",
                step=50000.0,
                format="%.0f"
            )
            st.number_input(
                "PD Per Accident",
                value=cl.pd_per_accident or 0.0,
                key=f"{prefix}_pd_per_accident",
                step=25000.0,
                format="%.0f"
            )
            st.number_input(
                "CSL",
                value=cl.csl or 0.0,
                key=f"{prefix}_csl",
                step=100000.0,
                format="%.0f",
                help="Combined Single Limit"
            )
        with col2:
            st.number_input(
                "UM/UIM",
                value=cl.um_uim or 0.0,
                key=f"{prefix}_um_uim",
                step=50000.0,
                format="%.0f",
                help="Uninsured/Underinsured Motorist"
            )
            st.number_input(
                "Comprehensive Deductible",
                value=cl.comprehensive or 0.0,
                key=f"{prefix}_comprehensive",
                step=100.0,
                format="%.0f"
            )
            st.number_input(
                "Collision Deductible",
                value=cl.collision or 0.0,
                key=f"{prefix}_collision",
                step=100.0,
                format="%.0f"
            )

    elif section == "umbrella":
        st.number_input(
            "Umbrella Limit",
            value=cl.umbrella_limit or 0.0,
            key=f"{prefix}_umbrella_limit",
            step=1000000.0,
            format="%.0f"
        )


def _render_carrier_editor(idx: int, bundle: CarrierBundle) -> None:
    """Render editable form for a single carrier's data."""
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
                step=100.0,
                format="%.2f"
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
            st.number_input(
                "All-Peril Deductible",
                value=bundle.home.deductible or 0.0,
                key=f"edit_carrier_{idx}_home_deductible",
                step=500.0,
                format="%.0f"
            )
        with ded_cols[1]:
            st.number_input(
                "Wind/Hail Deductible",
                value=bundle.home.wind_hail_deductible or 0.0,
                key=f"edit_carrier_{idx}_wind_hail_deductible",
                step=500.0,
                format="%.0f"
            )

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
        if quote and quote.discounts_applied:
            all_discounts.extend(quote.discounts_applied)
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
                      "csl", "um_uim", "comprehensive", "collision"]:
            val = st.session_state.get(f"{prefix}_{field}", 0.0)
            cl_fields[field] = val if val != 0.0 else None
    elif section == "umbrella":
        val = st.session_state.get(f"{prefix}_umbrella_limit", 0.0)
        cl_fields["umbrella_limit"] = val if val != 0.0 else None

    coverage_limits = CoverageLimits(**cl_fields)

    # Read premium
    premium = st.session_state.get(f"edit_carrier_{carrier_idx}_{section}_premium", 0.0)

    # Read deductibles (home only)
    deductible = 0.0
    wind_hail_deductible = None
    if section == "home":
        deductible = st.session_state.get(f"edit_carrier_{carrier_idx}_home_deductible", 0.0)
        wind_hail_val = st.session_state.get(f"edit_carrier_{carrier_idx}_wind_hail_deductible", 0.0)
        wind_hail_deductible = wind_hail_val if wind_hail_val != 0.0 else None
    else:
        # For auto/umbrella, use original deductible or default to 0.0
        deductible = original.deductible

    # Read endorsements/discounts/notes from text areas
    endorsements_raw = st.session_state.get(f"edit_carrier_{carrier_idx}_endorsements", "")
    endorsements = [e.strip() for e in endorsements_raw.split("\n") if e.strip()]

    discounts_raw = st.session_state.get(f"edit_carrier_{carrier_idx}_discounts", "")
    discounts = [d.strip() for d in discounts_raw.split("\n") if d.strip()]

    notes_raw = st.session_state.get(f"edit_carrier_{carrier_idx}_notes", "")

    return InsuranceQuote(
        carrier_name=original.carrier_name,
        policy_type=original.policy_type,
        annual_premium=premium if premium != 0.0 else 0.0,
        deductible=deductible if deductible != 0.0 else 0.0,
        coverage_limits=coverage_limits,
        wind_hail_deductible=wind_hail_deductible,
        endorsements=endorsements,
        discounts_applied=discounts,
        notes=notes_raw.strip() or None,
        # Preserve fields we don't edit in UI
        effective_date=original.effective_date,
        expiration_date=original.expiration_date,
        monthly_premium=original.monthly_premium,
        exclusions=original.exclusions,
        confidence=original.confidence,
        raw_source=original.raw_source,
    )


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


def _build_edited_current_policy() -> Optional[CurrentPolicy]:
    """Reconstruct CurrentPolicy from edited session state values."""
    if st.session_state.current_policy_data is None:
        return None

    def clean_float(key: str) -> Optional[float]:
        val = st.session_state.get(key, 0.0)
        return val if val != 0.0 else None

    def clean_str(key: str) -> Optional[str]:
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


def render_review_stage() -> None:
    """Step 2: Review & Edit — Full implementation with editable forms."""
    sections = st.session_state.sections_included

    # --- Extraction Warnings (top of Review stage) ---
    if st.session_state.extraction_warnings:
        with st.expander(
            f"⚠️ {len(st.session_state.extraction_warnings)} Extraction Warnings",
            expanded=True
        ):
            for warning in st.session_state.extraction_warnings:
                st.warning(warning)

    # --- Current Policy Editor (if exists) ---
    if st.session_state.current_policy_data:
        with st.expander("📋 Current Policy", expanded=True):
            cp = st.session_state.current_policy_data

            st.text_input(
                "Current Carrier",
                value=cp.carrier_name,
                key="edit_cp_carrier_name"
            )

            if "home" in sections:
                st.subheader("🏠 Home")
                col1, col2 = st.columns(2)
                with col1:
                    st.number_input(
                        "Premium",
                        value=cp.home_premium or 0.0,
                        key="edit_cp_home_premium",
                        step=100.0,
                        format="%.2f"
                    )
                    st.number_input(
                        "Dwelling",
                        value=cp.home_dwelling or 0.0,
                        key="edit_cp_home_dwelling",
                        step=10000.0,
                        format="%.0f"
                    )
                    st.number_input(
                        "Other Structures",
                        value=cp.home_other_structures or 0.0,
                        key="edit_cp_home_other_structures",
                        step=1000.0,
                        format="%.0f"
                    )
                    st.number_input(
                        "Personal Property",
                        value=cp.home_personal_property or 0.0,
                        key="edit_cp_home_personal_property",
                        step=1000.0,
                        format="%.0f"
                    )
                with col2:
                    st.number_input(
                        "Liability",
                        value=cp.home_liability or 0.0,
                        key="edit_cp_home_liability",
                        step=50000.0,
                        format="%.0f"
                    )
                    st.number_input(
                        "Loss of Use",
                        value=cp.home_loss_of_use or 0.0,
                        key="edit_cp_home_loss_of_use",
                        step=1000.0,
                        format="%.0f"
                    )
                    st.number_input(
                        "Deductible",
                        value=cp.home_deductible or 0.0,
                        key="edit_cp_home_deductible",
                        step=500.0,
                        format="%.0f"
                    )

            if "auto" in sections:
                st.subheader("🚗 Auto")
                st.info("💡 If current policy was extracted from PDF, auto fields may need manual entry.")
                col1, col2 = st.columns(2)
                with col1:
                    st.number_input(
                        "Premium",
                        value=cp.auto_premium or 0.0,
                        key="edit_cp_auto_premium",
                        step=100.0,
                        format="%.2f"
                    )
                    st.text_input(
                        "Liability Limits",
                        value=cp.auto_limits or "",
                        key="edit_cp_auto_limits",
                        placeholder="e.g., 500/500/250"
                    )
                with col2:
                    st.text_input(
                        "UM/UIM",
                        value=cp.auto_um_uim or "",
                        key="edit_cp_auto_um_uim",
                        placeholder="e.g., 500/500"
                    )
                    st.text_input(
                        "Comp Deductible",
                        value=cp.auto_comp_deductible or "",
                        key="edit_cp_auto_comp_deductible",
                        placeholder="e.g., $500"
                    )
                    st.number_input(
                        "Collision Deductible",
                        value=cp.auto_collision_deductible or 0.0,
                        key="edit_cp_auto_collision_deductible",
                        step=100.0,
                        format="%.0f"
                    )

            if "umbrella" in sections:
                st.subheader("☂️ Umbrella")
                col1, col2 = st.columns(2)
                with col1:
                    st.number_input(
                        "Premium",
                        value=cp.umbrella_premium or 0.0,
                        key="edit_cp_umbrella_premium",
                        step=100.0,
                        format="%.2f"
                    )
                    st.text_input(
                        "Limits",
                        value=cp.umbrella_limits or "",
                        key="edit_cp_umbrella_limits",
                        placeholder="e.g., 1M CSL"
                    )
                with col2:
                    st.number_input(
                        "Deductible",
                        value=cp.umbrella_deductible or 0.0,
                        key="edit_cp_umbrella_deductible",
                        step=100.0,
                        format="%.0f"
                    )

    # --- Carrier Data Editors ---
    for i, bundle in enumerate(st.session_state.carrier_bundles):
        with st.expander(f"📊 {bundle.carrier_name}", expanded=(i == 0)):
            _render_carrier_editor(i, bundle)

    # --- Approve & Continue Button ---
    st.markdown("---")
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("✅ Approve & Continue", type="primary"):
            st.session_state.edited_bundles = _build_edited_bundles()
            st.session_state.edited_current_policy = _build_edited_current_policy()
            st.session_state.review_complete = True
            st.session_state.current_step = 3
            st.rerun()


def _build_comparison_session() -> ComparisonSession:
    """Build ComparisonSession from edited data for export."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return ComparisonSession(
        client_name=st.session_state.client_name,
        date=date_str,
        sections_included=st.session_state.sections_included,
        carriers=st.session_state.edited_bundles,
        current_policy=st.session_state.edited_current_policy,
        agent_notes=st.session_state.get("agent_notes", "").strip() or None,
    )


def render_export_stage() -> None:
    """Step 3: Export — PDF generation and Google Sheets export."""
    # Agent Notes
    st.text_area(
        "Agent Notes (optional — appears on PDF and Sheet)",
        key="agent_notes",
        height=100,
        placeholder="Add any notes for the client...",
    )

    st.markdown("---")

    # ── PDF Section ──
    st.subheader("PDF Comparison Report")

    col1, col2 = st.columns([1, 3])
    with col1:
        generate_pdf_btn = st.button("Generate PDF", type="primary")

    if generate_pdf_btn:
        with st.spinner("Generating PDF..."):
            try:
                session = _build_comparison_session()

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
                label="Download PDF",
                data=pdf_bytes,
                file_name=Path(pdf_path).name,
                mime="application/pdf",
            )

    st.markdown("---")

    # ── Google Sheets Section ──
    st.subheader("Google Sheets Export")

    col1, col2 = st.columns([1, 3])
    with col1:
        generate_sheets_btn = st.button("Export to Google Sheets", type="primary")

    if generate_sheets_btn:
        with st.spinner("Exporting to Google Sheets..."):
            try:
                session = _build_comparison_session()

                sheets_client = SheetsClient()
                sheet_url = sheets_client.create_comparison(session)

                st.session_state.export_sheet_url = sheet_url
                st.success("Google Sheet created!")

            except Exception as e:
                st.error(f"Sheets export failed: {e}")
                logger.error("Sheets export error", exc_info=True)

    # Show link if Sheet was created
    if st.session_state.get("export_sheet_url"):
        st.markdown(f"[Open Google Sheet]({st.session_state.export_sheet_url})")

    st.markdown("---")

    # Re-export info
    st.info("You can re-generate exports after making changes. Go back to Review to edit data.")


def inject_custom_css() -> None:
    """Inject custom CSS for professional styling and branding."""
    st.markdown("""
    <style>
    /* ── Hide Streamlit defaults ── */
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    .stDeployButton {display: none !important;}
    [data-testid="stHeader"] {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}

    /* ── Global Typography ── */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1100px !important;
    }
    h1, .branded-title {
        color: #871c30 !important;
        font-weight: 700 !important;
    }
    h2 {
        color: #871c30 !important;
        font-size: 1.3rem !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #f0e8e0;
        padding-bottom: 0.4rem;
        margin-top: 1.2rem !important;
        margin-bottom: 0.8rem !important;
    }
    h3 {
        color: #5a1220 !important;
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        margin-top: 0.8rem !important;
    }

    /* ── Primary Buttons — maroon with white text ── */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background-color: #871c30 !important;
        border-color: #871c30 !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        padding: 0.5rem 1.5rem !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        background-color: #6b1626 !important;
        border-color: #6b1626 !important;
        box-shadow: 0 2px 10px rgba(135, 28, 48, 0.35) !important;
    }
    .stButton > button[kind="primary"]:active,
    .stFormSubmitButton > button[kind="primary"]:active {
        background-color: #551220 !important;
        transform: translateY(1px) !important;
    }

    /* Secondary buttons */
    .stButton > button[kind="secondary"],
    .stButton > button:not([kind="primary"]) {
        border: 1.5px solid #871c30 !important;
        color: #871c30 !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stButton > button:not([kind="primary"]):hover {
        background-color: rgba(135, 28, 48, 0.06) !important;
        border-color: #6b1626 !important;
        color: #6b1626 !important;
    }

    /* ── Expander Styling (Step Accordion) ── */
    .streamlit-expanderHeader {
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        background-color: #faf7f4 !important;
        border-radius: 8px 8px 0 0 !important;
        border-left: 4px solid #871c30 !important;
        padding: 0.75rem 1rem !important;
    }
    .streamlit-expanderContent {
        border-left: 4px solid #871c30 !important;
        border-radius: 0 0 8px 8px !important;
        padding-top: 0.5rem !important;
    }

    /* ── Containers / Cards ── */
    [data-testid="stExpander"] {
        border: 1px solid #e8e0d8 !important;
        border-radius: 8px !important;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06) !important;
        margin-bottom: 0.75rem !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"]) {
        border-radius: 8px !important;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05) !important;
    }

    /* ── Sidebar Styling ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #faf7f4 0%, #f4ede5 100%) !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: #e0d6cc !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        width: 100% !important;
    }

    /* ── Form inputs — subtle refinements ── */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stTextArea > div > div > textarea {
        border-radius: 6px !important;
    }
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #871c30 !important;
        box-shadow: 0 0 0 1px #871c30 !important;
    }

    /* ── Progress bar ── */
    .stProgress > div > div > div > div {
        background-color: #871c30 !important;
    }

    /* ── File uploader ── */
    [data-testid="stFileUploader"] section {
        border-radius: 8px !important;
        border: 1.5px dashed #c9b8a8 !important;
        transition: border-color 0.2s ease !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: #871c30 !important;
    }

    /* ── Multiselect pills ── */
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
        background-color: #871c30 !important;
        color: white !important;
    }

    /* ── Hide heading anchor links ── */
    [data-testid="stHeading"] a {
        display: none !important;
    }
    h1 a, h2 a, h3 a {
        display: none !important;
    }

    /* ── Radio buttons ── */
    .stRadio > div {
        gap: 0.3rem !important;
    }
    .stRadio > div > label > div:first-child {
        color: #871c30 !important;
    }

    /* ── Tighten vertical spacing inside expanders ── */
    .streamlit-expanderContent [data-testid="stVerticalBlock"] {
        gap: 0.6rem !important;
    }

    /* ── Download button ── */
    .stDownloadButton > button {
        background-color: #871c30 !important;
        border-color: #871c30 !important;
        color: white !important;
        border-radius: 6px !important;
    }
    .stDownloadButton > button:hover {
        background-color: #6b1626 !important;
    }

    /* ══════ Step Indicator ══════ */
    .step-indicator {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 0;
        margin: 0 0 1.5rem 0;
        padding: 1rem 1.5rem;
        background: linear-gradient(135deg, #faf7f4 0%, #f4ede5 100%);
        border-radius: 10px;
        border: 1px solid #e8e0d8;
    }
    .step-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .step-circle {
        width: 34px;
        height: 34px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.85rem;
        flex-shrink: 0;
        transition: all 0.3s ease;
    }
    .step-circle.active {
        background-color: #871c30;
        color: white;
        box-shadow: 0 2px 10px rgba(135, 28, 48, 0.35);
    }
    .step-circle.completed {
        background-color: #871c30;
        color: white;
    }
    .step-circle.pending {
        background-color: #e0d6cc;
        color: #8a7e72;
    }
    .step-label {
        font-size: 0.85rem;
        font-weight: 600;
        white-space: nowrap;
    }
    .step-label.active {
        color: #871c30;
    }
    .step-label.completed {
        color: #871c30;
    }
    .step-label.pending {
        color: #8a7e72;
    }
    .step-connector {
        width: 60px;
        height: 2px;
        margin: 0 1rem;
        flex-shrink: 0;
        border-radius: 1px;
    }
    .step-connector.completed {
        background-color: #871c30;
    }
    .step-connector.pending {
        background-color: #e0d6cc;
    }

    /* ══════ Branded Header ══════ */
    .branded-header {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 0.5rem;
        padding-bottom: 0.75rem;
        border-bottom: 3px solid #871c30;
    }
    .branded-header img {
        height: 56px;
        width: auto;
    }
    .branded-header .branded-title {
        margin: 0 !important;
        font-size: 1.6rem !important;
        line-height: 1.2;
    }
    .branded-subtitle {
        font-size: 0.95rem;
        color: #666;
        font-weight: 400;
        margin-top: 0.1rem;
    }
    </style>
    """, unsafe_allow_html=True)


def render_step_indicator() -> None:
    """Render visual step progress indicator: Upload -> Review -> Export."""
    current = st.session_state.current_step
    extraction_done = st.session_state.extraction_complete
    review_done = st.session_state.review_complete

    steps = [
        (1, "Upload", extraction_done),
        (2, "Review", review_done),
        (3, "Export", False),
    ]

    items_html = []
    for i, (num, label, done) in enumerate(steps):
        if done:
            cls = "completed"
            circle = f'<div class="step-circle completed">&#10003;</div>'
        elif num == current:
            cls = "active"
            circle = f'<div class="step-circle active">{num}</div>'
        else:
            cls = "pending"
            circle = f'<div class="step-circle pending">{num}</div>'

        items_html.append(
            f'<div class="step-item">{circle}<span class="step-label {cls}">{label}</span></div>'
        )

        # Add connector between steps (not after last)
        if i < len(steps) - 1:
            conn_cls = "completed" if done else "pending"
            items_html.append(f'<div class="step-connector {conn_cls}"></div>')

    html = f'<div class="step-indicator">{"".join(items_html)}</div>'
    st.markdown(html, unsafe_allow_html=True)


def _reset_session_callback() -> None:
    """Callback to reset all session state."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def render_sidebar() -> None:
    """Sidebar with logo, session info, and reset button."""
    with st.sidebar:
        # Logo
        logo_path = Path("assets/logo_rgb.png")
        if logo_path.exists():
            st.image(str(logo_path), width=220)

        st.markdown("---")

        # Session Info
        has_info = False
        if st.session_state.client_name:
            st.markdown(f"**Client:** {st.session_state.client_name}")
            has_info = True

        if st.session_state.carriers:
            named = [c for c in st.session_state.carriers if c.get("name", "").strip()]
            if named:
                st.markdown(f"**Carriers:** {len(named)}")
                has_info = True

        if st.session_state.sections_included:
            st.markdown(f"**Sections:** {', '.join(s.title() for s in st.session_state.sections_included)}")
            has_info = True

        if has_info:
            st.markdown("---")

        # Reset Button
        st.button("Reset Session", key="reset_btn", on_click=_reset_session_callback, type="secondary")


def main() -> None:
    """Main application entry point."""
    st.set_page_config(
        page_title="Scioto Insurance — Quote Comparison",
        page_icon="assets/logo_rgb.png",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize session state
    init_session_state()

    # Inject custom CSS (must be first visual element)
    inject_custom_css()

    # Branded header
    logo_path = Path("assets/logo_rgb.png")
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        st.markdown(f"""
        <div class="branded-header">
            <img src="data:image/png;base64,{logo_b64}" alt="Scioto Insurance Group" />
            <div>
                <div class="branded-title" style="font-size:1.6rem; font-weight:700; color:#871c30; margin:0;">
                    Scioto Insurance Group
                </div>
                <div class="branded-subtitle">Quote Comparison Tool</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="branded-title" style="font-size:1.6rem; font-weight:700; color:#871c30;">Scioto Insurance Group — Quote Comparison</div>',
            unsafe_allow_html=True
        )

    # Step progress indicator
    render_step_indicator()

    # Sidebar
    render_sidebar()

    # ── Step 1: Upload & Extract ──
    step1_expanded = (st.session_state.current_step == 1)
    step1_label = "Upload & Extract  ✅" if st.session_state.extraction_complete else "Upload & Extract"

    with st.expander(step1_label, expanded=step1_expanded):
        render_upload_stage()

    # ── Step 2: Review & Edit ──
    if st.session_state.extraction_complete:
        step2_expanded = (st.session_state.current_step == 2)
        step2_label = "Review & Edit  ✅" if st.session_state.review_complete else "Review & Edit"

        with st.expander(step2_label, expanded=step2_expanded):
            render_review_stage()

    # ── Step 3: Export ──
    if st.session_state.review_complete:
        step3_expanded = (st.session_state.current_step == 3)

        with st.expander("Export Results", expanded=step3_expanded):
            render_export_stage()


if __name__ == "__main__":
    main()
