"""Tkinter desktop UI: 18-field deterministic auditing, live bilingual toggling, and auto-updater."""

from __future__ import annotations

import json
import re
import sys
import threading
import traceback
import difflib
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, messagebox, ttk
import tkinter as tk
from tkinter import messagebox

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
        "co_prompt_title": "Declaration Form / CO",
        "co_prompt_msg": "Does this document batch include a Certificate of Origin (CO) or Declaration Form?",
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
        "co_prompt_title": "เอกสารยืนยันถิ่นกำเนิดสินค้า (CO)",
        "co_prompt_msg": "ชุดเอกสารนี้มีใบรับรองถิ่นกำเนิดสินค้า (CO) หรือฟอร์มประกาศ (Declaration Form) รวมอยู่ด้วยหรือไม่?",
    },
}

def parse_audit_json(raw: str) -> dict:
  if not raw or not raw.strip():
    return {}

  clean = raw.strip()
  clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
  clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE).strip()

  m = re.search(r"\{[\s\S]*\}", clean)
  if m:
    clean = m.group(0)

  try:
    return json.loads(clean, strict=False)
  except Exception:
    pass

  clean_no_trailing = re.sub(r",\s*([\}\]])", r"\1", clean)
  try:
    return json.loads(clean_no_trailing, strict=False)
  except Exception:
    pass

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

