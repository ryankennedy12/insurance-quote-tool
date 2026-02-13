"""Tests for combined-carrier PDF extraction support."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.extraction.carrier_config import (
    COMBINED_CARRIERS,
    classify_policy_type,
    get_combined_sections,
    is_combined_carrier,
)
from app.extraction.models import (
    CoverageLimits,
    InsuranceQuote,
    MultiQuoteExtractionResult,
    MultiQuoteResponse,
)


# ---------------------------------------------------------------------------
# carrier_config: get_combined_sections
# ---------------------------------------------------------------------------


class TestGetCombinedSections:
    def test_grange_returns_home_umbrella(self) -> None:
        assert get_combined_sections("Grange Insurance") == ["home", "umbrella"]

    def test_grange_case_insensitive(self) -> None:
        assert get_combined_sections("GRANGE MUTUAL") == ["home", "umbrella"]

    def test_hanover_returns_home_auto(self) -> None:
        assert get_combined_sections("The Hanover") == ["home", "auto"]

    def test_hanover_full_name(self) -> None:
        assert get_combined_sections("Hanover Insurance Group") == ["home", "auto"]

    def test_unknown_carrier_returns_none(self) -> None:
        assert get_combined_sections("Erie Insurance") is None

    def test_empty_string_returns_none(self) -> None:
        assert get_combined_sections("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert get_combined_sections("   ") is None


# ---------------------------------------------------------------------------
# carrier_config: is_combined_carrier
# ---------------------------------------------------------------------------


class TestIsCombinedCarrier:
    def test_grange_is_combined(self) -> None:
        assert is_combined_carrier("Grange Insurance") is True

    def test_hanover_is_combined(self) -> None:
        assert is_combined_carrier("Hanover") is True

    def test_erie_is_not_combined(self) -> None:
        assert is_combined_carrier("Erie Insurance") is False

    def test_state_farm_is_not_combined(self) -> None:
        assert is_combined_carrier("State Farm") is False


# ---------------------------------------------------------------------------
# carrier_config: classify_policy_type (fuzzy matching)
# ---------------------------------------------------------------------------


class TestClassifyPolicyType:
    # Home variations
    def test_ho3(self) -> None:
        assert classify_policy_type("HO3") == "home"

    def test_ho5(self) -> None:
        assert classify_policy_type("HO5") == "home"

    def test_ho_dash_3(self) -> None:
        assert classify_policy_type("HO-3") == "home"

    def test_ho_dash_5(self) -> None:
        assert classify_policy_type("HO-5") == "home"

    def test_homeowners(self) -> None:
        assert classify_policy_type("Homeowners") == "home"

    def test_homeowner_policy(self) -> None:
        assert classify_policy_type("Homeowner Policy") == "home"

    def test_home_mixed_case(self) -> None:
        assert classify_policy_type("HOME") == "home"

    def test_dwelling_fire(self) -> None:
        assert classify_policy_type("Dwelling Fire DP3") == "home"

    # Auto variations
    def test_auto(self) -> None:
        assert classify_policy_type("Auto") == "auto"

    def test_personal_auto(self) -> None:
        assert classify_policy_type("Personal Auto") == "auto"

    def test_automobile(self) -> None:
        assert classify_policy_type("Automobile") == "auto"

    def test_car_insurance(self) -> None:
        assert classify_policy_type("Car Insurance") == "auto"

    def test_vehicle(self) -> None:
        assert classify_policy_type("Vehicle") == "auto"

    def test_motor_vehicle(self) -> None:
        assert classify_policy_type("Motor Vehicle") == "auto"

    # Umbrella variations
    def test_umbrella(self) -> None:
        assert classify_policy_type("Umbrella") == "umbrella"

    def test_personal_umbrella(self) -> None:
        assert classify_policy_type("Personal Umbrella Policy") == "umbrella"

    def test_excess_liability(self) -> None:
        assert classify_policy_type("Excess Liability") == "umbrella"

    def test_pup(self) -> None:
        assert classify_policy_type("PUP") == "umbrella"

    def test_excess(self) -> None:
        assert classify_policy_type("Excess") == "umbrella"

    # Unrecognized
    def test_bop_returns_none(self) -> None:
        assert classify_policy_type("BOP") is None

    def test_empty_returns_none(self) -> None:
        assert classify_policy_type("") is None

    def test_commercial_returns_none(self) -> None:
        assert classify_policy_type("Commercial General Liability") is None


# ---------------------------------------------------------------------------
# models: MultiQuoteResponse
# ---------------------------------------------------------------------------


def _make_quote(**overrides: object) -> dict:
    """Build a minimal InsuranceQuote dict with defaults."""
    base = {
        "carrier_name": "Test Carrier",
        "policy_type": "HO3",
        "annual_premium": 1200.0,
        "deductible": 1000.0,
        "confidence": "high",
    }
    base.update(overrides)
    return base


class TestMultiQuoteResponse:
    def test_parse_two_quotes(self) -> None:
        data = {
            "quotes": [
                _make_quote(policy_type="HO3", annual_premium=1200.0),
                _make_quote(policy_type="Umbrella", annual_premium=350.0),
            ]
        }
        resp = MultiQuoteResponse.model_validate(data)
        assert len(resp.quotes) == 2
        assert resp.quotes[0].policy_type == "HO3"
        assert resp.quotes[1].policy_type == "Umbrella"

    def test_parse_empty_quotes(self) -> None:
        data = {"quotes": []}
        resp = MultiQuoteResponse.model_validate(data)
        assert len(resp.quotes) == 0

    def test_parse_single_quote(self) -> None:
        data = {"quotes": [_make_quote()]}
        resp = MultiQuoteResponse.model_validate(data)
        assert len(resp.quotes) == 1


class TestMultiQuoteExtractionResult:
    def test_success_result(self) -> None:
        q = InsuranceQuote(**_make_quote())
        result = MultiQuoteExtractionResult(
            filename="test.pdf",
            success=True,
            quotes=[q],
            warnings=["minor warning"],
        )
        assert result.success is True
        assert len(result.quotes) == 1
        assert len(result.warnings) == 1

    def test_failure_result(self) -> None:
        result = MultiQuoteExtractionResult(
            filename="test.pdf",
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert len(result.quotes) == 0
        assert result.error == "Something went wrong"


# ---------------------------------------------------------------------------
# ai_extractor: carrier hints are used when carrier_name is passed
# ---------------------------------------------------------------------------


class TestCarrierHintsUsed:
    """Verify that passing carrier_name actually injects the right hints."""

    @patch("app.extraction.ai_extractor._call_gemini_text")
    @patch("app.extraction.ai_extractor.extract_text_from_pdf")
    def test_grange_hints_in_prompt(
        self, mock_pdf: MagicMock, mock_gemini: MagicMock
    ) -> None:
        from app.extraction.ai_extractor import extract_quote_data

        mock_pdf.return_value = ("fake markdown text", True)
        mock_gemini.return_value = InsuranceQuote(**_make_quote())

        extract_quote_data(b"fake-pdf", "test.pdf", carrier_name="Grange Insurance")

        # Check that the system prompt passed to Gemini contains Grange hints
        call_args = mock_gemini.call_args
        system_prompt = call_args[0][1]  # second positional arg
        assert "GRANGE INSURANCE" in system_prompt
        assert "Section I" in system_prompt
        assert "combines Home and Umbrella" in system_prompt

    @patch("app.extraction.ai_extractor._call_gemini_text")
    @patch("app.extraction.ai_extractor.extract_text_from_pdf")
    def test_default_hints_without_carrier(
        self, mock_pdf: MagicMock, mock_gemini: MagicMock
    ) -> None:
        from app.extraction.ai_extractor import extract_quote_data

        mock_pdf.return_value = ("fake markdown text", True)
        mock_gemini.return_value = InsuranceQuote(**_make_quote())

        extract_quote_data(b"fake-pdf", "test.pdf")

        call_args = mock_gemini.call_args
        system_prompt = call_args[0][1]
        assert "No carrier-specific hints" in system_prompt

    @patch("app.extraction.ai_extractor._call_gemini_text")
    @patch("app.extraction.ai_extractor.extract_text_from_pdf")
    def test_hanover_hints_in_prompt(
        self, mock_pdf: MagicMock, mock_gemini: MagicMock
    ) -> None:
        from app.extraction.ai_extractor import extract_quote_data

        mock_pdf.return_value = ("fake markdown text", True)
        mock_gemini.return_value = InsuranceQuote(**_make_quote())

        extract_quote_data(b"fake-pdf", "test.pdf", carrier_name="Hanover Insurance")

        call_args = mock_gemini.call_args
        system_prompt = call_args[0][1]
        assert "HANOVER INSURANCE" in system_prompt
        assert "combines Home and Auto" in system_prompt


# ---------------------------------------------------------------------------
# ai_extractor: multi-quote prompt includes addendum
# ---------------------------------------------------------------------------


class TestMultiQuotePrompt:
    @patch("app.extraction.ai_extractor._call_gemini_text_multi")
    @patch("app.extraction.ai_extractor.extract_text_from_pdf")
    def test_multi_prompt_has_addendum(
        self, mock_pdf: MagicMock, mock_gemini: MagicMock
    ) -> None:
        from app.extraction.ai_extractor import extract_multi_quote_data

        mock_pdf.return_value = ("fake markdown text", True)
        mock_gemini.return_value = [InsuranceQuote(**_make_quote())]

        extract_multi_quote_data(
            b"fake-pdf", "test.pdf",
            carrier_name="Grange Insurance",
            expected_policy_types=["home", "umbrella"],
        )

        call_args = mock_gemini.call_args
        system_prompt = call_args[0][1]
        assert "MULTIPLE policy types" in system_prompt
        assert "Home, Umbrella" in system_prompt
        assert "GRANGE INSURANCE" in system_prompt


# ---------------------------------------------------------------------------
# ai_extractor: _parse_multi_response_text fallback
# ---------------------------------------------------------------------------


class TestParseMultiResponseText:
    def test_parse_wrapper_format(self) -> None:
        from app.extraction.ai_extractor import _parse_multi_response_text

        data = {"quotes": [_make_quote(policy_type="HO3"), _make_quote(policy_type="Umbrella")]}
        result = _parse_multi_response_text(json.dumps(data))
        assert len(result) == 2
        assert result[0].policy_type == "HO3"

    def test_parse_bare_list_format(self) -> None:
        from app.extraction.ai_extractor import _parse_multi_response_text

        data = [_make_quote(policy_type="HO3"), _make_quote(policy_type="Auto")]
        result = _parse_multi_response_text(json.dumps(data))
        assert len(result) == 2

    def test_parse_single_object_fallback(self) -> None:
        from app.extraction.ai_extractor import _parse_multi_response_text

        data = _make_quote(policy_type="HO3")
        result = _parse_multi_response_text(json.dumps(data))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# ai_extractor: extract_and_validate_multi fewer-than-expected fallback
# ---------------------------------------------------------------------------


class TestExtractAndValidateMultiFallback:
    @patch("app.extraction.ai_extractor.extract_multi_quote_data")
    def test_fewer_quotes_warns_but_succeeds(self, mock_extract: MagicMock) -> None:
        from app.extraction.ai_extractor import extract_and_validate_multi

        # Return only 1 quote when 2 expected
        mock_extract.return_value = [
            InsuranceQuote(**_make_quote(policy_type="HO3"))
        ]

        result = extract_and_validate_multi(
            b"fake-pdf", "test.pdf",
            carrier_name="Grange",
            expected_policy_types=["home", "umbrella"],
        )

        assert result.success is True
        assert len(result.quotes) == 1
        # Should have a warning about missing types
        assert any("only extracted 1" in w for w in result.warnings)

    @patch("app.extraction.ai_extractor.extract_multi_quote_data")
    def test_exact_count_no_extra_warning(self, mock_extract: MagicMock) -> None:
        from app.extraction.ai_extractor import extract_and_validate_multi

        mock_extract.return_value = [
            InsuranceQuote(**_make_quote(policy_type="HO3")),
            InsuranceQuote(**_make_quote(policy_type="Umbrella", annual_premium=350.0)),
        ]

        result = extract_and_validate_multi(
            b"fake-pdf", "test.pdf",
            carrier_name="Grange",
            expected_policy_types=["home", "umbrella"],
        )

        assert result.success is True
        assert len(result.quotes) == 2
        # No "only extracted" warning
        assert not any("only extracted" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# COMBINED_CARRIERS dict is extensible
# ---------------------------------------------------------------------------


class TestCombinedCarriersExtensible:
    def test_dict_is_mutable(self) -> None:
        """Confirm new carriers can be added at runtime (for testing extensibility)."""
        original_len = len(COMBINED_CARRIERS)
        COMBINED_CARRIERS["test_carrier"] = ["home", "auto", "umbrella"]
        assert len(COMBINED_CARRIERS) == original_len + 1
        assert get_combined_sections("test_carrier") == ["home", "auto", "umbrella"]
        # Clean up
        del COMBINED_CARRIERS["test_carrier"]
        assert len(COMBINED_CARRIERS) == original_len
