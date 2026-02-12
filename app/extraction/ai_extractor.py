import json
import logging
import os
import tempfile

import json_repair
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.extraction.models import InsuranceQuote, QuoteExtractionResult
from app.extraction.pdf_parser import extract_text_from_pdf
from app.utils.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_NAME = "gemini-2.5-flash"

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """\
You are an expert insurance document analyst. Your job is to extract structured data from insurance quote documents with perfect accuracy.

RULES:
1. Extract ONLY information explicitly stated in the document. Never guess or infer values.
2. If a field is not present in the document, return null for that field.
3. For dollar amounts, extract the numeric value only (no $ signs, no commas). Example: "$1,234.56" → 1234.56
4. For dates, use ISO 8601 format: YYYY-MM-DD
5. For coverage limits, map to standardized field names (see mapping below).
6. If a value is ambiguous or you're unsure, set confidence to "medium" or "low" and explain in the notes field.
7. Extract ALL endorsements and exclusions listed, using the exact names from the document.
8. If the document contains multiple policy options or quote variations, extract only the FIRST/PRIMARY quote unless the document clearly labels one as "selected" or "recommended."

COVERAGE FIELD NAME MAPPING:
Use these exact keys in the coverage_limits dictionary:
- "dwelling" — Dwelling coverage (Coverage A)
- "other_structures" — Other Structures (Coverage B)
- "personal_property" — Personal Property (Coverage C)
- "loss_of_use" — Loss of Use / Additional Living Expense (Coverage D)
- "personal_liability" — Personal Liability (Coverage E / Section II)
- "medical_payments" — Medical Payments to Others (Coverage F)
- "bi_per_person" — Bodily Injury per person (auto)
- "bi_per_accident" — Bodily Injury per accident (auto)
- "pd_per_accident" — Property Damage per accident (auto)
- "um_uim" — Uninsured/Underinsured Motorist (auto)
- "comprehensive" — Comprehensive deductible (auto)
- "collision" — Collision deductible (auto)
- "building" — Building coverage (commercial/BOP)
- "bpp" — Business Personal Property (commercial/BOP)
- "general_liability" — General Liability (commercial)
- "business_income" — Business Income (commercial)

For any coverage type not in this list, create a descriptive snake_case key.

CARRIER-SPECIFIC HINTS:
{carrier_hints}"""

