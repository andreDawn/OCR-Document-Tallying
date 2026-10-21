"""Application version reader supporting PyInstaller bundled version.json."""

from __future__ import annotations

import json
from pathlib import Path
import sys

FALLBACK_VERSION = "1.1.0"


def get_current_version() -> str:
  """Read version from injected version.json (in .exe) or live git/fallback (in dev)."""
  # 1. Check for bundled version.json inside PyInstaller's extraction folder
  base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
  version_file = base_path / "version.json"

  if version_file.exists():
    try:
      data = json.loads(version_file.read_text(encoding="utf-8"))
      return data.get("version", FALLBACK_VERSION)
    except Exception:
      pass

  # 2. Local development fallback (when running directly from python main.py)
  return FALLBACK_VERSION