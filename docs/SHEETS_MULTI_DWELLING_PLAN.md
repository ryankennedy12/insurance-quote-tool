# Phase 4: Sheets Client Multi-Dwelling Implementation Plan

## Current Fixed 25-Row Layout

```
Row  | Label               | Type
-----|---------------------|-----------------
  1  | (logo merge A1:A2)  | TITLE (maroon)
  2  | (date in B2)        | DATE (italic)
  3  | "Premium Breakout"  | HEADER (maroon)
  4  | "Auto Premium"      | PREMIUM (currency)
  5  | "Home Premium"      | PREMIUM (currency)
  6  | "Umbrella Premium"  | PREMIUM (currency)
  7  | "Total"             | TOTAL (bold, currency)
  8  | ""                  | BLANK separator
  9  | "Home Coverage"     | HEADER (maroon)
 10  | "Dwelling"          | DATA (currency)
 11  | "Other Structures"  | DATA (currency)
 12  | "Liability"         | DATA (currency)
 13  | "Personal Property" | DATA (currency)
 14  | "Loss of Use"       | DATA (currency)
 15  | "Deductible"        | DATA (currency)
 16  | ""                  | BLANK separator
 17  | "Auto Coverage"     | HEADER (maroon)
 18  | "Limits"            | DATA (text)
 19  | "UM/UIM"            | DATA (text)
 20  | "Comprehensive"     | DATA (currency)
 21  | "Collision"         | DATA (currency)
 22  | ""                  | BLANK separator
 23  | "Umbrella Coverage" | HEADER (maroon)
 24  | "Limits"            | DATA (text)
 25  | "Deductible"        | DATA (currency)
```

**Column layout:** `A` (labels) | `B` (Current or first carrier) | `C`-`H` (carriers, up to 6)

---

## Proposed Multi-Dwelling Layout (34 rows)

When `_has_multi_dwelling(session)` is True:

```
Row  | Label                    | Type
-----|--------------------------|-------------------
  1  | (logo merge A1:A2)       | TITLE (maroon)
  2  | (date in B2)             | DATE (italic)
  3  | "Premium Breakout"       | HEADER (maroon)
  4  | "Auto Premium"           | PREMIUM (currency)
  5  | "Home 1 Premium"         | PREMIUM (currency)  *CHANGED*
  6  | "Home 2 Premium"         | PREMIUM (currency)  *NEW*
  7  | "Umbrella Premium"       | PREMIUM (currency)
  8  | "Total"                  | TOTAL (bold, currency)
  9  | ""                       | BLANK separator
 10  | "Home Coverage"          | HEADER (maroon)
 11  | "Dwelling 1"             | SUB-HEADER (lighter maroon) *NEW*
 12  | "Dwelling"               | DATA (currency)
 13  | "Other Structures"       | DATA (currency)
 14  | "Liability"              | DATA (currency)
 15  | "Personal Property"      | DATA (currency)
 16  | "Loss of Use"            | DATA (currency)
 17  | "Deductible"             | DATA (currency)
 18  | "Dwelling 2"             | SUB-HEADER (lighter maroon) *NEW*
 19  | "Dwelling"               | DATA (currency)
 20  | "Other Structures"       | DATA (currency)
 21  | "Liability"              | DATA (currency)
 22  | "Personal Property"      | DATA (currency)
 23  | "Loss of Use"            | DATA (currency)
 24  | "Deductible"             | DATA (currency)
 25  | ""                       | BLANK separator
 26  | "Auto Coverage"          | HEADER (maroon)
 27  | "Limits"                 | DATA (text)
 28  | "UM/UIM"                 | DATA (text)
 29  | "Comprehensive"          | DATA (currency)
 30  | "Collision"              | DATA (currency)
 31  | ""                       | BLANK separator
 32  | "Umbrella Coverage"      | HEADER (maroon)
 33  | "Limits"                 | DATA (text)
 34  | "Deductible"             | DATA (currency)
```

Single-dwelling: unchanged at 25 rows.
Multi-dwelling: 34 rows (+1 premium row, +1 Dw1 sub-header, +6 Dw2 data rows, +1 Dw2 sub-header = +9).

---

## Hardcoded Constants That Need Refactoring

These are currently module-level constants. In multi-dwelling mode they are all wrong:

