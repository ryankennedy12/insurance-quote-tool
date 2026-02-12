"""Google Sheets integration for insurance quote comparison output."""

import logging
from typing import Any, Callable, Optional

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound

from app.extraction.models import (
    CarrierBundle,
    ComparisonSession,
    CurrentPolicy,
    InsuranceQuote,
)
from app.utils.config import GOOGLE_SERVICE_ACCOUNT_FILE, SPREADSHEET_ID

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


class TemplateNotFoundError(SheetsClientError):
    """Template worksheet not found in spreadsheet."""
    pass


class PermissionDeniedError(SheetsClientError):
    """Service account lacks permission to access spreadsheet."""
    pass


class QuotaExceededError(SheetsClientError):
    """Google Sheets API quota exceeded."""
    pass


# ============================================================================
# Main Client Class
# ============================================================================


class SheetsClient:
    """Google Sheets integration for multi-policy comparison output.

    Transforms a ComparisonSession into a fixed 25-row Google Sheets
    layout matching the agency's template structure.
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
            TemplateNotFoundError: "Template" worksheet not found
            QuotaExceededError: API quota exceeded
            SheetsClientError: Other API errors
        """
        logger.info(
            "Creating comparison for client=%s, date=%s, carriers=%d",
            session.client_name, session.date, len(session.carriers)
        )

        try:
            # 1. Duplicate template worksheet
            new_ws = self._duplicate_template(session.client_name, session.date)

            # 2. Build data grid
            grid = self._build_data_grid(session)

            # 3. Write to worksheet
            self._write_to_worksheet(new_ws, grid)

            # 4. Construct URL
            url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={new_ws.id}"

            logger.info("Comparison created: %s", url)
            return url

        except WorksheetNotFound as exc:
            raise TemplateNotFoundError(
                'Template worksheet not found. '
                'Create a worksheet named "Template" in the spreadsheet.'
            ) from exc
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

    def _build_auto_section(self, session: ComparisonSession) -> list[list[Any]]:
        """Build rows 18-21 (Auto coverage details).

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
    # Main Grid Builder
    # ========================================================================

    def _build_data_grid(self, session: ComparisonSession) -> list[list[Any]]:
        """Build 22-row x 7-column grid (rows 4-25, columns B-H).

        Args:
            session: Comparison session

        Returns:
            Grid as list of lists, ready for batch update at B4
        """
        grid = []

        # Row 4: Auto Premium
        grid.append(self._build_premium_row(
            session,
            lambda cp: cp.auto_premium,
            lambda cb: cb.auto.annual_premium if cb.auto else None
        ))

        # Row 5: Home Premium
        grid.append(self._build_premium_row(
            session,
            lambda cp: cp.home_premium,
            lambda cb: cb.home.annual_premium if cb.home else None
        ))

        # Row 6: Umbrella Premium
        grid.append(self._build_premium_row(
            session,
            lambda cp: cp.umbrella_premium,
            lambda cb: cb.umbrella.annual_premium if cb.umbrella else None
        ))

        # Row 7: Total
        grid.append(self._build_total_row(session))

        # Row 8: Blank separator
        grid.append([""] * 7)

        # Row 9: Home section header (template handles this)
        grid.append([""] * 7)

        # Rows 10-15: Home details (conditional on sections_included)
        if "home" in session.sections_included:
            grid.extend(self._build_home_section(session))
        else:
            grid.extend([[""] * 7] * 6)

        # Row 16: Blank separator
        grid.append([""] * 7)

        # Row 17: Auto section header (template handles this)
        grid.append([""] * 7)

        # Rows 18-21: Auto details (conditional on sections_included)
        if "auto" in session.sections_included:
            grid.extend(self._build_auto_section(session))
        else:
            grid.extend([[""] * 7] * 4)

        # Row 22: Blank separator
        grid.append([""] * 7)

        # Row 23: Umbrella section header (template handles this)
        grid.append([""] * 7)

        # Rows 24-25: Umbrella details (conditional on sections_included)
        if "umbrella" in session.sections_included:
            grid.extend(self._build_umbrella_section(session))
        else:
            grid.extend([[""] * 7] * 2)

        logger.debug("Built grid: %d rows x %d columns", len(grid), len(grid[0]) if grid else 0)
        return grid

    # ========================================================================
    # Worksheet Operations
    # ========================================================================

    def _duplicate_template(self, client_name: str, date: str) -> gspread.Worksheet:
        """Duplicate Template worksheet with unique name.

        Args:
            client_name: Client name for worksheet title
            date: ISO date string (YYYY-MM-DD)

        Returns:
            New duplicated worksheet

        Raises:
            WorksheetNotFound: Template worksheet not found
        """
        base_name = f"Quote_{client_name}_{date}"

        # Find Template worksheet
        template_ws = self.spreadsheet.worksheet("Template")

        # Check for existing worksheets with same name
        existing_names = [ws.title for ws in self.spreadsheet.worksheets()]

        # Find unique name
        worksheet_name = base_name
        counter = 2
        while worksheet_name in existing_names:
            worksheet_name = f"{base_name}_{counter}"
            counter += 1

        # Duplicate
        new_ws = template_ws.duplicate(new_sheet_name=worksheet_name)

        logger.info("Duplicated Template → %s", worksheet_name)
        return new_ws

    def _write_to_worksheet(
        self,
        worksheet: gspread.Worksheet,
        grid: list[list[Any]]
    ) -> None:
        """Write data grid to worksheet starting at B4.

        Uses single batch update for efficiency (gspread v6.1+ API).

        Args:
            worksheet: Target worksheet
            grid: 22x7 grid of data (rows 4-25, columns B-H)
        """
        # gspread v6.1+ syntax: values first, then range
        worksheet.update(grid, 'B4')

        logger.info("Wrote %d rows to worksheet %s", len(grid), worksheet.title)