CARRIER_HINTS: dict[str, str] = {
    "erie": """
ERIE INSURANCE specifics:
- Erie labels dwelling coverage as "Coverage A - Dwelling"
- Erie often shows "ErieSecure Home" as the product name — the policy type is still HO3 or HO5
- Look for "Total Estimated Annual Premium" for the premium amount
- Erie may show both "Base Premium" and "Total Premium" — use Total Premium
- Erie's endorsement "ERIE Rate Lock" is common — include it
- Wind/hail deductible may be listed separately as "Wind/Hail Ded"
- Erie groups discounts under "Premium Credits" section
""",
    "state farm": """
STATE FARM specifics:
- State Farm uses "Dwelling - Coverage A" format
- Premium may appear as "Annual Premium" or "Estimated Annual Cost"
- State Farm quotes often include multiple coverage options in one document — extract only the highlighted/selected option, or the first if none is highlighted
- Look for "Policy Form" to determine HO3 vs HO5
- State Farm uses "Personal Articles Policy" for scheduled items — list as endorsement
""",
    "progressive": """
PROGRESSIVE specifics:
- Progressive labels coverages as "Coverage A (Dwelling)", "Coverage B (Other Structures)", etc.
- Premium is typically labeled "Annual Premium" or "Total Annual Premium"
- Progressive often shows monthly payment breakdowns prominently — ensure you extract the ANNUAL total, not monthly
- For auto quotes, Progressive uses "BI" for Bodily Injury and "PD" for Property Damage
- Progressive bundles are labeled "HomeQuote Explorer" — this is their HO3/HO5 product
""",
    "safeco": """
SAFECO specifics:
- Safeco (a Liberty Mutual company) labels dwelling as "Coverage A - Dwelling Protection"
- Look for "Total Annual Premium" — Safeco may also show "Policy Premium" which excludes fees
- Safeco uses "Safeco Insurance" or "Safeco" as carrier name — normalize to "Safeco"
- Endorsement "Safeco Remodel Coverage" is specific to Safeco — include it
- Safeco quotes may include a "Package Discount" — list under discounts_applied
""",
    "nationwide": """
NATIONWIDE specifics:
- Nationwide labels coverages with letters: "A - Dwelling", "B - Other Structures", etc.
- Premium is labeled "Total Estimated Annual Premium" or "Estimated Annual Premium"
- Nationwide uses "On Your Side" branding — the policy type is still HO3/HO5
- Look for "Brand New Belongings" endorsement (their replacement cost enhancement)
- Nationwide may show "Member Discount" — include in discounts_applied
""",
    "allstate": """
ALLSTATE specifics:
- Allstate uses "Dwelling Protection" instead of "Coverage A"
- Premium may be labeled "Annual Estimated Premium" or "Your Annual Premium"
- Allstate's "House & Home" is their HO3 product
- Look for "Claim-Free Bonus" and "Early Signing Discount" in discounts
- Allstate endorsements may be called "Additional Coverages" or "Optional Coverages"
- Allstate often shows a comparison of their own tiers (Bronze/Silver/Gold) — extract the one labeled as "selected" or "recommended"
""",
    "westfield": """
WESTFIELD specifics:
- Westfield is common in Ohio markets
- Westfield labels premium as "Annual Premium" under "Premium Summary"
- Coverage labels follow standard A/B/C/D/E/F convention
- Look for "Inflation Guard" endorsement — very common with Westfield
- Westfield uses "Westfield Insurance" as full name
""",
    "grange": """
GRANGE INSURANCE specifics:
- Grange is an Ohio-based carrier, common in Columbus market
- Grange labels coverages as "Section I" (property) and "Section II" (liability)
- Premium is under "Total Annual Premium"
- Grange uses "Grange Mutual" or "Grange Insurance" — normalize to "Grange Insurance"
- Look for "GrangeGold" or "GrangeClassic" to determine HO3 vs HO5
""",
    "default": """
No carrier-specific hints available for this carrier. Use standard extraction rules.
Pay special attention to:
- Which number is the total annual premium vs. a monthly or partial-year amount
- Whether the document shows multiple quote options (extract the primary/recommended one)
- Any carrier-specific endorsement names
""",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_carrier_hints(carrier_name: str) -> str:
    """Return carrier-specific hints based on detected carrier name."""
    carrier_lower = carrier_name.lower().strip()
    for key, hints in CARRIER_HINTS.items():
        if key in carrier_lower:
            return hints
    return CARRIER_HINTS["default"]


def _clean_schema_for_gemini(schema: dict) -> dict:
    """Remove unsupported properties from schema for Gemini structured output."""
    for key in ("additionalProperties", "examples", "title", "default"):
        schema.pop(key, None)
    for key, value in schema.items():
        if isinstance(value, dict):
            _clean_schema_for_gemini(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _clean_schema_for_gemini(item)
    for prop in schema.get("properties", {}).values():
        if isinstance(prop, dict):
            _clean_schema_for_gemini(prop)
    for defn in schema.get("$defs", {}).values():
        if isinstance(defn, dict):
            _clean_schema_for_gemini(defn)
    return schema


def _parse_response(response_text: str) -> InsuranceQuote:
    """Parse Gemini JSON response into InsuranceQuote, with json-repair fallback."""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        logger.warning("JSON parse failed, attempting json-repair...")
        repaired = json_repair.repair_json(response_text)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            snippet = response_text[:200]
            raise ValueError(
                f"JSON parse failed even after repair. Raw response: {snippet}"
            ) from exc

    return InsuranceQuote.model_validate(data)


# ---------------------------------------------------------------------------
# Gemini API calls
# ---------------------------------------------------------------------------


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _call_gemini_text(text: str, system_prompt: str) -> InsuranceQuote:
    """Send extracted markdown text to Gemini for structured extraction."""
    clean_schema = _clean_schema_for_gemini(InsuranceQuote.model_json_schema())
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=clean_schema,
        temperature=0,
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"Extract the insurance quote data from this document:\n\n{text}",
        config=config,
    )

    # SDK returns a dict when using dict schema; convert to Pydantic model
    if response.parsed is not None:
        if isinstance(response.parsed, dict):
            return InsuranceQuote.model_validate(response.parsed)
        return response.parsed
    return _parse_response(response.text)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _call_gemini_multimodal(pdf_bytes: bytes, system_prompt: str) -> InsuranceQuote:
    """Send raw PDF to Gemini for multimodal extraction (scanned docs)."""
    clean_schema = _clean_schema_for_gemini(InsuranceQuote.model_json_schema())
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=clean_schema,
        temperature=0,
    )

    tmp_fd = None
    tmp_path: str | None = None
    try:
        # Use mkstemp to get raw file descriptor (Windows-compatible)
        # mkstemp returns (fd, path) - we must close fd before Gemini reads file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.write(tmp_fd, pdf_bytes)
        os.close(tmp_fd)  # Close file descriptor immediately
        tmp_fd = None  # Mark as closed

        uploaded_file = client.files.upload(file=tmp_path)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                "Extract the insurance quote data from this PDF document.",
                types.Part(
                    file_data=types.FileData(
                        file_uri=uploaded_file.uri,
                        mime_type="application/pdf",
                    )
                ),
            ],
            config=config,
        )
    finally:
        # Clean up file descriptor if still open
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # SDK returns a dict when using dict schema; convert to Pydantic model
    if response.parsed is not None:
        if isinstance(response.parsed, dict):
            return InsuranceQuote.model_validate(response.parsed)
        return response.parsed
    return _parse_response(response.text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_quote_data(pdf_bytes: bytes, filename: str = "") -> InsuranceQuote:
    """Extract structured quote data from PDF bytes via Gemini.

    Uses text path for digital PDFs, multimodal path for scanned PDFs.
    Retries up to 3 times with exponential backoff on API errors.
    """
    text, is_digital = extract_text_from_pdf(pdf_bytes)
    system_prompt = SYSTEM_PROMPT.replace("{carrier_hints}", CARRIER_HINTS["default"])

    if is_digital and text:
        logger.info("Using text extraction path for %s", filename or "unknown")
        quote = _call_gemini_text(text, system_prompt)
        raw_source = "text"
    else:
        logger.warning("Using multimodal extraction path for %s", filename or "unknown")
        quote = _call_gemini_multimodal(pdf_bytes, system_prompt)
        raw_source = "multimodal"

    quote = quote.model_copy(update={"raw_source": raw_source})

    logger.info(
        "Extraction complete: carrier=%s, confidence=%s, path=%s, file=%s",
        quote.carrier_name, quote.confidence, raw_source, filename,
    )
    return quote


def extract_and_validate(pdf_bytes: bytes, filename: str) -> QuoteExtractionResult:
    """Full extraction pipeline: extract → validate → return result."""
    from app.extraction.validator import validate_quote

    try:
        quote = extract_quote_data(pdf_bytes, filename)
        quote, warnings = validate_quote(quote)
        return QuoteExtractionResult(
            filename=filename,
            success=True,
            quote=quote,
            warnings=warnings,
        )
    except Exception as exc:
        logger.error("Extraction failed for %s: %s", filename, exc)
        return QuoteExtractionResult(
            filename=filename,
            success=False,
            error=str(exc),
        )
