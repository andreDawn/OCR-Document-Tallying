"""In-app background updater for Logistics PDF Auditor using GitHub Releases."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
import requests

from version import get_current_version

GITHUB_REPO = "andreDawn/OCR-Document-Tallying"


def parse_version(v_str: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v_str)
    return tuple(int(n) for n in nums) if nums else (0,)


def check_for_updates() -> tuple[bool, str, str]:
    """Check GitHub Releases API.
    
    Returns:
        (update_available: bool, latest_version: str, download_url: str)
    """
    current_ver = get_current_version()
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "DawnShipping-LogisticsAuditor",
        }
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return False, current_ver, ""

        data = resp.json()
        latest_tag = data.get("tag_name", "").strip()
        if not latest_tag:
            return False, current_ver, ""

        if parse_version(latest_tag) > parse_version(current_ver):
            for asset in data.get("assets", []):
                if asset.get("name", "").lower().endswith(".exe"):
                    return True, latest_tag, asset.get("browser_download_url", "")
            return True, latest_tag, data.get("html_url", "")

        return False, current_ver, ""
    except Exception:
        return False, current_ver, ""


def apply_update_and_restart(download_url: str, progress_callback=None) -> None:
    """Download new executable and trigger self-replacing restart script."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("In-app updating only operates inside a compiled .exe.")

    target_exe = Path(sys.executable).resolve()
    temp_new_exe = target_exe.parent / "LogisticsAuditor_new.exe"
    updater_bat = target_exe.parent / "updater.bat"

    with requests.get(
        download_url,
        headers={"User-Agent": "DawnShipping-LogisticsAuditor"},
        stream=True,
        timeout=60,
    ) as resp:
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

    subprocess.Popen(
        ["cmd.exe", "/c", str(updater_bat)],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        shell=False,
    )
    sys.exit(0)