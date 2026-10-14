"""Dynamic application version resolver."""

from __future__ import annotations

import json
from pathlib import Path
from paths import get_bundle_dir, get_app_dir

FALLBACK_VERSION = "1.0.0-dev"


def get_current_version() -> str:
    """Read version dynamically injected during build, or fall back to dev version."""
    for base in [get_bundle_dir(), get_app_dir(), Path.cwd()]:
        v_file = base / "version.json"
        if v_file.is_file():
            try:
                data = json.loads(v_file.read_text(encoding="utf-8"))
                return data.get("version", FALLBACK_VERSION).lstrip("v")
            except Exception:
                pass
    return FALLBACK_VERSION