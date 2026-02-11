# Starter Files Reference — Copy These Into the Project

> **This file contains the exact contents of configuration files and the HTML template that Claude Code should create verbatim.**

---

## File: requirements.txt

```
streamlit>=1.41.0
gspread>=6.2.0
gspread-formatting>=1.2.0
google-auth>=2.36.0
pymupdf4llm>=0.0.17
google-generativeai>=0.8.0
openai>=1.0.0
python-dotenv>=1.0.1
pydantic>=2.10.0
jinja2>=3.1.5
fpdf2>=2.8.0
weasyprint>=62.0  # Remove this line if Windows install fails
json-repair>=0.30.0
sentry-sdk>=2.19.0  # Optional: error tracking
```

---

## File: .env.example

```
# === REQUIRED ===
GEMINI_API_KEY=your-gemini-api-key-here
GOOGLE_SERVICE_ACCOUNT_FILE=./secrets/service_account.json
SPREADSHEET_ID=your-google-spreadsheet-id-here

# === OPTIONAL ===
OPENAI_API_KEY=your-openai-api-key-here
AGENCY_NAME=Your Insurance Agency
AGENCY_PHONE=(614) 555-0100
AGENCY_LICENSE=OH-1234567
MAX_UPLOAD_FILES=6
LOG_LEVEL=INFO
```

---

## File: .gitignore

