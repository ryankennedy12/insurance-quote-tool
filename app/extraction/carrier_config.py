"""Carrier-specific configuration for combined PDF handling."""

from typing import Optional


# Maps carrier name patterns (lowercase) to the list of policy types
# bundled into a single PDF by that carrier.
# Key: substring to match in carrier name (lowercase)
# Value: list of policy section names that come combined in one PDF
COMBINED_CARRIERS: dict[str, list[str]] = {
    "grange": ["home", "umbrella"],
    "hanover": ["home", "auto"],
}


def get_combined_sections(carrier_name: str) -> Optional[list[str]]:
    """Return combined policy sections for a carrier, or None if not combined.

    Args:
        carrier_name: Carrier name string (case-insensitive substring matching)

    Returns:
        List of combined section names (e.g., ["home", "umbrella"]) or None
    """
    carrier_lower = carrier_name.lower().strip()
    for pattern, sections in COMBINED_CARRIERS.items():
        if pattern in carrier_lower:
            return sections
    return None


def is_combined_carrier(carrier_name: str) -> bool:
    """Check if a carrier bundles multiple policy types in one PDF."""
    return get_combined_sections(carrier_name) is not None


def classify_policy_type(policy_type: str) -> Optional[str]:
    """Map an InsuranceQuote.policy_type string to a CarrierBundle section name.

    Uses fuzzy substring matching to handle variations like "Homeowners",
    "HO-3", "Personal Umbrella", "Excess Liability", "Personal Auto", etc.

    Args:
        policy_type: Raw policy type from extraction (e.g., "HO3", "Auto", "Umbrella")

    Returns:
        Section name ("home", "auto", "umbrella") or None if unrecognized
    """
    pt = policy_type.lower().strip()

    # Home policies
    home_keywords = [
        "ho3", "ho5", "ho-3", "ho-5", "ho 3", "ho 5",
        "homeowner", "home owner", "dwelling", "dp3", "dp-3",
        "houseowner", "house owner",
    ]
    if any(kw in pt for kw in home_keywords):
        return "home"
    # Catch bare "home" but not "homeowner" (already caught above)
    if "home" in pt and "umbrella" not in pt:
        return "home"

    # Auto policies
    auto_keywords = [
        "auto", "car", "vehicle", "personal auto", "pa ",
        "motor", "automobile",
    ]
    if any(kw in pt for kw in auto_keywords):
        return "auto"

    # Umbrella policies
    umbrella_keywords = [
        "umbrella", "excess", "pup", "personal umbrella",
        "excess liability",
    ]
    if any(kw in pt for kw in umbrella_keywords):
        return "umbrella"

    return None
