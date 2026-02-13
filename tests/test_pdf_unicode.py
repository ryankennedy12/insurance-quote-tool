"""
Tests that Unicode characters in AI-extracted text don't crash PDF generation.

Reproduces: FPDFUnicodeEncodingException: Character "\u2013" at index 268 in text
is outside the range of characters supported by the font used: "helveticaI".

Every text path that touches cell() or multi_cell() is exercised with Unicode
characters that Helvetica cannot render (en dash, smart quotes, bullets, etc.).
"""

import os
import tempfile
import pytest

from app.extraction.models import (
    ComparisonSession,
    CarrierBundle,
    CurrentPolicy,
    InsuranceQuote,
)
from app.pdf_gen.generator import generate_comparison_pdf, _sanitize_text


# ── Sanitizer unit tests ──────────────────────────────────────


class TestSanitizeText:
    """Unit tests for the _sanitize_text function."""

    def test_en_dash(self):
        assert _sanitize_text("coverage \u2013 limits") == "coverage - limits"

    def test_em_dash(self):
        assert _sanitize_text("note \u2014 important") == "note - important"

    def test_smart_single_quotes(self):
        assert _sanitize_text("\u2018hello\u2019") == "'hello'"

    def test_smart_double_quotes(self):
        assert _sanitize_text("\u201chello\u201d") == '"hello"'

    def test_bullet(self):
        assert _sanitize_text("\u2022 item") == "- item"

    def test_ellipsis(self):
        assert _sanitize_text("wait\u2026") == "wait..."

    def test_non_breaking_space(self):
        assert _sanitize_text("hello\u00a0world") == "hello world"

    def test_figure_dash(self):
        assert _sanitize_text("100\u2012200") == "100-200"

    def test_middle_dot(self):
        assert _sanitize_text("item\u00b7next") == "item-next"

    def test_multiple_replacements(self):
        text = "\u201cCoverage A\u201d \u2013 Dwelling \u2022 $325,000"
        result = _sanitize_text(text)
        assert result == '"Coverage A" - Dwelling - $325,000'
        # Verify no Unicode remains
        for ch in result:
            assert ord(ch) < 128, f"Non-ASCII character remains: {ch!r} (U+{ord(ch):04X})"

    def test_passthrough_ascii(self):
        text = "Normal ASCII text $1,234.56"
        assert _sanitize_text(text) == text

    def test_non_string_passthrough(self):
        assert _sanitize_text(42) == 42
        assert _sanitize_text(None) is None


# ── PDF generation integration tests ──────────────────────────