### 1. `ROW_LABELS` (lines 59-85)
- Fixed 25-element list mapping 1-indexed row positions to display labels
- **Problem:** Multi-dwelling shifts every row after "Home Premium"
- **Fix:** Replace with dynamic label generation inside `_build_full_grid`

### 2. `HEADER_ROWS = [1, 3, 9, 17, 23]` (line 87)
- 1-indexed row numbers that get maroon background formatting
- **Problem:** Rows 9/17/23 shift in multi-dwelling layout
- **Fix:** Track header rows dynamically as grid is built

### 3. `CURRENCY_ROWS = [4, 5, 6, 7, 10, 11, 12, 13, 14, 15]` (line 88)
- 1-indexed rows that receive currency number format
- **Problem:** All positions shift in multi-dwelling; also needs to include Dw2 rows
- **Fix:** Track currency rows dynamically as grid is built

### 4. Hardcoded `25` in `_create_worksheet` (line 592)
- `rows=25` when creating worksheet
- **Fix:** Accept dynamic total from grid builder

### 5. Hardcoded row ranges in `_apply_formatting` (lines 811-854)
- `even_data_rows = [4, 6, 10, 12, 14, 18, 20, 24]`
- `"B4:B7"`, `"B10:B15"`, `"B18:B21"`, `"B24:B25"` (current policy column)
- `"A3:{last_col}25"` (border range)
- `"B4:{last_col}25"` (data alignment)
- `"A4:A25"` (label alignment)
- **Fix:** All derived from dynamic config dict

---

## Implementation Steps

### Step 1: Add `_has_multi_dwelling()` helper (module-level)

```python
def _has_multi_dwelling(session: ComparisonSession) -> bool:
    """Detect if session has multi-dwelling data."""
    cp = session.current_policy
    if cp and cp.home_2_premium:
        return True
    return any(c.home_2 is not None for c in session.carriers)
```

### Step 2: Define `GridConfig` dataclass

Replace hardcoded constants with a config object returned alongside the grid.

```python
from dataclasses import dataclass, field

@dataclass
class GridConfig:
    """Dynamic layout config computed alongside grid rows."""
    total_rows: int                        # Total grid rows (25 or 34)
    header_rows: list[int] = field(default_factory=list)     # 1-indexed, maroon bg
    sub_header_rows: list[int] = field(default_factory=list) # 1-indexed, lighter maroon bg (new)
    currency_rows: list[int] = field(default_factory=list)   # 1-indexed, currency format
    total_row: int = 0                     # 1-indexed, bold formatting
    even_data_rows: list[int] = field(default_factory=list)  # 1-indexed, gray shading
    current_col_ranges: list[str] = field(default_factory=list)  # "B4:B8", etc.
    border_range: str = ""                 # "A3:{last_col}34"
    data_align_range: str = ""             # "B4:{last_col}34"
    label_align_range: str = ""            # "A4:A34"
```

### Step 3: Refactor `_build_full_grid` to return `(grid, config)`

**Signature change:**
```python
def _build_full_grid(
    self, session: ComparisonSession, num_data_cols: int
) -> tuple[list[list[Any]], GridConfig]:
```

**Implementation approach:**
- Build rows sequentially using `grid.append()` (already the pattern)
- Track the current 1-indexed row number as you go
- As each row is appended, record its position in the appropriate config list
- Stop using `ROW_LABELS[idx]` — instead, inline the label string directly

**Pseudo-code for the premium block:**
```python
config = GridConfig(total_rows=0)
row_num = 1  # 1-indexed, increments with each grid.append()

# ... rows 1-3 (title, date, header) ...
config.header_rows.extend([1, 3])
row_num = 3

# Auto Premium
row_num += 1
grid.append(["Auto Premium"] + pad_row(auto_premium_data))
config.currency_rows.append(row_num)

# Home Premium(s)
if is_multi_dw:
    row_num += 1
    grid.append(["Home 1 Premium"] + pad_row(home1_premium_data))
    config.currency_rows.append(row_num)
    row_num += 1
    grid.append(["Home 2 Premium"] + pad_row(home2_premium_data))
    config.currency_rows.append(row_num)
else:
    row_num += 1
    grid.append(["Home Premium"] + pad_row(home_premium_data))
    config.currency_rows.append(row_num)

# ... continue for umbrella, total, sections ...
```

