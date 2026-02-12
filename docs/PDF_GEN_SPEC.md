# PDF Generation Spec — Phase 4 (Steps 9-10)

> Place in `docs/`. Reference from CLAUDE.md.
> The existing code in the user's message is the FOUNDATION — preserve all branding, typography, responsive layout logic, header/footer patterns, and font registration. Modify, don't rewrite.

---

## What's Changing from the Existing Code

### 1. Remove green "best value" highlighting
- **OLD:** Lowest premium carrier gets green column background (`best_value_bg`, `best_value_border`) and ★ prefix
- **NEW:** All carrier columns use the same color scheme (alternating `row_alt`/`row_white`). No green. No ★ star marker. Remove `best_idx` logic entirely.

### 2. Remove insurance license from footer
- **OLD:** Footer shows `self.agency_license` + page number + disclaimer
- **NEW:** Footer shows page number + disclaimer ONLY. No license number anywhere.

### 3. Add Current Policy column
- **NEW:** Column between the label column (A) and first carrier column
- **Visual distinction:** Light blue/gray background (e.g., `(230, 240, 248)` — soft blue-gray)
- **Header:** "Current" or carrier name from `CurrentPolicy.carrier_name` with the blue-gray background instead of maroon
- **Data:** Pulls from `CurrentPolicy` fields (home_premium, home_dwelling, auto_limits, etc.)
- **Optional:** If `session.current_policy` is None, skip this column entirely (carriers start at column 2)

### 4. Restructure to multi-section layout (match Google Sheets)
- **OLD:** Flat layout — Coverage Limits → Deductibles → Premium (single table)
- **NEW:** Stacked sections matching SPEC_UPDATE.md:

```
PREMIUM SUMMARY
  Home Premium
  Auto Premium
  Umbrella Premium
  Total

HOME DETAILS (if "home" in sections_included)
  Dwelling (Cov A)
  Other Structures (B)
  Personal Property (C)
  Loss of Use (D)
  Personal Liability (E)
  Medical Payments (F)
  All-Peril Deductible
  Wind/Hail Deductible

AUTO DETAILS (if "auto" in sections_included)
  Limits
  UM/UIM
  Deductibles (Comp)
  Deductibles (Collision)

UMBRELLA DETAILS (if "umbrella" in sections_included)
  Limits
  Deductible
```

- Premium summary at TOP (not bottom like the old layout)
- Each section is a separate sub-table with its own section divider row
- Sections only render if present in `session.sections_included`

### 5. Input model change
- **OLD:** `generate_comparison_pdf(client_name, quotes: list[dict], ...)`
- **NEW:** `generate_comparison_pdf(session: ComparisonSession, output_path, logo_path, date_str)`
- Pull data from `session.current_policy` (CurrentPolicy), `session.carriers` (list[CarrierBundle])
- Each CarrierBundle has `.home`, `.auto`, `.umbrella` (Optional[InsuranceQuote])
- Coverage limits come from `quote.coverage_limits` dict (keys: "dwelling", "other_structures", etc.)

### 6. Notes section — two parts
- **Part A: Per-carrier notes** — AI-generated, pre-filled from `InsuranceQuote.notes` field. Displayed per carrier with carrier name as bold label.
- **Part B: General notes** — Freeform text block from `session` (new field: `agent_notes: Optional[str]`). Rendered as a separate "AGENT NOTES" section after per-carrier notes. If empty/None, section is hidden.
- Both are editable in the Streamlit review stage BEFORE PDF export.

### 7. Endorsements & discounts accuracy
- Data comes from AI extraction (`InsuranceQuote.endorsements`, `InsuranceQuote.discounts_applied`)
- These are editable in the Streamlit review stage before PDF generation
- The PDF generator just renders what it receives — accuracy is enforced upstream
- Keep the existing `add_endorsements_section` pattern but pull from CarrierBundle structure

---

## Updated Brand Constants

```python
BRAND = {
    "primary":       (135, 28, 48),    # #871c30 — sampled from Scioto template
    "primary_dark":  (95, 18, 25),
    "primary_light": (178, 60, 72),
    "cream":         (248, 240, 232),
    "white":         (255, 255, 255),
    "text_dark":     (40, 40, 40),
    "text_medium":   (100, 100, 100),
    "text_light":    (160, 160, 160),
    "row_alt":       (252, 248, 248),
    "row_white":     (255, 255, 255),
    "current_bg":    (230, 240, 248),   # Light blue-gray for Current Policy column
    "current_header":(180, 200, 220),   # Slightly darker blue-gray for Current header
    "border_light":  (220, 215, 215),
    "divider":       (200, 190, 190),
}
```

**Removed:** `best_value_bg`, `best_value_border` (no more green highlighting)
**Added:** `current_bg`, `current_header` (Current Policy column distinction)
**Updated:** `primary` from `(127, 27, 36)` to `(135, 28, 48)` — matches #871c30

---

## Column Layout (Updated)

```
| Label | Current | Carrier 1 | Carrier 2 | ... | Carrier N |
```

- Label column: fixed width from LAYOUT_CONFIG
- Current column: same width as carrier columns (only if current_policy exists)
- Carrier columns: fill remaining width equally
- Total columns: 1 (label) + 0-1 (current) + 2-6 (carriers) = 3-8 columns

