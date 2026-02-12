# Plan: Rewrite sheets_client.py — Template-Free Programmatic Sheet Generation

## Context

`app/sheets/sheets_client.py` currently depends on a pre-existing "Template" worksheet in Google Sheets for row labels, section headers, and all formatting. This creates a brittle setup requirement. The rewrite eliminates this dependency: create a blank worksheet and build everything programmatically — labels, data, and formatting.

**Only file modified:** `app/sheets/sheets_client.py`
**Sole caller:** `app/ui/streamlit_app.py:1190` — `sheets_client.create_comparison(session)` — signature unchanged.

---

## Changes

### 1. Remove `TemplateNotFoundError` exception class (line 35-37)

No template = no template error. Only used internally — no external imports.

### 2. Add module-level formatting constants (above SheetsClient class)

Centralizes all magic values for single-line edits later:

- **`MAROON_BG`** — `{"red": 0.529, "green": 0.110, "blue": 0.188}` (RGB 135,28,48)
- **`WHITE_TEXT`** — `{"red": 1.0, "green": 1.0, "blue": 1.0}`
- **`LIGHT_GRAY_BG`** — `{"red": 0.973, "green": 0.973, "blue": 0.973}` (#f8f8f8)
- **`ROW_LABELS`** — 25-element list of column A labels (index 0 = row 1)
- **`HEADER_ROWS`** — `[1, 3, 9, 17, 23]` (maroon background rows)
- **`CURRENCY_ROWS`** — `[4, 5, 6, 7, 10, 11, 12, 13, 14, 15]` (premium + home coverage rows)
- **`LABEL_COL_WIDTH`** = 140, **`DATA_COL_WIDTH`** = 120

### 3. Replace `_duplicate_template()` with `_create_worksheet()`

Same unique-name logic (`Quote_{client}_{date}` with `_2`, `_3` suffixes), but calls `self.spreadsheet.add_worksheet(title=name, rows=25, cols=8)` instead of `template.duplicate()`.

### 4. Replace `_build_data_grid()` with `_build_full_grid()`

The old method built 22 rows of columns B-H (no labels, no headers). The new method builds all 25 rows including:

- **Row 1:** Title — `"Quote Comparison — {client_name}"`
- **Row 2:** Date string
- **Row 3:** Carrier names header — `["", "Current: {name}", "Carrier1", "Carrier2", ...]`
- **Rows 4-25:** `[ROW_LABEL] + existing_helper_row` — prepends column A label, then delegates data columns to the unchanged `_build_premium_row`, `_build_home_section`, etc.

Each row padded to `1 + num_data_cols` via inner `pad_row()` function.

### 5. Add `_get_num_data_columns()` helper

Returns `len(carriers) + (1 if current_policy else 0)`. Used by both grid builder (padding) and formatter (range calculation).

### 6. Modify `_write_to_worksheet()`

Single change: `worksheet.update(grid, 'B4')` → `worksheet.update(grid, 'A1')`

### 7. Add `_apply_formatting()` — the core new method

Uses `worksheet.batch_format()` (one API call) + `self.spreadsheet.batch_update()` (one API call for column widths + row 1 merge). Format rules:

| Rule | Range | Format |
|------|-------|--------|
| Maroon headers | Rows 1, 3, 9, 17, 23 (full width) | Maroon BG, white bold text, centered |
| Bold total | Row 7 (full width) | Bold |
| Currency | Rows 4-7, 10-15 (B through last col) | `"$"#,##0` |
| Alternating shading | Even data rows not in separators/headers | Light gray #f8f8f8 BG |
| Borders | A3 through last-col:25 | Thin solid all sides |
| Data alignment | B4 through last-col:25 | Center |
| Label alignment | A4:A25 | Left |
| Date row | Row 2 | Italic, left |
| Column widths | Col A=140px, B-last=120px | via `updateDimensionProperties` |
| Row 1 merge | A1 through last-col:1 | `mergeCells` MERGE_ALL |

`last_col_letter` computed as `chr(ord('A') + num_data_cols)`.

### 8. Modify `create_comparison()`

New flow: `_create_worksheet()` → `_build_full_grid()` → `_write_to_worksheet()` → `_apply_formatting()`. Remove `WorksheetNotFound`/`TemplateNotFoundError` catch block; keep `APIError` handling.

### 9. Keep all existing helper methods unchanged

`_format_cell_value`, `_get_auto_limits`, `_get_umbrella_limits`, `_build_premium_row`, `_build_total_row`, `_build_home_section`, `_build_auto_section`, `_build_umbrella_section`, `_build_coverage_row`, `_build_auto_limits_row`, `_build_umbrella_limits_row` — no changes.

---

## Verification

1. `python -c "from app.sheets.sheets_client import SheetsClient; print('Import OK')"` — confirms no syntax errors
2. `python -c "from app.ui.streamlit_app import main; print('Streamlit import OK')"` — confirms caller still works
3. `python -m pytest tests/ -v` — confirms no test regressions
4. Manual end-to-end: `streamlit run app/main.py` → Upload → Extract → Review → Approve → Export to Google Sheets → verify sheet has correct data + formatting
