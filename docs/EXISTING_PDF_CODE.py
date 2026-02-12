"""
Scioto Insurance Group — Branded Quote Comparison PDF Generator
Uses fpdf2 to produce professional, branded comparison PDFs.
Drop-in module for the insurance-quote-tool project.

Handles 2–6 carrier quotes per comparison:
  - 2–4 carriers: Portrait layout
  - 5–6 carriers: Landscape layout with scaled fonts
"""

from fpdf import FPDF
from datetime import datetime
from pathlib import Path
from typing import Optional
import os


# ──────────────────────────────────────────────
# Brand Constants
# ──────────────────────────────────────────────
BRAND = {
    "primary":       (127, 27, 36),    # Deep crimson from logo
    "primary_dark":  (95, 18, 25),     # Darker shade for contrast
    "primary_light": (178, 60, 72),    # Lighter accent
    "cream":         (248, 240, 232),  # Warm cream for highlights
    "white":         (255, 255, 255),
    "text_dark":     (40, 40, 40),     # Near-black body text
    "text_medium":   (100, 100, 100),  # Muted secondary text
    "text_light":    (160, 160, 160),  # Subtle hints
    "row_alt":       (252, 248, 248),  # Very light blush alternating rows
    "row_white":     (255, 255, 255),
    "best_value_bg": (230, 245, 230),  # Soft green highlight
    "best_value_border": (76, 175, 80),
    "border_light":  (220, 215, 215),  # Table borders
    "divider":       (200, 190, 190),  # Section dividers
}

# ──────────────────────────────────────────────
# Layout scaling by carrier count
# ──────────────────────────────────────────────
LAYOUT_CONFIG = {
    2: {"orientation": "P", "label_w": 60, "header_font": 9, "body_font": 8.5, "row_h": 9},
    3: {"orientation": "P", "label_w": 52, "header_font": 8, "body_font": 8,   "row_h": 8},
    4: {"orientation": "P", "label_w": 48, "header_font": 7.5, "body_font": 7.5, "row_h": 8},
    5: {"orientation": "L", "label_w": 52, "header_font": 8, "body_font": 7.5, "row_h": 8},
    6: {"orientation": "L", "label_w": 48, "header_font": 7, "body_font": 7,   "row_h": 7},
}


