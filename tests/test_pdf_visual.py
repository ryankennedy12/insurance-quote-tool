"""
Visual test script for PDF generator.
Creates 4 sample PDFs with different configurations for manual review.

Run: python tests/test_pdf_visual.py
Output: data/outputs/test_*.pdf
"""

from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extraction.models import (
    ComparisonSession,
    CarrierBundle,
    CurrentPolicy,
    InsuranceQuote,
)
from app.pdf_gen.generator import generate_comparison_pdf


def create_test_1_2carriers_current() -> ComparisonSession:
    """Test 1: 2 carriers + current policy, home only (portrait)."""

    current = CurrentPolicy(
        carrier_name="Nationwide",
        home_premium=1450.0,
        home_dwelling=325000.0,
        home_other_structures=32500.0,
        home_liability=300000.0,
        home_personal_property=162500.0,
        home_loss_of_use=65000.0,
        home_deductible=1000.0,
    )

    erie_home = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="HO3",
        effective_date="2026-03-01",
        expiration_date="2027-03-01",
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
            "Water Backup Coverage ($10K)",
            "Scheduled Personal Property - Jewelry ($15K)",
            "Extended Replacement Cost (125%)",
        ],
        discounts_applied=[
            "Multi-Policy Discount",
            "Protective Device Discount",
            "Claims-Free Discount",
        ],
        confidence="high",
        notes="Excellent rate with superior water backup coverage. Recommend bundling auto for additional 12% discount.",
    )

    westfield_home = InsuranceQuote(
        carrier_name="Westfield",
        policy_type="HO5",
        effective_date="2026-03-01",
        expiration_date="2027-03-01",
        annual_premium=1425.0,
        deductible=1000.0,
        wind_hail_deductible=None,
        coverage_limits={
            "dwelling": 325000,
            "other_structures": 32500,
            "personal_property": 243750,
            "loss_of_use": "ALS",  # Actual Loss Sustained
            "personal_liability": 500000,
            "medical_payments": 5000,
        },
        endorsements=[
            "Ordinance or Law Coverage (50%)",
            "Equipment Breakdown Coverage",
            "Identity Fraud Expense Coverage ($25K)",
        ],
        discounts_applied=[
            "New Home Discount",
            "Protective Device Discount",
        ],
        confidence="high",
        notes="HO5 open-perils policy with superior coverage. Higher liability limits included. Slightly higher premium reflects broader coverage.",
    )

    return ComparisonSession(
        client_name="John & Sarah Martinez",
        date="2026-02-11",
        current_policy=current,
        carriers=[
            CarrierBundle(carrier_name="Erie Insurance", home=erie_home),
            CarrierBundle(carrier_name="Westfield", home=westfield_home),
        ],
        sections_included=["home"],
    )


