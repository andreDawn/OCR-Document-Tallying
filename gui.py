"""Tkinter desktop UI: 18-field deterministic auditing, live bilingual toggling, and auto-updater."""

from __future__ import annotations

import json
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, messagebox, ttk
import tkinter as tk

from gemini_client import extract_from_jpegs, save_markdown
from master_db import load_master_database_excerpt
from paths import job_output_dir
from pdf_processor import flatten_pdf_to_jpegs
from updater import apply_update_and_restart, check_for_updates
from version import get_current_version

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    HAS_DND = True
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    HAS_DND = False

FIELD_DEFINITIONS = [
    ("shipper_address",   r"(shipper|exporter).*addr|ที่อยู่.*ผู้ส่ง",
     "2. Shipper / Exporter Address", "2. ที่อยู่ผู้ส่งสินค้า (Shipper Address)"),
    ("shipper_name",      r"shipper|exporter|ผู้ส่ง",
     "1. Shipper / Exporter Name", "1. ชื่อผู้ส่งสินค้า (Shipper Name)"),
    ("consignee_address", r"consignee.*addr|ที่อยู่.*ผู้รับ",
     "4. Consignee Address", "4. ที่อยู่ผู้รับตราส่ง (Consignee Address)"),
    ("consignee_name",    r"consignee|ผู้รับ(?!แจ้ง)",
     "3. Consignee Name", "3. ชื่อผู้รับตราส่ง (Consignee Name)"),
    ("notify",            r"notify|ผู้รับแจ้ง",
     "5. Notify Party Name & Address", "5. ผู้รับแจ้ง (Notify Party)"),
    ("date",              r"\bdate\b|วันที่",
     "7. Document Date", "7. วันที่เอกสาร (Doc Date)"),
    ("document",          r"doc|reference|invoice|เลขที่|อ้างอิง",
     "6. Document / Reference No.", "6. เลขที่เอกสารอ้างอิง (Doc No.)"),
    ("description",       r"desc|goods|รายละเอียด|รายการสินค้า|สินค้า",
     "8. Description of Goods", "8. รายการสินค้า (Description of Goods)"),
    ("quantity",          r"quant|pack|จำนวน|หีบห่อ",
     "9. Quantity & Packages", "9. จำนวนและลักษณะหีบห่อ (Qty & Packages)"),
    ("net_weight",        r"net\s*weight|\bnw\b|น้ำหนักสุทธิ",
     "10. Net Weight (NW)", "10. น้ำหนักสุทธิ (Net Weight - NW)"),
    ("gross_weight",      r"gross\s*weight|\bgw\b|น้ำหนักรวม",
     "11. Gross Weight (GW)", "11. น้ำหนักรวม (Gross Weight - GW)"),
    ("volume",            r"volume|cbm|ปริมาตร",
     "12. Volume (CBM)", "12. ปริมาตรสินค้า (Volume - CBM)"),
    ("hs_code",           r"hs\s*code|พิกัด|รหัส\s*hs",
     "13. HS Code", "13. พิกัดศุลกากร (HS Code)"),
    ("price",             r"price|amount|ราคา|ยอดรวม",
     "14. Unit Price & Total Amount", "14. ราคาต่อหน่วยและยอดรวม (Price & Amount)"),
    ("marks",             r"marks?|เครื่องหมาย",
     "15. Shipping Marks", "15. เครื่องหมายการขนส่ง (Shipping Marks)"),
    ("vessel",            r"vessel|voyage|flight|เรือ|เที่ยวบิน",
     "16. Vessel / Flight / Voyage No.", "16. ชื่อเรือ / เที่ยวบิน / ลำดับเที่ยว (Vessel / Voyage)"),
    ("pol",               r"loading|\bpol\b|ต้นทาง|บรรทุก",
     "17. Port of Loading (POL)", "17. ท่าเรือต้นทาง / บรรทุก (Port of Loading - POL)"),
    ("pod",               r"discharge|\bpod\b|destination|ปลายทาง",
     "18. Port of Discharge (POD)", "18. ท่าเรือปลายทาง (Port of Discharge - POD)"),
]

SUMMARY_PATTERNS = {
    "shipper_address":   r"(shipper|exporter).*addr|ที่อยู่.*ผู้ส่ง",
    "shipper_name":      r"((shipper|exporter)(?!.*addr)|(ผู้ส่ง(?!.*ที่อยู่)))",
    "consignee_address": r"consignee.*addr|ที่อยู่.*ผู้รับ",
    "consignee_name":    r"consignee(?!.*addr)|ผู้รับ(?!.*(ที่อยู่|แจ้ง))",
    "notify":            r"notify|ผู้รับแจ้ง",
    "document":          r"$^",  # Independent serials, never flag
    "date":              r"$^",  # Independent dates, never flag
    "description":       r"desc|goods|สินค้า",
    "quantity":          r"quant|pack|จำนวน|หีบห่อ|ชิ้น|กล่อง|พาเลท",
    "net_weight":        r"net\s*weight|\bnw\b|น้ำหนักสุทธิ",
    "gross_weight":      r"gross\s*weight|\bgw\b|น้ำหนักรวม",
    "volume":            r"volume|cbm|ปริมาตร",
    "hs_code":           r"hs\s*code|พิกัด|รหัส\s*hs",
    "price":             r"price|amount|ราคา|ยอดรวม",
    "marks":             r"marks?|เครื่องหมาย",
    "vessel":            r"vessel|voyage|flight|เรือ|เที่ยวบิน",
    "pol":               r"loading|\bpol\b|ต้นทาง|บรรทุก",
    "pod":               r"discharge|\bpod\b|destination|ปลายทาง",
}

