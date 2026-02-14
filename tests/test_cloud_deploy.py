"""
Cloud deployment simulation tests.

Verifies the full pipeline works in a simulated Streamlit Cloud environment:
- No DejaVu fonts (Helvetica only)
- Credentials from st.secrets fallback
- Password gate logic
- PDF generation and Sheets grid building without real API calls
"""

# CRITICAL: Set env var BEFORE any app imports — config.py validates at import time.
import os
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-ci")

import importlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.extraction.models import (
    CarrierBundle,
    ComparisonSession,
    CoverageLimits,
    CurrentPolicy,
    InsuranceQuote,
)
from app.pdf_gen.generator import generate_comparison_pdf, SciotoComparisonPDF
from app.sheets.sheets_client import SheetsClient


# ═══════════════════════════════════════════════════════════════════════════════
# Shared Fixture
# ═══════════════════════════════════════════════════════════════════════════════


def _make_cloud_session(
    *,
    include_home_2: bool = False,
    include_current: bool = True,
) -> ComparisonSession:
    """Build a ComparisonSession with 2 carriers for testing."""
    erie_home = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="HO3",
        annual_premium=1850.00,
        deductible=1000.0,
        coverage_limits=CoverageLimits(
            dwelling=350000, other_structures=35000,
            personal_property=175000, loss_of_use=70000,
            personal_liability=300000, medical_payments=5000,
        ),
        confidence="high",
    )
    erie_auto = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="Auto",
        annual_premium=1200.00,
        deductible=500.0,
        coverage_limits=CoverageLimits(
            bi_per_person=500000, bi_per_accident=500000,
            pd_per_accident=250000, um_uim=500000,
            comprehensive=500, collision=500,
        ),
        confidence="high",
    )
    erie_umbrella = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="Umbrella",
        annual_premium=350.00,
        deductible=0.0,
        coverage_limits=CoverageLimits(umbrella_limit=1000000),
        confidence="high",
    )

    westfield_home = InsuranceQuote(
        carrier_name="Westfield Insurance",
        policy_type="HO5",
        annual_premium=2100.00,
        deductible=2500.0,
        coverage_limits=CoverageLimits(
            dwelling=350000, other_structures=35000,
            personal_property=175000, loss_of_use=70000,
            personal_liability=300000, medical_payments=5000,
        ),
        confidence="high",
    )
    westfield_auto = InsuranceQuote(
        carrier_name="Westfield Insurance",
        policy_type="Auto",
        annual_premium=1350.00,
        deductible=500.0,
        coverage_limits=CoverageLimits(
            bi_per_person=500000, bi_per_accident=500000,
            pd_per_accident=250000, um_uim=500000,
            comprehensive=500, collision=500,
        ),
        confidence="high",
    )
    westfield_umbrella = InsuranceQuote(
        carrier_name="Westfield Insurance",
        policy_type="Umbrella",
        annual_premium=400.00,
        deductible=0.0,
        coverage_limits=CoverageLimits(umbrella_limit=1000000),
        confidence="high",
    )

    erie_bundle = CarrierBundle(
        carrier_name="Erie Insurance",
        home=erie_home,
        auto=erie_auto,
        umbrella=erie_umbrella,
    )
    westfield_bundle = CarrierBundle(
        carrier_name="Westfield Insurance",
        home=westfield_home,
        auto=westfield_auto,
        umbrella=westfield_umbrella,
    )

    # Add home_2 if requested (multi-dwelling scenario)
    if include_home_2:
        erie_home_2 = InsuranceQuote(
            carrier_name="Erie Insurance",
            policy_type="HO3",
            annual_premium=950.00,
            deductible=1000.0,
            coverage_limits=CoverageLimits(
                dwelling=200000, other_structures=20000,
                personal_property=100000, loss_of_use=40000,
                personal_liability=300000, medical_payments=5000,
            ),
            confidence="high",
        )
        westfield_home_2 = InsuranceQuote(
            carrier_name="Westfield Insurance",
            policy_type="HO5",
            annual_premium=1050.00,
            deductible=2500.0,
            coverage_limits=CoverageLimits(
                dwelling=200000, other_structures=20000,
                personal_property=100000, loss_of_use=40000,
                personal_liability=300000, medical_payments=5000,
            ),
            confidence="high",
        )
        erie_bundle = CarrierBundle(
            carrier_name="Erie Insurance",
            home=erie_home, home_2=erie_home_2,
            auto=erie_auto, umbrella=erie_umbrella,
        )
        westfield_bundle = CarrierBundle(
            carrier_name="Westfield Insurance",
            home=westfield_home, home_2=westfield_home_2,
            auto=westfield_auto, umbrella=westfield_umbrella,
        )

    current_policy = None
    if include_current:
        current_policy = CurrentPolicy(
            carrier_name="State Farm",
            home_premium=2000.0,
            home_dwelling=350000,
            home_other_structures=35000,
            home_liability=300000,
            home_personal_property=175000,
            home_loss_of_use=70000,
            home_deductible=1000,
            home_2_premium=1100.0 if include_home_2 else None,
            home_2_dwelling=200000 if include_home_2 else None,
            auto_premium=1400.0,
            auto_limits="500/500/250",
            auto_um_uim="500/500",
            auto_comp_deductible="$500",
            auto_collision_deductible=500.0,
            umbrella_premium=375.0,
            umbrella_limits="1M CSL",
            umbrella_deductible=0.0,
        )

    return ComparisonSession(
        client_name="Test Client",
        date="2026-02-14",
        current_policy=current_policy,
        carriers=[erie_bundle, westfield_bundle],
        sections_included=["home", "auto", "umbrella"],
        agent_notes="This is a test comparison for cloud deployment verification.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Font Simulation — DejaVu regression guard
# ═══════════════════════════════════════════════════════════════════════════════


class TestFontSimulation:
    """Ensure DejaVu fonts are not referenced; only Helvetica is used."""

    def test_no_dejavu_in_generator_source(self) -> None:
        source_path = Path(__file__).resolve().parent.parent / "app" / "pdf_gen" / "generator.py"
        source = source_path.read_text(encoding="utf-8")
        assert "dejavu" not in source.lower(), "generator.py still references DejaVu fonts"

    def test_pdf_output_uses_helvetica(self, tmp_path: Path) -> None:
        session = _make_cloud_session()
        out = str(tmp_path / "test.pdf")
        generate_comparison_pdf(session, out)
        raw = Path(out).read_bytes()
        assert b"Helvetica" in raw
        assert b"DejaVu" not in raw

    def test_register_fonts_sets_helvetica(self) -> None:
        pdf = SciotoComparisonPDF()
        assert pdf.font_family_name == "Helvetica"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Mock ComparisonSession — fixture correctness
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockComparisonSession:
    """Verify the shared fixture builds correct data structures."""

    def test_two_carriers(self) -> None:
        session = _make_cloud_session()
        assert len(session.carriers) == 2

    def test_all_three_sections(self) -> None:
        session = _make_cloud_session()
        assert session.sections_included == ["home", "auto", "umbrella"]

    def test_current_policy_present(self) -> None:
        session = _make_cloud_session()
        assert session.current_policy is not None
        assert session.current_policy.carrier_name == "State Farm"

    def test_agent_notes_set(self) -> None:
        session = _make_cloud_session()
        assert session.agent_notes is not None
        assert len(session.agent_notes) > 0

    def test_each_carrier_has_all_policies(self) -> None:
        session = _make_cloud_session()
        for carrier in session.carriers:
            assert carrier.home is not None, f"{carrier.carrier_name} missing home"
            assert carrier.auto is not None, f"{carrier.carrier_name} missing auto"
            assert carrier.umbrella is not None, f"{carrier.carrier_name} missing umbrella"

    def test_total_premium_positive(self) -> None:
        session = _make_cloud_session()
        for carrier in session.carriers:
            assert carrier.total_premium > 0, f"{carrier.carrier_name} total_premium is 0"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PDF Generation — end-to-end pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class TestPDFGeneration:
    """End-to-end PDF generation tests."""

    def test_generate_returns_path(self, tmp_path: Path) -> None:
        session = _make_cloud_session()
        out = str(tmp_path / "comparison.pdf")
        result = generate_comparison_pdf(session, out)
        assert result == out

    def test_output_file_created(self, tmp_path: Path) -> None:
        session = _make_cloud_session()
        out = str(tmp_path / "comparison.pdf")
        generate_comparison_pdf(session, out)
        assert Path(out).exists()
        assert Path(out).stat().st_size > 1024  # > 1KB

    def test_valid_pdf_header(self, tmp_path: Path) -> None:
        session = _make_cloud_session()
        out = str(tmp_path / "comparison.pdf")
        generate_comparison_pdf(session, out)
        with open(out, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_with_agent_notes(self, tmp_path: Path) -> None:
        session = _make_cloud_session()
        out = str(tmp_path / "notes.pdf")
        generate_comparison_pdf(session, out, agent_notes="Custom agent notes for testing")
        assert Path(out).exists()
        assert Path(out).stat().st_size > 1024

    def test_with_date_override(self, tmp_path: Path) -> None:
        session = _make_cloud_session()
        out = str(tmp_path / "dated.pdf")
        generate_comparison_pdf(session, out, date_str="January 1, 2026")
        assert Path(out).exists()
        assert Path(out).stat().st_size > 1024

    def test_without_current_policy(self, tmp_path: Path) -> None:
        session = _make_cloud_session(include_current=False)
        out = str(tmp_path / "no_current.pdf")
        generate_comparison_pdf(session, out)
        assert Path(out).exists()
        assert Path(out).stat().st_size > 1024


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Sheets Grid Build — grid building without Google API
# ═══════════════════════════════════════════════════════════════════════════════


class TestSheetsGridBuild:
    """Test _build_full_grid using object.__new__ to bypass constructor."""

    def _make_client(self) -> SheetsClient:
        """Create SheetsClient without calling __init__ (no gspread auth)."""
        return object.__new__(SheetsClient)

    def test_single_dwelling_row_count(self) -> None:
        client = self._make_client()
        session = _make_cloud_session()
        num_data_cols = len(session.carriers) + (1 if session.current_policy else 0)
        grid, config = client._build_full_grid(session, num_data_cols)
        assert config.total_rows == 25

    def test_multi_dwelling_row_count(self) -> None:
        client = self._make_client()
        session = _make_cloud_session(include_home_2=True)
        num_data_cols = len(session.carriers) + (1 if session.current_policy else 0)
        grid, config = client._build_full_grid(session, num_data_cols)
        assert config.total_rows == 34

    def test_num_data_cols_with_current(self) -> None:
        client = self._make_client()
        session = _make_cloud_session(include_current=True)
        num_data_cols = client._get_num_data_columns(session)
        # 2 carriers + 1 current = 3
        assert num_data_cols == 3

    def test_num_data_cols_without_current(self) -> None:
        client = self._make_client()
        session = _make_cloud_session(include_current=False)
        num_data_cols = client._get_num_data_columns(session)
        # 2 carriers, no current = 2
        assert num_data_cols == 2

    def test_header_rows_populated(self) -> None:
        client = self._make_client()
        session = _make_cloud_session()
        num_data_cols = client._get_num_data_columns(session)
        _, config = client._build_full_grid(session, num_data_cols)
        assert len(config.header_rows) > 0

    def test_currency_rows_populated(self) -> None:
        client = self._make_client()
        session = _make_cloud_session()
        num_data_cols = client._get_num_data_columns(session)
        _, config = client._build_full_grid(session, num_data_cols)
        assert len(config.currency_rows) > 0

    def test_grid_title_contains_client_name(self) -> None:
        client = self._make_client()
        session = _make_cloud_session()
        num_data_cols = client._get_num_data_columns(session)
        grid, _ = client._build_full_grid(session, num_data_cols)
        # grid[0][1] is the title cell (B1)
        assert "Test Client" in grid[0][1]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Streamlit Imports — all streamlit_app.py imports resolve
# ═══════════════════════════════════════════════════════════════════════════════


class TestStreamlitImports:
    """Verify that all imports used by streamlit_app.py resolve without error."""

    def test_stdlib_imports(self) -> None:
        import base64
        import logging
        from datetime import datetime
        from pathlib import Path
        from typing import Optional
        assert all([base64, logging, datetime, Path, Optional])

    def test_streamlit_import(self) -> None:
        import streamlit
        assert streamlit is not None

    def test_model_imports(self) -> None:
        from app.extraction.models import (
            ComparisonSession, CarrierBundle, CurrentPolicy,
            InsuranceQuote, CoverageLimits,
        )
        assert all([ComparisonSession, CarrierBundle, CurrentPolicy,
                     InsuranceQuote, CoverageLimits])

    def test_extractor_imports(self) -> None:
        from app.extraction.ai_extractor import extract_and_validate, extract_and_validate_multi
        assert all([extract_and_validate, extract_and_validate_multi])

    def test_carrier_config_imports(self) -> None:
        from app.extraction.carrier_config import get_combined_sections, classify_policy_type
        assert all([get_combined_sections, classify_policy_type])

    def test_pdf_generator_import(self) -> None:
        from app.pdf_gen.generator import generate_comparison_pdf
        assert generate_comparison_pdf is not None

    def test_sheets_client_import(self) -> None:
        from app.sheets.sheets_client import SheetsClient
        assert SheetsClient is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Password Gate — password logic
# ═══════════════════════════════════════════════════════════════════════════════


class _StopExecution(Exception):
    """Sentinel exception to simulate st.stop()."""
    pass


def _password_gate(st_mod: MagicMock) -> None:
    """Replicate the exact password gate logic from streamlit_app.py main()."""
    password = st_mod.text_input("Password", type="password")
    if not password or password != st_mod.secrets["APP_PASSWORD"]:
        st_mod.info("Enter password to continue")
        st_mod.stop()


class TestPasswordGate:
    """Test the password gate logic without running Streamlit."""

    def _make_st_mock(self, password_value: str) -> MagicMock:
        mock = MagicMock()
        mock.secrets = {"APP_PASSWORD": "correct"}
        mock.text_input.return_value = password_value
        mock.stop.side_effect = _StopExecution
        return mock

    def test_wrong_password_calls_stop(self) -> None:
        st_mock = self._make_st_mock("wrong")
        with pytest.raises(_StopExecution):
            _password_gate(st_mock)
        st_mock.stop.assert_called_once()

    def test_empty_string_calls_stop(self) -> None:
        st_mock = self._make_st_mock("")
        with pytest.raises(_StopExecution):
            _password_gate(st_mock)
        st_mock.stop.assert_called_once()

    def test_none_calls_stop(self) -> None:
        st_mock = self._make_st_mock(None)
        with pytest.raises(_StopExecution):
            _password_gate(st_mock)
        st_mock.stop.assert_called_once()

    def test_correct_password_does_not_stop(self) -> None:
        st_mock = self._make_st_mock("correct")
        _password_gate(st_mock)  # Should not raise
        st_mock.stop.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Streamlit Secrets Fallback — config.py secrets chain
# ═══════════════════════════════════════════════════════════════════════════════


class TestStreamlitSecretsFallback:
    """Test that config.py falls back to st.secrets when env vars are missing."""

    def test_secrets_fallback_provides_gemini_key(self) -> None:
        saved_val = os.environ.get("GEMINI_API_KEY")
        saved_modules = {
            k: sys.modules.pop(k)
            for k in list(sys.modules)
            if k == "app.utils.config" or k.startswith("app.utils.config.")
        }
        try:
            os.environ.pop("GEMINI_API_KEY", None)

            # Mock streamlit with secrets containing the key
            mock_st = MagicMock()
            mock_st.secrets = {"GEMINI_API_KEY": "from-secrets"}
            sys.modules["streamlit"] = mock_st

            # Prevent load_dotenv from re-reading .env file
            with patch("dotenv.load_dotenv", return_value=None):
                import app.utils.config as config_mod
                importlib.reload(config_mod)

            assert config_mod.GEMINI_API_KEY == "from-secrets"
        finally:
            if saved_val is not None:
                os.environ["GEMINI_API_KEY"] = saved_val
            else:
                os.environ.setdefault("GEMINI_API_KEY", "test-key-for-ci")
            for k, v in saved_modules.items():
                sys.modules[k] = v
            if "streamlit" in sys.modules and isinstance(sys.modules["streamlit"], MagicMock):
                sys.modules["streamlit"] = importlib.import_module("streamlit")

    def test_missing_key_raises_without_fallback(self) -> None:
        saved_val = os.environ.get("GEMINI_API_KEY")
        saved_modules = {
            k: sys.modules.pop(k)
            for k in list(sys.modules)
            if k == "app.utils.config" or k.startswith("app.utils.config.")
        }
        try:
            os.environ.pop("GEMINI_API_KEY", None)

            # Mock streamlit with empty secrets
            mock_st = MagicMock()
            mock_st.secrets = {}
            sys.modules["streamlit"] = mock_st

            # Prevent load_dotenv from re-reading .env file
            with patch("dotenv.load_dotenv", return_value=None):
                with pytest.raises(ValueError, match="GEMINI_API_KEY not found"):
                    import app.utils.config as config_mod
                    importlib.reload(config_mod)
        finally:
            if saved_val is not None:
                os.environ["GEMINI_API_KEY"] = saved_val
            else:
                os.environ.setdefault("GEMINI_API_KEY", "test-key-for-ci")
            for k, v in saved_modules.items():
                sys.modules[k] = v
            if "streamlit" in sys.modules and isinstance(sys.modules["streamlit"], MagicMock):
                sys.modules["streamlit"] = importlib.import_module("streamlit")

    def test_env_var_takes_precedence(self) -> None:
        saved_val = os.environ.get("GEMINI_API_KEY")
        saved_modules = {
            k: sys.modules.pop(k)
            for k in list(sys.modules)
            if k == "app.utils.config" or k.startswith("app.utils.config.")
        }
        try:
            os.environ["GEMINI_API_KEY"] = "from-env"

            # Mock streamlit with a different key in secrets
            mock_st = MagicMock()
            mock_st.secrets = {"GEMINI_API_KEY": "from-secrets"}
            sys.modules["streamlit"] = mock_st

            # Prevent load_dotenv from re-reading .env file
            with patch("dotenv.load_dotenv", return_value=None):
                import app.utils.config as config_mod
                importlib.reload(config_mod)

            assert config_mod.GEMINI_API_KEY == "from-env"
        finally:
            if saved_val is not None:
                os.environ["GEMINI_API_KEY"] = saved_val
            else:
                os.environ.setdefault("GEMINI_API_KEY", "test-key-for-ci")
            for k, v in saved_modules.items():
                sys.modules[k] = v
            if "streamlit" in sys.modules and isinstance(sys.modules["streamlit"], MagicMock):
                sys.modules["streamlit"] = importlib.import_module("streamlit")