def _get_layout(num_carriers: int) -> dict:
    """Return layout config clamped to 2–6 range."""
    n = max(2, min(6, num_carriers))
    return LAYOUT_CONFIG[n]


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
        self.agency_license = "OH License #1234567"

    def _register_fonts(self):
        """Register bundled DejaVu fonts for professional typography."""
        font_dir = "/usr/share/fonts/truetype/dejavu/"
        if os.path.exists(font_dir + "DejaVuSans.ttf"):
            self.add_font("DejaVu", "", font_dir + "DejaVuSans.ttf")
            self.add_font("DejaVu", "B", font_dir + "DejaVuSans-Bold.ttf")
            self.add_font("DejaVu", "I", font_dir + "DejaVuSans-Oblique.ttf")
            self.font_family_name = "DejaVu"
        else:
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
        self.cell(100, 8, self.agency_name, align="R")

        self.set_font(self.font_family_name, "", 8)
        self.set_text_color(*BRAND["cream"])
        self.set_xy(page_w - 110, 17)
        self.cell(100, 5, self.agency_phone, align="R")
        self.set_xy(page_w - 110, 22)
        self.cell(100, 5, self.agency_email, align="R")

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
        self.cell(0, 8, self.agency_name, align="L")

        self.set_font(self.font_family_name, "", 8)
        self.set_xy(page_w - 50, 2)
        self.cell(40, 8, f"Page {self.page_no()}", align="R")

        self.set_y(16)

    def footer(self):
        """Branded footer with license + disclaimer."""
        self.set_y(-20)

        # Thin divider
        self.set_draw_color(*BRAND["divider"])
        self.set_line_width(0.3)
        self.line(15, self.get_y(), self.w - 15, self.get_y())

        self.ln(2)
        self.set_font(self.font_family_name, "I", 6.5)
        self.set_text_color(*BRAND["text_light"])
        self.cell(0, 4, self.agency_license, align="L")
        self.set_x(self.w / 2 - 20)
        self.cell(40, 4, f"Page {self.page_no()}/{{nb}}", align="C")
        self.ln(4)
        self.set_font(self.font_family_name, "", 5.5)
        self.multi_cell(
            0, 3,
            "This comparison is for informational purposes only and does not constitute a contract of insurance. "
            "Coverage is subject to the terms, conditions, and exclusions of each carrier's policy. "
            "Please review full policy documents before making a decision.",
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
        self.cell(0, 4, "PREPARED FOR")

        self.set_xy(20, y_start + 7)
        self.set_font(self.font_family_name, "B", 13)
        self.set_text_color(*BRAND["primary"])
        self.cell(0, 6, client_name)

        # Right side: Date
        self.set_xy(self.w - 80, y_start + 2)
        self.set_font(self.font_family_name, "", 7)
        self.set_text_color(*BRAND["text_medium"])
        self.cell(60, 4, "DATE", align="R")

        self.set_xy(self.w - 80, y_start + 7)
        self.set_font(self.font_family_name, "B", 10)
        self.set_text_color(*BRAND["primary"])
        self.cell(60, 6, date_str, align="R")

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
        self.cell(0, 7, title.upper())
        self.ln(10)

    def add_comparison_table(self, quotes: list[dict], layout: dict):
        """
        Build the carrier comparison table, responsive to carrier count.

        quotes: list of InsuranceQuote-like dicts
        layout: dict from LAYOUT_CONFIG with sizing parameters
        """
        if not quotes:
            return

        num_carriers = len(quotes)
        page_w = self.w
        margin = 15
        usable_w = page_w - 2 * margin
        label_col_w = layout["label_w"]
        carrier_col_w = (usable_w - label_col_w) / num_carriers
        hf = layout["header_font"]
        bf = layout["body_font"]
        row_h = layout["row_h"]
        x_start = margin

        # Find best value (lowest premium)
        premiums = [q.get("annual_premium", float("inf")) for q in quotes]
        best_idx = premiums.index(min(premiums))

        # ── Table Header Row ──
        self._ensure_space(row_h + 10)
        y = self.get_y()

        # Label column header
        self.set_fill_color(*BRAND["primary"])
        self.set_text_color(*BRAND["white"])
        self.set_font(self.font_family_name, "B", hf)
        self.set_xy(x_start, y)
        self.cell(label_col_w, 10, "  COVERAGE", border=1, fill=True, align="L")

        # Carrier column headers
        for i, q in enumerate(quotes):
            x = x_start + label_col_w + i * carrier_col_w
            self.set_xy(x, y)
            is_best = (i == best_idx)
            if is_best:
                self.set_fill_color(*BRAND["best_value_border"])
            else:
                self.set_fill_color(*BRAND["primary"])
            name = q.get("carrier_name", "Carrier")
            # Truncate long names for tight columns
            if carrier_col_w < 35 and len(name) > 14:
                name = name[:13] + "…"
            self.cell(carrier_col_w, 10, name, border=1, fill=True, align="C")

        self.ln(10)

        # ── Policy Type Sub-header ──
        y = self.get_y()
        self.set_fill_color(*BRAND["cream"])
        self.set_text_color(*BRAND["text_medium"])
        self.set_font(self.font_family_name, "I", bf - 1)
        self.set_xy(x_start, y)
        self.cell(label_col_w, 7, "  Policy Type", border=1, fill=True, align="L")
        for i, q in enumerate(quotes):
            x = x_start + label_col_w + i * carrier_col_w
            self.set_xy(x, y)
            self.cell(carrier_col_w, 7, q.get("policy_type", "—"), border=1, fill=True, align="C")
        self.ln(7)

        # ── Coverage Limit Rows ──
        coverage_order = [
            ("dwelling", "Dwelling (Cov A)"),
            ("other_structures", "Other Structures (B)"),
            ("personal_property", "Personal Property (C)"),
            ("loss_of_use", "Loss of Use (D)"),
            ("personal_liability", "Personal Liability (E)"),
            ("medical_payments", "Medical Payments (F)"),
        ]

        self._add_section_divider_row("COVERAGE LIMITS", num_carriers, label_col_w, carrier_col_w, x_start, bf)

        for row_idx, (key, label) in enumerate(coverage_order):
            self._add_data_row(
                label=label,
                values=[self._fmt_currency(q.get("coverage_limits", {}).get(key)) for q in quotes],
                row_idx=row_idx,
                best_idx=best_idx,
                label_col_w=label_col_w,
                carrier_col_w=carrier_col_w,
                x_start=x_start,
                num_carriers=num_carriers,
                font_size=bf,
                row_h=row_h,
            )

        # ── Deductible Rows ──
        self._add_section_divider_row("DEDUCTIBLES", num_carriers, label_col_w, carrier_col_w, x_start, bf)

        self._add_data_row(
            label="All-Peril Deductible",
            values=[self._fmt_currency(q.get("deductible")) for q in quotes],
            row_idx=0,
            best_idx=best_idx,
            label_col_w=label_col_w,
            carrier_col_w=carrier_col_w,
            x_start=x_start,
            num_carriers=num_carriers,
            font_size=bf,
            row_h=row_h,
        )

        wind_hail_values = [q.get("wind_hail_deductible") for q in quotes]
        if any(v is not None for v in wind_hail_values):
            self._add_data_row(
                label="Wind/Hail Deductible",
                values=[self._fmt_currency(v) if v else "Included" for v in wind_hail_values],
                row_idx=1,
                best_idx=best_idx,
                label_col_w=label_col_w,
                carrier_col_w=carrier_col_w,
                x_start=x_start,
                num_carriers=num_carriers,
                font_size=bf,
                row_h=row_h,
            )

        # ── Premium Summary (bold, highlighted) ──
        self._add_section_divider_row("PREMIUM", num_carriers, label_col_w, carrier_col_w, x_start, bf)

        premium_row_h = row_h + 2
        y = self.get_y()
        self.set_font(self.font_family_name, "B", bf + 1)
        self.set_xy(x_start, y)
        self.set_fill_color(*BRAND["cream"])
        self.set_text_color(*BRAND["primary_dark"])
        self.cell(label_col_w, premium_row_h, "  Annual Premium", border=1, fill=True, align="L")

        for i, q in enumerate(quotes):
            x = x_start + label_col_w + i * carrier_col_w
            self.set_xy(x, y)
            is_best = (i == best_idx)
            if is_best:
                self.set_fill_color(*BRAND["best_value_bg"])
                self.set_text_color(*BRAND["best_value_border"])
            else:
                self.set_fill_color(*BRAND["cream"])
                self.set_text_color(*BRAND["primary_dark"])

            premium_str = self._fmt_currency(q.get("annual_premium"))
            if is_best:
                premium_str = f"★ {premium_str}"
            self.cell(carrier_col_w, premium_row_h, premium_str, border=1, fill=True, align="C")

        self.ln(premium_row_h)

        # Monthly row (if any carrier has it)
        monthly_values = [q.get("monthly_premium") for q in quotes]
        if any(v is not None for v in monthly_values):
            self._add_data_row(
                label="Monthly Premium",
                values=[self._fmt_currency(v) if v else "—" for v in monthly_values],
                row_idx=1,
                best_idx=best_idx,
                label_col_w=label_col_w,
                carrier_col_w=carrier_col_w,
                x_start=x_start,
                num_carriers=num_carriers,
                font_size=bf,
                row_h=row_h,
            )

    def add_endorsements_section(self, quotes: list[dict]):
        """List endorsements and discounts per carrier."""
        self.ln(4)
        self.add_section_title("Endorsements & Discounts")

        for q in quotes:
            carrier = q.get("carrier_name", "Carrier")
            endorsements = q.get("endorsements", [])
            discounts = q.get("discounts_applied", [])

            # Ensure room for carrier name + 2 lines before drawing
            self._ensure_space(18)

            # Carrier sub-header
            self.set_font(self.font_family_name, "B", 9)
            self.set_text_color(*BRAND["primary"])
            self.cell(0, 6, carrier)
            self.ln(6)

            if endorsements:
                self.set_font(self.font_family_name, "I", 7)
                self.set_text_color(*BRAND["text_medium"])
                self.cell(0, 4, "Endorsements:  " + ", ".join(endorsements))
                self.ln(4)
            else:
                self.set_font(self.font_family_name, "I", 7)
                self.set_text_color(*BRAND["text_light"])
                self.cell(0, 4, "No endorsements listed")
                self.ln(4)

            if discounts:
                self.set_font(self.font_family_name, "I", 7)
                self.set_text_color(*BRAND["text_medium"])
                self.cell(0, 4, "Discounts:  " + ", ".join(discounts))
                self.ln(4)

            self.ln(3)

    def add_notes_section(self, quotes: list[dict]):
        """Agent notes / extraction caveats per carrier."""
        notes_exist = any(q.get("notes") for q in quotes)
        if not notes_exist:
            return

        self.ln(2)
        self.add_section_title("Notes")

        for q in quotes:
            if q.get("notes"):
                self._ensure_space(10)
                self.set_font(self.font_family_name, "B", 8)
                self.set_text_color(*BRAND["primary"])
                self.cell(35, 5, q["carrier_name"] + ":")
                self.set_font(self.font_family_name, "", 7.5)
                self.set_text_color(*BRAND["text_dark"])
                self.multi_cell(0, 5, q["notes"])
                self.ln(1)

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────
    def _add_section_divider_row(self, title, num_carriers, label_w, carrier_w, x_start, font_size):
        """Dark mini-header to separate table sections."""
        self._ensure_space(8)
        y = self.get_y()
        total_w = label_w + num_carriers * carrier_w
        self.set_fill_color(*BRAND["primary_dark"])
        self.set_text_color(*BRAND["white"])
        self.set_font(self.font_family_name, "B", font_size - 1)
        self.set_xy(x_start, y)
        self.cell(total_w, 6, f"  {title}", border=1, fill=True, align="L")
        self.ln(6)

    def _add_data_row(self, label, values, row_idx, best_idx, label_col_w, carrier_col_w,
                      x_start, num_carriers, font_size, row_h):
        """Single data row with alternating background and best-value highlight."""
        self._ensure_space(row_h + 2)
        y = self.get_y()
        is_alt = row_idx % 2 == 0
        bg = BRAND["row_alt"] if is_alt else BRAND["row_white"]

        # Label cell
        self.set_fill_color(*bg)
        self.set_text_color(*BRAND["text_dark"])
        self.set_font(self.font_family_name, "", font_size)
        self.set_xy(x_start, y)
        self.cell(label_col_w, row_h, f"  {label}", border="LBR", fill=True, align="L")

        # Value cells
        for i in range(num_carriers):
            x = x_start + label_col_w + i * carrier_col_w
            self.set_xy(x, y)
            if i == best_idx:
                self.set_fill_color(*BRAND["best_value_bg"])
            else:
                self.set_fill_color(*bg)
            self.set_font(self.font_family_name, "", font_size)
            self.set_text_color(*BRAND["text_dark"])
            val = values[i] if i < len(values) else "—"
            self.cell(carrier_col_w, row_h, val, border="LBR", fill=True, align="C")

        self.ln(row_h)

    @staticmethod
    def _fmt_currency(value) -> str:
        if value is None:
            return "—"
        try:
            v = float(value)
            if v >= 1000:
                return f"${v:,.0f}"
            else:
                return f"${v:,.2f}"
        except (ValueError, TypeError):
            return str(value)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────
def generate_comparison_pdf(
    client_name: str,
    quotes: list[dict],
    output_path: str,
    logo_path: Optional[str] = None,
    date_str: Optional[str] = None,
) -> str:
    """
    Generate a branded comparison PDF. Automatically selects portrait
    or landscape based on carrier count (2–4 = portrait, 5–6 = landscape).

    Args:
        client_name: Client's full name
        quotes: List of InsuranceQuote-like dicts (2–6 items)
        output_path: Where to save the PDF
        logo_path: Path to agency logo PNG
        date_str: Override date string (default: today)

    Returns:
        The output_path for chaining
    """
    layout = _get_layout(len(quotes))

    pdf = SciotoComparisonPDF(logo_path=logo_path, orientation=layout["orientation"])
    pdf.alias_nb_pages()
    pdf.add_page()

    # Client info
    pdf.add_client_section(client_name, date_str)

    # Comparison table
    pdf.add_section_title("Coverage Comparison")
    pdf.add_comparison_table(quotes, layout)

    # Endorsements & Discounts
    pdf.add_endorsements_section(quotes)

    # Notes
    pdf.add_notes_section(quotes)

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pdf.output(output_path)
    return output_path


# ──────────────────────────────────────────────
# Demo — generates 3 PDFs: 2, 3, and 6 carriers
# ──────────────────────────────────────────────
if __name__ == "__main__":

    def _make_carrier(name, policy, premium, deductible, wind_hail=None,
                      dwelling=325000, liability=300000, med=5000,
                      endorsements=None, discounts=None, notes=None):
        return {
            "carrier_name": name,
            "policy_type": policy,
            "annual_premium": premium,
            "monthly_premium": round(premium / 12, 2),
            "deductible": deductible,
            "wind_hail_deductible": wind_hail,
            "coverage_limits": {
                "dwelling": dwelling,
                "other_structures": round(dwelling * 0.10),
                "personal_property": round(dwelling * 0.50),
                "loss_of_use": round(dwelling * 0.20),
                "personal_liability": liability,
                "medical_payments": med,
            },
            "endorsements": endorsements or [],
            "discounts_applied": discounts or [],
            "notes": notes,
        }

    # Base carriers
    erie = _make_carrier(
        "Erie Insurance", "HO3", 1847, 1000, wind_hail=2500,
        endorsements=["Water Backup ($10K)", "Equipment Breakdown", "Identity Recovery"],
        discounts=["Multi-Policy", "Home Buyer", "Protective Devices", "Claims Free (5yr)"],
        notes="Includes ErieSecure Home bundle. 3% auto discount also available.",
    )
    state_auto = _make_carrier(
        "State Auto", "HO5", 2134, 1000, liability=300000, med=5000,
        dwelling=325000,
        endorsements=["Water Backup ($15K)", "Replacement Cost on Contents", "Scheduled Jewelry ($8K)"],
        discounts=["Multi-Policy", "New Home", "Loyalty (3yr)"],
        notes="HO5 open-peril on personal property. Higher loss of use limit.",
    )
    westfield = _make_carrier(
        "Westfield", "HO3", 1695, 2500, wind_hail=2500,
        liability=100000, med=1000,
        endorsements=["Water Backup ($5K)"],
        discounts=["Multi-Policy", "Protective Devices"],
        notes="Lowest premium but higher deductible and lower liability.",
    )
    central_mutual = _make_carrier(
        "Central Mutual", "HO3", 1920, 1000,
        endorsements=["Water Backup ($10K)", "Scheduled Jewelry ($5K)"],
        discounts=["Multi-Policy", "New Roof"],
    )
    encova = _make_carrier(
        "Encova Insurance", "HO3", 2015, 1000, wind_hail=1000,
        liability=500000, med=5000,
        endorsements=["Water Backup ($25K)", "Equipment Breakdown", "Home Business ($10K)"],
        discounts=["Multi-Policy", "Smart Home", "Claims Free (3yr)"],
        notes="Higher liability limit included. Strong water backup coverage.",
    )
    grange = _make_carrier(
        "Grange Insurance", "HO3", 1775, 1000, wind_hail=2500,
        endorsements=["Water Backup ($10K)", "Identity Theft"],
        discounts=["Multi-Policy", "Protective Devices", "Loyalty (5yr)"],
    )

    # ── 2-carrier PDF (portrait, wide columns) ──
    generate_comparison_pdf(
        client_name="Martinez Family",
        quotes=[erie, westfield],
        output_path="/home/claude/output_2_carriers.pdf",
        logo_path="/home/claude/logo_rgb.png",
    )
    print("✓ 2-carrier PDF generated")

    # ── 3-carrier PDF (portrait, standard) ──
    generate_comparison_pdf(
        client_name="Johnson Family",
        quotes=[erie, state_auto, westfield],
        output_path="/home/claude/output_3_carriers.pdf",
        logo_path="/home/claude/logo_rgb.png",
    )
    print("✓ 3-carrier PDF generated")

    # ── 6-carrier PDF (landscape, tight) ──
    generate_comparison_pdf(
        client_name="Thompson Family",
        quotes=[erie, state_auto, westfield, central_mutual, encova, grange],
        output_path="/home/claude/output_6_carriers.pdf",
        logo_path="/home/claude/logo_rgb.png",
    )
    print("✓ 6-carrier PDF generated")
