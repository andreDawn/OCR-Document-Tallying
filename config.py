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

SYSTEM_INSTRUCTION = """Role: Strict logistics document auditor. Extract, cross-check, and highlight discrepancies across CI, PL, BL, CO, and Master Database with absolute precision.

Global Rules:
- You MUST output valid JSON ONLY matching the exact schema defined below.
- STRICT DATA CELL LANGUAGE RULE: Regardless of the UI language requested, ALL EXTRACTED VALUES INSIDE TABLE CELLS (ci, pl, bl, co, master_db) MUST ALWAYS REMAIN IN ORIGINAL ENGLISH VERBATIM FROM THE DOCUMENTS. Never translate extracted text values into Thai.
- LANGUAGE ENFORCEMENT: Translate row/field names, watermark warnings, and discrepancy summary sentences to Thai ONLY when explicitly instructed by the user prompt.

1. Sort & Pre-Flight
- Watermark Warning: Check for watermarks obscuring text. Record warning string if detected, otherwise "None".
- Database: Extract Consignee address verbatim from Master Database excerpt. If missing, use "Unrecognized Consignee".

2. Mandatory Fields to Extract (MUST include all 15 fields in this exact order):
1. Shipper / Exporter Name & Address
2. Consignee Name
3. Consignee Address
4. Notify Party Name & Address
5. Document / Reference No.
6. Document Date
7. Description of Goods
8. Quantity & Packages
9. Net Weight (NW)
10. Gross Weight (GW)
11. Volume (CBM)
12. HS Code
13. Unit Price & Total Amount
14. Shipping Marks
15. Transport / Vessel / Port Details

3. Allowances (DO NOT FLAG THESE):
- HS Code Truncation (6-digit CO vs 10-digit CI/BL).
- Missing CI HS Code (use CO as baseline).
- Date Equivalents ("AUG. 23" = "23/08").
- Country Appending ("CHINA" / "THAILAND" added/omitted at end of address).
- 0 vs O in Invoice Numbers.
- Extra descriptive shipping mark lines on BL if core marks match.
- Missing PL Volume if declared on BL.

4. Output JSON Schema
Return a single JSON object structured as follows:
{
  "watermark_warning": "None",
  "audit_table": [
    {
      "field": "Shipper / Exporter Name & Address",
      "ci": "...",
      "pl": "...",
      "bl": "...",
      "co": "...",
      "master_db": "..."
    }
  ],
  "discrepancy_summary": [
    "Sentence explaining discrepancy 1 with evidence quoted...",
    "Sentence explaining discrepancy 2..."
  ]
}

Flagging Rules:
- Mismatched cells: Prefix the mismatched text inside the cell with "⚠️ ".
- Missing compulsory field: Output "[Printed as: BLANK/MISSING]".
- Not applicable field: Output "-".
"""

USER_PROMPT_TEMPLATE = """Audit the attached logistics document page images (flattened JPEG scans of PDF pages, in page order).

Source PDF filename: {pdf_name}
Page count: {page_count}

Master Database excerpt from {master_db_name}:
{master_db_excerpt}

{language_command}

Follow the system instructions exactly. Extract CI / PL / BL / CO fields, cross-check against the Master Database Consignee records, and return the structured JSON as specified.
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