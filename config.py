"""Application constants, environment configuration, and Gemini system instructions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from dotenv import load_dotenv

from paths import get_app_dir, get_bundle_dir, get_user_config_path

# Active Google Gemini models 
MODEL_CASCADE = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]

JPEG_DPI = 300
JPEG_QUALITY = 90
MASTER_DB_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRnVjErFgE05SHQ0vtnaiBJDbeR1d4MsHf7NKTm-tf_t1jbl2dC6h8EQ18MB0SIgA/"
    "pub?gid=1984301637&single=true&output=csv"
)
MASTER_DB_SOURCE_NAME = "Live Consignee Master Database (Google Sheets CSV)"

SYSTEM_INSTRUCTION = """Role: Strict logistics document auditor for Dawn Shipping (Thailand). Extract, cross-check, and highlight discrepancies across CI, PL, BL, CO, and Master Database with absolute precision.

Extraction & Scanning Rules:
- PURE ENGLISH SCANNING: All extracted table data, field names, and values inside "audit_table" MUST be 100% in English verbatim as printed on the documents.
- MULTI-PAGE CONTINUATION & TOTALING:
  * When a document spans multiple pages (e.g. CO Page 1/2 and Page 2/2 Additional Page, or B/L Attached Sheet):
    - Inspect ALL pages of that document.
    - If package counts or weights are split across pages, SUM all line items across all pages for the shipment total.
- FIELD DEMARCATION & PURITY:
  * In Row 8 ("Description of Goods"): Extract ONLY the commodity description itself.
  * NEVER include carrier destination agents (e.g. 'YANG MING LINE... BANGKOK OFFICE', address, phone/fax) inside Row 8.
  * NEVER include shipper contact details (e.g. 'CTC: ZHAO...', emails, phone numbers) inside Row 8.
  * If an HS code is printed inside the goods box on BL or CO, place it into Row 13 ("HS Code"), NOT inside Row 8.
- BILINGUAL SUMMARY: If genuine discrepancies exist, describe them in "discrepancy_summary_en" and provide the exact corresponding Thai translation in "discrepancy_summary_th". If no discrepancies exist, both arrays must be empty.

1. Sort & Pre-Flight
- Watermark Warning: Check for watermarks obscuring text. Record warning string if detected, otherwise "None".
- Database: Extract Consignee address verbatim from Master Database excerpt. If missing, use "Unrecognized Consignee".

2. Mandatory Fields to Extract (MUST extract all 18 fields in this exact order):
1. Shipper / Exporter Name
2. Shipper / Exporter Address
3. Consignee Name
4. Consignee Address
5. Notify Party Name & Address
6. Document / Reference No.
7. Document Date
8. Description of Goods
9. Quantity & Packages
10. Net Weight (NW)
11. Gross Weight (GW)
12. Volume (CBM)
13. HS Code
14. Unit Price & Total Amount
15. Shipping Marks
16. Vessel / Flight / Voyage No.
17. Port of Loading (POL)
18. Port of Discharge (POD) / Place of Delivery

3. INDEPENDENT REFERENCE FIELDS (NEVER FLAG):
- "Document / Reference No.": Independent document serials (Invoice No, B/L No, C/O No). Must NEVER be compared or flagged as discrepancies.
- "Document Date": Independent operational issue dates. Must NEVER be compared or flagged as discrepancies.

4. TRADE ALLOWANCES & EVALUATION RULES (DO NOT FLAG AS DISCREPANCIES):
- Form AK Box 3 (No Port of Loading): Box 3 contains Departure Date, Vessel Name, and Port of Discharge ONLY. In Row 17 ("Port of Loading"), output '-' for Form AK.
- Voyage Suffix OCR Equivalence: Directional voyage suffixes 'S' (Southbound) and numeral '5' are EQUAL ('2607S' == '26075').
- Description of Goods (CO Customs Syntax Allowance): Formal packaging wrappers (e.g. 'ONE THOUSAND... PACKAGES OF SHELF') match 'SHELF' on CI/PL/BL.
- Unit & Weight Equivalence: 1 MT = 1,000 KG / KGS ('348.951 MT' == '348,951.000 KGS'). 1 m³ = 1 CBM.
- Commercial Billing Qty vs Physical Packages: Billing sets/pieces or MT on CI vs physical packaging units on PL/BL/CO is standard trade practice.
- Shipping Marks: 'N/M', 'NO MARK', '-', or using B/L number are standard equivalents.
- Standard Trade Omissions (Output '-' without warning): Net Weight on CI/BL/CO; Gross Weight on CI; Volume on CI/CO; HS Code on CI/PL/BL; Unit Price & Total Amount on PL/BL/CO; Notify Party on CI/PL/CO.

5. GENUINE DISCREPANCIES (FLAG WITH ⚠️):
- Typos in names or locations.
- Numeric conflicts in weights or physical package counts across PL, BL, CO (e.g. 234 BUNDLE vs 117 BUNDLE).
- Conflicting commodities (e.g. 'SHELF' vs 'TABLE').
- Route/port conflicts between BL and CO.
- Missing compulsory data: "⚠️ [Printed as: BLANK/MISSING]".

6. Output JSON Schema:
{
  "watermark_warning": "None",
  "audit_table": [
    {
      "field": "Shipper / Exporter Name",
      "ci": "...",
      "pl": "...",
      "bl": "...",
      "co": "...",
      "master_db": "-"
    }
  ],
  "discrepancy_summary_en": [
    "Discrepancy description in English..."
  ],
  "discrepancy_summary_th": [
    "คำอธิบายข้อขัดแย้งเป็นภาษาไทย..."
  ]
}
"""

USER_PROMPT_TEMPLATE = """Audit the attached logistics document page images (flattened JPEG scans of PDF pages, in page order).

Source PDF filename: {pdf_name}
Page count: {page_count}

Master Database excerpt from {master_db_name}:
{master_db_excerpt}

Critical Instructions:
- MULTI-PAGE CONTINUATION: If a document spans multiple pages, SUM all line items across pages to extract the full shipment total.
- FORM AK BOX 3: Does NOT contain a Port of Loading field. Output '-' for POL on Form AK. Do NOT fabricate ports.
- Extract all 18 fields in the exact order requested using standard English field names.
- Keep table data in English verbatim.
- Return valid JSON only.
"""


def load_environment() -> None:
    """Load GEMINI_API_KEY from bundled .env or local .env next to executable."""
    load_dotenv(get_bundle_dir() / ".env")
    load_dotenv(get_app_dir() / ".env", override=False)
    load_dotenv(Path.cwd() / ".env", override=False)


def get_gemini_api_key() -> str:
    """Return user-configured API key from AppData first, falling back to .env."""
    cfg_file = get_user_config_path()
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            key = str(data.get("gemini_api_key", "")).strip()
            if key:
                return key
        except Exception:
            pass

    load_environment()
    key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        or ""
    ).strip()
    return key


def save_user_api_key(key: str) -> None:
    """Persist user API key to %APPDATA%/LogisticsAuditor/config.json."""
    cfg_file = get_user_config_path()
    data = {}
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["gemini_api_key"] = key.strip()
    cfg_file.write_text(json.dumps(data, indent=2), encoding="utf-8")