### Updated LAYOUT_CONFIG

The layout config needs to account for the Current Policy column. When current_policy exists, there's one more data column:

```python
def _get_layout(num_carriers: int, has_current: bool) -> dict:
    """Return layout config. Total data columns = num_carriers + (1 if has_current)."""
    total_data_cols = num_carriers + (1 if has_current else 0)
    # Use total_data_cols to pick orientation threshold:
    # Portrait: up to 5 data columns (4 carriers + current, or 5 carriers no current)
    # Landscape: 6+ data columns
    ...
```

---

## Data Extraction Mapping

### Premium Summary rows
| Row | Current Policy field | CarrierBundle field |
|-----|---------------------|---------------------|
| Home Premium | `current_policy.home_premium` | `bundle.home.annual_premium` |
| Auto Premium | `current_policy.auto_premium` | `bundle.auto.annual_premium` |
| Umbrella Premium | `current_policy.umbrella_premium` | `bundle.umbrella.annual_premium` |
| Total | `current_policy.total_premium` | `bundle.total_premium` |

### Home Details rows
| Row | Current Policy field | CarrierBundle field |
|-----|---------------------|---------------------|
| Dwelling | `home_dwelling` | `bundle.home.coverage_limits.get("dwelling")` |
| Other Structures | `home_other_structures` | `bundle.home.coverage_limits.get("other_structures")` |
| Personal Property | `home_personal_property` | `bundle.home.coverage_limits.get("personal_property")` |
| Loss of Use | `home_loss_of_use` | `bundle.home.coverage_limits.get("loss_of_use")` |
| Personal Liability | `home_liability` | `bundle.home.coverage_limits.get("personal_liability")` |
| Medical Payments | (not on CurrentPolicy) | `bundle.home.coverage_limits.get("medical_payments")` |
| All-Peril Deductible | `home_deductible` | `bundle.home.deductible` |
| Wind/Hail Deductible | (not on CurrentPolicy) | `bundle.home.wind_hail_deductible` |

### Auto Details rows
| Row | Current Policy field | CarrierBundle field |
|-----|---------------------|---------------------|
| Limits | `auto_limits` (str) | `_get_auto_limits(bundle.auto)` |
| UM/UIM | `auto_um_uim` (str) | `bundle.auto.coverage_limits.get("um_uim")` |
| Comp Deductible | `auto_comp_deductible` (str) | `bundle.auto.coverage_limits.get("comprehensive")` |
| Collision Deductible | `auto_collision_deductible` | `bundle.auto.deductible` |

### Umbrella Details rows
| Row | Current Policy field | CarrierBundle field |
|-----|---------------------|---------------------|
| Limits | `umbrella_limits` (str) | `_get_umbrella_limits(bundle.umbrella)` |
| Deductible | `umbrella_deductible` | `bundle.umbrella.deductible` |

---

## Value Formatting (same as Sheets client)

- `None` → `"-"` (dash string)
- `float/int` → raw number formatted as currency string `"$1,234"` (PDF needs display strings unlike Sheets)
- `str` → pass through (for "ALS", "500/500/250", "1M CSL", "Included")

**Note:** Unlike the Sheets client which writes raw numbers, the PDF must write formatted display strings since there's no template formatting layer.

---

## Public API (Updated)

```python
def generate_comparison_pdf(
    session: ComparisonSession,
    output_path: str,
    logo_path: Optional[str] = None,
    date_str: Optional[str] = None,
    agent_notes: Optional[str] = None,
) -> str:
```

---

## File Structure

- `app/pdf_gen/generator.py` — main module (SciotoComparisonPDF class + generate_comparison_pdf function)
- `assets/logo_rgb.png` — Scioto logo (already exists or will be provided)
- No HTML templates needed — fpdf2 handles everything programmatically

---

## What to Preserve from Existing Code

- ✅ SciotoComparisonPDF class structure (FPDF subclass)
- ✅ `_register_fonts()` with DejaVu fallback
- ✅ `_draw_branded_header()` (page 1 full banner)
- ✅ `_draw_continuation_header()` (subsequent pages)
- ✅ `add_client_section()` (prepared for / date banner)
- ✅ `add_section_title()` (crimson accent bar)
- ✅ `_add_section_divider_row()` (dark mini-header)
- ✅ `_add_data_row()` — modify to handle Current column + remove best_idx
- ✅ `_ensure_space()` and `_space_remaining()`
- ✅ LAYOUT_CONFIG responsive scaling (portrait/landscape by carrier count)
- ✅ `_fmt_currency()` static method
- ✅ Font sizing, row heights, margin calculations

## What to Remove

- ❌ `best_idx` / `best_value_bg` / `best_value_border` / green highlighting / ★ star
- ❌ `self.agency_license` from footer
- ❌ Old `generate_comparison_pdf(client_name, quotes: list[dict])` signature

## What to Add

- ➕ Current Policy column with blue-gray styling
- ➕ Multi-section layout (Premium Summary → Home → Auto → Umbrella)
- ➕ `agent_notes` parameter and rendering section
- ➕ Updated brand primary color to `(135, 28, 48)`
- ➕ Data extraction from ComparisonSession/CarrierBundle/CurrentPolicy models
