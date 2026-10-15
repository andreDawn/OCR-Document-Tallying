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
    """Check GitHub Releases API for newer compiled binaries."""
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
            return False, current_ver, ""

        return False, current_ver, ""
    except Exception:
        return False, current_ver, ""


def apply_update_and_restart(download_url: str, new_version: str = "", progress_callback=None) -> None:
    """Download versioned executable, remove old version, and relaunch."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("In-app updating only operates inside a compiled .exe.")

    target_exe = Path(sys.executable).resolve()

    ver_tag = new_version.strip()
    if ver_tag and not ver_tag.startswith("v"):
        ver_tag = f"v{ver_tag}"

    final_name = f"LogisticsAuditor_{ver_tag}.exe" if ver_tag else "LogisticsAuditor.exe"
    final_exe = target_exe.parent / final_name
    temp_download = target_exe.parent / f"~download_{final_name}"
    stray_new_exe = target_exe.parent / "LogisticsAuditor_new.exe"
    updater_bat = target_exe.parent / "updater.bat"

    try:
        with requests.get(
            download_url,
            headers={"User-Agent": "DawnShipping-LogisticsAuditor"},
            stream=True,
            timeout=60,
        ) as resp:
            resp.raise_for_status()
            total_len = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(temp_download, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_len:
                            pct = int((downloaded / total_len) * 100)
                            progress_callback(pct)
    except Exception:
        if temp_download.exists():
            temp_download.unlink(missing_ok=True)
        raise

    current_pid = os.getpid()
    bat_content = f"""@echo off
setlocal
:: Strip PyInstaller environment variables to prevent DLL load errors
set "_MEIPASS2="
set "_MEIPASS="
timeout /t 1 /nobreak > nul

:wait_loop
tasklist /FI "PID eq {current_pid}" 2>NUL | find /I "{current_pid}" > nul
if not errorlevel 1 (
    timeout /t 1 /nobreak > nul
    goto wait_loop
)

:: Place the new versioned executable
move /y "{temp_download}" "{final_exe}" > nul

:: Delete the old executable if its name differs from the new version
if /I not "{target_exe}"=="{final_exe}" (
    del /f /q "{target_exe}" > nul
)

:: Clean up any leftover LogisticsAuditor_new.exe from previous runs
if exist "{stray_new_exe}" (
    del /f /q "{stray_new_exe}" > nul
)

:: Launch the updated versioned executable
start "" "{final_exe}"

:: Delete this batch script
del "%~f0"
"""
    updater_bat.write_text(bat_content, encoding="ascii")

    clean_env = os.environ.copy()
    clean_env.pop("_MEIPASS2", None)
    clean_env.pop("_MEIPASS", None)

    subprocess.Popen(
        ["cmd.exe", "/c", str(updater_bat)],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        env=clean_env,
        shell=False,
    )

    os._exit(0)