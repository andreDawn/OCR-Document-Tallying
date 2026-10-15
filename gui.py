"""Tkinter desktop UI: 18-field auditing, dynamic versioning, and auto-update flow."""

from __future__ import annotations

import json
import re
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

# Master definition table: (field_pattern, summary_pattern_override, thai_label)
FIELD_DEFINITIONS = [
    (r"(shipper|exporter).*addr",       None,                            "2. ที่อยู่ผู้ส่งสินค้า (Shipper Address)"),
    (r"shipper|exporter",              r"(shipper|exporter)(?!.*addr)", "1. ชื่อผู้ส่งสินค้า (Shipper Name)"),
    (r"consignee.*addr",               None,                            "4. ที่อยู่ผู้รับตราส่ง (Consignee Address)"),
    (r"consignee",                     r"consignee(?!.*addr)",          "3. ชื่อผู้รับตราส่ง (Consignee Name)"),
    (r"notify",                        None,                            "5. ผู้รับแจ้ง (Notify Party)"),
    (r"document|reference|invoice",   None,                            "6. เลขที่เอกสารอ้างอิง (Doc No.)"),
    (r"\bdate\b",                      None,                            "7. วันที่เอกสาร (Doc Date)"),
    (r"desc|goods",                    None,                            "8. รายการสินค้า (Description of Goods)"),
    (r"quant|pack",                    None,                            "9. จำนวนและลักษณะหีบห่อ (Qty & Packages)"),
    (r"net\s*weight|\bnw\b",           None,                            "10. น้ำหนักสุทธิ (Net Weight - NW)"),
    (r"gross\s*weight|\bgw\b",         None,                            "11. น้ำหนักรวม (Gross Weight - GW)"),
    (r"volume|cbm",                    None,                            "12. ปริมาตรสินค้า (Volume - CBM)"),
    (r"hs\s*code",                     None,                            "13. พิกัดศุลกากร (HS Code)"),
    (r"price|amount",                  None,                            "14. ราคาต่อหน่วยและยอดรวม (Price & Amount)"),
    (r"marks?",                        None,                            "15. เครื่องหมายการขนส่ง (Shipping Marks)"),
    (r"vessel|voyage|flight",          None,                            "16. ชื่อเรือ / เที่ยวบิน / ลำดับเที่ยว (Vessel / Voyage)"),
    (r"loading|\bpol\b",               None,                            "17. ท่าเรือต้นทาง / บรรทุก (Port of Loading - POL)"),
    (r"discharge|\bpod\b|destination", None,                            "18. ท่าเรือปลายทาง (Port of Discharge - POD)"),
]

