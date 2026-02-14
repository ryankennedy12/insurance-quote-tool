"""
Scioto Insurance Group — Branded Quote Comparison PDF Generator
Uses fpdf2 to produce professional, branded comparison PDFs.
Drop-in module for the insurance-quote-tool project.

Handles 2–6 carrier quotes per comparison with multi-policy bundles (Home + Auto + Umbrella).
Supports Current Policy baseline comparison column.
"""

from fpdf import FPDF
from datetime import datetime
from pathlib import Path
from typing import Optional
import os
import re

from app.extraction.models import ComparisonSession, CarrierBundle, CurrentPolicy, InsuranceQuote


# ──────────────────────────────────────────────
# Brand Constants
# ──────────────────────────────────────────────
BRAND = {
    "primary":       (135, 28, 48),    # #871c30 maroon
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
    "current_header":(180, 200, 220),   # Darker blue-gray for Current header
    "border_light":  (220, 215, 215),
    "divider":       (200, 190, 190),
}


# ──────────────────────────────────────────────
# Layout configuration based on total data columns
# ──────────────────────────────────────────────
def _get_layout(num_carriers: int, has_current: bool) -> dict:
    """Return layout config based on total data columns."""
    total_data_cols = num_carriers + (1 if has_current else 0)

    # Portrait: 2-5 data columns, Landscape: 6-7 data columns
    if total_data_cols <= 3:
        return {"orientation": "P", "label_w": 52, "header_font": 8, "body_font": 8, "row_h": 8}
    elif total_data_cols == 4:
        return {"orientation": "P", "label_w": 50, "header_font": 7.5, "body_font": 7.5, "row_h": 8}
    elif total_data_cols == 5:
        return {"orientation": "P", "label_w": 48, "header_font": 7.5, "body_font": 7.5, "row_h": 8}
    elif total_data_cols == 6:
        return {"orientation": "L", "label_w": 50, "header_font": 7.5, "body_font": 7, "row_h": 7.5}
    else:  # 7 data columns (6 carriers + current)
        return {"orientation": "L", "label_w": 46, "header_font": 7, "body_font": 6.5, "row_h": 7}


def _sanitize_text(text: str) -> str:
    """Replace Unicode characters with ASCII equivalents for Helvetica compatibility."""
    if not isinstance(text, str):
        return text
    replacements = {
        "\u2013": "-",   # en dash
        "\u2014": "-",   # em dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2022": "-",   # bullet
        "\u2026": "...", # ellipsis
        "\u00a0": " ",   # non-breaking space
        "\u2010": "-",   # hyphen
        "\u2011": "-",   # non-breaking hyphen
        "\u2012": "-",   # figure dash
        "\u00b7": "-",   # middle dot
    }
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    return text


def _session_has_multi_dwelling(
    current_policy: Optional[CurrentPolicy],
    carriers: list[CarrierBundle]
) -> bool:
    """Detect if session has multi-dwelling data."""
    if current_policy and current_policy.home_2_premium:
        return True
    return any(c.home_2 is not None for c in carriers)


_BRACKET_TAG_RE = re.compile(r"^\s*\[\w+\]\s*")


def _strip_bracket_tag(text: str) -> str:
    """Remove leading bracket tags like [home], [auto] from note strings."""
    if not isinstance(text, str):
        return text
    return _BRACKET_TAG_RE.sub("", text)


class SciotoComparisonPDF(FPDF):
    """Custom FPDF subclass with Scioto Insurance Group branding."""

    def __init__(self, logo_path: Optional[str] = None, orientation: str = "P"):
        super().__init__(orientation=orientation, unit="mm", format="Letter")
        self.logo_path = logo_path
        self.set_auto_page_break(auto=True, margin=25)
        self._orientation_mode = orientation

        # Register fonts
        self._register_fonts()

        # Metadata — update these for production
        self.agency_name = "Scioto Insurance Group"
        self.agency_phone = "(614) 555-0199"
        self.agency_email = "quotes@sciotoinsurance.com"

    def cell(self, w=None, h=None, text="", *args, **kwargs):
        """Override to sanitize text before rendering (safety net)."""
        return super().cell(w, h, _sanitize_text(text), *args, **kwargs)

    def multi_cell(self, w, h=None, text="", *args, **kwargs):
        """Override to sanitize text before rendering (safety net)."""
        return super().multi_cell(w, h, _sanitize_text(text), *args, **kwargs)

    def _register_fonts(self):
        """Set font family. Uses Helvetica (fpdf2 built-in) for cross-platform reliability."""
        self.font_family_name = "Helvetica"

    @property
    def _footer_margin(self) -> float:
        """Space reserved for footer (mm)."""
        return 25

    def _space_remaining(self) -> float:
        """Usable vertical space before footer zone."""
        return self.h - self.get_y() - self._footer_margin

    def _ensure_space(self, needed_mm: float):
        """Add a page break if there isn't enough room for `needed_mm`."""
        if self._space_remaining() < needed_mm:
            self.add_page()

    # ──────────────────────────────────────────
    # Header & Footer
    # ──────────────────────────────────────────
    def header(self):
        if self.page_no() == 1:
            self._draw_branded_header()
        else:
            self._draw_continuation_header()

    def _draw_branded_header(self):
        """Full branded header on page 1 with logo and crimson band."""
        page_w = self.w

        # Crimson banner — full width
        self.set_fill_color(*BRAND["primary"])
        self.rect(0, 0, page_w, 38, "F")

        # Subtle gradient overlay strip at bottom of banner
        self.set_fill_color(*BRAND["primary_dark"])
        self.rect(0, 35, page_w, 3, "F")

        # Logo
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, x=10, y=3, h=32)

        # Agency name + contact (right-aligned, on banner)
        self.set_font(self.font_family_name, "B", 16)
        self.set_text_color(*BRAND["white"])
        self.set_xy(page_w - 110, 8)
        self.cell(100, 8, _sanitize_text(self.agency_name), align="R")

        self.set_font(self.font_family_name, "", 8)
        self.set_text_color(*BRAND["cream"])
        self.set_xy(page_w - 110, 17)
        self.cell(100, 5, _sanitize_text(self.agency_phone), align="R")
        self.set_xy(page_w - 110, 22)
        self.cell(100, 5, _sanitize_text(self.agency_email), align="R")

        # Decorative thin line under banner
        self.set_draw_color(*BRAND["primary_light"])
        self.set_line_width(0.5)
        self.line(15, 40, page_w - 15, 40)

        self.set_y(44)

    def _draw_continuation_header(self):
        """Slim header on subsequent pages."""
        page_w = self.w
        self.set_fill_color(*BRAND["primary"])
        self.rect(0, 0, page_w, 12, "F")

        self.set_font(self.font_family_name, "B", 8)
        self.set_text_color(*BRAND["white"])
        self.set_xy(10, 2)
        self.cell(0, 8, _sanitize_text(self.agency_name), align="L")

        self.set_font(self.font_family_name, "", 8)
        self.set_xy(page_w - 50, 2)
        self.cell(40, 8, _sanitize_text(f"Page {self.page_no()}"), align="R")

        self.set_y(16)

    def footer(self):
        """Branded footer with page number + disclaimer."""
        self.set_y(-20)

        # Thin divider
        self.set_draw_color(*BRAND["divider"])
        self.set_line_width(0.3)
        self.line(15, self.get_y(), self.w - 15, self.get_y())

        self.ln(2)
        self.set_font(self.font_family_name, "I", 7)
        self.set_text_color(*BRAND["text_medium"])
        # Centered page number
        self.cell(0, 4, _sanitize_text(f"Page {self.page_no()}/{{nb}}"), align="C")

        self.ln(4)
        self.set_font(self.font_family_name, "", 5.5)
        self.multi_cell(
            0, 3,
            _sanitize_text(
                "This comparison is for informational purposes only and does not constitute a contract of insurance. "
                "Coverage is subject to the terms, conditions, and exclusions of each carrier's policy. "
                "Please review full policy documents before making a decision."
            ),
            align="C",
        )

    # ──────────────────────────────────────────
    # Content Sections
    # ──────────────────────────────────────────
    def add_client_section(self, client_name: str, date_str: Optional[str] = None):
        """Client name and date banner below header."""
        if not date_str:
            date_str = datetime.now().strftime("%B %d, %Y")

        y_start = self.get_y()
        self.set_fill_color(*BRAND["cream"])
        self.rect(15, y_start, self.w - 30, 16, "F")

        # Left side: "Prepared for"
        self.set_xy(20, y_start + 2)
        self.set_font(self.font_family_name, "", 7)
        self.set_text_color(*BRAND["text_medium"])
        self.cell(0, 4, _sanitize_text("PREPARED FOR"))

        self.set_xy(20, y_start + 7)
        self.set_font(self.font_family_name, "B", 13)
        self.set_text_color(*BRAND["primary"])
        self.cell(0, 6, _sanitize_text(client_name))

        # Right side: Date
        self.set_xy(self.w - 80, y_start + 2)
        self.set_font(self.font_family_name, "", 7)
        self.set_text_color(*BRAND["text_medium"])
        self.cell(60, 4, _sanitize_text("DATE"), align="R")

        self.set_xy(self.w - 80, y_start + 7)
        self.set_font(self.font_family_name, "B", 10)
        self.set_text_color(*BRAND["primary"])
        self.cell(60, 6, _sanitize_text(date_str), align="R")

        self.set_y(y_start + 20)

    def add_section_title(self, title: str):
        """
        Section title with crimson left accent bar.
        Checks for space BEFORE drawing anything to prevent orphaned
        accent bars bleeding into the footer zone.
        """
        # Need ~20mm: 7mm title bar + ~13mm min content after it
        self._ensure_space(20)

        y = self.get_y()
        # Accent bar
        self.set_fill_color(*BRAND["primary"])
        self.rect(15, y, 3, 7, "F")

        self.set_xy(21, y)
        self.set_font(self.font_family_name, "B", 11)
        self.set_text_color(*BRAND["primary_dark"])
        self.cell(0, 7, _sanitize_text(title.upper()))
        self.ln(10)

    def add_comparison_table(
        self,
        session: ComparisonSession,
        layout: dict
    ):
        """Build multi-section comparison table: Premium Summary → Home → Auto → Umbrella."""

        # Setup: calculate column widths
        num_carriers = len(session.carriers)
        has_current = session.current_policy is not None
        page_w = self.w
        margin = 15
        usable_w = page_w - 2 * margin
        label_col_w = layout["label_w"]

        # Data columns = current (0 or 1) + carriers (2-6)
        num_data_cols = num_carriers + (1 if has_current else 0)
        data_col_w = (usable_w - label_col_w) / num_data_cols

        # Extract font sizes from layout
        hf = layout["header_font"]
        bf = layout["body_font"]
        row_h = layout["row_h"]
        x_start = margin

        # ── TABLE HEADER ROW ──
        self._add_table_header(
            x_start, label_col_w, data_col_w, hf,
            session.current_policy, session.carriers
        )

        # ── SECTION 1: PREMIUM SUMMARY (always shown) ──
        self._add_premium_section(
            x_start, label_col_w, data_col_w, bf, row_h,
            session.current_policy, session.carriers, session.sections_included
        )

        # ── SECTION 2: HOME DETAILS ──
        if "home" in session.sections_included:
            self._add_home_section(
                x_start, label_col_w, data_col_w, bf, row_h,
                session.current_policy, session.carriers
            )

        # ── SECTION 3: AUTO DETAILS ──
        if "auto" in session.sections_included:
            self._add_auto_section(
                x_start, label_col_w, data_col_w, bf, row_h,
                session.current_policy, session.carriers
            )

        # ── SECTION 4: UMBRELLA DETAILS ──
        if "umbrella" in session.sections_included:
            self._add_umbrella_section(
                x_start, label_col_w, data_col_w, bf, row_h,
                session.current_policy, session.carriers
            )

    def _add_table_header(
        self,
        x_start: float,
        label_col_w: float,
        data_col_w: float,
        header_font: float,
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ):
        """Render table header row: Label | Current | Carrier 1 | ... | Carrier N."""
        self._ensure_space(12)
        y = self.get_y()

        # Label column header
        self.set_fill_color(*BRAND["primary"])
        self.set_text_color(*BRAND["white"])
        self.set_font(self.font_family_name, "B", header_font)
        self.set_xy(x_start, y)
        self.cell(label_col_w, 10, _sanitize_text("  COVERAGE"), border=1, fill=True, align="L")

        col_idx = 0

        # Current Policy column (if exists)
        if current_policy:
            x = x_start + label_col_w + col_idx * data_col_w
            self.set_xy(x, y)
            self.set_fill_color(*BRAND["current_header"])
            self.set_text_color(*BRAND["white"])
            self.cell(data_col_w, 10, _sanitize_text(current_policy.carrier_name), border=1, fill=True, align="C")
            col_idx += 1

        # Carrier columns
        for carrier in carriers:
            x = x_start + label_col_w + col_idx * data_col_w
            self.set_xy(x, y)
            self.set_fill_color(*BRAND["primary"])
            self.set_text_color(*BRAND["white"])
            name = carrier.carrier_name
            if data_col_w < 35 and len(name) > 14:
                name = name[:13] + "..."
            self.cell(data_col_w, 10, _sanitize_text(name), border=1, fill=True, align="C")
            col_idx += 1

        self.ln(10)

    def _add_premium_section(
        self,
        x_start: float,
        label_col_w: float,
        data_col_w: float,
        body_font: float,
        row_h: float,
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle],
        sections_included: list[str]
    ):
        """Premium Summary section: Home, Auto, Umbrella, Total."""
        self._add_section_divider_row(
            "PREMIUM SUMMARY", label_col_w, data_col_w, x_start, body_font,
            current_policy, carriers
        )

        row_idx = 0
        is_multi_dw = _session_has_multi_dwelling(current_policy, carriers)

        # Home Premium (if included)
        if "home" in sections_included:
            if is_multi_dw:
                # Split into Home 1 / Home 2 rows
                self._add_data_row(
                    label="Home 1 Premium",
                    values=self._extract_premium_row("home", current_policy, carriers),
                    row_idx=row_idx,
                    label_col_w=label_col_w,
                    data_col_w=data_col_w,
                    x_start=x_start,
                    font_size=body_font,
                    row_h=row_h,
                    current_policy=current_policy
                )
                row_idx += 1
                self._add_data_row(
                    label="Home 2 Premium",
                    values=self._extract_premium_row("home_2", current_policy, carriers),
                    row_idx=row_idx,
                    label_col_w=label_col_w,
                    data_col_w=data_col_w,
                    x_start=x_start,
                    font_size=body_font,
                    row_h=row_h,
                    current_policy=current_policy
                )
                row_idx += 1
            else:
                self._add_data_row(
                    label="Home Premium",
                    values=self._extract_premium_row("home", current_policy, carriers),
                    row_idx=row_idx,
                    label_col_w=label_col_w,
                    data_col_w=data_col_w,
                    x_start=x_start,
                    font_size=body_font,
                    row_h=row_h,
                    current_policy=current_policy
                )
                row_idx += 1

        # Auto Premium (if included)
        if "auto" in sections_included:
            self._add_data_row(
                label="Auto Premium",
                values=self._extract_premium_row("auto", current_policy, carriers),
                row_idx=row_idx,
                label_col_w=label_col_w,
                data_col_w=data_col_w,
                x_start=x_start,
                font_size=body_font,
                row_h=row_h,
                current_policy=current_policy
            )
            row_idx += 1

        # Umbrella Premium (if included)
        if "umbrella" in sections_included:
            self._add_data_row(
                label="Umbrella Premium",
                values=self._extract_premium_row("umbrella", current_policy, carriers),
                row_idx=row_idx,
                label_col_w=label_col_w,
                data_col_w=data_col_w,
                x_start=x_start,
                font_size=body_font,
                row_h=row_h,
                current_policy=current_policy
            )
            row_idx += 1

        # Total (bold, highlighted)
        self._add_total_row(
            x_start, label_col_w, data_col_w, body_font, row_h,
            current_policy, carriers
        )

    def _add_home_section(
        self,
        x_start: float,
        label_col_w: float,
        data_col_w: float,
        body_font: float,
        row_h: float,
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ):
        """Home Details section: Dwelling, Other Structures, etc."""
        is_multi_dw = _session_has_multi_dwelling(current_policy, carriers)

        self.ln(3)  # Small gap between sections
        self._add_section_divider_row(
            "HOME DETAILS", label_col_w, data_col_w, x_start, body_font,
            current_policy, carriers
        )

        home_rows = [
            ("Dwelling (Cov A)", "dwelling", "home_dwelling"),
            ("Other Structures (B)", "other_structures", "home_other_structures"),
            ("Personal Property (C)", "personal_property", "home_personal_property"),
            ("Loss of Use (D)", "loss_of_use", "home_loss_of_use"),
            ("Personal Liability (E)", "personal_liability", "home_liability"),
            ("Medical Payments (F)", "medical_payments", None),  # Not on CurrentPolicy
            ("All-Peril Deductible", "deductible", "home_deductible"),
            ("Wind/Hail Deductible", "wind_hail_deductible", None),
        ]

        if is_multi_dw:
            # Dwelling 1 sub-section
            self._add_sub_divider_row(
                "DWELLING 1", label_col_w, data_col_w, x_start, body_font,
                current_policy, carriers
            )
            for row_idx, (label, carrier_key, current_key) in enumerate(home_rows):
                values = self._extract_home_row(carrier_key, current_key, current_policy, carriers, dwelling=1)
                self._add_data_row(
                    label=label, values=values, row_idx=row_idx,
                    label_col_w=label_col_w, data_col_w=data_col_w, x_start=x_start,
                    font_size=body_font, row_h=row_h, current_policy=current_policy
                )

            # Dwelling 2 sub-section
            self._add_sub_divider_row(
                "DWELLING 2", label_col_w, data_col_w, x_start, body_font,
                current_policy, carriers
            )
            for row_idx, (label, carrier_key, current_key) in enumerate(home_rows):
                values = self._extract_home_row(carrier_key, current_key, current_policy, carriers, dwelling=2)
                self._add_data_row(
                    label=label, values=values, row_idx=row_idx,
                    label_col_w=label_col_w, data_col_w=data_col_w, x_start=x_start,
                    font_size=body_font, row_h=row_h, current_policy=current_policy
                )
        else:
            # Single dwelling — no sub-dividers
            for row_idx, (label, carrier_key, current_key) in enumerate(home_rows):
                values = self._extract_home_row(carrier_key, current_key, current_policy, carriers)
                self._add_data_row(
                    label=label, values=values, row_idx=row_idx,
                    label_col_w=label_col_w, data_col_w=data_col_w, x_start=x_start,
                    font_size=body_font, row_h=row_h, current_policy=current_policy
                )

    def _add_auto_section(
        self,
        x_start: float,
        label_col_w: float,
        data_col_w: float,
        body_font: float,
        row_h: float,
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ):
        """Auto Details section: Limits, UM/UIM, Deductibles."""
        self.ln(3)
        self._add_section_divider_row(
            "AUTO DETAILS", label_col_w, data_col_w, x_start, body_font,
            current_policy, carriers
        )

        auto_rows = [
            ("Limits", "limits", "auto_limits"),
            ("UM/UIM", "um_uim", "auto_um_uim"),
            ("Deductibles (Comp)", "comprehensive", "auto_comp_deductible"),
            ("Deductibles (Collision)", "collision", "auto_collision_deductible"),
        ]

        for row_idx, (label, carrier_key, current_key) in enumerate(auto_rows):
            values = self._extract_auto_row(carrier_key, current_key, current_policy, carriers)
            self._add_data_row(
                label=label,
                values=values,
                row_idx=row_idx,
                label_col_w=label_col_w,
                data_col_w=data_col_w,
                x_start=x_start,
                font_size=body_font,
                row_h=row_h,
                current_policy=current_policy
            )

    def _add_umbrella_section(
        self,
        x_start: float,
        label_col_w: float,
        data_col_w: float,
        body_font: float,
        row_h: float,
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ):
        """Umbrella Details section: Limits, Deductible."""
        # Keep header + tables together — break before if insufficient space
        self._ensure_space(90)
        self.ln(3)
        self._add_section_divider_row(
            "UMBRELLA DETAILS", label_col_w, data_col_w, x_start, body_font,
            current_policy, carriers
        )

        umbrella_rows = [
            ("Limits", "limits", "umbrella_limits"),
            ("Deductible", "deductible", "umbrella_deductible"),
        ]

        for row_idx, (label, carrier_key, current_key) in enumerate(umbrella_rows):
            values = self._extract_umbrella_row(carrier_key, current_key, current_policy, carriers)
            self._add_data_row(
                label=label,
                values=values,
                row_idx=row_idx,
                label_col_w=label_col_w,
                data_col_w=data_col_w,
                x_start=x_start,
                font_size=body_font,
                row_h=row_h,
                current_policy=current_policy
            )

    def _add_total_row(
        self,
        x_start: float,
        label_col_w: float,
        data_col_w: float,
        body_font: float,
        row_h: float,
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ):
        """Total Premium row (bold, cream background, no green highlighting)."""
        self._ensure_space(row_h + 3)
        y = self.get_y()

        # Label cell
        self.set_fill_color(*BRAND["cream"])
        self.set_text_color(*BRAND["primary_dark"])
        self.set_font(self.font_family_name, "B", body_font + 1)
        self.set_xy(x_start, y)
        self.cell(label_col_w, row_h + 2, _sanitize_text("  Total"), border=1, fill=True, align="L")

        col_idx = 0

        # Current Policy total
        if current_policy:
            x = x_start + label_col_w + col_idx * data_col_w
            self.set_xy(x, y)
            self.set_fill_color(*BRAND["current_bg"])
            self.set_text_color(*BRAND["primary_dark"])
            total_str = _sanitize_text(self._fmt_currency(current_policy.total_premium))
            self.cell(data_col_w, row_h + 2, total_str, border=1, fill=True, align="C")
            col_idx += 1

        # Carrier totals
        for carrier in carriers:
            x = x_start + label_col_w + col_idx * data_col_w
            self.set_xy(x, y)
            self.set_fill_color(*BRAND["cream"])
            self.set_text_color(*BRAND["primary_dark"])
            total_str = _sanitize_text(self._fmt_currency(carrier.total_premium))
            self.cell(data_col_w, row_h + 2, total_str, border=1, fill=True, align="C")
            col_idx += 1

        self.ln(row_h + 2)

    # ──────────────────────────────────────────
    # Data Extraction Helpers
    # ──────────────────────────────────────────
    def _extract_premium_row(
        self,
        policy_type: str,  # "home", "auto", or "umbrella"
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ) -> list[str]:
        """Extract premium values for a given policy type."""
        values = []

        # Current Policy value
        if current_policy:
            if policy_type == "home":
                values.append(self._fmt_currency(current_policy.home_premium))
            elif policy_type == "home_2":
                values.append(self._fmt_currency(current_policy.home_2_premium))
            elif policy_type == "auto":
                values.append(self._fmt_currency(current_policy.auto_premium))
            elif policy_type == "umbrella":
                values.append(self._fmt_currency(current_policy.umbrella_premium))

        # Carrier values
        for carrier in carriers:
            if policy_type == "home" and carrier.home:
                values.append(self._fmt_currency(carrier.home.annual_premium))
            elif policy_type == "home_2" and carrier.home_2:
                values.append(self._fmt_currency(carrier.home_2.annual_premium))
            elif policy_type == "auto" and carrier.auto:
                values.append(self._fmt_currency(carrier.auto.annual_premium))
            elif policy_type == "umbrella" and carrier.umbrella:
                values.append(self._fmt_currency(carrier.umbrella.annual_premium))
            else:
                values.append("-")

        return values

    def _extract_home_row(
        self,
        carrier_key: str,  # e.g., "dwelling", "deductible"
        current_key: Optional[str],  # e.g., "home_dwelling", "home_deductible"
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle],
        dwelling: int = 1  # 1 for primary, 2 for Dwelling 2
    ) -> list[str]:
        """Extract home coverage row values for a given dwelling number."""
        values = []

        # For Dwelling 2, adjust current_key to home_2_* prefix
        effective_current_key = current_key
        if dwelling == 2 and current_key:
            effective_current_key = current_key.replace("home_", "home_2_", 1)

        # Current Policy value
        if current_policy and effective_current_key:
            current_val = getattr(current_policy, effective_current_key, None)
            values.append(self._fmt_currency(current_val))
        elif current_policy:
            values.append("-")  # Field doesn't exist on CurrentPolicy

        # Carrier values — select the right dwelling quote
        for carrier in carriers:
            quote = carrier.home if dwelling == 1 else carrier.home_2
            if not quote:
                values.append("-")
            elif carrier_key in ["deductible", "wind_hail_deductible"]:
                # Direct attributes on InsuranceQuote
                val = getattr(quote, carrier_key, None)
                values.append(self._fmt_currency(val) if val else "-")
            else:
                # coverage_limits model field
                val = getattr(quote.coverage_limits, carrier_key, None)
                if val is None:
                    values.append("-")
                elif isinstance(val, str):
                    values.append(val)  # Pass through text like "ALS"
                else:
                    values.append(self._fmt_currency(val))

        return values

    def _extract_auto_row(
        self,
        carrier_key: str,  # "limits", "um_uim", "comprehensive", "collision"
        current_key: str,  # "auto_limits", "auto_um_uim", etc.
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ) -> list[str]:
        """Extract auto coverage row values."""
        values = []

        # Current Policy value
        if current_policy:
            current_val = getattr(current_policy, current_key, None)
            if current_val is None:
                values.append("-")
            elif isinstance(current_val, str):
                values.append(current_val)
            else:
                values.append(self._fmt_currency(current_val))

        # Carrier values
        for carrier in carriers:
            if not carrier.auto:
                values.append("-")
            elif carrier_key == "limits":
                # Use helper from sheets_client pattern
                values.append(self._get_auto_limits(carrier.auto))
            elif carrier_key == "collision":
                # Direct deductible attribute
                values.append(self._fmt_currency(carrier.auto.deductible))
            else:
                # coverage_limits model field (um_uim, comprehensive)
                val = getattr(carrier.auto.coverage_limits, carrier_key, None)
                if val is None:
                    values.append("-")
                elif isinstance(val, str):
                    values.append(val)
                else:
                    values.append(self._fmt_currency(val))

        return values

    def _extract_umbrella_row(
        self,
        carrier_key: str,  # "limits" or "deductible"
        current_key: str,  # "umbrella_limits" or "umbrella_deductible"
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ) -> list[str]:
        """Extract umbrella coverage row values."""
        values = []

        # Current Policy value
        if current_policy:
            current_val = getattr(current_policy, current_key, None)
            if current_val is None:
                values.append("-")
            elif isinstance(current_val, str):
                values.append(current_val)
            else:
                values.append(self._fmt_currency(current_val))

        # Carrier values
        for carrier in carriers:
            if not carrier.umbrella:
                values.append("-")
            elif carrier_key == "limits":
                # Use helper from sheets_client pattern
                values.append(self._get_umbrella_limits(carrier.umbrella))
            else:  # deductible
                val = carrier.umbrella.deductible
                values.append(self._fmt_currency(val) if val else "-")

        return values

    def _get_auto_limits(self, quote: InsuranceQuote) -> str:
        """Format auto liability limits into display string."""
        cl = quote.coverage_limits

        # Split limits: BI/BI/PD format
        if cl.bi_per_person and cl.bi_per_accident and cl.pd_per_accident:
            return f"{int(cl.bi_per_person/1000)}/{int(cl.bi_per_accident/1000)}/{int(cl.pd_per_accident/1000)}"

        # CSL (Combined Single Limit)
        if cl.csl:
            if cl.csl >= 1_000_000:
                return f"{int(cl.csl/1_000_000)}M CSL"
            else:
                return f"{int(cl.csl/1000)}K CSL"

        return "-"

    def _get_umbrella_limits(self, quote: InsuranceQuote) -> str:
        """Format umbrella limits into display string."""
        limit = quote.coverage_limits.umbrella_limit

        if limit is None:
            return "-"

        # Format numeric values >= 1M as "XM CSL"
        if limit >= 1_000_000:
            return f"{int(limit/1_000_000)}M CSL"

        # Smaller values return as currency
        return self._fmt_currency(limit)

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────
    def _add_section_divider_row(
        self,
        title: str,
        label_w: float,
        data_col_w: float,
        x_start: float,
        font_size: float,
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ):
        """Dark mini-header to separate table sections."""
        self._ensure_space(8)
        y = self.get_y()

        num_data_cols = len(carriers) + (1 if current_policy else 0)
        total_w = label_w + num_data_cols * data_col_w

        self.set_fill_color(*BRAND["primary_dark"])
        self.set_text_color(*BRAND["white"])
        self.set_font(self.font_family_name, "B", font_size - 1)
        self.set_xy(x_start, y)
        self.cell(total_w, 6, _sanitize_text(f"  {title}"), border=1, fill=True, align="L")
        self.ln(6)

    def _add_sub_divider_row(
        self,
        title: str,
        label_w: float,
        data_col_w: float,
        x_start: float,
        font_size: float,
        current_policy: Optional[CurrentPolicy],
        carriers: list[CarrierBundle]
    ):
        """Lighter sub-header for DWELLING 1 / DWELLING 2 labels."""
        self._ensure_space(7)
        y = self.get_y()

        num_data_cols = len(carriers) + (1 if current_policy else 0)
        total_w = label_w + num_data_cols * data_col_w

        self.set_fill_color(*BRAND["primary_light"])
        self.set_text_color(*BRAND["white"])
        self.set_font(self.font_family_name, "B", font_size - 1)
        self.set_xy(x_start, y)
        self.cell(total_w, 5, _sanitize_text(f"  {title}"), border=1, fill=True, align="L")
        self.ln(5)

    def _add_data_row(
        self,
        label: str,
        values: list[str],
        row_idx: int,
        label_col_w: float,
        data_col_w: float,
        x_start: float,
        font_size: float,
        row_h: float,
        current_policy: Optional[CurrentPolicy]
    ):
        """Single data row with alternating background and Current column styling."""
        self._ensure_space(row_h + 2)
        y = self.get_y()
        is_alt = row_idx % 2 == 0
        bg = BRAND["row_alt"] if is_alt else BRAND["row_white"]

        # Label cell
        self.set_fill_color(*bg)
        self.set_text_color(*BRAND["text_dark"])
        self.set_font(self.font_family_name, "", font_size)
        self.set_xy(x_start, y)
        self.cell(label_col_w, row_h, _sanitize_text(f"  {label}"), border="LBR", fill=True, align="L")

        # Data cells (Current + Carriers)
        for i, val in enumerate(values):
            x = x_start + label_col_w + i * data_col_w
            self.set_xy(x, y)

            # First value is Current Policy if it exists
            if i == 0 and current_policy:
                self.set_fill_color(*BRAND["current_bg"])
            else:
                self.set_fill_color(*bg)

            self.set_font(self.font_family_name, "", font_size)
            self.set_text_color(*BRAND["text_dark"])
            self.cell(data_col_w, row_h, _sanitize_text(val), border="LBR", fill=True, align="C")

        self.ln(row_h)

    @staticmethod
    def _fmt_currency(value) -> str:
        if value is None:
            return "-"  # Simple dash for consistency with Sheets
        try:
            v = float(value)
            if v >= 1000:
                return f"${v:,.0f}"
            else:
                return f"${v:,.2f}"
        except (ValueError, TypeError):
            return _sanitize_text(str(value))

    def add_endorsements_section(self, carriers: list[CarrierBundle]):
        """List endorsements and discounts per carrier."""
        self.ln(4)
        self.add_section_title("Endorsements & Discounts")

        for bundle in carriers:
            # Collect endorsements and discounts from all policies in bundle
            all_endorsements = []
            all_discounts = []

            for policy_type in ["home", "home_2", "auto", "umbrella"]:
                quote = getattr(bundle, policy_type)
                if quote:
                    all_endorsements.extend(quote.endorsements)
                    all_discounts.extend(quote.discounts_applied)

            # Deduplicate
            all_endorsements = list(dict.fromkeys(all_endorsements))
            all_discounts = list(dict.fromkeys(all_discounts))

            self._ensure_space(18)

            # Carrier sub-header
            self.set_font(self.font_family_name, "B", 9)
            self.set_text_color(*BRAND["primary"])
            self.cell(0, 6, _sanitize_text(bundle.carrier_name))
            self.ln(6)

            if all_endorsements:
                self.set_font(self.font_family_name, "I", 7)
                self.set_text_color(*BRAND["text_medium"])
                self.cell(0, 4, _sanitize_text("Endorsements:  " + ", ".join(all_endorsements)))
                self.ln(4)
            else:
                self.set_font(self.font_family_name, "I", 7)
                self.set_text_color(*BRAND["text_light"])
                self.cell(0, 4, _sanitize_text("No endorsements listed"))
                self.ln(4)

            if all_discounts:
                self.set_font(self.font_family_name, "I", 7)
                self.set_text_color(*BRAND["text_medium"])
                self.cell(0, 4, _sanitize_text("Discounts:  " + ", ".join(all_discounts)))
                self.ln(4)

            self.ln(3)

    def add_notes_section(
        self,
        carriers: list[CarrierBundle],
        agent_notes: Optional[str] = None
    ):
        """Two-part notes section: per-carrier AI notes + optional agent notes."""

        # Part A: Per-carrier notes (from InsuranceQuote.notes)
        carrier_notes_exist = False
        for bundle in carriers:
            for policy_type in ["home", "home_2", "auto", "umbrella"]:
                quote = getattr(bundle, policy_type)
                if quote and quote.notes:
                    carrier_notes_exist = True
                    break

        if carrier_notes_exist:
            self.ln(2)
            self.add_section_title("Carrier Notes")

            for bundle in carriers:
                # Collect notes from all policies in bundle
                notes_list = []
                for policy_type in ["home", "home_2", "auto", "umbrella"]:
                    quote = getattr(bundle, policy_type)
                    if quote and quote.notes:
                        clean_note = _strip_bracket_tag(quote.notes)
                        display_label = "Home 2" if policy_type == "home_2" else policy_type.title()
                        notes_list.append(f"{display_label}: {clean_note}")

                if notes_list:
                    self._ensure_space(10)
                    self.set_font(self.font_family_name, "B", 8)
                    self.set_text_color(*BRAND["primary"])
                    self.cell(35, 5, _sanitize_text(bundle.carrier_name + ":"))
                    self.set_font(self.font_family_name, "", 7.5)
                    self.set_text_color(*BRAND["text_dark"])
                    self.multi_cell(0, 5, _sanitize_text(" | ".join(notes_list)))
                    self.ln(1)

        # Part B: General agent notes (from session.agent_notes or parameter)
        if agent_notes and agent_notes.strip():
            self.ln(2)
            self.add_section_title("Agent Notes")

            self.set_font(self.font_family_name, "", 8)
            self.set_text_color(*BRAND["text_dark"])
            self.multi_cell(0, 5, _sanitize_text(agent_notes))
            self.ln(2)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────