```
# Environment and secrets
.env
secrets/
service_account.json

# Data directories (contain PII)
data/uploads/
data/outputs/
data/logs/

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

---

## File: run.bat (Windows Launcher)

```batch
@echo off
echo Starting Insurance Quote Comparison Tool...
cd /d "%~dp0"
call .venv\Scripts\activate 2>nul || call venv\Scripts\activate 2>nul || echo No virtual environment found, using system Python
streamlit run app/main.py --server.port 8501
pause
```

---

## File: app/pdf_gen/templates/comparison.html

This is the complete Jinja2 HTML template for branded PDF generation. Claude Code should create this file exactly.

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Insurance Quote Comparison — {{ client_name }}</title>
<style>
  /* === PAGE SETUP === */
  @page {
    size: letter;
    margin: 0.75in;
    @bottom-center {
      content: "Page " counter(page) " of " counter(pages);
      font-size: 9px;
      color: #666;
    }
  }

  /* === BASE STYLES === */
  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 11px;
    line-height: 1.4;
    color: #333;
  }

  /* === HEADER === */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 12px;
    border-bottom: 3px solid #2c5aa0;
    margin-bottom: 20px;
  }

  .agency-name {
    font-size: 20px;
    font-weight: 700;
    color: #2c5aa0;
  }

  .agency-contact {
    font-size: 10px;
    color: #555;
    text-align: right;
  }

  /* === CLIENT INFO === */
  .client-info {
    margin-bottom: 16px;
  }

  .client-info h2 {
    font-size: 14px;
    color: #2c5aa0;
    margin-bottom: 4px;
  }

  .client-info .date {
    font-size: 10px;
    color: #666;
  }

  /* === COMPARISON TABLE === */
  table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
  }

  th {
    background-color: #2c5aa0;
    color: white;
    padding: 8px 10px;
    text-align: left;
    font-weight: 600;
    font-size: 11px;
  }

  th:first-child {
    width: 160px;
  }

  td {
    padding: 6px 10px;
    border-bottom: 1px solid #dee2e6;
    font-size: 11px;
  }

  /* Alternating rows */
  tr:nth-child(even) td {
    background-color: #f8f9fa;
  }

  /* Row label column */
  td:first-child {
    font-weight: 600;
    color: #444;
  }

  /* Best value highlight */
  .best-value {
    background-color: #d4edda !important;
    font-weight: 700;
  }

  /* Premium summary row */
  .premium-row td {
    font-size: 13px;
    font-weight: 700;
    border-top: 2px solid #2c5aa0;
    border-bottom: 2px solid #2c5aa0;
    padding: 10px;
  }

  /* === ENDORSEMENTS SECTION === */
  .endorsements-section {
    margin-top: 16px;
    page-break-inside: avoid;
  }

  .endorsements-section h3 {
    font-size: 12px;
    color: #2c5aa0;
    margin-bottom: 8px;
    border-bottom: 1px solid #dee2e6;
    padding-bottom: 4px;
  }

  .endorsement-list {
    font-size: 10px;
    color: #555;
    margin-bottom: 12px;
  }

  .endorsement-list strong {
    color: #333;
  }

  /* === FOOTER === */
  .footer {
    margin-top: 30px;
    padding-top: 12px;
    border-top: 1px solid #dee2e6;
    font-size: 9px;
    color: #888;
  }

  .disclaimer {
    margin-top: 4px;
    font-style: italic;
  }
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div>
    {% if logo_path %}
    <img src="{{ logo_path }}" alt="Agency Logo" style="height: 40px; margin-bottom: 4px;"><br>
    {% endif %}
    <span class="agency-name">{{ agency_name }}</span>
  </div>
  <div class="agency-contact">
    {% if agency_phone %}{{ agency_phone }}<br>{% endif %}
    {% if agency_license %}License: {{ agency_license }}{% endif %}
  </div>
</div>

<!-- CLIENT INFO -->
<div class="client-info">
  <h2>Quote Comparison for {{ client_name }}</h2>
  <span class="date">Prepared {{ date }}</span>
</div>

<!-- COMPARISON TABLE -->
<table>
  <thead>
    <tr>
      <th>Coverage</th>
      {% for quote in quotes %}
      <th>{{ quote.carrier_name }}</th>
      {% endfor %}
    </tr>
  </thead>
  <tbody>
    <!-- Policy Type -->
    <tr>
      <td>Policy Type</td>
      {% for quote in quotes %}
      <td>{{ quote.policy_type }}</td>
      {% endfor %}
    </tr>

    <!-- Effective Date -->
    <tr>
      <td>Effective Date</td>
      {% for quote in quotes %}
      <td>{{ quote.effective_date or "—" }}</td>
      {% endfor %}
    </tr>

    <!-- Deductible -->
    <tr>
      <td>Deductible</td>
      {% for quote in quotes %}
      <td>${{ "{:,.0f}".format(quote.deductible) }}</td>
      {% endfor %}
    </tr>

    {% if quotes[0].wind_hail_deductible %}
    <tr>
      <td>Wind/Hail Deductible</td>
      {% for quote in quotes %}
      <td>{{ "${:,.0f}".format(quote.wind_hail_deductible) if quote.wind_hail_deductible else "—" }}</td>
      {% endfor %}
    </tr>
    {% endif %}

    <!-- Coverage Limits -->
    {% set coverage_labels = {
      "dwelling": "Dwelling (A)",
      "other_structures": "Other Structures (B)",
      "personal_property": "Personal Property (C)",
      "loss_of_use": "Loss of Use (D)",
      "personal_liability": "Personal Liability (E)",
      "medical_payments": "Medical Payments (F)",
      "bi_per_person": "BI Per Person",
      "bi_per_accident": "BI Per Accident",
      "pd_per_accident": "PD Per Accident",
      "um_uim": "UM/UIM",
      "comprehensive": "Comprehensive Ded",
      "collision": "Collision Ded",
      "building": "Building",
      "bpp": "Business Personal Property",
      "general_liability": "General Liability",
      "business_income": "Business Income"
    } %}

    {% set all_coverage_keys = [] %}
    {% for quote in quotes %}
      {% for key in quote.coverage_limits.keys() %}
        {% if key not in all_coverage_keys %}
          {% set _ = all_coverage_keys.append(key) %}
        {% endif %}
      {% endfor %}
    {% endfor %}

    {% for key in all_coverage_keys %}
    <tr>
      <td>{{ coverage_labels.get(key, key | replace("_", " ") | title) }}</td>
      {% for quote in quotes %}
      <td>{{ "${:,.0f}".format(quote.coverage_limits.get(key, 0)) if quote.coverage_limits.get(key) else "—" }}</td>
      {% endfor %}
    </tr>
    {% endfor %}

    <!-- PREMIUM ROW -->
    <tr class="premium-row">
      <td>Annual Premium</td>
      {% for quote in quotes %}
      <td class="{{ 'best-value' if loop.index0 == best_premium_index else '' }}">
        ${{ "{:,.2f}".format(quote.annual_premium) }}
      </td>
      {% endfor %}
    </tr>
  </tbody>
</table>

<!-- ENDORSEMENTS -->
{% set has_endorsements = false %}
{% for quote in quotes %}
  {% if quote.endorsements %}{% set has_endorsements = true %}{% endif %}
{% endfor %}

{% if has_endorsements %}
<div class="endorsements-section">
  <h3>Endorsements Included</h3>
  {% for quote in quotes %}
  {% if quote.endorsements %}
  <div class="endorsement-list">
    <strong>{{ quote.carrier_name }}:</strong>
    {{ quote.endorsements | join(", ") }}
  </div>
  {% endif %}
  {% endfor %}
</div>
{% endif %}

<!-- DISCOUNTS -->
{% set has_discounts = false %}
{% for quote in quotes %}
  {% if quote.discounts_applied %}{% set has_discounts = true %}{% endif %}
{% endfor %}

{% if has_discounts %}
<div class="endorsements-section">
  <h3>Discounts Applied</h3>
  {% for quote in quotes %}
  {% if quote.discounts_applied %}
  <div class="endorsement-list">
    <strong>{{ quote.carrier_name }}:</strong>
    {{ quote.discounts_applied | join(", ") }}
  </div>
  {% endif %}
  {% endfor %}
</div>
{% endif %}

<!-- FOOTER -->
<div class="footer">
  {{ agency_name }}{% if agency_license %} | License: {{ agency_license }}{% endif %}
  <div class="disclaimer">
    This comparison is for informational purposes only and does not constitute a binding offer of insurance.
    Coverage details, terms, and conditions should be verified directly with each carrier.
    Premiums shown are estimates and may vary based on underwriting review.
  </div>
</div>

</body>
</html>
```