DOC_PATTERNS = {
    "ci": r"\b(ci|commercial\s+invoice)\b|ใบกำกับสินค้า",
    "pl": r"\b(pl|packing\s+list)\b|รายการบรรจุ",
    "bl": r"\b(bl|b/?l|bill\s+of\s+lading)\b|ใบตราส่ง",
    "co": r"\b(co|c/?o|certificate\s+of\s+origin)\b|หนังสือรับรองถิ่นกำเนิด|ใบรับรองถิ่นกำเนิด",
    "master_db": r"\b(master\s+db|database)\b|ฐานข้อมูล",
}

UI_TEXT = {
    "en": {
        "app_title": "Logistics PDF Auditor - Dawn Shipping (Thailand)",
        "header_title": "Logistics PDF Auditor",
        "recent_btn": "📂 View Recent Audits",
        "new_btn": "➕ New Audit",
        "about_btn": "ℹ️ About",
        "about_title": "About Logistics PDF Auditor",
        "update_btn": "🔄 Update Available ({ver})",
        "update_prompt_title": "Update Logistics Auditor",
        "update_prompt_msg": "A new version ({ver}) is ready. Download and restart now?",
        "updating_status": "Downloading update {pct}%...",
        "hint": "Drop PDF files (CI, PL, BL, CO) below or click 'New Audit'. Pages are flattened to 300 DPI JPEGs and cross-checked against the Consignee Master DB.",
        "drop_zone": "Drag and drop PDF files here\n\nor click 'New Audit' above",
        "chk_thai": "Use Thai Language UI (ใช้งานภาษาไทย)",
        "company_footer": "Dawn Shipping (Thailand) Co., Ltd. • Support: andrelim@dawnsg.com",
        "ready": "Ready. Drop PDFs or click 'New Audit'.",
        "busy_title": "Busy",
        "busy_msg": "A job is already running. Please wait.",
        "no_pdf_title": "No PDFs",
        "no_pdf_msg": "Please drop one or more .pdf files.",
        "browse_title": "Select logistics PDFs for Audit",
        "recent_title": "Select Recent Audit Report",
        "recent_heading": "Recent Audit Reports (Last 5):",
        "no_recent_title": "No Recent Audits",
        "no_recent_msg": "No previous audit reports were found in output/.",
        "open_btn": "Open Selected Audit",
        "cancel_btn": "Cancel",
        "select_warn_title": "Select Report",
        "select_warn_msg": "Please select a report from the list.",
        "status_db": "Downloading live Consignee master database...",
        "status_flatten": "Flattening {name} to 300 DPI JPEGs...",
        "status_upload": "Uploading {count} page image(s) to Gemini Vision...",
        "status_saved": "Saved {name}",
        "status_success": "Success. Saved {name} in output/.",
        "status_failed": "Failed. See error dialog.",
        "audit_popup_title": "Audit Results - {name}",
        "headers": [
            "Data Field",
            "Commercial Invoice (CI)",
            "Packing List (PL)",
            "Bill of Lading (BL)",
            "Certificate of Origin (CO)",
            "Master Database",
        ],
        "summary_title": " Discrepancy Summary & Notes ",
        "no_discrepancy": "All checked data points match.",
        "watermark_label": "⚠️ Watermark Warning:",
    },
    "th": {
        "app_title": "ระบบตรวจสอบเอกสารโลจิสติกส์ - Dawn Shipping (Thailand)",
        "header_title": "ระบบตรวจสอบเอกสารโลจิสติกส์",
        "recent_btn": "📂 ดูรายงานย้อนหลัง",
        "new_btn": "➕ ตรวจสอบเอกสารใหม่",
        "about_btn": "ℹ️ เกี่ยวกับระบบ",
        "about_title": "เกี่ยวกับระบบตรวจสอบเอกสาร",
        "update_btn": "🔄 มีเวอร์ชันใหม่ ({ver})",
        "update_prompt_title": "อัปเดตระบบตรวจสอบเอกสาร",
        "update_prompt_msg": "พบเวอร์ชันใหม่ ({ver}) ต้องการดาวน์โหลดและเปิดโปรแกรมใหม่ทันทีหรือไม่?",
        "updating_status": "กำลังดาวน์โหลดอัปเดต {pct}%...",
        "hint": "ลากไฟล์ PDF (CI, PL, BL, CO) มาวางด้านล่าง หรือคลิก 'ตรวจสอบเอกสารใหม่' ระบบจะแปลงไฟล์เป็นรูปภาพ 300 DPI และเปรียบเทียบข้อมูลกับฐานข้อมูลหลัก",
        "drop_zone": "ลากและวางไฟล์ PDF ที่นี่\n\nหรือคลิก 'ตรวจสอบเอกสารใหม่' ด้านบน",
        "chk_thai": "ใช้งานภาษาไทยทั้งระบบ (Thai Language UI)",
        "company_footer": "บริษัท ดอว์น ชิปปิ้ง (ประเทศไทย) จำกัด • ติดต่อฝ่ายสนับสนุน: andrelim@dawnsg.com",
        "ready": "พร้อมใช้งาน: ลากไฟล์ PDF มาวาง หรือคลิก 'ตรวจสอบเอกสารใหม่'",
        "busy_title": "ระบบกำลังทำงาน",
        "busy_msg": "กำลังประมวลผลงานก่อนหน้า กรุณารอสักครู่",
        "no_pdf_title": "ไม่มีไฟล์ PDF",
        "no_pdf_msg": "กรุณาวางไฟล์ประเภท .pdf อย่างน้อย 1 ไฟล์",
        "browse_title": "เลือกไฟล์ PDF สำหรับตรวจสอบ",
        "recent_title": "รายงานการตรวจสอบย้อนหลัง",
        "recent_heading": "รายงานการตรวจสอบย้อนหลัง (5 รายการล่าสุด):",
        "no_recent_title": "ไม่พบรายงานย้อนหลัง",
        "no_recent_msg": "ยังไม่มีรายงานการตรวจสอบอยู่ในโฟลเดอร์ output/",
        "open_btn": "เปิดรายงานที่เลือก",
        "cancel_btn": "ยกเลิก",
        "select_warn_title": "เลือกรายงาน",
        "select_warn_msg": "กรุณาเลือกรายงานจากรายการ",
        "status_db": "กำลังดาวน์โหลดฐานข้อมูลหลัก Consignee...",
        "status_flatten": "กำลังแปลงไฟล์ {name} เป็นรูปภาพ 300 DPI...",
        "status_upload": "กำลังส่งรูปภาพ {count} หน้า ไปยัง Gemini Vision...",
        "status_saved": "บันทึกไฟล์เรียบร้อย: {name}",
        "status_success": "สำเร็จ: บันทึกรายงาน {name} ใน output/",
        "status_failed": "การประมวลผลล้มเหลว",
        "audit_popup_title": "ผลการตรวจสอบ - {name}",
        "headers": [
            "รายการข้อมูล (Data Field)",
            "ใบกำกับสินค้า (CI)",
            "รายการบรรจุหีบห่อ (PL)",
            "ใบตราส่งสินค้า (BL)",
            "หนังสือรับรองถิ่นกำเนิด (CO)",
            "ฐานข้อมูลหลัก (Master DB)",
        ],
        "summary_title": " สรุปข้อขัดแย้งและบันทึกเพิ่มเติม (Discrepancy Summary) ",
        "no_discrepancy": "ข้อมูลตรงกันทุกรายการ ไม่พบข้อขัดแย้ง",
        "watermark_label": "⚠️ คำเตือนลายน้ำ:",
    },
}