def create_test_2_3carriers_current() -> ComparisonSession:
    """Test 2: 3 carriers + current policy, home + auto (portrait)."""

    current = CurrentPolicy(
        carrier_name="State Farm",
        home_premium=1620.0,
        home_dwelling=450000.0,
        home_other_structures=45000.0,
        home_liability=300000.0,
        home_personal_property=225000.0,
        home_loss_of_use=90000.0,
        home_deductible=2500.0,
        auto_premium=2280.0,
        auto_limits="250/500/100",
        auto_um_uim="250/500",
        auto_comp_deductible="$500 (glass $0)",
        auto_collision_deductible=500.0,
    )

    erie_home = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="HO3",
        effective_date="2026-03-15",
        annual_premium=1480.0,
        deductible=2500.0,
        wind_hail_deductible=5000.0,
        coverage_limits={
            "dwelling": 450000,
            "other_structures": 45000,
            "personal_property": 225000,
            "loss_of_use": 90000,
            "personal_liability": 500000,
            "medical_payments": 5000,
        },
        endorsements=["Water Backup ($15K)", "Sewer Backup", "Identity Theft ($50K)"],
        discounts_applied=["Bundle Discount", "Claims-Free", "Protective Devices"],
        confidence="high",
        notes="Competitive rate with upgraded liability limits.",
    )

    erie_auto = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="Auto",
        effective_date="2026-03-15",
        annual_premium=1995.0,
        deductible=500.0,
        coverage_limits={
            "bodily_injury": "500/500",
            "property_damage": 250000,
            "um_uim": "500/500",
            "comprehensive": 500,
        },
        endorsements=["Accident Forgiveness", "Vanishing Deductible"],
        discounts_applied=["Multi-Policy", "Safe Driver", "Anti-Theft"],
        confidence="high",
        notes="Excellent multi-car discount. 2019 Honda Pilot + 2021 Toyota Camry.",
    )

    westfield_home = InsuranceQuote(
        carrier_name="Westfield",
        policy_type="HO3",
        effective_date="2026-03-15",
        annual_premium=1525.0,
        deductible=2500.0,
        coverage_limits={
            "dwelling": 450000,
            "other_structures": 45000,
            "personal_property": 225000,
            "loss_of_use": 90000,
            "personal_liability": 300000,
            "medical_payments": 5000,
        },
        endorsements=["Equipment Breakdown", "Ordinance or Law (25%)"],
        discounts_applied=["Multi-Policy", "Claim-Free"],
        confidence="high",
        notes="Standard coverage. Competitive pricing for the area.",
    )

    westfield_auto = InsuranceQuote(
        carrier_name="Westfield",
        policy_type="Auto",
        effective_date="2026-03-15",
        annual_premium=2120.0,
        deductible=500.0,
        coverage_limits={
            "bodily_injury": "500/500",
            "property_damage": 250000,
            "um_uim": "500/500",
            "comprehensive": 500,
        },
        endorsements=["Rental Reimbursement", "Roadside Assistance"],
        discounts_applied=["Bundle Discount", "Safe Driver"],
        confidence="high",
        notes="Good coverage but auto rate is higher than Erie.",
    )

    grange_home = InsuranceQuote(
        carrier_name="Grange Insurance",
        policy_type="HO3",
        effective_date="2026-03-15",
        annual_premium=1555.0,
        deductible=2500.0,
        coverage_limits={
            "dwelling": 450000,
            "other_structures": 45000,
            "personal_property": 225000,
            "loss_of_use": 90000,
            "personal_liability": 300000,
            "medical_payments": 5000,
        },
        endorsements=["Water Backup ($10K)", "Home Systems Protection"],
        discounts_applied=["Multi-Policy", "Loyalty Discount"],
        confidence="medium",
        notes="Ohio-based carrier with local service focus.",
    )

    grange_auto = InsuranceQuote(
        carrier_name="Grange Insurance",
        policy_type="Auto",
        effective_date="2026-03-15",
        annual_premium=2050.0,
        deductible=500.0,
        coverage_limits={
            "bodily_injury": "500/500",
            "property_damage": 250000,
            "um_uim": "500/500",
            "comprehensive": 500,
        },
        endorsements=["Accident Forgiveness"],
        discounts_applied=["Bundle Discount"],
        confidence="medium",
        notes="Competitive total premium with strong local claims service.",
    )

    return ComparisonSession(
        client_name="Robert & Jennifer Chen",
        date="2026-02-11",
        current_policy=current,
        carriers=[
            CarrierBundle(carrier_name="Erie Insurance", home=erie_home, auto=erie_auto),
            CarrierBundle(carrier_name="Westfield", home=westfield_home, auto=westfield_auto),
            CarrierBundle(carrier_name="Grange Insurance", home=grange_home, auto=grange_auto),
        ],
        sections_included=["home", "auto"],
    )