---

## Google Sheets Template Layout

Create this manually in Google Sheets before running the tool. Name the worksheet "Template".

```
Row 1: [Merged header] "Insurance Quote Comparison" — bold, navy background, white text
Row 2: [Labels] | Coverage | (carrier columns start at B2) |

Row 3:  Carrier Name
Row 4:  Policy Type
Row 5:  Effective Date
Row 6:  Annual Premium        ← Bold, currency format ($#,##0.00)
Row 7:  Monthly Premium       ← Currency format
Row 8:  Deductible            ← Currency format
Row 9:  Wind/Hail Deductible  ← Currency format
Row 10: Dwelling (A)          ← Currency format ($#,##0)
Row 11: Other Structures (B)
Row 12: Personal Property (C)
Row 13: Loss of Use (D)
Row 14: Personal Liability (E)
Row 15: Medical Payments (F)
Row 16: Endorsements          ← Text wrap
Row 17: Exclusions            ← Text wrap
Row 18: Discounts Applied     ← Text wrap
Row 19: Confidence Level

Formatting:
- Column A: 180px wide, left-aligned, bold labels, light gray background (#f2f2f2)
- Columns B-G: 140px wide, center-aligned
- Row 1: Merged B1:G1, navy background (#2c5aa0), white text, 14pt bold
- Row 6 (Premium): Bold text, bottom border
- Alternating row colors on data rows
- Conditional formatting on Row 6: lowest value gets green background (#d4edda)
```
