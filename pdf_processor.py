"""Flatten PDF pages to 300 DPI JPEGs with PyMuPDF. No local OCR is performed."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from config import JPEG_DPI, JPEG_QUALITY
from paths import job_output_dir


def flatten_pdf_to_jpegs(
    pdf_path: Path,
    dpi: int = JPEG_DPI,
    quality: int = JPEG_QUALITY,
) -> list[Path]:
    """Render every page of pdf_path to JPEG files at 300 DPI."""
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    out_dir = job_output_dir(pdf_path)
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    jpeg_paths: list[Path] = []

    with pymupdf.open(pdf_path) as document:
        if document.page_count == 0:
            raise ValueError(f"PDF has no pages: {pdf_path}")

        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            jpeg_path = out_dir / f"page_{index:03d}.jpg"
            pixmap.save(str(jpeg_path), output="jpeg", jpg_quality=quality)
            jpeg_paths.append(jpeg_path)

    return jpeg_paths