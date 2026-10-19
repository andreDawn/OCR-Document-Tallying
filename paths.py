"""Filesystem path helpers for portable execution, PyInstaller bundling, and user config."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_bundle_dir() -> Path:
    """Return read-only PyInstaller temporary unpack dir (_MEIPASS) or repo root."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


def get_app_dir() -> Path:
    """Return persistent folder containing the .exe or main.py (never _MEIPASS)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_output_dir() -> Path:
    """Return the persistent output directory next to the application."""
    out = get_app_dir() / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def job_output_dir(report_path: Path) -> Path:
    """Return subdirectory inside output/ for a specific audit run."""
    job_dir = get_output_dir() / report_path.stem
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def get_user_config_path() -> Path:
    """Return persistent config path in %APPDATA%/LogisticsAuditor/config.json."""
    appdata = Path(os.getenv("APPDATA", Path.home()))
    cfg_dir = appdata / "LogisticsAuditor"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "config.json"