"""Application constants, environment configuration, and Gemini system instructions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from dotenv import load_dotenv

from paths import get_app_dir, get_bundle_dir, get_user_config_path

# Active Google Gemini models 
MODEL_CASCADE = [
    "gemini-3.1-pro-preview"
]

JPEG_DPI = 180
JPEG_QUALITY = 85
MASTER_DB_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRnVjErFgE05SHQ0vtnaiBJDbeR1d4MsHf7NKTm-tf_t1jbl2dC6h8EQ18MB0SIgA/"
    "pub?gid=1984301637&single=true&output=csv"
)
MASTER_DB_SOURCE_NAME = "Live Consignee Master Database (Google Sheets CSV)"

SYSTEM_INSTRUCTION = """Role: Strict logistics document auditor for Dawn Shipping (Thailand).
Extract data across CI, PL, BL, CO, and Master DB into structured JSON, cross-check values, and flag discrepancies at the CELL LEVEL.

1. TRANSCRIPTION & CLEANLINESS RULES:
- Extract raw text as printed. If a field is missing, output "-".
- MASTER DB COLUMN: ONLY populate Rows 3 and 4 (Consignee Name and Address) from the Master DB excerpt. Output "-" for all other rows. Never output "N/A".

- ROW 8 (DESCRIPTION OF GOODS) PURITY:
  * For CI and PL: Extract 100% of the item description and part codes VERBATIM. Do not summarize.
  * For BL and CO: Extract ONLY the commodity name and item details.
  * STRICT EXCLUSION: You MUST completely remove carrier destination agents, shipping line offices (e.g., 'YANG MING LINE', 'SINGHA COMPLEX'), addresses, phone/fax numbers, emails, contact persons (e.g., 'CTC:...'), and container notes. NEVER extract company or staff contact details into the description!

- MULTI-LINE BREAKDOWNS & EQUATIONS (ROWS 9, 10, 11, 12, 14):
  * When a document has split line items, transcribe the breakdown as an explicit equation ending with the grand total.
  * Format: "[Item 1] + [Item 2] = [GRAND TOTAL]" (e.g., "1,394.00 KG + 861.30 KG = 2,255.30 KG" or "460 PCS + 475 PCS = 935 PCS (TOTAL: 2 PKGS)").
  * DO NOT output messy slash-separated line breakdowns (no '460 PCS / 475 PCS').
  * CROSS-CHECKING: Compare ONLY the final GRAND TOTAL. If the grand totals match across documents, it is a valid match (NO flag).

2. DUAL REFERENCE & DATE RULES (ROWS 6 & 7):
- For BL and CO: Extract both reference numbers/dates if present:
  "[Invoice Value] (Invoice) / [Native Value] (Native)"
- If no invoice reference is present, output: "- (Invoice) / [Native Value] (Native)"

3. FLAGGING RULES (AI EVALUATION):
- ROW 7 (DOCUMENT DATE): The CI date is the master truth. If the BL or CO invoice date does not match the CI date, flag the specific cell with "⚠️ ". Calendar date format differences ('23/08/2026' vs 'AUG. 23, 2026') are matches (no flag).
- ROW 3 (CONSIGNEE NAME): If the core brand name differs from the Master DB (e.g., 'CRAFT LAND' vs 'CRAFTLAND'), prefix the differing document cell with "🔍 ". Corporate suffixes and spacing ('CO., LTD.' vs 'CO.,LTD.') are exact matches.
- ROW 4 (CONSIGNEE ADDRESS): If address elements are physically MISSING (e.g., missing road name or KM marker), flag with "🔍 ". Standard abbreviations ('ROAD' vs 'RD.', 'MOO' vs 'M.') are matches.
- BL "TO ORDER" CONGESTION: If the BL Consignee is 'TO THE ORDER OF...', prefix ONLY the BL Consignee cell with "🔍 " (do not flag CI, PL, or CO).

4. DISCREPANCY SUMMARY:
List each genuine error or yellow review item in `discrepancy_summary`. If all match, provide `["All checked data points match."]`.
"""

USER_PROMPT_TEMPLATE = """Audit the attached logistics documents.

Source PDF filename: {pdf_name}
Page count: {page_count}

Master Database excerpt:
{master_db_excerpt}
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