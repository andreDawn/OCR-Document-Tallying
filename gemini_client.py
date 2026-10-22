"""Gemini Vision client with dynamic model discovery, jittered backoff, and robust error trapping."""

from __future__ import annotations

import random
import time
import json
from pathlib import Path
from typing import Callable, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

# Pydantic Schemas for Strict JSON Enforcement ---
class RowData(BaseModel):
    field: Literal[
        "1. Shipper / Exporter Name",
        "2. Shipper / Exporter Address",
        "3. Consignee Name",
        "4. Consignee Address",
        "5. Notify Party Name & Address",
        "6. Document / Reference No.",
        "7. Document Date",
        "8. Description of Goods",
        "9. Quantity & Packages",
        "10. Net Weight (NW)",
        "11. Gross Weight (GW)",
        "12. Volume (CBM)",
        "13. HS Code",
        "14. Unit Price & Total Amount",
        "15. Shipping Marks",
        "16. Vessel / Flight / Voyage No.",
        "17. Port of Loading (POL)",
        "18. Port of Discharge (POD)"
    ]
    ci: str
    pl: str
    bl: str
    co: str
    master_db: str
    discrepancy_note: str 

class SemanticValidation(BaseModel):
    shipper_info_matches: bool
    consignee_info_matches: bool
    notify_party_matches: bool
    description_is_valid_summary: bool

class AuditResult(BaseModel):
    watermark_warning: str
    semantic_validation: SemanticValidation
    audit_table: list[RowData]

RowData.model_rebuild()
SemanticValidation.model_rebuild()
AuditResult.model_rebuild()

from config import (
    MASTER_DB_SOURCE_NAME,
    MODEL_CASCADE,
    SYSTEM_INSTRUCTION,
    USER_PROMPT_TEMPLATE,
    get_gemini_api_key,
)

CONFIG_FILE = Path.home() / ".dawn_auditor_config.json"

def get_saved_api_key() -> str:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("api_key", "")
        except Exception:
            return ""
    return ""

def save_api_key(api_key: str) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump({"api_key": api_key}, f)

def validate_api_key(api_key: str) -> bool:
    try:
        test_client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=10000) 
        )
        model_pager = test_client.models.list()
        next(model_pager) 
        return True
        
    except Exception as e:
        print("\n" + "="*50)
        print("🚨 API VALIDATION FAILED. ACTUAL ERROR:")
        print(str(e))
        print("="*50 + "\n")
        return False

def _get_live_fallback_models(client: genai.Client) -> list[str]:
    """Query Google API for any currently active generateContent models as an emergency fallback."""
    try:
        available: list[str] = []
        for m in client.models.list():
            name = m.name.replace("models/", "")
            actions = getattr(m, "supported_actions", []) or []
            if "generateContent" in actions and "flash" in name.lower() and "preview" not in name.lower():
                available.append(name)
        return available
    except Exception:
        return []