def create_test_3_5carriers_current() -> ComparisonSession:
    """Test 3: 5 carriers + current policy, home + auto + umbrella (landscape)."""

    current = CurrentPolicy(
        carrier_name="Progressive",
        home_premium=2100.0,
        home_dwelling=650000.0,
        home_other_structures=65000.0,
        home_liability=300000.0,
        home_personal_property=325000.0,
        home_loss_of_use=130000.0,
        home_deductible=5000.0,
        auto_premium=3200.0,
        auto_limits="1M CSL",
        auto_um_uim="1M CSL",
        auto_comp_deductible="$1000",
        auto_collision_deductible=1000.0,
        umbrella_premium=385.0,
        umbrella_limits="2M",
        umbrella_deductible=0.0,
    )

    # Erie bundle
    erie_home = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="HO5",
        annual_premium=1925.0,
        deductible=5000.0,
        wind_hail_deductible=10000.0,
        coverage_limits={
            "dwelling": 650000,
            "other_structures": 65000,
            "personal_property": 487500,
            "loss_of_use": "ALS",
            "personal_liability": 500000,
            "medical_payments": 10000,
        },
        endorsements=["Water Backup ($25K)", "Ordinance/Law (100%)", "Jewelry Schedule ($75K)"],
        discounts_applied=["Bundle", "Claims-Free", "Security System", "Loyalty"],
        confidence="high",
        notes="HO5 open-perils. Excellent coverage for high-value home.",
    )

    erie_auto = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="Auto",
        annual_premium=2850.0,
        deductible=1000.0,
        coverage_limits={"bodily_injury": "1M CSL", "um_uim": "1M CSL", "comprehensive": 1000},
        endorsements=["Accident Forgiveness", "Vanishing Deductible", "Rental Coverage"],
        discounts_applied=["Multi-Policy", "Safe Driver", "Multi-Car"],
        confidence="high",
        notes="3 vehicles: 2022 Tesla Model Y, 2023 Lexus RX, 2020 Honda Accord.",
    )

    erie_umbrella = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="Umbrella",
        annual_premium=320.0,
        deductible=0.0,
        coverage_limits={"liability": "2M"},
        endorsements=["Worldwide Coverage"],
        discounts_applied=["Bundle Discount"],
        confidence="high",
        notes="Excellent value for $2M coverage. Requires Erie auto/home.",
    )

    # Westfield bundle
    westfield_home = InsuranceQuote(
        carrier_name="Westfield",
        policy_type="HO5",
        annual_premium=2050.0,
        deductible=5000.0,
        coverage_limits={
            "dwelling": 650000,
            "other_structures": 65000,
            "personal_property": 487500,
            "loss_of_use": 195000,
            "personal_liability": 500000,
            "medical_payments": 10000,
        },
        endorsements=["Equipment Breakdown", "Identity Fraud ($50K)", "Cyber Protection"],
        discounts_applied=["Bundle", "New Home"],
        confidence="high",
        notes="Competitive HO5. Strong coverage breadth.",
    )

    westfield_auto = InsuranceQuote(
        carrier_name="Westfield",
        policy_type="Auto",
        annual_premium=2975.0,
        deductible=1000.0,
        coverage_limits={"bodily_injury": "1M CSL", "um_uim": "1M CSL", "comprehensive": 1000},
        endorsements=["Rental Reimbursement", "Roadside Assistance"],
        discounts_applied=["Multi-Policy", "Safe Driver"],
        confidence="high",
        notes="Solid rate for premium vehicles.",
    )

    westfield_umbrella = InsuranceQuote(
        carrier_name="Westfield",
        policy_type="Umbrella",
        annual_premium=350.0,
        deductible=0.0,
        coverage_limits={"liability": "2M"},
        endorsements=[],
        discounts_applied=["Bundle Discount"],
        confidence="high",
        notes="Standard umbrella terms.",
    )

    # State Farm bundle
    statefarm_home = InsuranceQuote(
        carrier_name="State Farm",
        policy_type="HO3",
        annual_premium=2200.0,
        deductible=5000.0,
        coverage_limits={
            "dwelling": 650000,
            "other_structures": 65000,
            "personal_property": 325000,
            "loss_of_use": 130000,
            "personal_liability": 500000,
            "medical_payments": 5000,
        },
        endorsements=["Water Backup ($10K)", "Extended Replacement Cost (125%)"],
        discounts_applied=["Multi-Policy"],
        confidence="high",
        notes="HO3 only (no HO5 available for this risk). Higher premium.",
    )

    statefarm_auto = InsuranceQuote(
        carrier_name="State Farm",
        policy_type="Auto",
        annual_premium=3100.0,
        deductible=1000.0,
        coverage_limits={"bodily_injury": "1M CSL", "um_uim": "1M CSL", "comprehensive": 1000},
        endorsements=["Accident Forgiveness", "Rental Coverage"],
        discounts_applied=["Bundle", "Safe Driver"],
        confidence="high",
        notes="Competitive but higher than Erie/Westfield.",
    )

    statefarm_umbrella = InsuranceQuote(
        carrier_name="State Farm",
        policy_type="Umbrella",
        annual_premium=380.0,
        deductible=0.0,
        coverage_limits={"liability": "2M"},
        endorsements=[],
        discounts_applied=[],
        confidence="high",
        notes="Standard umbrella pricing.",
    )

    # Nationwide bundle
    nationwide_home = InsuranceQuote(
        carrier_name="Nationwide",
        policy_type="HO3",
        annual_premium=2175.0,
        deductible=5000.0,
        coverage_limits={
            "dwelling": 650000,
            "other_structures": 65000,
            "personal_property": 325000,
            "loss_of_use": 130000,
            "personal_liability": 500000,
            "medical_payments": 5000,
        },
        endorsements=["Water Backup ($15K)", "Scheduled Property"],
        discounts_applied=["Multi-Policy", "Claims-Free"],
        confidence="high",
        notes="Strong HO3 coverage. Good middle option.",
    )

    nationwide_auto = InsuranceQuote(
        carrier_name="Nationwide",
        policy_type="Auto",
        annual_premium=3050.0,
        deductible=1000.0,
        coverage_limits={"bodily_injury": "1M CSL", "um_uim": "1M CSL", "comprehensive": 1000},
        endorsements=["Accident Forgiveness", "Vanishing Deductible"],
        discounts_applied=["Bundle", "Safe Driver"],
        confidence="high",
        notes="Competitive multi-car pricing.",
    )

    nationwide_umbrella = InsuranceQuote(
        carrier_name="Nationwide",
        policy_type="Umbrella",
        annual_premium=365.0,
        deductible=0.0,
        coverage_limits={"liability": "2M"},
        endorsements=[],
        discounts_applied=["Bundle Discount"],
        confidence="high",
        notes="Good value for umbrella coverage.",
    )

    # Grange bundle
    grange_home = InsuranceQuote(
        carrier_name="Grange Insurance",
        policy_type="HO3",
        annual_premium=2125.0,
        deductible=5000.0,
        coverage_limits={
            "dwelling": 650000,
            "other_structures": 65000,
            "personal_property": 325000,
            "loss_of_use": 130000,
            "personal_liability": 500000,
            "medical_payments": 5000,
        },
        endorsements=["Water Backup ($10K)", "Home Systems Protection"],
        discounts_applied=["Multi-Policy", "Loyalty"],
        confidence="medium",
        notes="Best overall pricing. Ohio-based with strong local service.",
    )

    grange_auto = InsuranceQuote(
        carrier_name="Grange Insurance",
        policy_type="Auto",
        annual_premium=2900.0,
        deductible=1000.0,
        coverage_limits={"bodily_injury": "1M CSL", "um_uim": "1M CSL", "comprehensive": 1000},
        endorsements=["Accident Forgiveness", "Rental Coverage"],
        discounts_applied=["Bundle", "Safe Driver"],
        confidence="medium",
        notes="Most competitive auto rate among Ohio carriers.",
    )

    grange_umbrella = InsuranceQuote(
        carrier_name="Grange Insurance",
        policy_type="Umbrella",
        annual_premium=340.0,
        deductible=0.0,
        coverage_limits={"liability": "2M"},
        endorsements=[],
        discounts_applied=["Bundle Discount"],
        confidence="medium",
        notes="Best umbrella rate. Total bundle is lowest overall.",
    )

    return ComparisonSession(
        client_name="Michael & Patricia Williams",
        date="2026-02-11",
        current_policy=current,
        carriers=[
            CarrierBundle(carrier_name="Erie Insurance", home=erie_home, auto=erie_auto, umbrella=erie_umbrella),
            CarrierBundle(carrier_name="Westfield", home=westfield_home, auto=westfield_auto, umbrella=westfield_umbrella),
            CarrierBundle(carrier_name="State Farm", home=statefarm_home, auto=statefarm_auto, umbrella=statefarm_umbrella),
            CarrierBundle(carrier_name="Nationwide", home=nationwide_home, auto=nationwide_auto, umbrella=nationwide_umbrella),
            CarrierBundle(carrier_name="Grange Insurance", home=grange_home, auto=grange_auto, umbrella=grange_umbrella),
        ],
        sections_included=["home", "auto", "umbrella"],
    )