def generate_comparison_pdf(
    session: ComparisonSession,
    output_path: str,
    logo_path: Optional[str] = None,
    date_str: Optional[str] = None,
    agent_notes: Optional[str] = None,
) -> str:
    """
    Generate a branded comparison PDF from a ComparisonSession.

    Args:
        session: ComparisonSession with current_policy, carriers, sections_included
        output_path: Where to save the PDF
        logo_path: Path to agency logo PNG (optional)
        date_str: Override date string (default: session.date)
        agent_notes: General agent notes (optional, separate from per-carrier notes)

    Returns:
        The output_path for chaining
    """
    # Validate carriers
    if not session.carriers or len(session.carriers) > 6:
        raise ValueError("Must have 2-6 carriers")

    # Determine layout
    has_current = session.current_policy is not None
    layout = _get_layout(len(session.carriers), has_current)

    # Initialize PDF
    pdf = SciotoComparisonPDF(logo_path=logo_path, orientation=layout["orientation"])
    pdf.alias_nb_pages()
    pdf.add_page()

    # Client info
    pdf.add_client_section(session.client_name, date_str or session.date)

    # Comparison table (multi-section)
    pdf.add_section_title("Coverage Comparison")
    pdf.add_comparison_table(session, layout)

    # Endorsements & Discounts
    pdf.add_endorsements_section(session.carriers)

    # Notes (two-part)
    pdf.add_notes_section(session.carriers, agent_notes)

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pdf.output(output_path)
    return output_path
