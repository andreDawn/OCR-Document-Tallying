"""Gemini API client handling PDF page extraction and structured JSON auditing."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from google import genai
from google.genai import types

from config import (
    MODEL_CASCADE,
    SYSTEM_INSTRUCTION,
    USER_PROMPT_TEMPLATE,
    MASTER_DB_SOURCE_NAME,
    get_gemini_api_key,
)


def _build_user_prompt(
    pdf_path: Path,
    page_count: int,
    master_db_excerpt: str,
    use_thai: bool,
) -> str:
    language_command = (
        "LANGUAGE INSTRUCTION: Output ALL field/row names, watermark warnings, and "
        "discrepancy summary descriptions in THAI. HOWEVER, ALL EXTRACTED VALUE STRINGS "
        "INSIDE TABLE DATA CELLS (ci, pl, bl, co, master_db) MUST REMAIN STRICTLY IN ORIGINAL ENGLISH VERBATIM."
        if use_thai
        else "LANGUAGE INSTRUCTION: Output all JSON text in ENGLISH. All extracted value strings inside data cells must remain in English verbatim."
    )
    return USER_PROMPT_TEMPLATE.format(
        pdf_name=pdf_path.name,
        page_count=page_count,
        master_db_name=MASTER_DB_SOURCE_NAME,
        master_db_excerpt=master_db_excerpt,
        language_command=language_command,
    )


def extract_from_jpegs(
    pdf_path: Path,
    jpeg_paths: list[Path],
    master_db_excerpt: str,
    use_thai: bool = False,
    status_callback: Callable[[str], None] | None = None,
) -> str:
    """Upload JPEGs to Gemini Vision with structured JSON output, timeouts, and transient retry handling."""
    if not jpeg_paths:
        raise ValueError("No JPEG images were provided for extraction.")

    # Strict 30-second HTTP request timeout
    client = genai.Client(
        api_key=get_gemini_api_key(),
        http_options=types.HttpOptions(timeout=30000),
    )

    uploaded_files = []
    try:
        # 1. Upload page JPEGs
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

        prompt = _build_user_prompt(
            pdf_path=pdf_path,
            page_count=len(jpeg_paths),
            master_db_excerpt=master_db_excerpt,
            use_thai=use_thai,
        )

        last_error: Exception | None = None

        # 2. Try models in cascade with transient 503/429 retries
        for model_name in MODEL_CASCADE:
            for attempt in range(2):
                try:
                    if status_callback:
                        msg = (
                            f"กำลังตรวจสอบด้วย {model_name}..."
                            if use_thai
                            else f"Auditing with {model_name}..."
                        )
                        status_callback(msg)

                    response = client.models.generate_content(
                        model=model_name,
                        contents=[prompt, *uploaded_files],
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            response_mime_type="application/json",
                            temperature=0.1,
                            top_p=0.95,
                            max_output_tokens=8192,
                        ),
                    )
                    text = (getattr(response, "text", None) or "").strip()
                    if not text:
                        raise RuntimeError("Gemini returned an empty response.")
                    return text

                except Exception as exc:
                    last_error = exc
                    err_str = str(exc)

                    # Check for transient demand or rate spikes
                    is_transient = any(
                        token in err_str
                        for token in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]
                    )

                    if is_transient and attempt == 0:
                        if status_callback:
                            retry_msg = (
                                f"{model_name} กำลังมีผู้ใช้งานหนาแน่น (503/429) รอ 3 วินาทีเพื่อลองใหม่..."
                                if use_thai
                                else f"{model_name} busy/rate-limited (503/429). Retrying in 3s..."
                            )
                            status_callback(retry_msg)
                        time.sleep(3)
                        continue

                    if status_callback:
                        switch_msg = (
                            f"รุ่น {model_name} ไม่พร้อมใช้งาน กำลังเปลี่ยนรุ่นถัดไป..."
                            if use_thai
                            else f"{model_name} unavailable. Switching to next model..."
                        )
                        status_callback(switch_msg)
                    break

        raise RuntimeError(f"All models in cascade failed. Last error: {last_error}")

    finally:
        for f in uploaded_files:
            try:
                client.files.delete(name=f.name)
            except Exception:
                pass


def save_markdown(pdf_path: Path, content: str, out_dir: Path) -> Path:
    """Save raw JSON audit report to destination path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{pdf_path.stem}.json"
    out_file.write_text(content, encoding="utf-8")
    return out_file