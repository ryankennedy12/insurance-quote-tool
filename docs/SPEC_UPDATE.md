# Spec Update — Multi-Policy Layout & Current Policy Comparison

> **This document supersedes conflicting sections in PROJECT_SPEC.md and STARTER_FILES.md.**
> Place in `docs/` and reference from CLAUDE.md. When this file conflicts with PROJECT_SPEC.md, this file wins.

---

## What Changed and Why

The original spec assumed one policy type per comparison (e.g., just HO3). The actual agency workflow compares **bundled quotes** across carriers — a single comparison sheet may include Home + Auto + Umbrella for each carrier, with a Total row summing all three. Additionally, the agent needs a **Current Policy** column showing what the customer has today, so the customer can see how each carrier's quote compares to their existing coverage.

---

## Updated Data Model

### Keep: `InsuranceQuote` (one field type change)
Each PDF still produces one `InsuranceQuote`. A Home quote PDF → one InsuranceQuote. An Auto quote PDF → another InsuranceQuote.

**One change needed in `app/extraction/models.py`:**
```python
# OLD:
coverage_limits: dict[str, float]
# NEW (supports "ALS", "Actual Loss Sustained", and other text values):
coverage_limits: dict[str, float | str]
```
This is the only change to InsuranceQuote. All other fields remain the same.

### New: `CarrierBundle`
Groups multiple policies from the same carrier into one column on the sheet.

```python
from pydantic import BaseModel, Field
from typing import Optional

class CarrierBundle(BaseModel):
    """All quotes from a single carrier for one customer comparison."""
    carrier_name: str = Field(description="Carrier name for column header")
    home: Optional[InsuranceQuote] = Field(None, description="Home/HO3/HO5 quote")
    auto: Optional[InsuranceQuote] = Field(None, description="Auto quote")
    umbrella: Optional[InsuranceQuote] = Field(None, description="Umbrella/excess liability quote")

    @property
    def total_premium(self) -> float:
        """Sum of all policy premiums for this carrier."""
        total = 0.0
        if self.home:
            total += self.home.annual_premium
        if self.auto:
            total += self.auto.annual_premium
        if self.umbrella:
            total += self.umbrella.annual_premium
        return total

    @property
    def policy_types_present(self) -> list[str]:
        """Which policy types have quotes."""
        types = []
        if self.home:
            types.append("home")
        if self.auto:
            types.append("auto")
        if self.umbrella:
            types.append("umbrella")
        return types
```

### New: `CurrentPolicy`
The customer's existing coverage. Can be populated via manual entry OR PDF extraction of a current declarations page.

```python
class CurrentPolicy(BaseModel):
    """Customer's current coverage for comparison baseline."""
    carrier_name: str = Field(description="Current carrier name")

    # Home
    home_premium: Optional[float] = Field(None, description="Current annual home premium")
    home_dwelling: Optional[float] = Field(None, description="Current dwelling coverage limit")
    home_other_structures: Optional[float] = Field(None, description="Current other structures limit")
    home_liability: Optional[float] = Field(None, description="Current liability limit")
    home_personal_property: Optional[float] = Field(None, description="Current personal property limit")
    home_loss_of_use: Optional[float] = Field(None, description="Current loss of use limit")
    home_deductible: Optional[float] = Field(None, description="Current home deductible")

    # Auto
    auto_premium: Optional[float] = Field(None, description="Current annual auto premium")
    auto_limits: Optional[str] = Field(None, description="Current auto limits e.g. '500/500/250' or '1M CSL'")
    auto_um_uim: Optional[str] = Field(None, description="Current UM/UIM limits")
    auto_comp_deductible: Optional[str] = Field(None, description="Current comprehensive deductible and terms")
    auto_collision_deductible: Optional[float] = Field(None, description="Current collision deductible")

    # Umbrella
    umbrella_premium: Optional[float] = Field(None, description="Current annual umbrella premium")
    umbrella_limits: Optional[str] = Field(None, description="Current umbrella limits e.g. '1M CSL'")
    umbrella_deductible: Optional[float] = Field(None, description="Current umbrella deductible")

    @property
    def total_premium(self) -> float:
        total = 0.0
        if self.home_premium:
            total += self.home_premium
        if self.auto_premium:
            total += self.auto_premium
        if self.umbrella_premium:
            total += self.umbrella_premium
        return total
```

### New: `ComparisonSession`
Top-level container for an entire comparison workflow.

```python
class ComparisonSession(BaseModel):
    """Complete comparison session with all data."""
    client_name: str
    date: str = Field(description="ISO date YYYY-MM-DD")
    current_policy: Optional[CurrentPolicy] = None
    carriers: list[CarrierBundle] = Field(default_factory=list, description="2-6 carrier bundles")
    sections_included: list[str] = Field(
        default_factory=list,
        description="Which sections are active: 'home', 'auto', 'umbrella'"
    )
```

---

## Updated Google Sheets Layout

### Fixed row structure (matches the actual agency template)

The template has a fixed row layout. Sections that aren't needed are left blank or hidden, NOT deleted — the row numbers stay consistent.