**For the home section (multi-dwelling):**
```python
# Home Coverage section header
row_num += 1
grid.append(section_header("Home Coverage"))
config.header_rows.append(row_num)

if is_multi_dw:
    # Dwelling 1 sub-header
    row_num += 1
    grid.append(["Dwelling 1"] + [""] * num_data_cols)
    config.sub_header_rows.append(row_num)

    # 6 Dwelling 1 data rows
    for label, current_getter, carrier_getter in home_1_rows:
        row_num += 1
        grid.append([label] + pad_row(build_row(current_getter, carrier_getter)))
        config.currency_rows.append(row_num)

    # Dwelling 2 sub-header
    row_num += 1
    grid.append(["Dwelling 2"] + [""] * num_data_cols)
    config.sub_header_rows.append(row_num)

    # 6 Dwelling 2 data rows
    for label, current_getter, carrier_getter in home_2_rows:
        row_num += 1
        grid.append([label] + pad_row(build_row(current_getter, carrier_getter)))
        config.currency_rows.append(row_num)
else:
    # 6 data rows (unchanged)
    ...
```

**Even data rows:** Track odd/even within each section independently. The simplest approach: after building the grid, compute even_data_rows as every other data row within each section's data range.

**Current policy column ranges:** Build `current_col_ranges` by recording the start and end row of each contiguous data block (premium rows 4-8, home rows, auto rows, umbrella rows).

**At the end:**
```python
config.total_rows = row_num
config.border_range = f"A3:{last_col}{row_num}"
config.data_align_range = f"B4:{last_col}{row_num}"
config.label_align_range = f"A4:A{row_num}"
return grid, config
```

### Step 4: Add `_build_home_2_section()` method

Mirrors `_build_home_section()` but reads from `cb.home_2` and `cp.home_2_*`:

```python
def _build_home_2_section(self, session: ComparisonSession) -> list[list[Any]]:
    """Build Dwelling 2 home coverage rows."""
    return [
        self._build_coverage_row(
            session,
            lambda cp: cp.home_2_dwelling,
            lambda cb: cb.home_2.coverage_limits.dwelling if cb.home_2 else None
        ),
        self._build_coverage_row(
            session,
            lambda cp: cp.home_2_other_structures,
            lambda cb: cb.home_2.coverage_limits.other_structures if cb.home_2 else None
        ),
        self._build_coverage_row(
            session,
            lambda cp: cp.home_2_liability,
            lambda cb: cb.home_2.coverage_limits.personal_liability if cb.home_2 else None
        ),
        self._build_coverage_row(
            session,
            lambda cp: cp.home_2_personal_property,
            lambda cb: cb.home_2.coverage_limits.personal_property if cb.home_2 else None
        ),
        self._build_coverage_row(
            session,
            lambda cp: cp.home_2_loss_of_use,
            lambda cb: cb.home_2.coverage_limits.loss_of_use if cb.home_2 else None
        ),
        self._build_coverage_row(
            session,
            lambda cp: cp.home_2_deductible,
            lambda cb: cb.home_2.deductible if cb.home_2 else None
        ),
    ]
```

### Step 5: Add `_build_home_2_premium_row()` or parameterize existing

Option A: Add an explicit method:
```python
def _build_home_2_premium_row(self, session):
    return self._build_premium_row(
        session,
        lambda cp: cp.home_2_premium,
        lambda cb: cb.home_2.annual_premium if cb.home_2 else None
    )
```

Option B: Inline the lambda in `_build_full_grid` (simpler, matches existing pattern for home/auto/umbrella premium rows).

**Recommended:** Option B (inline lambda, same as existing pattern).

### Step 6: Update `_create_worksheet` to accept dynamic row count

```python
def _create_worksheet(self, client_name, date, num_data_cols, total_rows=25):
    # ...
    new_ws = self.spreadsheet.add_worksheet(
        title=worksheet_name,
        rows=total_rows,  # was hardcoded 25
        cols=1 + num_data_cols,
    )
```

### Step 7: Refactor `_apply_formatting` to use `GridConfig`

**Signature change:**
```python
def _apply_formatting(
    self,
    worksheet: gspread.Worksheet,
    num_data_cols: int,
    config: GridConfig,
    *,
    has_current_policy: bool = True,
) -> None:
```

**Replace all hardcoded references:**

