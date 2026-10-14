"""Filesystem paths for application data, configuration, and job outputs."""

from __future__ import annotations

import sys
from pathlib import Path


def get_bundle_dir() -> Path:
    """Return directory where internal bundled assets (.env) are unpacked."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def get_app_dir() -> Path:
    """Return directory where the user launched the .exe (for output/ folder)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def output_root() -> Path:
    """Return the output/ directory next to the application."""
    out = get_app_dir() / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def job_output_dir(identifier: Path | str) -> Path:
    """Return a sub-folder under output/ for a specific audit report run."""
    stem = Path(identifier).stem
    job_dir = output_root() / stem
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir