"""In-app background updater for Logistics PDF Auditor using GitHub Releases."""

from __future__ import annotations
from version import get_current_version

import os
import re
import subprocess
import sys
from pathlib import Path
import requests

GITHUB_REPO = "andreDawn/OCR-Document-Tallying"
CURRENT_VERSION = get_current_version()


def parse_version(v_str: str) -> tuple[int, ...]:
    """Extract numeric version tuple from strings like 'v1.0.2' -> (1, 0, 2)."""
    nums = re.findall(r"\d+", v_str)
    return tuple(int(n) for n in nums) if nums else (0,)


def check_for_updates() -> tuple[bool, str, str]:
    """Check GitHub Releases API.
    
    Returns:
        (update_available: bool, latest_version: str, download_url: str)
    """
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return False, CURRENT_VERSION, ""

        data = resp.json()
        latest_tag = data.get("tag_name", "").strip()
        if not latest_tag:
            return False, CURRENT_VERSION, ""

        if parse_version(latest_tag) > parse_version(CURRENT_VERSION):
            # Locate the .exe release asset
            for asset in data.get("assets", []):
                if asset.get("name", "").lower().endswith(".exe"):
                    return True, latest_tag, asset.get("browser_download_url", "")
            
            # Fallback if no asset attached directly
            return True, latest_tag, data.get("html_url", "")

        return False, CURRENT_VERSION, ""
    except Exception:
        return False, CURRENT_VERSION, ""


def apply_update_and_restart(download_url: str, progress_callback=None) -> None:
    """Download new executable and trigger self-replacing restart script."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("In-app updating only operates inside a compiled .exe.")

    target_exe = Path(sys.executable).resolve()
    temp_new_exe = target_exe.parent / "LogisticsAuditor_new.exe"
    updater_bat = target_exe.parent / "updater.bat"

    # 1. Download new executable
    with requests.get(download_url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total_len = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(temp_new_exe, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_len:
                        pct = int((downloaded / total_len) * 100)
                        progress_callback(pct)

    # 2. Write detached handoff batch script
    current_pid = os.getpid()
    bat_content = f"""@echo off
setlocal
timeout /t 1 /nobreak > nul

:wait_loop
tasklist /FI "PID eq {current_pid}" 2>NUL | find /I "{current_pid}" > nul
if not errorlevel 1 (
    timeout /t 1 /nobreak > nul
    goto wait_loop
)

move /y "{temp_new_exe}" "{target_exe}" > nul
start "" "{target_exe}"
del "%~f0"
"""
    updater_bat.write_text(bat_content, encoding="ascii")

    # 3. Launch handoff script detached and terminate current app
    subprocess.Popen(
        ["cmd.exe", "/c", str(updater_bat)],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        shell=False,
    )
    sys.exit(0)