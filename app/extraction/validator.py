import logging
from datetime import date

from app.extraction.models import InsuranceQuote

logger = logging.getLogger(__name__)

VALID_DEDUCTIBLES: frozenset[float] = frozenset(
    [250, 500, 1000, 2500, 5000, 10000]
)
VALID_CONFIDENCE: frozenset[str] = frozenset(["high", "medium", "low"])


def validate_quote(quote: InsuranceQuote) -> tuple[InsuranceQuote, list[str]]:
    """Validate an extracted quote and return warnings. Never rejects a quote."""
    warnings: list[str] = []

    # 1. Carrier name — only "hard error" (but we still just warn)
    if not quote.carrier_name or not quote.carrier_name.strip():
        warnings.append("Missing carrier name")

    # 2. Annual premium range
    if quote.annual_premium <= 0:
        warnings.append(f"Annual premium is non-positive: ${quote.annual_premium:,.2f}")
    elif quote.annual_premium >= 50_000:
        warnings.append(f"Annual premium seems too high: ${quote.annual_premium:,.2f}")

    # 3. Non-standard deductible
    if quote.deductible not in VALID_DEDUCTIBLES:
        warnings.append(f"Non-standard deductible: ${quote.deductible:,.0f}")

    # 4. Coverage limits — each value must be positive
    for key, value in quote.coverage_limits.items():
        if isinstance(value, (int, float)) and value <= 0:
            warnings.append(f"Coverage limit '{key}' is non-positive: {value}")

    # 5. Effective date format
    if quote.effective_date is not None:
        try:
            date.fromisoformat(quote.effective_date)
        except ValueError:
            warnings.append(f"Invalid effective date format: '{quote.effective_date}'")

    # 6. Confidence — default to "low" if invalid
    if quote.confidence not in VALID_CONFIDENCE:
        warnings.append(
            f"Invalid confidence '{quote.confidence}', defaulted to 'low'"
        )
        quote = quote.model_copy(update={"confidence": "low"})

    if warnings:
        logger.warning("Quote '%s' has %d validation warning(s): %s",
                        quote.carrier_name, len(warnings), "; ".join(warnings))
    else:
        logger.info("Quote '%s' passed validation with no warnings", quote.carrier_name)

    return quote, warnings