```
Column A: Row labels (fixed)
Column B: Current Policy (customer's existing coverage)
Columns C-H: Carrier quotes (2-6 carriers, max 6)

ROW   LABEL                    SECTION
---   -----                    -------
1     [Header row with logo]   Header
2     [Blank / carrier names]  Header
3     [Blank]                  Header
4     Auto                     Premium Summary
5     Home                     Premium Summary
6     Umbrella                 Premium Summary
7     Total                    Premium Summary (bold, summed)
8     [Blank separator]
9     [Home section header]    Home Details
10    Dwelling                 Home Details
11    Other Structures         Home Details
12    Liability                Home Details
13    Personal Property        Home Details
14    Loss of Use              Home Details
15    Deductible               Home Details
16    [Blank separator]
17    [Auto section header]    Auto Details
18    Limits                   Auto Details
19    UM/UIM                   Auto Details
20    Deductibles (Comp)       Auto Details
21    Deductibles (Collision)  Auto Details
22    [Blank separator]
23    [Umbrella header]        Umbrella Details
24    Limits                   Umbrella Details
25    Deductible               Umbrella Details
```

### Column mapping
```
Column A: Row labels (always present, from template)
Column B: Current Policy
Column C: Carrier 1
Column D: Carrier 2
Column E: Carrier 3
Column F: Carrier 4
Column G: Carrier 5
Column H: Carrier 6
```

### Writing strategy
- Duplicate the "Template" worksheet (preserves all formatting)
- Write Current Policy data to Column B
- Write each CarrierBundle to Columns C-H
- Sections not included in the comparison are left blank (template formatting preserved)
- The data write starts at B4 (first premium row) as a single batch update

---

## Updated Branding

| Element | Old Value | New Value |
|---|---|---|
| Primary color | Navy `#2c5aa0` | Maroon `#871c30` |
| Header style | Navy background, white text | Maroon background, white text |
| Agency name | Configurable | "Scioto Insurance Group" |

> **Confirmed:** Maroon `#871c30` sampled from the Scioto template screenshot.

---

## Updated UI Workflow

### Upload Stage (replaces simple multi-file upload)

The agent needs to:
1. Enter client name
2. **Optionally** enter or upload current policy info
3. **Select which sections are included** (Home, Auto, Umbrella — checkboxes)
4. **For each carrier**, upload the relevant PDFs grouped by carrier

Suggested UI structure:
```
Client Name: [___________]

Current Policy:
  ○ Enter manually  ○ Upload dec page PDF  ○ Skip
  [Manual entry form OR file uploader based on selection]

Sections to compare:
  ☑ Home  ☑ Auto  ☐ Umbrella

Carrier 1: [Carrier Name: ___________]
  Home PDF: [upload]  Auto PDF: [upload]  Umbrella PDF: [upload]

Carrier 2: [Carrier Name: ___________]
  Home PDF: [upload]  Auto PDF: [upload]

[+ Add Another Carrier]
```

### Review Stage
- Editable table grouped by section (Home, Auto, Umbrella)
- Current Policy shown as first data column
- Validation warnings per carrier per section

### Export Stage
- Google Sheets (matching template layout exactly)
- Branded PDF (matching template branding)

---

## Updated Extraction Pipeline

The extraction pipeline (`extract_quote_data`) doesn't change — it still takes one PDF and returns one `InsuranceQuote`. What changes is how the UI groups extracted quotes into `CarrierBundle` objects:

```
Agent uploads:
  Carrier "Western Reserve": home.pdf, auto.pdf, umbrella.pdf
  Carrier "Hanover": home.pdf, auto.pdf

For each PDF:
  extract_quote_data(pdf_bytes) → InsuranceQuote

UI groups results:
  CarrierBundle(carrier_name="Western Reserve", home=quote1, auto=quote2, umbrella=quote3)
  CarrierBundle(carrier_name="Hanover", home=quote4, auto=quote5)
```

---

## What This Means for the Build

### Already built (minor tweak needed):
- `app/extraction/models.py` — Change `coverage_limits: dict[str, float]` to `dict[str, float | str]` for ALS support. Then ADD CarrierBundle, CurrentPolicy, ComparisonSession.
- `app/extraction/pdf_parser.py` — unchanged
- `app/extraction/ai_extractor.py` — unchanged
- `app/extraction/validator.py` — update coverage_limits validation to handle str values
- `app/utils/config.py` — unchanged
- `app/utils/logging_config.py` — unchanged

### Needs to be built (new):
- `app/sheets/sheets_client.py` — write to match actual template layout
- `app/pdf_gen/templates/comparison.html` — update branding + multi-section layout
- `app/pdf_gen/generator.py` — handle CarrierBundle structure
- `app/ui/` — new upload flow with carrier grouping + current policy entry

### Needs updating in docs:
- `CLAUDE.md` — add reference to this file
- `docs/PROJECT_SPEC.md` — note that SPEC_UPDATE.md supersedes certain sections

---

## Resolved Design Decisions

1. **Exact maroon hex color:** `#871c30` (sampled from Scioto template screenshot)
2. **Current policy extraction:** Both options — manual entry AND dec page PDF upload with Gemini extraction
3. **Auto limits format:** Normalize into structured fields (parse "1M CSL" → structured data, "500/500/250" → split BI/PD fields)
4. **Unavailable products:** Write a dash `"-"` in the cell
5. **"ALS" in Loss of Use:** "Actual Loss Sustained" — coverage limit cells must support `str | float` (text OR dollar amounts). This means `coverage_limits: dict[str, float]` in InsuranceQuote needs to become `coverage_limits: dict[str, float | str]`