def create_test_4_3carriers_no_current() -> ComparisonSession:
    """Test 4: 3 carriers, NO current policy, home + auto, with agent notes."""

    erie_home = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="HO3",
        annual_premium=1680.0,
        deductible=2500.0,
        wind_hail_deductible=5000.0,
        coverage_limits={
            "dwelling": 425000,
            "other_structures": 42500,
            "personal_property": 212500,
            "loss_of_use": 85000,
            "personal_liability": 500000,
            "medical_payments": 5000,
        },
        endorsements=["Water Backup ($15K)", "Equipment Breakdown", "Identity Theft ($25K)"],
        discounts_applied=["New Customer", "Protective Devices", "Claims-Free"],
        confidence="high",
        notes="Best overall value. Strong bundle discount potential if auto added.",
    )

    erie_auto = InsuranceQuote(
        carrier_name="Erie Insurance",
        policy_type="Auto",
        annual_premium=2150.0,
        deductible=500.0,
        coverage_limits={
            "bodily_injury": "500/500",
            "property_damage": 250000,
            "um_uim": "500/500",
            "comprehensive": 500,
        },
        endorsements=["Accident Forgiveness", "Rental Coverage ($50/day)"],
        discounts_applied=["Bundle Discount (12%)", "Safe Driver", "Anti-Theft"],
        confidence="high",
        notes="Includes 12% bundle discount already applied. Vehicles: 2021 Subaru Outback, 2023 Honda CR-V.",
    )

    westfield_home = InsuranceQuote(
        carrier_name="Westfield",
        policy_type="HO3",
        annual_premium=1725.0,
        deductible=2500.0,
        coverage_limits={
            "dwelling": 425000,
            "other_structures": 42500,
            "personal_property": 212500,
            "loss_of_use": 85000,
            "personal_liability": 500000,
            "medical_payments": 5000,
        },
        endorsements=["Ordinance or Law (50%)", "Sewer Backup"],
        discounts_applied=["New Home", "Claim-Free"],
        confidence="high",
        notes="Competitive rate with ordinance/law coverage included.",
    )

    westfield_auto = InsuranceQuote(
        carrier_name="Westfield",
        policy_type="Auto",
        annual_premium=2250.0,
        deductible=500.0,
        coverage_limits={
            "bodily_injury": "500/500",
            "property_damage": 250000,
            "um_uim": "500/500",
            "comprehensive": 500,
        },
        endorsements=["Roadside Assistance", "Rental Reimbursement"],
        discounts_applied=["Bundle Discount", "Safe Driver"],
        confidence="high",
        notes="Solid coverage but auto rate is $100/year higher than Erie.",
    )

    statefarm_home = InsuranceQuote(
        carrier_name="State Farm",
        policy_type="HO3",
        annual_premium=1795.0,
        deductible=2500.0,
        coverage_limits={
            "dwelling": 425000,
            "other_structures": 42500,
            "personal_property": 212500,
            "loss_of_use": 85000,
            "personal_liability": 300000,
            "medical_payments": 5000,
        },
        endorsements=["Water Backup ($10K)", "Extended Replacement Cost (125%)"],
        discounts_applied=["Multi-Policy"],
        confidence="high",
        notes="Higher home premium. Lower liability limits (300K vs 500K from Erie/Westfield).",
    )

    statefarm_auto = InsuranceQuote(
        carrier_name="State Farm",
        policy_type="Auto",
        annual_premium=2325.0,
        deductible=500.0,
        coverage_limits={
            "bodily_injury": "500/500",
            "property_damage": 250000,
            "um_uim": "500/500",
            "comprehensive": 500,
        },
        endorsements=["Accident Forgiveness"],
        discounts_applied=["Bundle", "Drive Safe & Save"],
        confidence="high",
        notes="Highest total premium among the three options.",
    )

    return ComparisonSession(
        client_name="Amanda & David Thompson",
        date="2026-02-11",
        current_policy=None,
        carriers=[
            CarrierBundle(carrier_name="Erie Insurance", home=erie_home, auto=erie_auto),
            CarrierBundle(carrier_name="Westfield", home=westfield_home, auto=westfield_auto),
            CarrierBundle(carrier_name="State Farm", home=statefarm_home, auto=statefarm_auto),
        ],
        sections_included=["home", "auto"],
        agent_notes="Client prefers Erie for bundling discount. Follow up by Friday.",
    )


