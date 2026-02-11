> ⚠️ **SDK WARNING:** The code samples in this file use the DEPRECATED `google-generativeai` SDK. 
> When implementing, use `google-genai` instead. See CLAUDE.md for correct import patterns.
> Model string: use `gemini-2.5-flash` NOT `gemini-2.5-flash-preview-05-20`.
```

**Option B:** Don't touch the docs, but add this to your first prompt to Claude Code: *"The code samples in docs/EXTRACTION_PROMPT.md use the deprecated google-generativeai SDK. Use the google-genai SDK as specified in CLAUDE.md instead."*

I'd go with Option A — it's a one-time fix that prevents the issue in every future session.

## Also: Your CLAUDE.md `@` References

Make sure your CLAUDE.md references match the actual file paths. They should be:
```
See @docs/PROJECT_SPEC.md for full specification.
See @docs/IMPLEMENTATION_PLAN.md for current build progress.

# Extraction Engine Reference — Prompts, Schema, Carrier Hints

> **This is the most important document in the project.** If the AI can't reliably read the PDFs, nothing else matters. Reference this file when building `app/extraction/ai_extractor.py`.

---

## System Prompt (Use Verbatim)

```
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
{carrier_hints}
```

---

## Carrier-Specific Hints Dictionary

Store this in `ai_extractor.py` as a constant. After the LLM identifies the carrier name, inject the matching hints into the system prompt's `{carrier_hints}` placeholder.

```python
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
"""
}


def get_carrier_hints(carrier_name: str) -> str:
    """Return carrier-specific hints based on detected carrier name."""
    carrier_lower = carrier_name.lower().strip()
    for key, hints in CARRIER_HINTS.items():
        if key in carrier_lower:
            return hints
    return CARRIER_HINTS["default"]
```

---

## Two-Phase Extraction Strategy

The extraction works in two phases within a single API call for efficiency, but can be split into two calls if accuracy is insufficient on a specific carrier.

### Single-Call Approach (Default)
Send the full system prompt with the `{carrier_hints}` placeholder filled with the `default` hints. The LLM identifies the carrier AND extracts data in one pass.

### Two-Call Approach (Fallback for Problem Carriers)
1. **Call 1 — Carrier identification only:** "What insurance carrier issued this document? Reply with only the carrier name."
2. Look up carrier-specific hints using `get_carrier_hints()`
3. **Call 2 — Full extraction:** Send document + system prompt with carrier-specific hints injected

```python
# Implement both and use a config flag or automatic fallback
def extract_quote_data(pdf_bytes: bytes, filename: str = "", two_phase: bool = False) -> InsuranceQuote:
    text, is_digital = extract_text_from_pdf(pdf_bytes)

    if two_phase:
        # Phase 1: Identify carrier
        carrier = identify_carrier(text if is_digital else pdf_bytes, is_digital)
        hints = get_carrier_hints(carrier)
    else:
        hints = CARRIER_HINTS["default"]

    # Phase 2 (or single phase): Full extraction
    system_prompt = SYSTEM_PROMPT.replace("{carrier_hints}", hints)
    quote = call_gemini(text if is_digital else pdf_bytes, system_prompt, is_digital)

    return quote
```

---

## Gemini API Call Implementation

```python
import google.generativeai as genai
from app.utils.config import GEMINI_API_KEY
from app.extraction.models import InsuranceQuote
import json
import json_repair
import logging

logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.5-flash-preview-05-20"

def call_gemini_text(text: str, system_prompt: str) -> InsuranceQuote:
    """Send extracted markdown text to Gemini for structured extraction."""
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=InsuranceQuote,
        ),
    )

    response = model.generate_content(
        f"Extract the insurance quote data from this document:\n\n{text}"
    )

    return _parse_response(response.text)


def call_gemini_multimodal(pdf_bytes: bytes, system_prompt: str) -> InsuranceQuote:
    """Send PDF pages as images to Gemini for extraction (scanned docs)."""
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=InsuranceQuote,
        ),
    )

    # Upload PDF as file for multimodal processing
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        uploaded_file = genai.upload_file(tmp_path, mime_type="application/pdf")
        response = model.generate_content([
            "Extract the insurance quote data from this PDF document.",
            uploaded_file,
        ])
    finally:
        os.unlink(tmp_path)

    return _parse_response(response.text)


def _parse_response(response_text: str) -> InsuranceQuote:
    """Parse Gemini response into InsuranceQuote, with json-repair fallback."""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        logger.warning("JSON parse failed, attempting repair...")
        repaired = json_repair.repair_json(response_text)
        data = json.loads(repaired)

    return InsuranceQuote.model_validate(data)
```

