"""Application constants, environment configuration, and Gemini system instructions."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from paths import get_app_dir, get_bundle_dir

MODEL_CASCADE = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
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

Global Rules:
- You MUST output valid JSON ONLY matching the exact schema defined below.
- STRICT DATA CELL LANGUAGE RULE: Regardless of UI language requested, ALL EXTRACTED VALUES INSIDE TABLE CELLS (ci, pl, bl, co, master_db) MUST ALWAYS REMAIN IN ORIGINAL ENGLISH VERBATIM FROM THE DOCUMENTS. Never translate extracted text values into Thai.
- LANGUAGE ENFORCEMENT: Translate row/field names, watermark warnings, and discrepancy summary sentences to Thai ONLY when explicitly instructed by the user prompt.

1. Sort & Pre-Flight
- Watermark Warning: Check for watermarks obscuring text. Record warning string if detected, otherwise "None".
- Database: Extract Consignee address verbatim from Master Database excerpt. If missing, use "Unrecognized Consignee".

2. Mandatory Fields to Extract (MUST include all 18 fields in this exact order):
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

3. Allowances (DO NOT FLAG THESE AS DISCREPANCIES):
- Unit Price & Total Amount omitted on PL, BL, and CO (standard international shipping confidentiality; if CI has it and others show "-", this is NORMAL).
- HS Code Truncation (6-digit CO vs 10-digit CI/BL).
- Missing CI HS Code (use CO as baseline).
- Date Equivalents ("AUG. 23" = "23/08" = "2026.08.23").
- Country Appending ("CHINA" / "THAILAND" added or omitted at end of address).
- 0 vs O in Invoice Numbers.
- Extra descriptive shipping mark lines on BL if core marks match.
- Missing PL Volume if declared on BL.

# Insert/Update these rules inside SYSTEM_INSTRUCTION in config.py:

4. TRADE ALLOWANCES & UNIT CONVENTIONS (DO NOT FLAG AS DISCREPANCIES):
- Header Unit Inheritance (CRITICAL):
  * When a document table places the unit of measure in the column or row header rather than inside the cell (e.g. Header is 'Net weight kg', 'Gross weight kg', 'Total volume m³', 'GW (KGS)', 'CBM'), you MUST synthesize the header unit with the cell number.
  * Example: Cell shows '54' under column 'Net weight kg' -> Extract as '54 KGS'.
  * Example: Cell shows '0.7' under column 'Total volume m³' -> Extract as '0.700 CBM' (or '0.7 CBM').
  * NEVER extract bare numbers without units if the unit is declared in the table header.

- Package Method & Count Combination:
  * If a document splits the package description and package number into separate columns (e.g. Column 'Packing method: pallet' and Column 'Packing number: 1'), combine them into one string: '1 PALLET' (or '1 PALLET / 1 PKG').

- Metric & Unit Equivalences:
  * 1 m³ = 1 CBM (Cubic Meter). '0.7 m³' on PL and '0.700 CBM' on BL are 100% EQUAL and MATCHING.
  * 1 kg = 1 KG = 1 KGS. '54 kg' and '54 KGS' are 100% EQUAL and MATCHING.
  * Numbers matching with or without trailing zeros are EQUAL (67 = 67.000; 0.7 = 0.700).
  * Shorthand counts or package references (e.g. '1 PALLET' on PL vs '1 PACKAGE' on BL) describing the same single physical cargo unit are MATCHING.

- Commercial Invoicing vs Physical Packages:
  * Commercial Invoice stating billing weight ('54KGS') in the Quantity column while PL/BL declare physical handling units ('1 PALLET', '1 PACKAGE') is standard international trade practice. Consider them MATCHING.

5. WHAT CONSTITUTES A REAL DISCREPANCY (FLAG WITH "⚠️ "):
- Genuine typos in names, addresses, or locations (e.g. "CIINA" vs "CHINA").
- Numeric conflicts in weights or quantities (e.g. 67 KGS on PL vs 120 KGS on BL).
- Conflicting commodity descriptions (e.g. "CONVEYOR BELT" vs "STEEL PIPES").
- Conflicting discharge ports or routing between BL and CO.
- Missing compulsory data on a document where legally mandated (e.g. Gross Weight missing from BL, or Consignee Name missing anywhere). ONLY in these mandatory violations output: "⚠️ [Printed as: BLANK/MISSING]".

6. MANDATORY CELL FLAGGING RULES:
- If and ONLY if a genuine discrepancy is listed in "discrepancy_summary", prefix the offending cell(s) in "audit_table" with "⚠️ ".
- If an item falls under Section 4 Allowances, DO NOT include it in "discrepancy_summary" and DO NOT prefix the cell with "⚠️ ".

7. Output JSON Schema
Return a single JSON object:
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
  "discrepancy_summary": [
    "Sentence explaining only real, genuine discrepancies..."
  ]
}
"""

USER_PROMPT_TEMPLATE = """Audit the attached logistics document page images (flattened JPEG scans of PDF pages, in page order).

Source PDF filename: {pdf_name}
Page count: {page_count}

Master Database excerpt from {master_db_name}:
{master_db_excerpt}

{language_command}

Follow the system instructions exactly:
- Extract all 18 fields in the exact order requested.
- Ensure any document with a discrepancy or typo has its cell text prefixed with "⚠️ ".
- Return the structured JSON as specified.
"""


def load_environment() -> None:
    """Load GEMINI_API_KEY from bundled .env or local .env next to executable."""
    load_dotenv(get_bundle_dir() / ".env")
    load_dotenv(get_app_dir() / ".env", override=False)
    load_dotenv(Path.cwd() / ".env", override=False)


def get_gemini_api_key() -> str:
    """Return the Gemini API key or raise RuntimeError if missing."""
    load_environment()
    key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        or ""
    ).strip()
    if not key:
        raise RuntimeError(
            "Gemini API key not found. Ensure a .env file with "
            "GEMINI_API_KEY=your_key is placed next to the application."
        )
    return key