def _make_unicode_session() -> ComparisonSession:
    """Build a ComparisonSession with Unicode characters in every text field."""

    current = CurrentPolicy(
        carrier_name="Nationwide \u2013 Current",  # en dash in carrier name
        home_premium=1450.0,
        home_dwelling=325000.0,
        home_other_structures=32500.0,
        home_liability=300000.0,
        home_personal_property=162500.0,
        home_loss_of_use=65000.0,
        home_deductible=1000.0,
        auto_premium=2100.0,
        auto_limits="250/500/100",
        auto_um_uim="250/500",
        auto_comp_deductible="$500 \u2013 glass $0",  # en dash
        auto_collision_deductible=500.0,
        umbrella_premium=350.0,
        umbrella_limits="1M CSL",
        umbrella_deductible=0.0,
    )

    # Carrier 1: Unicode in endorsements (italic font path — the crash site)
    erie_home = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="HO3",
        annual_premium=1285.0,
        deductible=1000.0,
        wind_hail_deductible=2500.0,
        coverage_limits={
            "dwelling": 325000,
            "other_structures": 32500,
            "personal_property": 162500,
            "loss_of_use": 65000,
            "personal_liability": 300000,
            "medical_payments": 5000,
        },
        endorsements=[
            "Water Backup \u2013 $10K",           # en dash (the exact crash char)
            "Scheduled Property \u2014 Jewelry",   # em dash
            "\u2022 Extended Replacement Cost",     # bullet
            "Identity Theft ($25K\u2026)",          # ellipsis
        ],
        discounts_applied=[
            "Multi\u2010Policy Discount",           # Unicode hyphen
            "\u201cClaims\u2011Free\u201d Discount", # smart quotes + non-breaking hyphen
        ],
        confidence="high",
        notes="Excellent rate \u2013 superior water backup. \u201cBest value\u201d option.",
    )

    erie_auto = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="Auto",
        annual_premium=1995.0,
        deductible=500.0,
        coverage_limits={
            "bi_per_person": 500_000,
            "bi_per_accident": 500_000,
            "pd_per_accident": 250_000,
            "um_uim": 500_000,
            "comprehensive": 500,
        },
        endorsements=["Accident Forgiveness \u2013 included"],
        discounts_applied=["Safe Driver\u2019s Discount"],  # right single quote
        confidence="high",
        notes="2019 Honda Pilot \u2022 2021 Toyota Camry",  # bullet
    )

    erie_umbrella = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="Umbrella",
        annual_premium=320.0,
        deductible=0.0,
        coverage_limits={"umbrella_limit": 2_000_000},
        endorsements=["Worldwide Coverage \u2013 all territories"],
        discounts_applied=[],
        confidence="high",
        notes="Requires Erie auto/home\u2026",
    )

    # Carrier 2: Unicode in carrier name itself
    westfield_home = InsuranceQuote(
        carrier_name="Westfield\u00a0Insurance",  # non-breaking space
        policy_type="HO5",
        annual_premium=1425.0,
        deductible=1000.0,
        coverage_limits={
            "dwelling": 325000,
            "other_structures": 32500,
            "personal_property": 243750,
            "personal_liability": 500000,
            "medical_payments": 5000,
        },
        endorsements=[
            "Ordinance or Law (50%) \u00b7 Equipment Breakdown",  # middle dot
        ],
        discounts_applied=[
            "New Home Discount",
        ],
        confidence="high",
        notes="HO5 open\u2010perils policy\u2014broader coverage than HO3.",
    )

    westfield_auto = InsuranceQuote(
        carrier_name="Westfield\u00a0Insurance",
        policy_type="Auto",
        annual_premium=2120.0,
        deductible=500.0,
        coverage_limits={
            "bi_per_person": 500_000,
            "bi_per_accident": 500_000,
            "pd_per_accident": 250_000,
            "um_uim": 500_000,
            "comprehensive": 500,
        },
        endorsements=["Rental \u2013 $50/day", "Roadside \u2022 24/7"],
        discounts_applied=["Bundle Discount"],
        confidence="high",
        notes="Good coverage\u2026 auto rate higher than Erie\u2019s.",
    )

    westfield_umbrella = InsuranceQuote(
        carrier_name="Westfield\u00a0Insurance",
        policy_type="Umbrella",
        annual_premium=350.0,
        deductible=0.0,
        coverage_limits={"umbrella_limit": 2_000_000},
        endorsements=[],
        discounts_applied=[],
        confidence="high",
        notes="Standard terms.",
    )

    return ComparisonSession(
        client_name="John \u201cJack\u201d O\u2019Brien",  # smart quotes + right apostrophe
        date="2026-02-12",
        current_policy=current,
        carriers=[
            CarrierBundle(
                carrier_name="Erie Insurance",
                home=erie_home,
                auto=erie_auto,
                umbrella=erie_umbrella,
            ),
            CarrierBundle(
                carrier_name="Westfield\u00a0Insurance",
                home=westfield_home,
                auto=westfield_auto,
                umbrella=westfield_umbrella,
            ),
        ],
        sections_included=["home", "auto", "umbrella"],
        agent_notes=(
            "Client prefers Erie\u2019s bundle pricing. "
            "Follow up re: \u201cscheduled jewelry\u201d endorsement. "
            "Current policy expires 3/15 \u2013 need decision by 3/1\u2026"
        ),
    )


