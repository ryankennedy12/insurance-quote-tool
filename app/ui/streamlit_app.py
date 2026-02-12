"""
Streamlit UI — Insurance Quote Comparison Tool
Phase 5, Step 11: Wizard skeleton with session state management

Entry point: streamlit run app/ui/streamlit_app.py
"""

import streamlit as st
from pathlib import Path

# Future imports (not needed yet):
# from app.extraction.models import ComparisonSession, CarrierBundle, CurrentPolicy
# from app.extraction.ai_extractor import extract_and_validate
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


def render_upload_stage() -> None:
    """Step 1: Upload & Extract — placeholder UI."""
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

    if st.session_state.current_policy_mode == "Enter Manually":
        st.info("Manual entry form will go here (Step 12)")

    elif st.session_state.current_policy_mode == "Upload Dec Page PDF":
        st.file_uploader(
            "Upload Current Dec Page",
            type=["pdf"],
            key="current_policy_pdf"
        )

    # Carrier Uploads
    st.subheader("Carrier Quotes")
    st.info("Carrier upload section will go here (Step 12)")

    # Extract Button (placeholder)
    col1, col2 = st.columns([1, 4])
    with col1:
        extract_btn = st.button(
            "🔍 Extract All",
            type="primary",
            disabled=not st.session_state.client_name
        )

    if extract_btn:
        st.session_state.extraction_complete = True
        st.session_state.current_step = 2
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