def reconcile_discrepancies(data: dict) -> dict:
    rows = data.get("audit_table", [])

    def extract_entity_root(name: str) -> str:
        """Strips out corporate suffixes and punctuation to compare only the core business name."""
        t = str(name).upper()
        t = re.sub(r'\b(PUBLIC\s+COMPANY\s+LIMITED|COMPANY\s+LIMITED|CO\s*,\s*LTD|CO\s+LTD|LTD|COMPANY|CORP|INC|PCL|LLC)\b\.?', ' ', t)
        t = re.sub(r'[^\w\s]', ' ', t)
        return re.sub(r'\s+', ' ', t).strip()

    def norm_address(text: str) -> str:
        """Normalizes address abbreviations, comma spacing, and trailing punctuation."""
        t = str(text).upper()
        t = re.sub(r'\bRD\b\.?', 'ROAD', t)
        t = re.sub(r'\bM\b\.?', 'MOO', t)
        t = re.sub(r'\bCO\b\.?', 'COMPANY', t)
        t = re.sub(r'\bLTD\b\.?', 'LIMITED', t)
        t = re.sub(r'[^\w\s]', ' ', t)
        return re.sub(r'\s+', ' ', t).strip()

    def parse_standard_dates(text: str) -> set[str]:
        found = set()
        t = str(text).upper()
        months = {'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06',
                  'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'}
        for m in re.finditer(r'\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b', t):
            found.add(f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}")
        for m in re.finditer(r'\b(0?[1-9]|[12]\d|3[01])[-/](0?[1-9]|1[0-2])[-/](20\d{2})\b', t):
            found.add(f"{m.group(3)}{int(m.group(2)):02d}{int(m.group(1)):02d}")
        for m in re.finditer(r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\s*(0?[1-9]|[12]\d|3[01])\,?\s*(20\d{2})\b', t):
            found.add(f"{m.group(3)}{months[m.group(1)]}{int(m.group(2)):02d}")
        for m in re.finditer(r'\b(0?[1-9]|[12]\d|3[01])\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\,?\s*(20\d{2})\b', t):
            found.add(f"{m.group(3)}{months[m.group(2)]}{int(m.group(1)):02d}")
        return found

    ci_dates = set()
    for row in rows:
        if "date" in str(row.get("field", "")).lower():
            ci_dates = parse_standard_dates(str(row.get("ci", "")))
            break

    for row in rows:
        fname = str(row.get("field", "")).lower()

        # Hard Failsafe: Master DB should only display Consignee Info
        if not ("consignee" in fname and "notify" not in fname):
            row["master_db"] = "-"

        # Hard Failsafe 2: Net Weight on BL/CO must always be blank
        if "net weight" in fname:
            for col in ["bl", "co"]:
                if str(row.get(col, "")).strip() not in ["-", ""]:
                    row[col] = "-"

        # Hard Failsafe: Net Weight on BL/CO must always be blank
        if "net weight" in fname:
            for col in ["bl", "co"]:
                if str(row.get(col, "")).strip() not in ["-", ""]:
                    row[col] = "-"

        # CONSIGNEE NAME (ROW 3) & ADDRESS (ROW 4)
        if "consignee" in fname and "notify" not in fname:
            master_val = str(row.get("master_db", "")).strip()
            is_name_row = "name" in fname
            
            if master_val and master_val.upper() not in ["-", "N/A", "NONE"]:
                master_norm = extract_entity_root(master_val) if is_name_row else norm_address(master_val)

                for col in ["ci", "pl", "bl", "co"]:
                    val = str(row.get(col, "")).strip()
                    if not val or val == "-":
                        continue

                    v_clean = re.sub(r"^[⚠️🔍]\s*", "", val)
                    v_upper = v_clean.upper()

                    # BL 'TO THE ORDER OF' rule -> Only flag this specific cell
                    if "TO ORDER" in v_upper or "TO THE ORDER" in v_upper:
                        if not val.startswith("🔍") and not val.startswith("⚠️"):
                            row[col] = f"🔍 {v_clean}"
                        continue

                    # Compare normalized root against Master DB
                    v_norm = extract_entity_root(v_clean) if is_name_row else norm_address(v_clean)
                    
                    if v_norm == master_norm:
                        row[col] = v_clean  # Clean match: remove any accidental flag from AI
                    else:
                        if not val.startswith("🔍") and not val.startswith("⚠️"):
                            row[col] = f"🔍 {v_clean}" # Genuine entity mismatch (CRAFTLAND vs CRAFT LAND)

        # DOCUMENT DATE FAILSAFE (ROW 7)
        if "date" in fname and ci_dates:
            for col in ["pl", "bl", "co"]:
                val = str(row.get(col, "")).strip()
                if not val or val == "-":
                    continue
                v_clean = re.sub(r"^[⚠️🔍]\s*", "", val)
                
                inv_match = re.search(r"^(.*?)\s*\(Invoice\)", v_clean)
                check_str = inv_match.group(1) if inv_match else v_clean.replace("(Native)", "").strip()
                
                parsed = parse_standard_dates(check_str)
                if parsed and not (parsed & ci_dates):
                    if not val.startswith("⚠️"):
                        row[col] = f"⚠️ {val}"
                elif "- (Invoice)" in v_clean and not parsed:
                    if not val.startswith("⚠️"):
                        row[col] = f"⚠️ {val}"

    # Generate discrepancy summary based on final flags
    summaries = data.get("discrepancy_summary", [])
    if not summaries or summaries == ["Match"]:
        auto = []
        for r in rows:
            for c in ["ci", "pl", "bl", "co"]:
                val = str(r.get(c, ""))
                if "⚠️" in val:
                    auto.append(f"{r.get('field', 'Field')}: Mismatch in {c.upper()}")
                    break
                elif "🔍" in val:
                    auto.append(f"{r.get('field', 'Field')}: Review required in {c.upper()}")
                    break
        summaries = auto if auto else ["All checked data points match."]

    data["discrepancy_summary"] = summaries
    data["discrepancy_summary_en"] = summaries
    data["discrepancy_summary_th"] = summaries
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
        
        from gemini_client import get_saved_api_key
        if not get_saved_api_key():
            self.root.after(500, self._show_api_settings)

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

        self.api_btn = ttk.Button(nav_frame, text="🔑 API Settings", command=self._show_api_settings)
        self.api_btn.pack(side=tk.LEFT, padx=3)

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

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 10))

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

    def _show_api_settings(self) -> None:
        from gemini_client import get_saved_api_key, save_api_key, validate_api_key
        
        modal = tk.Toplevel(self.root)
        modal.title("API Key Settings")
        modal.geometry("450x230") 
        modal.resizable(False, False)
        modal.grab_set()

        ttk.Label(modal, text="Google Gemini API Key:", font=("Segoe UI", 10, "bold")).pack(pady=(20, 5))
        
        key_var = tk.StringVar(value=get_saved_api_key())
        entry = ttk.Entry(modal, textvariable=key_var, show="*", width=50)
        entry.pack(pady=5)

        status_lbl = ttk.Label(modal, text="", font=("Segoe UI", 9))
        status_lbl.pack(pady=5)

        def verify_and_save():
            btn.config(state="disabled")
            status_lbl.config(text="Validating key...", foreground="blue")
            
            def _check_key():
                test_key = key_var.get().strip()
                is_valid = validate_api_key(test_key)
                
                def _update_ui():
                    if is_valid:
                        save_api_key(test_key)
                        status_lbl.config(text="Authentication Successful! Key saved.", foreground="green")
                        modal.after(1500, modal.destroy)
                    else:
                        status_lbl.config(text="Invalid or expired API Key.", foreground="red")
                        btn.config(state="normal")
                
                modal.after(0, _update_ui)
                
            threading.Thread(target=_check_key, daemon=True).start()

        btn = ttk.Button(modal, text="Verify & Save", command=verify_and_save)
        btn.pack(pady=10)

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
                err_msg = str(exc)
                traceback.print_exc()

                def fail() -> None:
                    self._busy = False
                    self.progress.stop()
                    
                    if "NO_API_KEY" in err_msg or "401" in err_msg or "403" in err_msg:
                        self.status.set("Authentication failed. Please check API Key.")
                        self._show_api_settings()
                    else:
                        self.status.set(f"Error: {err_msg}")
                        messagebox.showerror("Error", err_msg)

                self.root.after(0, fail)

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
            pdfs = [Path(name) for name in filenames if name.lower().endswith(".pdf")]
            pdfs.sort()
            
            if not pdfs:
                messagebox.showwarning(self._t("no_pdf_title", lang), self._t("no_pdf_msg", lang))
                return
                
            self._start_jobs(pdfs)

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
            
        has_co = messagebox.askyesno(
            self._t("co_prompt_title", lang),
            self._t("co_prompt_msg", lang),
            parent=self.root
        )

        self._busy = True
        threading.Thread(target=self._run_jobs, args=(pdf_paths, has_co), daemon=True).start()

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status.set(message))

    def _run_jobs(self, pdf_paths: list[Path], has_declaration: bool) -> None:
        errors: list[str] = []
        saved: list[Path] = []
        lang = "th" if self.use_thai.get() else "en"
        
        self.root.after(0, lambda: self.progress.start(15))
        
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
                has_declaration=has_declaration
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
                self.progress.stop()
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
                self.progress.stop()
                self.status.set(f"Error: {err_msg}")
                messagebox.showerror("Error", err_msg)

            self.root.after(0, fail)

    def display_audit_results(self, pdf_name: str, result_str: str) -> None:
        popup = tk.Toplevel(self.root)
        popup.geometry("1360x840")
        popup.minsize(1080, 600)

        popup_lang = BooleanVar(value=self.use_thai.get())
        data = parse_audit_json(result_str)

        if not data or not data.get("audit_table"):
            popup.destroy()
            messagebox.showerror(
                "JSON Parsing Error", 
                "Gemini generated an invalid or badly formatted response.\n\nCheck your terminal window to see the raw output and identify the syntax error."
            )
            return

        data = reconcile_discrepancies(data)
        rows = data.get("audit_table", [])

        is_thai = self.use_thai.get()
        tag_inv = "【 ใบแจ้งหนี้ 】" if is_thai else "【 INVOICE 】"
        tag_nat = "【 ต้นฉบับ 】" if is_thai else "【 NATIVE 】"
        
        for row_idx, item in enumerate(rows):
            raw_field = str(item.get("field", "-"))
            cells = [
                raw_field,
                str(item.get("ci", "-")),
                str(item.get("pl", "-")),
                str(item.get("bl", "-")),
                str(item.get("co", "-")),
                str(item.get("master_db", "-")),
            ]

            for i in range(1, 6):
                if "(Invoice)" in cells[i]:
                    cells[i] = cells[i].replace("(Invoice)", tag_inv)
                if "(Native)" in cells[i]:
                    cells[i] = cells[i].replace("(Native)", tag_nat)

        top_bar = ttk.Frame(popup, padding=(14, 8, 14, 4))
        top_bar.pack(side=tk.TOP, fill=tk.X, expand=False)

        title_lbl = ttk.Label(top_bar, font=("Segoe UI", 12, "bold"))
        title_lbl.pack(side=tk.LEFT)

        lang_chk = ttk.Checkbutton(top_bar, variable=popup_lang)
        lang_chk.pack(side=tk.RIGHT)

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

        table_frame = ttk.Frame(popup, padding=(12, 4, 12, 4))
        table_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        v_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        h_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        inner_frame = tk.Frame(table_frame)
        inner_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        header_canvas = tk.Canvas(inner_frame, bg="#cbd5e1", highlightthickness=0, height=45)
        header_canvas.pack(side=tk.TOP, fill=tk.X)
        header_container = tk.Frame(header_canvas, bg="#cbd5e1")
        header_window = header_canvas.create_window((0, 0), window=header_container, anchor="nw")

        canvas = tk.Canvas(inner_frame, bg="#f1f5f9", highlightthickness=0)
        canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        grid_container = tk.Frame(canvas, bg="#cbd5e1")
        canvas_window = canvas.create_window((0, 0), window=grid_container, anchor="nw")

        def _on_h_scroll(*args):
            canvas.xview(*args)
            header_canvas.xview(*args)

        h_scroll.config(command=_on_h_scroll)
        v_scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        header_canvas.config(xscrollcommand=h_scroll.set)

        col_weights = [18, 16, 16, 18, 18, 14]
        for col_idx, weight in enumerate(col_weights):
            header_container.grid_columnconfigure(col_idx, weight=weight, minsize=170)
            grid_container.grid_columnconfigure(col_idx, weight=weight, minsize=170)

        col_cell_widgets: dict[int, list[tk.Label]] = {i: [] for i in range(6)}
        header_label_widgets: list[tk.Label] = []

        base_width = 1300
        initial_wraps = [max(int(w * base_width / 100) - 22, 140) for w in col_weights]

        for col_idx in range(6):
            hdr = tk.Label(
                header_container,
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

        for row_idx, item in enumerate(rows):
            raw_field = str(item.get("field", "-"))
            cells = [
                raw_field,
                str(item.get("ci", "-")),
                str(item.get("pl", "-")),
                str(item.get("bl", "-")),
                str(item.get("co", "-")),
                str(item.get("master_db", "-")),
            ]

            row_has_error = any("⚠️" in c or "[Printed as: BLANK/MISSING]" in c for c in cells[1:])

            for col_idx, cell_val in enumerate(cells):
                is_severe = (("⚠️" in cell_val or "[Printed as: BLANK/MISSING]" in cell_val) if col_idx > 0 else False)
                is_manual_review = ("🔍" in cell_val if col_idx > 0 else False)

                if is_severe:
                    bg_color, fg_color, font_style = "#fde8e8", "#991b1b", ("Segoe UI", 9, "bold")
                elif is_manual_review:
                    bg_color, fg_color, font_style = "#fef08a", "#854d0e", ("Segoe UI", 9, "bold")
                elif col_idx == 0:
                    bg_color = "#f8fafc"
                    fg_color = "#991b1b" if (row_has_error or "🔍" in str(cells)) else "#0f172a"
                    font_style = ("Segoe UI", 9, "bold" if (row_has_error or "🔍" in str(cells)) else "normal")
                else:
                    bg_color, fg_color, font_style = "#dcfce7", "#166534", ("Segoe UI", 9)

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
                cell_lbl.grid(row=row_idx, column=col_idx, sticky="nsew", padx=1, pady=1)
                col_cell_widgets[col_idx].append(cell_lbl)

                if col_idx == 0:
                    row_field_widgets.append((cell_lbl, raw_field))

        def _update_scrollregion(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            header_canvas.configure(scrollregion=header_canvas.bbox("all"))

        grid_container.bind("<Configure>", _update_scrollregion)
        header_container.bind("<Configure>", _update_scrollregion)

        last_width = [0]

        def _on_canvas_configure(event):
            cur_width = event.width
            if abs(cur_width - last_width[0]) < 8:
                return
            last_width[0] = cur_width

            target_width = max(cur_width - 4, 1260)
            canvas.itemconfig(canvas_window, width=target_width)
            header_canvas.itemconfig(header_window, width=target_width)

            for c_idx, weight in enumerate(col_weights):
                col_pixel_width = int(weight * target_width / 100)
                wrap_px = max(col_pixel_width - 22, 140)
                for widget in col_cell_widgets[c_idx]:
                    try:
                        widget.configure(wraplength=wrap_px)
                    except Exception:
                        pass

            popup.update_idletasks()
            _update_scrollregion()

        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            try:
                w = popup.winfo_containing(event.x_root, event.y_root)
                if w and (w == summary_text or "text" in str(w).lower()):
                    return
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        def _on_shift_mousewheel(event):
            try:
                if event.delta:
                    steps = int(-1 * (event.delta / 120))
                    canvas.xview_scroll(steps, "units")
                    header_canvas.xview_scroll(steps, "units")
            except Exception:
                pass

        popup.bind_all("<MouseWheel>", _on_mousewheel)
        popup.bind_all("<Shift-MouseWheel>", _on_shift_mousewheel)
        popup.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-2, "units"))
        popup.bind_all("<Button-5>", lambda e: canvas.yview_scroll(2, "units"))
        popup.bind("<Up>", lambda e: canvas.yview_scroll(-2, "units"))
        popup.bind("<Down>", lambda e: canvas.yview_scroll(2, "units"))
        popup.bind("<Prior>", lambda e: canvas.yview_scroll(-6, "units"))
        popup.bind("<Next>", lambda e: canvas.yview_scroll(6, "units"))

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