class TestPDFUnicodeGeneration:
    """Integration tests: generate real PDFs with Unicode-laden data."""

    def test_full_comparison_with_unicode(self, tmp_path):
        """
        Reproduce the exact crash: Unicode chars in endorsements/discounts/notes
        rendered in italic Helvetica font. Must not raise FPDFUnicodeEncodingException.
        """
        session = _make_unicode_session()
        output = str(tmp_path / "unicode_test.pdf")

        # This is the line that used to crash with FPDFUnicodeEncodingException
        result = generate_comparison_pdf(
            session=session,
            output_path=output,
        )

        assert os.path.exists(result)
        assert os.path.getsize(result) > 0

    def test_unicode_in_agent_notes_only(self, tmp_path):
        """Agent notes with smart quotes and dashes."""
        session = ComparisonSession(
            client_name="Test Client",
            date="2026-02-12",
            carriers=[
                CarrierBundle(
                    carrier_name="Carrier A",
                    home=InsuranceQuote(
                        carrier_name="Carrier A",
                        policy_type="HO3",
                        annual_premium=1000.0,
                        deductible=1000.0,
                        confidence="high",
                    ),
                ),
                CarrierBundle(
                    carrier_name="Carrier B",
                    home=InsuranceQuote(
                        carrier_name="Carrier B",
                        policy_type="HO3",
                        annual_premium=1100.0,
                        deductible=1000.0,
                        confidence="high",
                    ),
                ),
            ],
            sections_included=["home"],
            agent_notes="\u201cBest option\u201d \u2013 go with Carrier A\u2019s HO3\u2026",
        )
        output = str(tmp_path / "agent_notes_unicode.pdf")

        result = generate_comparison_pdf(session=session, output_path=output)
        assert os.path.exists(result)

    def test_unicode_in_carrier_name(self, tmp_path):
        """Carrier name with non-breaking space and en dash in table headers."""
        session = ComparisonSession(
            client_name="Test Client",
            date="2026-02-12",
            carriers=[
                CarrierBundle(
                    carrier_name="Auto\u2013Owners\u00a0Insurance",
                    home=InsuranceQuote(
                        carrier_name="Auto\u2013Owners\u00a0Insurance",
                        policy_type="HO3",
                        annual_premium=1200.0,
                        deductible=1000.0,
                        confidence="high",
                    ),
                ),
                CarrierBundle(
                    carrier_name="Carrier B",
                    home=InsuranceQuote(
                        carrier_name="Carrier B",
                        policy_type="HO3",
                        annual_premium=1100.0,
                        deductible=1000.0,
                        confidence="high",
                    ),
                ),
            ],
            sections_included=["home"],
        )
        output = str(tmp_path / "carrier_name_unicode.pdf")

        result = generate_comparison_pdf(session=session, output_path=output)
        assert os.path.exists(result)

    def test_unicode_in_client_name(self, tmp_path):
        """Client name with smart apostrophe (rendered in bold font)."""
        session = ComparisonSession(
            client_name="O\u2019Brien & Partners",
            date="2026-02-12",
            carriers=[
                CarrierBundle(
                    carrier_name="Carrier A",
                    home=InsuranceQuote(
                        carrier_name="Carrier A",
                        policy_type="HO3",
                        annual_premium=1000.0,
                        deductible=1000.0,
                        confidence="high",
                    ),
                ),
                CarrierBundle(
                    carrier_name="Carrier B",
                    home=InsuranceQuote(
                        carrier_name="Carrier B",
                        policy_type="HO3",
                        annual_premium=1100.0,
                        deductible=1000.0,
                        confidence="high",
                    ),
                ),
            ],
            sections_included=["home"],
        )
        output = str(tmp_path / "client_name_unicode.pdf")

        result = generate_comparison_pdf(session=session, output_path=output)
        assert os.path.exists(result)

    def test_endorsements_italic_font_crash(self, tmp_path):
        """
        Direct reproduction: en dash in endorsement text rendered in helveticaI.
        This was the exact error: Character "\u2013" ... font "helveticaI".
        """
        session = ComparisonSession(
            client_name="Test Client",
            date="2026-02-12",
            carriers=[
                CarrierBundle(
                    carrier_name="Erie Insurance",
                    home=InsuranceQuote(
                        carrier_name="Erie Insurance",
                        policy_type="HO3",
                        annual_premium=1285.0,
                        deductible=1000.0,
                        coverage_limits={"dwelling": 325000},
                        endorsements=[
                            "Water Backup Coverage \u2013 $10,000 limit",
                            "Scheduled Personal Property \u2014 Jewelry ($15K)",
                        ],
                        discounts_applied=[
                            "Multi\u2013Policy Discount",
                            "Claims\u2019 Free Discount",
                        ],
                        confidence="high",
                    ),
                ),
                CarrierBundle(
                    carrier_name="Westfield",
                    home=InsuranceQuote(
                        carrier_name="Westfield",
                        policy_type="HO3",
                        annual_premium=1400.0,
                        deductible=1000.0,
                        confidence="high",
                    ),
                ),
            ],
            sections_included=["home"],
        )
        output = str(tmp_path / "endorsements_italic_unicode.pdf")

        result = generate_comparison_pdf(session=session, output_path=output)
        assert os.path.exists(result)

    def test_all_unicode_chars_at_once(self, tmp_path):
        """Stress test: every mapped Unicode character in a single notes field."""
        all_chars = (
            "en\u2013dash em\u2014dash left\u2018sq right\u2019sq "
            "left\u201cdq right\u201ddq bullet\u2022 ellipsis\u2026 "
            "nbsp\u00a0here hyphen\u2010mark nbhyphen\u2011mark "
            "figdash\u2012mark middot\u00b7mark"
        )
        session = ComparisonSession(
            client_name="Test Client",
            date="2026-02-12",
            carriers=[
                CarrierBundle(
                    carrier_name="Carrier A",
                    home=InsuranceQuote(
                        carrier_name="Carrier A",
                        policy_type="HO3",
                        annual_premium=1000.0,
                        deductible=1000.0,
                        confidence="high",
                        notes=all_chars,
                    ),
                ),
                CarrierBundle(
                    carrier_name="Carrier B",
                    home=InsuranceQuote(
                        carrier_name="Carrier B",
                        policy_type="HO3",
                        annual_premium=1100.0,
                        deductible=1000.0,
                        confidence="high",
                    ),
                ),
            ],
            sections_included=["home"],
            agent_notes=all_chars,
        )
        output = str(tmp_path / "all_unicode_chars.pdf")

        result = generate_comparison_pdf(session=session, output_path=output)
        assert os.path.exists(result)
