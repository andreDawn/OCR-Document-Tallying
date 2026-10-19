"""Dynamic application version resolver."""

from __future__ import annotations

import json
from pathlib import Path
from paths import get_app_dir, get_bundle_dir

FALLBACK_VERSION = "1.0.9"


def get_current_version() -> str:
    """Read version injected by CI/CD at build time, or fall back cleanly."""
    for base in [get_bundle_dir(), get_app_dir(), Path.cwd()]:
        v_file = base / "version.json"
        if v_file.is_file():
            try:
                data = json.loads(v_file.read_text(encoding="utf-8"))
                ver = str(data.get("version", "")).strip().lstrip("v")
                if ver:
                    return ver
            except Exception:
                pass
    return FALLBACK_VERSION