| Old hardcoded                           | New from `config`                                    |
|----------------------------------------|------------------------------------------------------|
| `HEADER_ROWS` → `[1, 3, 9, 17, 23]`  | `config.header_rows`                                 |
| `CURRENCY_ROWS` → `[4,5,6,7,10-15]`   | `config.currency_rows`                               |
| `even_data_rows = [4,6,10,12,14,18,20,24]` | `config.even_data_rows`                         |
| `"B4:B7"`, `"B10:B15"` etc.           | `config.current_col_ranges`                          |
| `f"A3:{last_col}25"` (borders)        | `config.border_range`                                |
| `f"B4:{last_col}25"` (data align)     | `config.data_align_range`                            |
| `f"A4:A25"` (label align)             | `config.label_align_range`                           |
| Row 7 bold total                       | `config.total_row`                                   |

**New: Sub-header formatting** for "Dwelling 1"/"Dwelling 2" rows:
```python
# Lighter maroon for sub-headers
SUB_HEADER_BG = {"red": 0.698, "green": 0.235, "blue": 0.282}  # primary_light equivalent
for row in config.sub_header_rows:
    formats.append({
        "range": f"A{row}:{last_col}{row}",
        "format": {
            "backgroundColor": SUB_HEADER_BG,
            "textFormat": {"foregroundColor": WHITE_TEXT, "bold": True},
        },
    })
```

### Step 8: Update `create_comparison` to thread config through

```python
def create_comparison(self, session):
    num_data_cols = self._get_num_data_columns(session)

    # Build grid and config together
    grid, config = self._build_full_grid(session, num_data_cols)

    # Create worksheet with dynamic row count
    new_ws = self._create_worksheet(
        session.client_name, session.date, num_data_cols,
        total_rows=config.total_rows
    )

    self._write_to_worksheet(new_ws, grid)

    self._apply_formatting(
        new_ws, num_data_cols, config,
        has_current_policy=session.current_policy is not None,
    )
    # ... rest unchanged
```

### Step 9: Deprecate module-level constants

After refactoring, `ROW_LABELS`, `HEADER_ROWS`, and `CURRENCY_ROWS` are no longer used. Remove them. Keep `LABEL_COL_WIDTH`, `DATA_COL_WIDTH`, `MAROON_BG`, `WHITE_TEXT`, `LIGHT_GRAY_BG`, `CURRENT_COL_BG`, `CURRENT_HEADER_BG` as they are still referenced.

---

## Files Changed

| File | Changes |
|------|---------|
| `app/sheets/sheets_client.py` | All changes below |

## Methods Changed

| Method | Change |
|--------|--------|
| `_build_full_grid` | Return `(grid, config)` instead of `grid`. Build rows dynamically with inline labels. Add Dw2 premium + home rows when multi-dwelling. |
| `_create_worksheet` | Accept `total_rows` parameter (default 25). |
| `_apply_formatting` | Accept `GridConfig` parameter. Replace all hardcoded row references with config values. Add sub-header formatting. |
| `create_comparison` | Thread `GridConfig` through from `_build_full_grid` to `_create_worksheet` and `_apply_formatting`. |

## Methods Added

| Method | Purpose |
|--------|---------|
| `_has_multi_dwelling` | Module-level helper, same as PDF gen. |
| `_build_home_2_section` | Build 6 Dwelling 2 coverage rows (mirrors `_build_home_section`). |

## Constants Removed

| Constant | Reason |
|----------|--------|
| `ROW_LABELS` | Replaced by inline labels in `_build_full_grid` |
| `HEADER_ROWS` | Replaced by `GridConfig.header_rows` |
| `CURRENCY_ROWS` | Replaced by `GridConfig.currency_rows` |

## Constants Added

| Constant | Value | Purpose |
|----------|-------|---------|
| `SUB_HEADER_BG` | `{"red": 0.698, "green": 0.235, "blue": 0.282}` | Lighter maroon for Dwelling sub-headers |

## Backward Compatibility

- Single-dwelling sessions: `_has_multi_dwelling()` returns `False`, grid is 25 rows, all existing formatting applies unchanged.
- `GridConfig` for single-dwelling will contain the same values as the old hardcoded constants.
- No signature changes on public API (`create_comparison`).

## Testing

1. `pytest tests/ -v` — all existing tests must pass unchanged.
2. If Sheets credentials are available, manual test:
   - Single-dwelling session → verify 25 rows, same formatting as before.
   - Multi-dwelling session → verify 34 rows, "Dwelling 1"/"Dwelling 2" sub-headers, "Home 1 Premium"/"Home 2 Premium" rows, correct currency formatting, correct current policy column ranges.