def extract_from_jpegs(
    pdf_path: Path,
    jpeg_paths: list[Path],
    master_db_excerpt: str,
    use_thai: bool = False,
    status_callback: Callable[[str], None] | None = None,
    has_declaration: bool = False, 
) -> str:
    """Upload JPEGs to Gemini Vision with jittered retry and dynamic self-healing cascade."""
    if not jpeg_paths:
        raise ValueError("No JPEG images were provided for extraction.")

    api_key = get_saved_api_key()
    if not api_key:
        raise RuntimeError("No Gemini API key found. Please configure your key in Settings.")

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60000),
    )

    uploaded_files = []
    try:
        for i, img_path in enumerate(jpeg_paths, start=1):
            if status_callback:
                msg = (
                    f"กำลังอัปโหลดหน้า {i}/{len(jpeg_paths)} ไปยัง Gemini..."
                    if use_thai
                    else f"Uploading page {i}/{len(jpeg_paths)} to Gemini..."
                )
                status_callback(msg)
            f = client.files.upload(file=img_path)
            uploaded_files.append(f)

        prompt = USER_PROMPT_TEMPLATE.format(
            pdf_name=pdf_path.name,
            page_count=len(jpeg_paths),
            master_db_name=MASTER_DB_SOURCE_NAME,
            master_db_excerpt=master_db_excerpt,
        )
        
        active_system_instruction = SYSTEM_INSTRUCTION
        if has_declaration:
            active_system_instruction += "\n- DECLARATION FORMS: If processing a Declaration Form, extract the INVOICE DATE and INVOICE REFERENCE NUMBER instead of the form's own internal reference number."

        cascade_errors: list[str] = []
        attempt_models = list(MODEL_CASCADE)

        for model_name in attempt_models:
            max_attempts = 2
            for attempt in range(max_attempts):
                try:
                    if status_callback:
                        retry_info = f" (Attempt {attempt + 1})" if attempt > 0 else ""
                        msg = (
                            f"กำลังตรวจสอบด้วย {model_name}{retry_info}..."
                            if use_thai
                            else f"Auditing with {model_name}{retry_info}..."
                        )
                        status_callback(msg)

                    response = client.models.generate_content(
                        model=model_name,
                        contents=[prompt, *uploaded_files],
                        config=types.GenerateContentConfig(
                            system_instruction=active_system_instruction, 
                            response_mime_type="application/json",
                            response_schema=AuditResult,  # <--- ADD THIS LINE
                            temperature=0.1,
                            top_p=0.95,
                            # max_output_tokens=8192, # (Optional: Pro handles token limits natively)
                        ),
                    )
                    text = (getattr(response, "text", None) or "").strip()
                    
                    print("\n" + "="*40)
                    print("RAW GEMINI OUTPUT:")
                    print(text)
                    print("="*40 + "\n")
                    
                    if not text:
                        raise RuntimeError(f"{model_name} returned an empty response.")
                    return text

                except Exception as exc:
                    err_str = str(exc)
                    is_transient = any(
                        token in err_str
                        for token in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED"]
                    )

                    if is_transient and attempt < max_attempts - 1:
                        sleep_time = round(2.0 * (2 ** attempt) + random.uniform(0.5, 1.5), 1)
                        if status_callback:
                            msg = (
                                f"{model_name} ผู้ใช้งานหนาแน่น (503/429) รอ {sleep_time} วินาที..."
                                if use_thai
                                else f"{model_name} busy (503/429). Retrying in {sleep_time}s..."
                            )
                            status_callback(msg)
                        time.sleep(sleep_time)
                        continue

                    cascade_errors.append(f"• [{model_name}]: {err_str}")

                    if status_callback:
                        switch_msg = (
                            f"รุ่น {model_name} ไม่พร้อมใช้งาน กำลังเปลี่ยนรุ่นถัดไป..."
                            if use_thai
                            else f"{model_name} unavailable. Switching to next model..."
                        )
                        status_callback(switch_msg)
                    break

        live_fallbacks = [m for m in _get_live_fallback_models(client) if m not in attempt_models]
        for fallback_model in live_fallbacks:
            try:
                if status_callback:
                    status_callback(f"Connecting to live fallback: {fallback_model}...")

                response = client.models.generate_content(
                    model=fallback_model,
                    contents=[prompt, *uploaded_files],
                    config=types.GenerateContentConfig(
                        system_instruction=active_system_instruction,
                        response_mime_type="application/json",
                        response_schema=AuditResult,  # <--- ADD THIS LINE
                        temperature=0.1,
                        top_p=0.95,
                    ),
                )
                text = (getattr(response, "text", None) or "").strip()
                if text:
                    return text
            except Exception as exc:
                cascade_errors.append(f"• [{fallback_model}]: {exc}")

        error_summary = "\n\n".join(cascade_errors)
        raise RuntimeError(f"All models in cascade failed:\n\n{error_summary}")

    finally:
        for f in uploaded_files:
            try:
                client.files.delete(name=f.name)
            except Exception:
                pass


def save_markdown(report_path: Path, content: str, output_dir: Path) -> Path:
    """Save the raw audit JSON result to the designated output folder."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{report_path.stem}.json"
    out_file.write_text(content, encoding="utf-8")
    return out_file