def main():
    """Generate all 4 test PDFs."""
    output_dir = Path("data/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("PDF Visual Test Generator")
    print("=" * 60)
    print()

    tests = [
        ("test_2carriers_current.pdf", create_test_1_2carriers_current(), "2 carriers + current, home only"),
        ("test_3carriers_current.pdf", create_test_2_3carriers_current(), "3 carriers + current, home + auto"),
        ("test_5carriers_current.pdf", create_test_3_5carriers_current(), "5 carriers + current, full bundle"),
        ("test_3carriers_no_current.pdf", create_test_4_3carriers_no_current(), "3 carriers, no current, with notes"),
    ]

    for filename, session, description in tests:
        output_path = output_dir / filename
        print(f"Generating {filename}...")
        print(f"  Description: {description}")
        print(f"  Client: {session.client_name}")
        print(f"  Sections: {', '.join(session.sections_included)}")
        print(f"  Carriers: {len(session.carriers)}")
        print(f"  Has Current: {session.current_policy is not None}")
        print(f"  Has Notes: {session.agent_notes is not None}")

        try:
            result_path = generate_comparison_pdf(
                session=session,
                output_path=str(output_path),
                logo_path="assets/logo_transparent.png",
                date_str=session.date,
                agent_notes=session.agent_notes,
            )
            print(f"  [OK] Generated: {result_path}")
            print()
        except Exception as e:
            print(f"  [ERROR] {e}")
            print()
            raise

    print("=" * 60)
    print(f"All PDFs generated successfully in {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