DOC_PATTERNS = {
    "ci": r"\b(ci|commercial\s+invoice)\b",
    "pl": r"\b(pl|packing\s+list)\b",
    "bl": r"\b(bl|b/?l|bill\s+of\s+lading)\b",
    "co": r"\b(co|c/?o|certificate\s+of\s+origin)\b",
    "master_db": r"\b(master\s+db|database)\b",
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


def _translate_field_to_thai(raw_field: str) -> str:
    return next((thai for f_pat, _, thai in FIELD_DEFINITIONS if re.search(f_pat, raw_field, re.I)), raw_field)


def reconcile_discrepancies(data: dict) -> dict:
    rows = data.get("audit_table", [])
    summaries = data.get("discrepancy_summary", [])
    if not isinstance(summaries, list) or not rows:
        return data

    for summary in summaries:
        target_docs = [col for col, pat in DOC_PATTERNS.items() if re.search(pat, summary, re.I)]
        cols = target_docs if target_docs else ["ci", "pl", "bl", "co", "master_db"]

        for row in rows:
            fname = str(row.get("field", ""))
            is_match = any(
                re.search(f_pat, fname, re.I) and re.search(s_pat or f_pat, summary, re.I)
                for f_pat, s_pat, _ in FIELD_DEFINITIONS
            )
            if is_match:
                for col in cols:
                    val = str(row.get(col, "")).strip()
                    if val and val != "-" and not val.startswith("⚠️"):
                        row[col] = f"⚠️ {val}"

    return data

class LogisticsAuditorApp:
    """Desktop GUI with 18-row auditing, auto-updates, and bilingual support."""

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

    def _t(self, key: str) -> str:
        lang = "th" if self.use_thai.get() else "en"
        return UI_TEXT[lang].get(key, key)

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
        messagebox.showinfo(self._t("about_title"), _get_about_text(lang))

    def _update_ui_language(self) -> None:
        self.root.title(self._t("app_title"))
        self.title_label.config(text=self._t("header_title"))
        self.recent_btn.config(text=self._t("recent_btn"))
        self.new_btn.config(text=self._t("new_btn"))
        self.about_btn.config(text=self._t("about_btn"))
        self.hint_label.config(text=self._t("hint"))
        self.drop_zone.config(text=self._t("drop_zone"))
        self.chk_thai.config(text=self._t("chk_thai"))
        self.footer_label.config(text=self._t("company_footer"))

        if self._latest_ver:
            self.update_btn.config(text=self._t("update_btn").format(ver=self._latest_ver))

        if not self._busy:
            self.status.set(self._t("ready"))

    def _check_updates_background(self) -> None:
        def _worker():
            has_update, latest_ver, dl_url = check_for_updates()
            if has_update and dl_url:
                self._latest_ver = latest_ver
                self._download_url = dl_url
                self.root.after(0, self._reveal_update_button)

        threading.Thread(target=_worker, daemon=True).start()

    def _reveal_update_button(self) -> None:
        btn_text = self._t("update_btn").format(ver=self._latest_ver)
        self.update_btn.config(text=btn_text)
        self.update_btn.pack(side=tk.LEFT, padx=3, before=self.recent_btn)

    def _start_update_flow(self) -> None:
        title = self._t("update_prompt_title")
        msg = self._t("update_prompt_msg").format(ver=self._latest_ver)
        if not messagebox.askyesno(title, msg):
            return

        self._busy = True
        self.update_btn.config(state="disabled")

        def _worker():
            try:
                def on_progress(pct: int):
                    self._set_status(self._t("updating_status").format(pct=pct))

                apply_update_and_restart(self._download_url, progress_callback=on_progress)
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("Update Error", str(exc)))
                self._busy = False
                self.update_btn.config(state="normal")

        threading.Thread(target=_worker, daemon=True).start()

    def _enable_drag_and_drop(self) -> None:
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event) -> None:
        paths = self._parse_dropped_paths(event.data)
        pdfs = [path for path in paths if path.suffix.lower() == ".pdf"]
        if not pdfs:
            messagebox.showwarning(self._t("no_pdf_title"), self._t("no_pdf_msg"))
            return
        self._start_jobs(pdfs)

    def _parse_dropped_paths(self, data: str) -> list[Path]:
        try:
            raw_items = self.root.tk.splitlist(data)
        except tk.TclError:
            raw_items = data.split()
        return [Path(item.strip("{}")) for item in raw_items if item.strip()]

    def _browse_files(self) -> None:
        filenames = filedialog.askopenfilenames(
            title=self._t("browse_title"),
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if filenames:
            self._start_jobs([Path(name) for name in filenames])

    def _generate_report_name(self, result_str: str) -> str:
        shipper_name = ""
        try:
            data = json.loads(result_str)
        except Exception:
            clean_str = result_str.replace("```json", "").replace("```", "").strip()
            try:
                data = json.loads(clean_str)
            except Exception:
                data = {}

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
        recent_files = self._get_recent_audit_files()
        if not recent_files:
            messagebox.showinfo(self._t("no_recent_title"), self._t("no_recent_msg"))
            return

        popup = tk.Toplevel(self.root)
        popup.title(self._t("recent_title"))
        popup.geometry("580x380")
        popup.resizable(False, False)

        ttk.Label(
            popup,
            text=self._t("recent_heading"),
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
                messagebox.showwarning(self._t("select_warn_title"), self._t("select_warn_msg"))
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

        ttk.Button(btn_frame, text=self._t("open_btn"), command=open_selected).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text=self._t("cancel_btn"), command=popup.destroy).pack(side=tk.RIGHT, padx=4)

    def _start_jobs(self, pdf_paths: list[Path]) -> None:
        if self._busy:
            messagebox.showinfo(self._t("busy_title"), self._t("busy_msg"))
            return
        self._busy = True
        threading.Thread(target=self._run_jobs, args=(pdf_paths,), daemon=True).start()

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status.set(message))

    def _run_jobs(self, pdf_paths: list[Path]) -> None:
        errors: list[str] = []
        saved: list[Path] = []
        is_thai = self.use_thai.get()
        try:
            self._set_status(self._t("status_db"))
            master_excerpt = load_master_database_excerpt()

            all_jpegs: list[Path] = []
            for pdf_path in pdf_paths:
                self._set_status(self._t("status_flatten").format(name=pdf_path.name))
                all_jpegs.extend(flatten_pdf_to_jpegs(pdf_path))

            self._set_status(self._t("status_upload").format(count=len(all_jpegs)))

            result_str = extract_from_jpegs(
                pdf_path=pdf_paths[0],
                jpeg_paths=all_jpegs,
                master_db_excerpt=master_excerpt,
                use_thai=is_thai,
                status_callback=self._set_status,
            )

            report_name = self._generate_report_name(result_str)
            report_path = Path(report_name)
            out_dir = job_output_dir(report_path)

            result_path = save_markdown(report_path, result_str, out_dir)
            saved.append(result_path)

            self._set_status(self._t("status_saved").format(name=result_path.name))
            self.root.after(0, lambda: self.display_audit_results(report_name, result_str))

            def finish() -> None:
                self._busy = False
                if saved and not errors:
                    self.status.set(self._t("status_success").format(name=report_name))
                elif errors:
                    self.status.set(self._t("status_failed"))
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
        is_thai = self.use_thai.get()
        popup = tk.Toplevel(self.root)
        popup.title(self._t("audit_popup_title").format(name=pdf_name))
        popup.geometry("1300x800")

        try:
            data = json.loads(result_str)
        except Exception:
            clean_str = result_str.replace("```json", "").replace("```", "").strip()
            try:
                data = json.loads(clean_str)
            except Exception:
                data = {}

        data = reconcile_discrepancies(data)

        top_frame = ttk.Frame(popup)
        top_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        lang = "th" if is_thai else "en"
        headers = UI_TEXT[lang]["headers"]

        canvas = tk.Canvas(top_frame, bg="#f1f5f9", highlightthickness=0)
        v_scroll = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=canvas.yview)
        h_scroll = ttk.Scrollbar(top_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        grid_container = tk.Frame(canvas, bg="#cbd5e1")

        def _update_scrollregion(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        grid_container.bind("<Configure>", _update_scrollregion)
        canvas.create_window((0, 0), window=grid_container, anchor="nw")
        canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))

        for col_idx, header_text in enumerate(headers):
            col_width = 24 if col_idx == 0 else 22
            hdr = tk.Label(
                grid_container,
                text=header_text,
                font=("Segoe UI", 9, "bold"),
                bg="#e2e8f0",
                fg="#1e293b",
                width=col_width,
                padx=8,
                pady=8,
                anchor="w",
                relief=tk.FLAT,
            )
            hdr.grid(row=0, column=col_idx, sticky="nsew", padx=1, pady=1)

        rows = data.get("audit_table", [])
        for row_idx, item in enumerate(rows, start=1):
            raw_field = str(item.get("field", "-"))
            field_display = _translate_field_to_thai(raw_field) if is_thai else raw_field

            cells = [
                field_display,
                str(item.get("ci", "-")),
                str(item.get("pl", "-")),
                str(item.get("bl", "-")),
                str(item.get("co", "-")),
                str(item.get("master_db", "-")),
            ]

            row_has_error = any("⚠️" in c or "[Printed as: BLANK/MISSING]" in c for c in cells[1:])

            for col_idx, cell_val in enumerate(cells):
                col_width = 24 if col_idx == 0 else 22
                is_flagged = ("⚠️" in cell_val or "[Printed as: BLANK/MISSING]" in cell_val) if col_idx > 0 else False

                if is_flagged:
                    bg_color = "#fde8e8"
                    fg_color = "#991b1b"
                    font_style = ("Segoe UI", 9, "bold")
                elif col_idx == 0:
                    bg_color = "#f8fafc"
                    fg_color = "#991b1b" if row_has_error else "#0f172a"
                    font_style = ("Segoe UI", 9, "bold" if row_has_error else "normal")
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
                    width=col_width,
                    padx=8,
                    pady=6,
                    anchor="nw",
                    justify=tk.LEFT,
                    wraplength=190,
                )
                cell_lbl.grid(row=row_idx, column=col_idx, sticky="nsew", padx=1, pady=1)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        bottom_frame = ttk.LabelFrame(popup, text=self._t("summary_title"), padding=10)
        bottom_frame.pack(fill=tk.BOTH, expand=False, padx=12, pady=(0, 10))

        summary_text = tk.Text(
            bottom_frame,
            wrap="word",
            height=7,
            font=("Segoe UI", 10),
            bg="#f8f9fa",
            relief=tk.FLAT,
        )
        summary_scroll = ttk.Scrollbar(bottom_frame, orient=tk.VERTICAL, command=summary_text.yview)
        summary_text.configure(yscrollcommand=summary_scroll.set)

        summary_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        summary_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        watermark = str(data.get("watermark_warning", "None"))
        summaries = data.get("discrepancy_summary", [])

        summary_content = ""
        if watermark and watermark.lower() not in ("none", "null", ""):
            wm_label = self._t("watermark_label")
            summary_content += f"{wm_label} {watermark}\n\n"

        if isinstance(summaries, list) and summaries:
            summary_content += "\n".join(f"• {s}" for s in summaries)
        elif isinstance(summaries, str) and summaries:
            summary_content += summaries
        else:
            summary_content += self._t("no_discrepancy")

        summary_text.insert("1.0", summary_content)
        summary_text.config(state="disabled")

    def run(self) -> None:
        self.root.mainloop()