---

## Few-Shot Examples (Include in System Prompt)

Add 1–2 examples to the system prompt for better extraction. Place them after the rules section.

```
EXAMPLE INPUT (abbreviated):
"Erie Insurance Company
ErieSecure Home Policy - HO3
Effective Date: 03/15/2026
Coverage A - Dwelling: $325,000
Coverage B - Other Structures: $32,500
Coverage C - Personal Property: $162,500
Coverage D - Loss of Use: $65,000
Coverage E - Personal Liability: $100,000
Coverage F - Medical Payments: $5,000
Deductible: $1,000
Endorsements: Water Backup $10,000, ERIE Rate Lock, Identity Recovery
Total Estimated Annual Premium: $1,487.00"

EXAMPLE OUTPUT:
{
  "carrier_name": "Erie Insurance",
  "policy_type": "HO3",
  "effective_date": "2026-03-15",
  "annual_premium": 1487.00,
  "monthly_premium": null,
  "deductible": 1000.0,
  "wind_hail_deductible": null,
  "coverage_limits": {
    "dwelling": 325000,
    "other_structures": 32500,
    "personal_property": 162500,
    "loss_of_use": 65000,
    "personal_liability": 100000,
    "medical_payments": 5000
  },
  "endorsements": ["Water Backup $10,000", "ERIE Rate Lock", "Identity Recovery"],
  "exclusions": [],
  "discounts_applied": [],
  "confidence": "high",
  "notes": null
}
```

---

## GPT-4o-mini Backup Implementation

If Gemini is down or producing poor results on a specific carrier, fall back to GPT-4o-mini. The system prompt is identical — only the API call changes.

```python
from openai import OpenAI
from app.utils.config import OPENAI_API_KEY

def call_openai_backup(text: str, system_prompt: str) -> InsuranceQuote:
    """Backup extraction using GPT-4o-mini with constrained decoding."""
    client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.responses.create(
        model="gpt-4o-mini",
        instructions=system_prompt,
        input=f"Extract the insurance quote data from this document:\n\n{text}",
        text={
            "format": {
                "type": "json_schema",
                "name": "insurance_quote",
                "schema": InsuranceQuote.model_json_schema(),
                "strict": True,
            }
        },
        temperature=0,
    )

    return _parse_response(response.output_text)
```

> **Note:** The OpenAI backup only works for text-path extraction. For scanned PDFs that need multimodal, Gemini is the only option at this price point.

---

## Validation Integration

After extraction, always run validation:

```python
from app.extraction.validator import validate_quote

def extract_and_validate(pdf_bytes: bytes, filename: str) -> QuoteExtractionResult:
    """Full extraction pipeline: extract → validate → return result."""
    try:
        quote = extract_quote_data(pdf_bytes, filename)
        quote, warnings = validate_quote(quote)
        return QuoteExtractionResult(
            filename=filename,
            success=True,
            quote=quote,
            warnings=warnings,
        )
    except Exception as e:
        logger.error(f"Extraction failed for {filename}: {e}")
        return QuoteExtractionResult(
            filename=filename,
            success=False,
            error=str(e),
        )
```

---

## Troubleshooting Common Extraction Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| Premium is monthly instead of annual | Carrier shows monthly prominently | Add carrier hint: "Extract the ANNUAL premium, not monthly" |
| Coverage limits all zero | Scanned PDF, text extraction failed | Check `is_digital` flag — should fall back to multimodal |
| Wrong carrier name | Multi-carrier comparison doc | Add to prompt: "Extract only the FIRST carrier's quote" |
| JSON parse errors | LLM added markdown formatting | `json_repair` should handle this; if persistent, check `response_mime_type` is set |
| Endorsements missing | Listed in separate section of PDF | Add carrier hint pointing to section name |
| Confidence always "low" | System prompt too strict | Verify the confidence instruction is clear; add example of "high" confidence |
| Timeout on large PDFs | PDF has 20+ pages | Pre-filter: only send pages containing premium/coverage info |