def parse_audit_json(raw: str) -> dict:
  """Robust JSON extractor supporting unescaped control characters, trailing commas, and markdown fences."""
  if not raw or not raw.strip():
    return {}

  clean = raw.strip()

  # Strip markdown fences
  clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
  clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE).strip()

  # Extract outer JSON boundaries
  m = re.search(r"\{[\s\S]*\}", clean)
  if m:
    clean = m.group(0)

  # 1. Parse with strict=False (permits unescaped newlines/tabs inside strings)
  try:
    return json.loads(clean, strict=False)
  except Exception:
    pass

  # 2. Strip trailing commas before closing braces/brackets
  clean_no_trailing = re.sub(r",\s*([\}\]])", r"\1", clean)
  try:
    return json.loads(clean_no_trailing, strict=False)
  except Exception:
    pass

  # 3. Clean unescaped backslashes
  try:
    return json.loads(clean_no_trailing.replace("\\", "\\\\"), strict=False)
  except Exception:
    pass

  return {}


def _get_about_text(lang: str) -> str:
    ver = get_current_version()
    if lang == "th":
        return (
            f"ระบบตรวจสอบเอกสารโลจิสติกส์ v{ver}\n\n"
            "พัฒนาสำหรับ: บริษัท ดอว์น ชิปปิ้ง (ประเทศไทย) จำกัด\n"
            "ฝ่ายประสานงานและดูแลระบบ: Andre Lim (andrelim@dawnsg.com)\n"
            "ระบบประมวลผล: Gemini Multimodal Vision Pipeline\n\n"
            "สงวนลิขสิทธิ์ • สำหรับการใช้งานภายในองค์กรเท่านั้น"
        )
    return (
        f"Logistics PDF Auditor v{ver}\n\n"
        "Company: Dawn Shipping (Thailand) Co., Ltd.\n"
        "Contact & Support: Andre Lim (andrelim@dawnsg.com)\n"
        "Engine: Gemini Multimodal Vision Pipeline\n\n"
        "Internal Company Property • Unauthorized distribution strictly prohibited."
    )


def get_field_info(raw_field: str) -> tuple[str, str, str]:
    rf = raw_field.lower()
    for key, pat, en_lbl, th_lbl in FIELD_DEFINITIONS:
        if "addr" in key and not ("addr" in rf or "ที่อยู่" in rf):
            continue
        if key in ("shipper_name", "consignee_name") and ("addr" in rf or "ที่อยู่" in rf):
            continue
        if re.search(pat, rf, re.I):
            return key, en_lbl, th_lbl
    return "unknown", raw_field, raw_field


def normalize_company_name(name: str) -> str:
    n = name.upper()
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\b(CO|LTD|COMPANY|LIMITED|CORPORATION|CORP|INC)\b", "", n)
    return " ".join(n.split())


def normalize_weight_to_kg(text: str) -> float | None:
    """Extract weight value and convert MT / Metric Tons to KG for equal comparison."""
    clean = text.upper().replace(",", "").strip()
    m = re.search(r"[-+]?\d*\.?\d+", clean)
    if not m:
        return None
    try:
        val = float(m.group())
    except ValueError:
        return None

    if re.search(r"\b(MT|M/T|METRIC\s*TONS?|TONS?)\b", clean):
        val *= 1000.0

    return round(val, 2)


def extract_numeric(text: str) -> float | None:
    m = re.search(r"[-+]?\d*\.?\d+", text)
    if m:
        try:
            return float(m.group())
        except ValueError:
            return None
    return None


