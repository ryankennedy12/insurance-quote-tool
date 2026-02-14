"""Google Sheets integration for insurance quote comparison output."""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound

from app.extraction.models import (
    CarrierBundle,
    ComparisonSession,
    CurrentPolicy,
    InsuranceQuote,
)
from app.utils.config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    LOGO_DRIVE_FILE_ID,
    SPREADSHEET_ID,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Custom Exceptions
# ============================================================================


class SheetsClientError(Exception):
    """Base exception for sheets client errors."""
    pass


class SpreadsheetNotFoundError(SheetsClientError):
    """Spreadsheet ID not found or not accessible."""
    pass


class PermissionDeniedError(SheetsClientError):
    """Service account lacks permission to access spreadsheet."""
    pass


class QuotaExceededError(SheetsClientError):
    """Google Sheets API quota exceeded."""
    pass


# ============================================================================
# Formatting Constants
# ============================================================================

MAROON_BG: dict = {"red": 0.529, "green": 0.110, "blue": 0.188}
WHITE_TEXT: dict = {"red": 1.0, "green": 1.0, "blue": 1.0}
LIGHT_GRAY_BG: dict = {"red": 0.973, "green": 0.973, "blue": 0.973}
CURRENT_COL_BG: dict = {"red": 1.0, "green": 0.973, "blue": 0.941}  # #FFF8F0
CURRENT_HEADER_BG: dict = {"red": 0.961, "green": 0.902, "blue": 0.827}  # #F5E6D3

SUB_HEADER_BG: dict = {"red": 0.698, "green": 0.235, "blue": 0.282}
LABEL_COL_WIDTH: int = 140
DATA_COL_WIDTH: int = 120


@dataclass
class GridConfig:
    """Dynamic layout config computed alongside grid rows."""
    total_rows: int = 0
    header_rows: list[int] = field(default_factory=list)
    sub_header_rows: list[int] = field(default_factory=list)
    currency_rows: list[int] = field(default_factory=list)
    total_row: int = 0
    even_data_rows: list[int] = field(default_factory=list)
    current_col_ranges: list[str] = field(default_factory=list)
    border_range: str = ""
    data_align_range: str = ""
    label_align_range: str = ""


def _has_multi_dwelling(session: ComparisonSession) -> bool:
    """Detect if session has multi-dwelling data."""
    cp = session.current_policy
    if cp and cp.home_2_premium:
        return True
    return any(c.home_2 is not None for c in session.carriers)


# ============================================================================
# Main Client Class
# ============================================================================