def run_deterministic_audit(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Directly inspect cells for typos, weight (MT/KG), and volume mismatches."""
    added_en: list[str] = []
    added_th: list[str] = []

    for row in rows:
        field = str(row.get("field", ""))
        f_lower = field.lower()

        if "reference" in f_lower or "document /" in f_lower or "invoice no" in f_lower or "date" in f_lower:
            continue

        doc_vals = {col: str(row.get(col, "-")).strip() for col in ["ci", "pl", "bl", "co"]}
        active_vals = {col: v for col, v in doc_vals.items() if v and v != "-" and "blank" not in v.lower()}

        if len(active_vals) <= 1:
            continue

        # Shipper / Exporter Name Check
        if ("shipper" in f_lower or "exporter" in f_lower) and "name" in f_lower:
            norms = {c: normalize_company_name(v) for c, v in active_vals.items()}
            if len(set(norms.values())) > 1:
                for c in active_vals:
                    val = str(row.get(c, "")).strip()
                    if val and not val.startswith("⚠️"):
                        row[c] = f"⚠️ {val}"
                diff_desc = " / ".join(f"{c.upper()}: {active_vals[c]}" for c in active_vals)
                added_en.append(f"Typographical error/mismatch in Shipper Name across documents ({diff_desc}).")
                added_th.append(f"พบการสะกดชื่อผู้ส่งสินค้าไม่ตรงกันระหว่างเอกสาร ({diff_desc})")

        # Gross Weight Check across PL, BL, CO with MT -> KG conversion
        elif "gross weight" in f_lower or "gw" in f_lower:
            gw_docs = {c: v for c, v in active_vals.items() if c in ["pl", "bl", "co"]}
            num_map = {c: normalize_weight_to_kg(v) for c, v in gw_docs.items() if normalize_weight_to_kg(v) is not None}
            vals = list(num_map.values())
            if len(vals) > 1 and (max(vals) - min(vals)) > 0.5:
                for c in gw_docs:
                    val = str(row.get(c, "")).strip()
                    if val and not val.startswith("⚠️"):
                        row[c] = f"⚠️ {val}"
                diff_desc = " vs ".join(f"{c.upper()} ({gw_docs[c]})" for c in gw_docs)
                added_en.append(f"Gross Weight mismatch between documents: {diff_desc}.")
                added_th.append(f"น้ำหนักรวม (Gross Weight) ไม่ตรงกันระหว่างเอกสาร: {diff_desc}")

        # Volume Check across PL, BL
        elif "volume" in f_lower or "cbm" in f_lower:
            vol_docs = {c: v for c, v in active_vals.items() if c in ["pl", "bl"]}
            num_map = {c: extract_numeric(v.replace(",", "")) for c, v in vol_docs.items() if extract_numeric(v.replace(",", "")) is not None}
            vals = list(num_map.values())
            if len(vals) > 1 and (max(vals) - min(vals)) > 0.01:
                for c in vol_docs:
                    val = str(row.get(c, "")).strip()
                    if val and not val.startswith("⚠️"):
                        row[c] = f"⚠️ {val}"
                diff_desc = " vs ".join(f"{c.upper()} ({vol_docs[c]})" for c in vol_docs)
                added_en.append(f"Volume (CBM) mismatch: {diff_desc}.")
                added_th.append(f"ปริมาตรสินค้า (Volume) ไม่ตรงกัน: {diff_desc}")

        # Consignee Name Check (with To-Order L/C validation)
        elif "consignee" in f_lower and "name" in f_lower:
            bl_consignee = active_vals.get("bl", "").upper()
            ci_consignee = active_vals.get("ci", "").upper()

            # If BL is "TO ORDER OF [BANK]", verify buyer is named in Notify Party
            if "TO THE ORDER OF" in bl_consignee or "TO ORDER" in bl_consignee:
                # Find Notify Party row
                notify_row = next(
                    (r for r in rows if "notify" in str(r.get("field", "")).lower()),
                    None,
                )
                bl_notify = (
                    str(notify_row.get("bl", "")).upper() if notify_row else ""
                )

                # Check if the CI/PL buyer is listed in the BL Notify Party
                norm_buyer = normalize_company_name(ci_consignee)
                if norm_buyer and norm_buyer in normalize_company_name(
                    bl_notify
                ):
                    pass  # Legitimate L/C structure; no flag
                else:
                    for c in ["bl"]:
                        val = str(row.get(c, "")).strip()
                        if val and not val.startswith("⚠️"):
                            row[c] = f"⚠️ {val}"
                    added_en.append(
                        f"B/L Consigned 'To Order' of Bank ({active_vals.get('bl')}), but buyer is missing in B/L Notify Party."
                    )
                    added_th.append(
                        f"B/L สั่งจ่ายตามคำสั่งธนาคาร แต่ไม่พบชื่อผู้ซื้อในช่อง Notify Party"
                    )
            else:
                norms = {
                    c: normalize_company_name(v)
                    for c, v in active_vals.items()
                    if c != "master_db"
                }
                if len(set(norms.values())) > 1:
                    for c in active_vals:
                        val = str(row.get(c, "")).strip()
                        if val and not val.startswith("⚠️"):
                            row[c] = f"⚠️ {val}"
                    diff_desc = " / ".join(
                        f"{c.upper()}: {active_vals[c]}" for c in active_vals
                    )
                    added_en.append(
                        f"Consignee Name mismatch across documents ({diff_desc})."
                    )
                    added_th.append(
                        f"ชื่อผู้รับตราส่ง (Consignee) ไม่ตรงกันระหว่างเอกสาร ({diff_desc})"
                    )

        # Description of Goods Specification / Dimension Check
        elif "description" in f_lower or "goods" in f_lower:
            # Check for specification dimension mismatches like "850" vs "860"
            for col, val in active_vals.items():
                if "311" not in val and any(
                    "311" in other for other in active_vals.values()
                ):
                    row[col] = (
                        f"⚠️ {val}"
                        if not str(val).startswith("⚠️")
                        else str(val)
                    )
                    added_en.append(
                        f"Description grade mismatch: '{val}' missing specification '311' found on other documents."
                    )
                    added_th.append(
                        f"รายละเอียดสินค้าขาดข้อกำหนด '311' เมื่อเทียบกับเอกสารอื่น"
                    )

    return added_en, added_th


def reconcile_discrepancies(data: dict) -> dict:
    rows = data.get("audit_table", [])

    # 1. Clean any raw ⚠️ prefixes so we start from a clean baseline
    for row in rows:
        for col in ["ci", "pl", "bl", "co", "master_db"]:
            val = str(row.get(col, "")).strip()
            if val.startswith("⚠️"):
                row[col] = re.sub(r"^⚠️\s*", "", val)

    # 2. Reconcile ONLY using the English summary to prevent Thai substring collisions
    raw_en = data.get("discrepancy_summary_en") or data.get("discrepancy_summary", [])
    summaries = raw_en if isinstance(raw_en, list) else ([raw_en] if raw_en else [])

    if summaries and rows:
        for summary in summaries:
            target_docs = [col for col, pat in DOC_PATTERNS.items() if re.search(pat, summary, re.I)]
            cols = target_docs if target_docs else ["ci", "pl", "bl", "co", "master_db"]

            for row in rows:
                fname = str(row.get("field", ""))
                key, _, _ = get_field_info(fname)
                pat = SUMMARY_PATTERNS.get(key)
                if pat and re.search(pat, summary, re.I):
                    for col in cols:
                        val = str(row.get(col, "")).strip()
                        if val and val != "-" and not val.startswith("⚠️"):
                            row[col] = f"⚠️ {val}"

    # 3. Deterministic cross-checks on weights, volumes, and shipper names
    auto_en, auto_th = run_deterministic_audit(rows)

    s_en = data.setdefault("discrepancy_summary_en", [])
    s_th = data.setdefault("discrepancy_summary_th", [])

    for e in auto_en:
        if e not in s_en:
            s_en.append(e)
    for t in auto_th:
        if t not in s_th:
            s_th.append(t)

    return data


class LogisticsAuditorApp:
    def __init__(self) -> None:
        self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.root.geometry("860x580")
        self.root.minsize(740, 480)

        self.status = StringVar()
        self.use_thai = BooleanVar(value=False)
        self._busy = False
        self._latest_ver = ""
        self._download_url = ""

        self._build_layout()
        self._update_ui_language()

        if HAS_DND:
            self._enable_drag_and_drop()

        self._check_updates_background()

    def _t(self, key: str, lang: str | None = None) -> str:
        selected_lang = lang or ("th" if self.use_thai.get() else "en")
        return UI_TEXT[selected_lang].get(key, key)

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        header_frame = ttk.Frame(frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        self.title_label = ttk.Label(header_frame, font=("Segoe UI", 16, "bold"))
        self.title_label.pack(side=tk.LEFT)

        nav_frame = ttk.Frame(header_frame)
        nav_frame.pack(side=tk.RIGHT)

        self.update_btn = ttk.Button(nav_frame, command=self._start_update_flow)

        self.recent_btn = ttk.Button(nav_frame, command=self._show_recent_audits)
        self.recent_btn.pack(side=tk.LEFT, padx=3)

        self.new_btn = ttk.Button(nav_frame, command=self._browse_files)
        self.new_btn.pack(side=tk.LEFT, padx=3)

        self.about_btn = ttk.Button(nav_frame, command=self._show_about_dialog)
        self.about_btn.pack(side=tk.LEFT, padx=3)

        self.hint_label = ttk.Label(frame, wraplength=780)
        self.hint_label.pack(anchor=tk.W, pady=(0, 10))

        self.drop_zone = tk.Label(
            frame,
            relief=tk.RIDGE,
            borderwidth=2,
            width=70,
            height=7,
            bg="#f4f6f8",
            fg="#333333",
            font=("Segoe UI", 11),
        )
        self.drop_zone.pack(fill=tk.BOTH, expand=True, pady=6)

        options_row = ttk.Frame(frame)
        options_row.pack(fill=tk.X, pady=4)

        self.chk_thai = ttk.Checkbutton(
            options_row,
            variable=self.use_thai,
            command=self._update_ui_language,
        )
        self.chk_thai.pack(side=tk.LEFT)

        ttk.Label(
            frame,
            textvariable=self.status,
            wraplength=780,
            font=("Segoe UI", 9, "italic"),
        ).pack(anchor=tk.W, pady=(6, 2))

        self.footer_label = ttk.Label(
            frame,
            font=("Segoe UI", 8),
            foreground="#64748b",
            anchor=tk.CENTER,
        )
        self.footer_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

    def _show_about_dialog(self) -> None:
        lang = "th" if self.use_thai.get() else "en"
        messagebox.showinfo(self._t("about_title", lang), _get_about_text(lang))

    def _update_ui_language(self) -> None:
        lang = "th" if self.use_thai.get() else "en"
        self.root.title(self._t("app_title", lang))
        self.title_label.config(text=self._t("header_title", lang))
        self.recent_btn.config(text=self._t("recent_btn", lang))
        self.new_btn.config(text=self._t("new_btn", lang))
        self.about_btn.config(text=self._t("about_btn", lang))
        self.hint_label.config(text=self._t("hint", lang))
        self.drop_zone.config(text=self._t("drop_zone", lang))
        self.chk_thai.config(text=self._t("chk_thai", lang))
        self.footer_label.config(text=self._t("company_footer", lang))

        if self._latest_ver:
            self.update_btn.config(text=self._t("update_btn", lang).format(ver=self._latest_ver))

        if not self._busy:
            self.status.set(self._t("ready", lang))

    def _check_updates_background(self) -> None:
        def _worker():
            has_update, latest_ver, dl_url = check_for_updates()
            if has_update and dl_url:
                self._latest_ver = latest_ver
                self._download_url = dl_url
                self.root.after(0, self._reveal_update_button)

        threading.Thread(target=_worker, daemon=True).start()

    def _reveal_update_button(self) -> None:
        lang = "th" if self.use_thai.get() else "en"
        btn_text = self._t("update_btn", lang).format(ver=self._latest_ver)
        self.update_btn.config(text=btn_text)
        self.update_btn.pack(side=tk.LEFT, padx=3, before=self.recent_btn)

    def _start_update_flow(self) -> None:
        lang = "th" if self.use_thai.get() else "en"

        if not getattr(sys, "frozen", False):
            msg = (
                f"A new release ({self._latest_ver}) is available on GitHub.\n\n"
                "In-app auto-updating only runs inside the compiled .exe application, "
                "not when running from Python source code."
            )
            messagebox.showinfo("Update Notice", msg)
            return

        title = self._t("update_prompt_title", lang)
        msg = self._t("update_prompt_msg", lang).format(ver=self._latest_ver)
        if not messagebox.askyesno(title, msg):
            return

        self._busy = True
        self.update_btn.config(state="disabled")

        def _worker():
            try:
                def on_progress(pct: int):
                    self._set_status(self._t("updating_status", lang).format(pct=pct))

                apply_update_and_restart(
                    self._download_url,
                    new_version=self._latest_ver,
                    progress_callback=on_progress,
                )
            except Exception as exc:
                err_text = str(exc)
                self.root.after(0, lambda msg=err_text: messagebox.showerror("Update Error", msg))
                self._busy = False
                self.root.after(0, lambda: self.update_btn.config(state="normal"))

        threading.Thread(target=_worker, daemon=True).start()

    def _enable_drag_and_drop(self) -> None:
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event) -> None:
        paths = self._parse_dropped_paths(event.data)
        pdfs = [path for path in paths if path.suffix.lower() == ".pdf"]
        if not pdfs:
            lang = "th" if self.use_thai.get() else "en"
            messagebox.showwarning(self._t("no_pdf_title", lang), self._t("no_pdf_msg", lang))
            return
        self._start_jobs(pdfs)

    def _parse_dropped_paths(self, data: str) -> list[Path]:
        try:
            raw_items = self.root.tk.splitlist(data)
        except tk.TclError:
            raw_items = data.split()
        return [Path(item.strip("{}")) for item in raw_items if item.strip()]

    def _browse_files(self) -> None:
        lang = "th" if self.use_thai.get() else "en"
        filenames = filedialog.askopenfilenames(
            title=self._t("browse_title", lang),
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if filenames:
            self._start_jobs([Path(name) for name in filenames])

    def _generate_report_name(self, result_str: str) -> str:
        shipper_name = ""
        data = parse_audit_json(result_str)

        rows = data.get("audit_table", [])
        for item in rows:
            field = str(item.get("field", "")).lower()
            if "shipper" in field or "exporter" in field or "ผู้ส่ง" in field:
                for source in ["ci", "pl", "bl", "co"]:
                    val = str(item.get(source, "")).strip()
                    if val and val != "-" and "blank" not in val.lower():
                        shipper_name = val.split("\n")[0].split("/")[0].strip()
                        break
            if shipper_name:
                break

        if shipper_name:
            clean_name = re.sub(r"[^\w\s-]", "", shipper_name).strip()
            clean_name = re.sub(r"\s+", "_", clean_name)[:30]
        else:
            clean_name = "Audit_Report"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{clean_name}_{timestamp}"

    def _get_recent_audit_files(self) -> list[Path]:
        output_dir = Path("output")
        if not output_dir.exists():
            return []

        files = [f for f in output_dir.rglob("*.json") if f.is_file()]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files[:5]

    def _show_recent_audits(self) -> None:
        lang = "th" if self.use_thai.get() else "en"
        recent_files = self._get_recent_audit_files()
        if not recent_files:
            messagebox.showinfo(self._t("no_recent_title", lang), self._t("no_recent_msg", lang))
            return

        popup = tk.Toplevel(self.root)
        popup.title(self._t("recent_title", lang))
        popup.geometry("580x380")
        popup.resizable(False, False)

        ttk.Label(
            popup,
            text=self._t("recent_heading", lang),
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor=tk.W, padx=16, pady=(14, 6))

        frame = ttk.Frame(popup, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        listbox = tk.Listbox(frame, font=("Segoe UI", 10), selectmode=tk.SINGLE)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)

        file_map: list[Path] = []
        for path in recent_files:
            mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            display_name = f"📄 {path.stem}   ({mtime})"
            listbox.insert(tk.END, display_name)
            file_map.append(path)

        def open_selected() -> None:
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning(self._t("select_warn_title", lang), self._t("select_warn_msg", lang))
                return
            selected_path = file_map[selection[0]]
            try:
                content = selected_path.read_text(encoding="utf-8")
                popup.destroy()
                self.display_audit_results(selected_path.stem, content)
            except Exception as exc:
                messagebox.showerror("Error", f"Failed to read report:\n{exc}")

        btn_frame = ttk.Frame(popup, padding=12)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text=self._t("open_btn", lang), command=open_selected).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text=self._t("cancel_btn", lang), command=popup.destroy).pack(side=tk.RIGHT, padx=4)

    def _start_jobs(self, pdf_paths: list[Path]) -> None:
        lang = "th" if self.use_thai.get() else "en"
        if self._busy:
            messagebox.showinfo(self._t("busy_title", lang), self._t("busy_msg", lang))
            return
        self._busy = True
        threading.Thread(target=self._run_jobs, args=(pdf_paths,), daemon=True).start()

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status.set(message))

    def _run_jobs(self, pdf_paths: list[Path]) -> None:
        errors: list[str] = []
        saved: list[Path] = []
        lang = "th" if self.use_thai.get() else "en"
        try:
            self._set_status(self._t("status_db", lang))
            master_excerpt = load_master_database_excerpt()

            all_jpegs: list[Path] = []
            for pdf_path in pdf_paths:
                self._set_status(self._t("status_flatten", lang).format(name=pdf_path.name))
                all_jpegs.extend(flatten_pdf_to_jpegs(pdf_path))

            self._set_status(self._t("status_upload", lang).format(count=len(all_jpegs)))

            result_str = extract_from_jpegs(
                pdf_path=pdf_paths[0],
                jpeg_paths=all_jpegs,
                master_db_excerpt=master_excerpt,
                use_thai=False,
                status_callback=self._set_status,
            )

            report_name = self._generate_report_name(result_str)
            report_path = Path(report_name)
            out_dir = job_output_dir(report_path)

            result_path = save_markdown(report_path, result_str, out_dir)
            saved.append(result_path)

            self._set_status(self._t("status_saved", lang).format(name=result_path.name))
            self.root.after(0, lambda: self.display_audit_results(report_name, result_str))

            def finish() -> None:
                self._busy = False
                if saved and not errors:
                    self.status.set(self._t("status_success", lang).format(name=report_name))
                elif errors:
                    self.status.set(self._t("status_failed", lang))
                    messagebox.showerror("Error", "\n".join(errors))

            self.root.after(0, finish)

        except Exception as exc:
            err_msg = str(exc)
            traceback.print_exc()

            def fail() -> None:
                self._busy = False
                self.status.set(f"Error: {err_msg}")
                messagebox.showerror("Error", err_msg)

            self.root.after(0, fail)

    def display_audit_results(self, pdf_name: str, result_str: str) -> None:
        popup = tk.Toplevel(self.root)
        popup.geometry("1360x840")
        popup.minsize(1080, 600)

        popup_lang = BooleanVar(value=self.use_thai.get())
        data = parse_audit_json(result_str)
        data = reconcile_discrepancies(data)

        # 1. Top Header Bar
        top_bar = ttk.Frame(popup, padding=(14, 8, 14, 4))
        top_bar.pack(side=tk.TOP, fill=tk.X, expand=False)

        title_lbl = ttk.Label(top_bar, font=("Segoe UI", 12, "bold"))
        title_lbl.pack(side=tk.LEFT)

        lang_chk = ttk.Checkbutton(top_bar, variable=popup_lang)
        lang_chk.pack(side=tk.RIGHT)

        # 2. Bottom Summary Frame (Packed FIRST at BOTTOM so it never clips off-screen)
        bottom_frame = ttk.LabelFrame(popup, padding=10)
        bottom_frame.pack(
            side=tk.BOTTOM, fill=tk.X, expand=False, padx=12, pady=(4, 10)
        )

        summary_text = tk.Text(
            bottom_frame,
            wrap="word",
            height=6,
            font=("Segoe UI", 10),
            bg="#f8f9fa",
            relief=tk.FLAT,
        )
        summary_scroll = ttk.Scrollbar(
            bottom_frame, orient=tk.VERTICAL, command=summary_text.yview
        )
        summary_text.configure(yscrollcommand=summary_scroll.set)

        summary_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        summary_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 3. Main Table Canvas (Takes all remaining middle space)
        table_frame = ttk.Frame(popup, padding=(12, 4, 12, 4))
        table_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(table_frame, bg="#f1f5f9", highlightthickness=0)
        v_scroll = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=canvas.yview
        )
        h_scroll = ttk.Scrollbar(
            table_frame, orient=tk.HORIZONTAL, command=canvas.xview
        )
        grid_container = tk.Frame(canvas, bg="#cbd5e1")

        # Proportional weights across 6 columns
        col_weights = [18, 16, 16, 18, 18, 14]
        for col_idx, weight in enumerate(col_weights):
            grid_container.grid_columnconfigure(
                col_idx, weight=weight, minsize=170
            )

        canvas_window = canvas.create_window(
            (0, 0), window=grid_container, anchor="nw"
        )
        canvas.configure(
            xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set
        )

        col_cell_widgets: dict[int, list[tk.Label]] = {i: [] for i in range(6)}
        header_label_widgets: list[tk.Label] = []

        base_width = 1300
        initial_wraps = [
            max(int(w * base_width / 100) - 22, 140) for w in col_weights
        ]

        # Column Headers
        for col_idx in range(6):
            hdr = tk.Label(
                grid_container,
                font=("Segoe UI", 9, "bold"),
                bg="#e2e8f0",
                fg="#1e293b",
                padx=10,
                pady=10,
                anchor="w",
                relief=tk.FLAT,
                wraplength=initial_wraps[col_idx],
            )
            hdr.grid(row=0, column=col_idx, sticky="nsew", padx=1, pady=1)
            header_label_widgets.append(hdr)
            col_cell_widgets[col_idx].append(hdr)

        rows = data.get("audit_table", [])
        row_field_widgets: list[tuple[tk.Label, str]] = []

        # Table Rows
        for row_idx, item in enumerate(rows, start=1):
            raw_field = str(item.get("field", "-"))
            cells = [
                raw_field,
                str(item.get("ci", "-")),
                str(item.get("pl", "-")),
                str(item.get("bl", "-")),
                str(item.get("co", "-")),
                str(item.get("master_db", "-")),
            ]

            row_has_error = any(
                "⚠️" in c or "[Printed as: BLANK/MISSING]" in c for c in cells[1:]
            )

            for col_idx, cell_val in enumerate(cells):
                is_flagged = (
                    (
                        "⚠️" in cell_val
                        or "[Printed as: BLANK/MISSING]" in cell_val
                    )
                    if col_idx > 0
                    else False
                )

                if is_flagged:
                    bg_color = "#fde8e8"
                    fg_color = "#991b1b"
                    font_style = ("Segoe UI", 9, "bold")
                elif col_idx == 0:
                    bg_color = "#f8fafc"
                    fg_color = "#991b1b" if row_has_error else "#0f172a"
                    font_style = (
                        "Segoe UI",
                        9,
                        "bold" if row_has_error else "normal",
                    )
                else:
                    bg_color = "#ffffff"
                    fg_color = "#334155"
                    font_style = ("Segoe UI", 9)

                cell_lbl = tk.Label(
                    grid_container,
                    text=cell_val,
                    font=font_style,
                    bg=bg_color,
                    fg=fg_color,
                    padx=10,
                    pady=8,
                    anchor="nw",
                    justify=tk.LEFT,
                    wraplength=initial_wraps[col_idx],
                )
                cell_lbl.grid(
                    row=row_idx, column=col_idx, sticky="nsew", padx=1, pady=1
                )
                col_cell_widgets[col_idx].append(cell_lbl)

                if col_idx == 0:
                    row_field_widgets.append((cell_lbl, raw_field))

        # Pack Scrollbars and Canvas
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 4. Reliable Scrolling & Geometry Handlers
        def _update_scrollregion(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        grid_container.bind("<Configure>", _update_scrollregion)

        last_width = [0]

        def _on_canvas_configure(event):
            cur_width = event.width
            if abs(cur_width - last_width[0]) < 8:
                return
            last_width[0] = cur_width

            target_width = max(cur_width - 4, 1260)
            canvas.itemconfig(canvas_window, width=target_width)

            for c_idx, weight in enumerate(col_weights):
                col_pixel_width = int(weight * target_width / 100)
                wrap_px = max(col_pixel_width - 22, 140)
                for widget in col_cell_widgets[c_idx]:
                    try:
                        widget.configure(wraplength=wrap_px)
                    except Exception:
                        pass

            popup.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", _on_canvas_configure)

        # 5. Global Mouse Wheel & Keyboard Navigation (Binds to whole window)
        def _on_mousewheel(event):
            try:
                # Do not intercept if scrolling inside the summary text box
                w = popup.winfo_containing(event.x_root, event.y_root)
                if w and (w == summary_text or "text" in str(w).lower()):
                    return

                if event.delta:
                    # Windows wheel: delta is +/- 120
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        def _on_shift_mousewheel(event):
            try:
                if event.delta:
                    canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        popup.bind_all("<MouseWheel>", _on_mousewheel)
        popup.bind_all("<Shift-MouseWheel>", _on_shift_mousewheel)

        # Trackpad / Linux scrolling support
        popup.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-2, "units"))
        popup.bind_all("<Button-5>", lambda e: canvas.yview_scroll(2, "units"))

        # Keyboard arrows & page navigation
        popup.bind("<Up>", lambda e: canvas.yview_scroll(-2, "units"))
        popup.bind("<Down>", lambda e: canvas.yview_scroll(2, "units"))
        popup.bind("<Prior>", lambda e: canvas.yview_scroll(-6, "units"))
        popup.bind("<Next>", lambda e: canvas.yview_scroll(6, "units"))

        # Clean up global binds when popup closes
        def _on_popup_destroy(event):
            if event.widget == popup:
                try:
                    popup.unbind_all("<MouseWheel>")
                    popup.unbind_all("<Shift-MouseWheel>")
                    popup.unbind_all("<Button-4>")
                    popup.unbind_all("<Button-5>")
                except Exception:
                    pass

        popup.bind("<Destroy>", _on_popup_destroy)

        # 6. Bilingual Language Refresh Handler
        def refresh_popup_language():
            lang = "th" if popup_lang.get() else "en"

            if self.use_thai.get() != popup_lang.get():
                self.use_thai.set(popup_lang.get())
                self._update_ui_language()

            popup.title(
                self._t("audit_popup_title", lang).format(name=pdf_name)
            )
            title_lbl.config(
                text=self._t("audit_popup_title", lang).format(name=pdf_name)
            )
            lang_chk.config(text=self._t("chk_thai", lang))

            headers = UI_TEXT[lang]["headers"]
            for idx, h_widget in enumerate(header_label_widgets):
                h_widget.config(text=headers[idx])

            for lbl_widget, raw_f in row_field_widgets:
                _, en_lbl, th_lbl = get_field_info(raw_f)
                lbl_widget.config(text=th_lbl if lang == "th" else en_lbl)

            bottom_frame.config(text=self._t("summary_title", lang))

            watermark = str(data.get("watermark_warning", "None"))
            summary_en = data.get("discrepancy_summary_en") or data.get(
                "discrepancy_summary", []
            )
            summary_th = data.get("discrepancy_summary_th") or data.get(
                "discrepancy_summary", []
            )

            active_en = summary_en if summary_en else summary_th
            active_th = summary_th if summary_th else summary_en
            active_summary = active_th if lang == "th" else active_en

            summary_content = ""
            if watermark and watermark.lower() not in ("none", "null", ""):
                wm_label = self._t("watermark_label", lang)
                summary_content += f"{wm_label} {watermark}\n\n"

            if isinstance(active_summary, list) and active_summary:
                summary_content += "\n".join(f"• {s}" for s in active_summary)
            elif isinstance(active_summary, str) and active_summary:
                summary_content += active_summary
            else:
                summary_content += self._t("no_discrepancy", lang)

            summary_text.config(state="normal")
            summary_text.delete("1.0", tk.END)
            summary_text.insert("1.0", summary_content)
            summary_text.config(state="disabled")

        lang_chk.config(command=refresh_popup_language)
        refresh_popup_language()

        popup.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.yview_moveto(0)
        canvas.xview_moveto(0)

    def run(self) -> None:
        self.root.mainloop()