class SheetsClient:
    """Google Sheets integration for multi-policy comparison output.

    Transforms a ComparisonSession into a dynamic Google Sheets layout:
    25 rows for single-dwelling, 34 rows for multi-dwelling.
    """

    def __init__(self) -> None:
        """Authenticate and open spreadsheet.

        Raises:
            SpreadsheetNotFoundError: SPREADSHEET_ID not found
            PermissionDeniedError: Service account lacks permission
            QuotaExceededError: API quota exceeded
            SheetsClientError: Service account credentials not found
        """
        try:
            self.gc = gspread.service_account(filename=GOOGLE_SERVICE_ACCOUNT_FILE)
            logger.info("Authenticated with Google Sheets API")
        except FileNotFoundError as exc:
            raise SheetsClientError(
                f"Service account credentials not found at {GOOGLE_SERVICE_ACCOUNT_FILE}"
            ) from exc

        try:
            self.spreadsheet = self.gc.open_by_key(SPREADSHEET_ID)
            logger.info("Opened spreadsheet: %s", self.spreadsheet.title)
        except SpreadsheetNotFound as exc:
            raise SpreadsheetNotFoundError(
                f"Spreadsheet {SPREADSHEET_ID} not found. "
                "Check SPREADSHEET_ID in .env and service account permissions."
            ) from exc
        except APIError as exc:
            if exc.response.status_code == 403:
                raise PermissionDeniedError(
                    "Service account lacks permission to access spreadsheet. "
                    "Share the spreadsheet with the service account email."
                ) from exc
            elif exc.response.status_code == 429:
                raise QuotaExceededError(
                    "Google Sheets API quota exceeded. Try again later."
                ) from exc
            raise SheetsClientError(f"API error during spreadsheet access: {exc}") from exc

    def create_comparison(self, session: ComparisonSession) -> str:
        """Create comparison worksheet from session data.

        Args:
            session: Complete comparison session with client info, current policy,
                    and carrier bundles

        Returns:
            Worksheet URL (https://docs.google.com/spreadsheets/d/{id}/edit#gid={gid})

        Raises:
            QuotaExceededError: API quota exceeded
            SheetsClientError: Other API errors
        """
        logger.info(
            "Creating comparison for client=%s, date=%s, carriers=%d",
            session.client_name, session.date, len(session.carriers)
        )

        try:
            num_data_cols = self._get_num_data_columns(session)

            # 1. Build full grid and dynamic layout config
            grid, config = self._build_full_grid(session, num_data_cols)

            # 2. Create blank worksheet with dynamic row count
            new_ws = self._create_worksheet(
                session.client_name, session.date, num_data_cols,
                total_rows=config.total_rows,
            )

            # 3. Write to worksheet at A1
            self._write_to_worksheet(new_ws, grid)

            # 4. Apply formatting using dynamic config
            self._apply_formatting(
                new_ws, num_data_cols, config,
                has_current_policy=session.current_policy is not None,
            )

            # 5. Insert logo into merged A1:A2 (if configured)
            if LOGO_DRIVE_FILE_ID:
                logo_url = (
                    f"https://drive.google.com/uc?id={LOGO_DRIVE_FILE_ID}"
                )
                new_ws.update(
                    [[f'=IMAGE("{logo_url}",2)']],
                    "A1",
                    value_input_option="USER_ENTERED",
                )
                logger.info("Inserted logo formula into A1")

            # 6. Construct URL
            url = (
                f"https://docs.google.com/spreadsheets/d/"
                f"{SPREADSHEET_ID}/edit#gid={new_ws.id}"
            )

            logger.info("Comparison created: %s", url)
            return url

        except APIError as exc:
            if exc.response.status_code == 429:
                raise QuotaExceededError(
                    "Google Sheets API quota exceeded. Try again later."
                ) from exc
            raise SheetsClientError(f"API error during write: {exc}") from exc

    # ========================================================================
    # Value Formatting Methods
    # ========================================================================

    def _format_cell_value(self, value: Optional[float | str]) -> float | str:
        """Format cell value - returns raw numbers or strings.

        Google Sheets template formatting will handle currency display.

        Args:
            value: Raw value (float, int, str, or None)

        Returns:
            Raw number for numeric values, string for text/missing
        """
        if value is None:
            return "-"
        if isinstance(value, str):
            return value  # Text values like "ALS" pass through
        if isinstance(value, (int, float)):
            return value  # Raw number - template will format
        return str(value)

    def _get_auto_limits(self, quote: InsuranceQuote) -> str:
        """Format auto liability limits from coverage_limits.

        Args:
            quote: Auto insurance quote

        Returns:
            Formatted string like "500/500/250" or "1M CSL"
        """
        cl = quote.coverage_limits

        # Check for split limits (BI per person / BI per accident / PD)
        if all([cl.bi_per_person, cl.bi_per_accident, cl.pd_per_accident]):
            bi_p = int(cl.bi_per_person / 1000)
            bi_a = int(cl.bi_per_accident / 1000)
            pd_a = int(cl.pd_per_accident / 1000)
            return f"{bi_p}/{bi_a}/{pd_a}"

        # Check for CSL (Combined Single Limit)
        if cl.csl:
            if cl.csl >= 1_000_000:
                return f"{int(cl.csl / 1_000_000)}M CSL"
            else:
                return f"{int(cl.csl / 1000)}K CSL"

        # Fallback
        return "-"

    def _get_umbrella_limits(self, quote: InsuranceQuote) -> str | float:
        """Format umbrella limits from coverage_limits.

        Args:
            quote: Umbrella insurance quote

        Returns:
            Formatted string like "1M CSL" or raw number
        """
        limit_value = quote.coverage_limits.umbrella_limit

        if not limit_value:
            return "-"

        # Format in millions for readability
        if isinstance(limit_value, (int, float)):
            if limit_value >= 1_000_000:
                return f"{int(limit_value / 1_000_000)}M CSL"
            else:
                return limit_value  # Return raw number for template formatting

        return "-"

    # ========================================================================
    # Row Building Helpers
    # ========================================================================

    def _build_premium_row(
        self,
        session: ComparisonSession,
        current_getter: Callable[[CurrentPolicy], Optional[float]],
        carrier_getter: Callable[[CarrierBundle], Optional[float]]
    ) -> list[Any]:
        """Build a premium row (auto/home/umbrella).

        Args:
            session: Comparison session
            current_getter: Lambda to extract current policy value
            carrier_getter: Lambda to extract carrier bundle value

        Returns:
            Row with 7 cells (Column B + Columns C-H)
        """
        row = []

        # Column B: Current Policy
        if session.current_policy:
            value = current_getter(session.current_policy)
            row.append(self._format_cell_value(value))
        else:
            row.append("-")

        # Columns C-H: Carriers (up to 6)
        for carrier in session.carriers[:6]:
            value = carrier_getter(carrier)
            row.append(self._format_cell_value(value))

        # Pad remaining columns to reach 7 total
        while len(row) < 7:
            row.append("")

        return row

    def _build_total_row(self, session: ComparisonSession) -> list[Any]:
        """Build row 7 (Total premium - sum of auto/home/umbrella).

        Args:
            session: Comparison session

        Returns:
            Row with 7 cells containing total premiums
        """
        row = []

        # Column B: Current Policy total
        if session.current_policy:
            row.append(self._format_cell_value(session.current_policy.total_premium))
        else:
            row.append("-")

        # Columns C-H: Carrier totals
        for carrier in session.carriers[:6]:
            row.append(self._format_cell_value(carrier.total_premium))

        # Pad
        while len(row) < 7:
            row.append("")

        return row

    def _build_home_section(self, session: ComparisonSession) -> list[list[Any]]:
        """Build rows 10-15 (Home coverage details).

        Args:
            session: Comparison session

        Returns:
            6 rows for dwelling, other structures, liability, personal property,
            loss of use, and deductible
        """
        return [
            # Row 10: Dwelling
            self._build_coverage_row(
                session,
                lambda cp: cp.home_dwelling,
                lambda cb: cb.home.coverage_limits.dwelling if cb.home else None
            ),
            # Row 11: Other Structures
            self._build_coverage_row(
                session,
                lambda cp: cp.home_other_structures,
                lambda cb: cb.home.coverage_limits.other_structures if cb.home else None
            ),
            # Row 12: Liability
            self._build_coverage_row(
                session,
                lambda cp: cp.home_liability,
                lambda cb: cb.home.coverage_limits.personal_liability if cb.home else None
            ),
            # Row 13: Personal Property
            self._build_coverage_row(
                session,
                lambda cp: cp.home_personal_property,
                lambda cb: cb.home.coverage_limits.personal_property if cb.home else None
            ),
            # Row 14: Loss of Use
            self._build_coverage_row(
                session,
                lambda cp: cp.home_loss_of_use,
                lambda cb: cb.home.coverage_limits.loss_of_use if cb.home else None
            ),
            # Row 15: Deductible
            self._build_coverage_row(
                session,
                lambda cp: cp.home_deductible,
                lambda cb: cb.home.deductible if cb.home else None
            ),
        ]

    def _build_home_2_section(self, session: ComparisonSession) -> list[list[Any]]:
        """Build Dwelling 2 home coverage rows.

        Args:
            session: Comparison session

        Returns:
            6 rows for dwelling, other structures, liability, personal property,
            loss of use, and deductible (Dwelling 2)
        """
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

    def _build_auto_section(self, session: ComparisonSession) -> list[list[Any]]:
        """Build auto coverage detail rows.

        Args:
            session: Comparison session

        Returns:
            4 rows for limits, UM/UIM, comp deductible, collision deductible
        """
        return [
            # Row 18: Limits (special formatting)
            self._build_auto_limits_row(session),
            # Row 19: UM/UIM
            self._build_coverage_row(
                session,
                lambda cp: cp.auto_um_uim,
                lambda cb: cb.auto.coverage_limits.um_uim if cb.auto else None
            ),
            # Row 20: Comprehensive Deductible
            self._build_coverage_row(
                session,
                lambda cp: cp.auto_comp_deductible,
                lambda cb: cb.auto.coverage_limits.comprehensive if cb.auto else None
            ),
            # Row 21: Collision Deductible
            self._build_coverage_row(
                session,
                lambda cp: cp.auto_collision_deductible,
                lambda cb: cb.auto.deductible if cb.auto else None
            ),
        ]

    def _build_umbrella_section(self, session: ComparisonSession) -> list[list[Any]]:
        """Build rows 24-25 (Umbrella coverage details).

        Args:
            session: Comparison session

        Returns:
            2 rows for limits and deductible
        """
        return [
            # Row 24: Limits
            self._build_umbrella_limits_row(session),
            # Row 25: Deductible
            self._build_coverage_row(
                session,
                lambda cp: cp.umbrella_deductible,
                lambda cb: cb.umbrella.deductible if cb.umbrella else None
            ),
        ]

    def _build_coverage_row(
        self,
        session: ComparisonSession,
        current_getter: Callable[[CurrentPolicy], Any],
        carrier_getter: Callable[[CarrierBundle], Any]
    ) -> list[Any]:
        """Build a coverage row (handles float, str, or None).

        Args:
            session: Comparison session
            current_getter: Lambda to extract current policy value
            carrier_getter: Lambda to extract carrier bundle value

        Returns:
            Row with 7 cells
        """
        row = []

        # Column B: Current Policy
        if session.current_policy:
            value = current_getter(session.current_policy)
            row.append(self._format_cell_value(value))
        else:
            row.append("-")

        # Columns C-H: Carriers
        for carrier in session.carriers[:6]:
            value = carrier_getter(carrier)
            row.append(self._format_cell_value(value))

        # Pad
        while len(row) < 7:
            row.append("")

        return row

    def _build_auto_limits_row(self, session: ComparisonSession) -> list[Any]:
        """Build auto limits row (Row 18) - special formatting.

        Args:
            session: Comparison session

        Returns:
            Row with formatted auto limits like "500/500/250" or "1M CSL"
        """
        row = []

        # Column B: Current Policy
        if session.current_policy:
            row.append(session.current_policy.auto_limits or "-")
        else:
            row.append("-")

        # Columns C-H: Carriers
        for carrier in session.carriers[:6]:
            if carrier.auto:
                limits_str = self._get_auto_limits(carrier.auto)
                row.append(limits_str)
            else:
                row.append("-")

        # Pad
        while len(row) < 7:
            row.append("")

        return row

    def _build_umbrella_limits_row(self, session: ComparisonSession) -> list[Any]:
        """Build umbrella limits row (Row 24) - special formatting.

        Args:
            session: Comparison session

        Returns:
            Row with formatted umbrella limits like "1M CSL" or raw numbers
        """
        row = []

        # Column B: Current Policy
        if session.current_policy:
            row.append(session.current_policy.umbrella_limits or "-")
        else:
            row.append("-")

        # Columns C-H: Carriers
        for carrier in session.carriers[:6]:
            if carrier.umbrella:
                limits_value = self._get_umbrella_limits(carrier.umbrella)
                row.append(limits_value)
            else:
                row.append("-")

        # Pad
        while len(row) < 7:
            row.append("")

        return row

    # ========================================================================
    # Worksheet Operations
    # ========================================================================

    def _get_num_data_columns(self, session: ComparisonSession) -> int:
        """Return number of data columns (excluding label column A).

        Args:
            session: Comparison session

        Returns:
            Number of data columns
        """
        return len(session.carriers[:6]) + (1 if session.current_policy else 0)

    def _create_worksheet(
        self, client_name: str, date: str, num_data_cols: int,
        total_rows: int = 25,
    ) -> gspread.Worksheet:
        """Create blank worksheet with unique name.

        Args:
            client_name: Client name for worksheet title
            date: ISO date string (YYYY-MM-DD)
            num_data_cols: Number of data columns
            total_rows: Number of rows (25 single-dwelling, 34 multi-dwelling)

        Returns:
            New blank worksheet
        """
        base_name = f"Quote_{client_name}_{date}"

        # Check for existing worksheets with same name
        existing_names = [ws.title for ws in self.spreadsheet.worksheets()]

        # Find unique name
        worksheet_name = base_name
        counter = 2
        while worksheet_name in existing_names:
            worksheet_name = f"{base_name}_{counter}"
            counter += 1

        # Create blank worksheet
        new_ws = self.spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=total_rows,
            cols=1 + num_data_cols,
        )

        logger.info("Created worksheet: %s (%d rows)", worksheet_name, total_rows)
        return new_ws

    # ========================================================================
    # Main Grid Builder
    # ========================================================================

    def _build_full_grid(
        self, session: ComparisonSession, num_data_cols: int
    ) -> tuple[list[list[Any]], GridConfig]:
        """Build dynamic grid with labels, headers, and data.

        Returns 25 rows for single-dwelling, 34 rows for multi-dwelling.

        Args:
            session: Comparison session
            num_data_cols: Number of data columns

        Returns:
            Tuple of (grid rows, GridConfig with layout metadata)
        """
        total_cols = 1 + num_data_cols
        is_multi_dw = _has_multi_dwelling(session)
        config = GridConfig()
        data_blocks: list[tuple[int, int]] = []
        row_num = 0

        def pad_row(helper_row: list[Any]) -> list[Any]:
            """Trim helper row to num_data_cols, stripping current col if needed."""
            if not session.current_policy:
                data = helper_row[1:]  # Skip leading "-" (no current policy column)
            else:
                data = helper_row
            return (data + [""] * num_data_cols)[:num_data_cols]

        def label_row(label: str, helper_row: list[Any]) -> list[Any]:
            """Prepend row label to trimmed helper row."""
            return [label] + pad_row(helper_row)

        def empty_row() -> list[Any]:
            return [""] * total_cols

        def section_header(label: str) -> list[Any]:
            return [label] + [""] * num_data_cols

        grid: list[list[Any]] = []

        # Row 1: Title (A1:A2 reserved for logo)
        row_num += 1
        grid.append(
            ["", f"Quote Comparison \u2014 {session.client_name}"]
            + [""] * max(0, num_data_cols - 1)
        )
        config.header_rows.append(row_num)

        # Row 2: Date (B2, A2 is part of logo merge)
        row_num += 1
        grid.append(["", session.date] + [""] * max(0, num_data_cols - 1))

        # Row 3: Carrier names header
        row_num += 1
        carrier_header: list[Any] = ["Premium Breakout"]
        if session.current_policy:
            current_name = session.current_policy.carrier_name or "Current"
            carrier_header.append(f"Current: {current_name}")
        for carrier in session.carriers[:6]:
            carrier_header.append(carrier.carrier_name)
        carrier_header = (carrier_header + [""] * total_cols)[:total_cols]
        grid.append(carrier_header)
        config.header_rows.append(row_num)

        # === Premium Section ===
        premium_start = row_num + 1

        # Auto Premium
        row_num += 1
        grid.append(label_row("Auto Premium", self._build_premium_row(
            session,
            lambda cp: cp.auto_premium,
            lambda cb: cb.auto.annual_premium if cb.auto else None
        )))
        config.currency_rows.append(row_num)

        # Home Premium(s)
        if is_multi_dw:
            row_num += 1
            grid.append(label_row("Home 1 Premium", self._build_premium_row(
                session,
                lambda cp: cp.home_premium,
                lambda cb: cb.home.annual_premium if cb.home else None
            )))
            config.currency_rows.append(row_num)

            row_num += 1
            grid.append(label_row("Home 2 Premium", self._build_premium_row(
                session,
                lambda cp: cp.home_2_premium,
                lambda cb: cb.home_2.annual_premium if cb.home_2 else None
            )))
            config.currency_rows.append(row_num)
        else:
            row_num += 1
            grid.append(label_row("Home Premium", self._build_premium_row(
                session,
                lambda cp: cp.home_premium,
                lambda cb: cb.home.annual_premium if cb.home else None
            )))
            config.currency_rows.append(row_num)

        # Umbrella Premium
        row_num += 1
        grid.append(label_row("Umbrella Premium", self._build_premium_row(
            session,
            lambda cp: cp.umbrella_premium,
            lambda cb: cb.umbrella.annual_premium if cb.umbrella else None
        )))
        config.currency_rows.append(row_num)

        # Total
        row_num += 1
        grid.append(label_row("Total", self._build_total_row(session)))
        config.currency_rows.append(row_num)
        config.total_row = row_num
        data_blocks.append((premium_start, row_num))

        # Blank separator
        row_num += 1
        grid.append(empty_row())

        # === Home Coverage Section ===
        row_num += 1
        grid.append(section_header("Home Coverage"))
        config.header_rows.append(row_num)

        home_labels = [
            "Dwelling", "Other Structures", "Liability",
            "Personal Property", "Loss of Use", "Deductible",
        ]
        home_data = (
            self._build_home_section(session)
            if "home" in session.sections_included
            else None
        )

        if is_multi_dw:
            home_2_data = (
                self._build_home_2_section(session)
                if "home" in session.sections_included
                else None
            )

            # Dwelling 1 sub-header
            row_num += 1
            grid.append(section_header("Dwelling 1"))
            config.sub_header_rows.append(row_num)

            # Dwelling 1 data rows
            dw1_start = row_num + 1
            for i, label in enumerate(home_labels):
                row_num += 1
                if home_data:
                    grid.append(label_row(label, home_data[i]))
                else:
                    grid.append([label] + [""] * num_data_cols)
                config.currency_rows.append(row_num)
            data_blocks.append((dw1_start, row_num))

            # Dwelling 2 sub-header
            row_num += 1
            grid.append(section_header("Dwelling 2"))
            config.sub_header_rows.append(row_num)

            # Dwelling 2 data rows
            dw2_start = row_num + 1
            for i, label in enumerate(home_labels):
                row_num += 1
                if home_2_data:
                    grid.append(label_row(label, home_2_data[i]))
                else:
                    grid.append([label] + [""] * num_data_cols)
                config.currency_rows.append(row_num)
            data_blocks.append((dw2_start, row_num))
        else:
            # Single-dwelling: 6 data rows
            home_start = row_num + 1
            for i, label in enumerate(home_labels):
                row_num += 1
                if home_data:
                    grid.append(label_row(label, home_data[i]))
                else:
                    grid.append([label] + [""] * num_data_cols)
                config.currency_rows.append(row_num)
            data_blocks.append((home_start, row_num))

        # Blank separator
        row_num += 1
        grid.append(empty_row())

        # === Auto Coverage Section ===
        row_num += 1
        grid.append(section_header("Auto Coverage"))
        config.header_rows.append(row_num)

        auto_labels = ["Limits", "UM/UIM", "Comprehensive", "Collision"]
        auto_data = (
            self._build_auto_section(session)
            if "auto" in session.sections_included
            else None
        )
        auto_start = row_num + 1
        for i, label in enumerate(auto_labels):
            row_num += 1
            if auto_data:
                grid.append(label_row(label, auto_data[i]))
            else:
                grid.append([label] + [""] * num_data_cols)
        data_blocks.append((auto_start, row_num))

        # Blank separator
        row_num += 1
        grid.append(empty_row())

        # === Umbrella Coverage Section ===
        row_num += 1
        grid.append(section_header("Umbrella Coverage"))
        config.header_rows.append(row_num)

        umbrella_labels = ["Limits", "Deductible"]
        umbrella_data = (
            self._build_umbrella_section(session)
            if "umbrella" in session.sections_included
            else None
        )
        umbrella_start = row_num + 1
        for i, label in enumerate(umbrella_labels):
            row_num += 1
            if umbrella_data:
                grid.append(label_row(label, umbrella_data[i]))
            else:
                grid.append([label] + [""] * num_data_cols)
        data_blocks.append((umbrella_start, row_num))

        # Compute even_data_rows from data blocks
        for start, end in data_blocks:
            for i, row in enumerate(range(start, end + 1)):
                if i % 2 == 0:
                    config.even_data_rows.append(row)

        # Compute current_col_ranges from data blocks
        for start, end in data_blocks:
            config.current_col_ranges.append(f"B{start}:B{end}")

        # Finalize config
        last_col = chr(ord('A') + num_data_cols)
        config.total_rows = row_num
        config.border_range = f"A3:{last_col}{row_num}"
        config.data_align_range = f"B4:{last_col}{row_num}"
        config.label_align_range = f"A4:A{row_num}"

        logger.debug(
            "Built grid: %d rows x %d columns", len(grid), total_cols
        )
        return grid, config

    # ========================================================================
    # Write & Format
    # ========================================================================

    def _write_to_worksheet(
        self,
        worksheet: gspread.Worksheet,
        grid: list[list[Any]]
    ) -> None:
        """Write data grid to worksheet starting at A1.

        Args:
            worksheet: Target worksheet
            grid: 25-row grid of data
        """
        worksheet.update(grid, 'A1')
        logger.info("Wrote %d rows to worksheet %s", len(grid), worksheet.title)

    def _apply_formatting(
        self,
        worksheet: gspread.Worksheet,
        num_data_cols: int,
        config: GridConfig,
        *,
        has_current_policy: bool = True,
    ) -> None:
        """Apply all formatting to worksheet using dynamic GridConfig.

        Uses batch_format() for cell formatting and spreadsheet.batch_update()
        for column widths and cell merges.

        Args:
            worksheet: Target worksheet
            num_data_cols: Number of data columns
            config: Dynamic layout config from _build_full_grid
            has_current_policy: Whether column B is a current policy column
        """
        last_col = chr(ord('A') + num_data_cols)
        last_row = config.total_rows
        sheet_id = worksheet.id

        # Build format rules list
        formats: list[dict] = []

        # --- Maroon headers (dynamic from config) ---
        maroon_fmt = {
            "backgroundColor": MAROON_BG,
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": WHITE_TEXT,
                "bold": True,
            },
        }
        for row in config.header_rows:
            if row == 1:
                # Title row starts at B1 (A1:A2 reserved for logo)
                formats.append({
                    "range": f"B1:{last_col}1",
                    "format": maroon_fmt,
                })
            else:
                formats.append({
                    "range": f"A{row}:{last_col}{row}",
                    "format": maroon_fmt,
                })

        # --- Sub-headers (Dwelling 1 / Dwelling 2) — slightly lighter maroon ---
        sub_header_fmt = {
            "backgroundColor": SUB_HEADER_BG,
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": WHITE_TEXT,
                "bold": True,
            },
        }
        for row in config.sub_header_rows:
            formats.append({
                "range": f"A{row}:{last_col}{row}",
                "format": sub_header_fmt,
            })

        # --- Bold total row (dynamic from config) ---
        if config.total_row:
            formats.append({
                "range": f"A{config.total_row}:{last_col}{config.total_row}",
                "format": {"textFormat": {"bold": True}},
            })

        # --- Currency formatting (dynamic from config) on data columns only ---
        for row in config.currency_rows:
            formats.append({
                "range": f"B{row}:{last_col}{row}",
                "format": {
                    "numberFormat": {
                        "type": "CURRENCY",
                        "pattern": '"$"#,##0',
                    },
                },
            })

        # --- Alternating gray shading on even data rows (dynamic from config) ---
        for row in config.even_data_rows:
            formats.append({
                "range": f"A{row}:{last_col}{row}",
                "format": {"backgroundColor": LIGHT_GRAY_BG},
            })

        # --- Current Policy column: cream background on data rows only
        #     (skip section headers so maroon applies uniformly) ---
        if has_current_policy:
            for rng in config.current_col_ranges:
                formats.append({
                    "range": rng,
                    "format": {"backgroundColor": CURRENT_COL_BG},
                })

        # --- Thin borders (A3 through last row) ---
        thin_border = {
            "style": "SOLID",
            "color": {"red": 0.8, "green": 0.8, "blue": 0.8},
        }
        formats.append({
            "range": config.border_range,
            "format": {
                "borders": {
                    "top": thin_border,
                    "bottom": thin_border,
                    "left": thin_border,
                    "right": thin_border,
                },
            },
        })

        # --- Data alignment: center for data cols ---
        formats.append({
            "range": config.data_align_range,
            "format": {"horizontalAlignment": "CENTER"},
        })

        # --- Label alignment: left for column A ---
        formats.append({
            "range": config.label_align_range,
            "format": {"horizontalAlignment": "LEFT"},
        })

        # --- Date row: italic, left (B2 — A2 is part of logo merge) ---
        formats.append({
            "range": f"B2:{last_col}2",
            "format": {
                "textFormat": {"italic": True},
                "horizontalAlignment": "LEFT",
            },
        })

        # Apply all cell formatting in one call
        worksheet.batch_format(formats)
        logger.info("Applied %d format rules", len(formats))

        # --- Column widths + merges via raw batch_update ---
        requests: list[dict] = [
            # Column A width
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": LABEL_COL_WIDTH},
                    "fields": "pixelSize",
                },
            },
            # Data columns width (B through last)
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": 1 + num_data_cols,
                    },
                    "properties": {"pixelSize": DATA_COL_WIDTH},
                    "fields": "pixelSize",
                },
            },
            # Merge A1:A2 for logo placeholder
            {
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 2,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "mergeType": "MERGE_ALL",
                },
            },
            # Merge B1:last_col for title
            {
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 1,
                        "endColumnIndex": 1 + num_data_cols,
                    },
                    "mergeType": "MERGE_ALL",
                },
            },
            # Row 1-2 heights (taller for logo visibility)
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 2,
                    },
                    "properties": {"pixelSize": 45},
                    "fields": "pixelSize",
                },
            },
        ]

        self.spreadsheet.batch_update({"requests": requests})
        logger.info("Applied column widths and merges")
