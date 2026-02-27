"""Auto-update: check GitHub Releases → download → swap → restart."""
import os
import sys
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .version import APP_VERSION

# GitHub repo info
GITHUB_OWNER = "huypv2002"
GITHUB_REPO = "Grok-API"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "GrokVideoGenerator-windows.zip"


def _parse_version(tag: str) -> tuple:
    """Parse 'v1.2.3' → (1, 2, 3) để so sánh."""
    tag = tag.lstrip("vV").strip()
    parts = []
    for p in tag.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_newer(remote_tag: str) -> bool:
    """So sánh remote tag với APP_VERSION hiện tại."""
    return _parse_version(remote_tag) > _parse_version(APP_VERSION)


class UpdateChecker(QThread):
    """Check GitHub Releases cho bản mới (chạy background)."""
    # (has_update, tag, download_url, release_notes, error)
    result = Signal(bool, str, str, str, str)

    def run(self):
        import httpx
        try:
            r = httpx.get(RELEASES_API, timeout=15, follow_redirects=True)
            if r.status_code != 200:
                self.result.emit(False, "", "", "", f"HTTP {r.status_code}")
                return
            data = r.json()
            tag = data.get("tag_name", "")
            body = data.get("body", "") or ""
            if not tag or not is_newer(tag):
                self.result.emit(False, tag, "", "", "")
                return
            # Tìm asset ZIP
            dl_url = ""
            for asset in data.get("assets", []):
                if asset.get("name", "") == ASSET_NAME:
                    dl_url = asset.get("browser_download_url", "")
                    break
            if not dl_url:
                self.result.emit(False, tag, "", body, "Không tìm thấy file ZIP trong release")
                return
            self.result.emit(True, tag, dl_url, body, "")
        except Exception as e:
            self.result.emit(False, "", "", "", str(e))


class UpdateDownloader(QThread):
    """Download ZIP + extract + tạo batch script swap."""
    progress = Signal(int)  # percent 0-100
    finished = Signal(bool, str)  # (ok, error_or_path)

    def __init__(self, download_url: str):
        super().__init__()
        self.download_url = download_url
        self._stopped = False

    def stop(self):
        self._stopped = True

    def run(self):
        import httpx
        try:
            # Thư mục tạm cạnh app (không dùng %TEMP% vì có thể khác ổ đĩa)
            app_dir = self._get_app_dir()
            update_dir = os.path.join(app_dir, "_update_tmp")
            if os.path.exists(update_dir):
                shutil.rmtree(update_dir, ignore_errors=True)
            os.makedirs(update_dir, exist_ok=True)

            zip_path = os.path.join(update_dir, ASSET_NAME)

            # Download với progress
            with httpx.stream("GET", self.download_url, timeout=300, follow_redirects=True) as r:
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=65536):
                        if self._stopped:
                            self.finished.emit(False, "Đã hủy")
                            return
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self.progress.emit(int(downloaded * 100 / total))

            self.progress.emit(100)

            # Extract ZIP
            extract_dir = os.path.join(update_dir, "extracted")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # Tìm thư mục GrokVideoGenerator bên trong
            new_app_dir = None
            for item in os.listdir(extract_dir):
                candidate = os.path.join(extract_dir, item)
                if os.path.isdir(candidate):
                    # Kiểm tra có exe không
                    exe_path = os.path.join(candidate, "GrokVideoGenerator.exe")
                    if os.path.exists(exe_path):
                        new_app_dir = candidate
                        break
            if not new_app_dir:
                # Có thể exe nằm trực tiếp trong extract_dir
                if os.path.exists(os.path.join(extract_dir, "GrokVideoGenerator.exe")):
                    new_app_dir = extract_dir
                else:
                    self.finished.emit(False, "Không tìm thấy GrokVideoGenerator.exe trong ZIP")
                    return

            self.finished.emit(True, new_app_dir)

        except Exception as e:
            self.finished.emit(False, str(e))

    @staticmethod
    def _get_app_dir() -> str:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def apply_update(new_app_dir: str):
    """Tạo batch script để swap bản cũ → bản mới rồi restart.
    
    Flow:
    1. Tạo _updater.bat cạnh exe hiện tại
    2. Batch script: chờ process cũ tắt → xóa file cũ (giữ data/) → copy bản mới → start exe mới → xóa _update_tmp
    3. App gọi os._exit() sau khi launch batch
    """
    app_dir = _get_app_dir()
    exe_name = "GrokVideoGenerator.exe"
    current_exe = os.path.join(app_dir, exe_name)
    current_pid = os.getpid()
    
    bat_path = os.path.join(app_dir, "_updater.bat")
    
    # Batch script: chờ process cũ tắt, swap files, start mới
    # Giữ nguyên data/, output/, _updater.bat sẽ tự xóa
    bat_content = f'''@echo off
chcp 65001 >nul
title Updating GrokVideoGenerator...
echo ============================================
echo   Dang cap nhat GrokVideoGenerator...
echo ============================================
echo.

:: Cho process cu tat (max 30s)
echo Cho ung dung cu dong lai...
set /a count=0
:wait_loop
tasklist /FI "PID eq {current_pid}" 2>nul | find /I "{current_pid}" >nul
if not errorlevel 1 (
    set /a count+=1
    if %count% GEQ 30 (
        echo Timeout! Force kill...
        taskkill /PID {current_pid} /F >nul 2>&1
        timeout /t 2 /nobreak >nul
        goto :do_update
    )
    timeout /t 1 /nobreak >nul
    goto :wait_loop
)

:do_update
echo Dang cap nhat files...
timeout /t 1 /nobreak >nul

:: Xoa tat ca file/folder cu NGOAI TRU: data, output, _update_tmp, _updater.bat
for %%F in ("{app_dir}\\*") do (
    if /I not "%%~nxF"=="_updater.bat" (
        if /I not "%%~nxF"=="_update_tmp" (
            del /F /Q "%%F" >nul 2>&1
        )
    )
)
for /D %%D in ("{app_dir}\\*") do (
    if /I not "%%~nxD"=="data" (
        if /I not "%%~nxD"=="output" (
            if /I not "%%~nxD"=="_update_tmp" (
                rmdir /S /Q "%%D" >nul 2>&1
            )
        )
    )
)

:: Copy ban moi vao (NGOAI TRU data/ va output/ cua ban moi — giu data cu)
echo Copy ban moi...
for %%F in ("{new_app_dir}\\*") do (
    copy /Y "%%F" "{app_dir}\\" >nul 2>&1
)
for /D %%D in ("{new_app_dir}\\*") do (
    if /I not "%%~nxD"=="data" (
        if /I not "%%~nxD"=="output" (
            xcopy /E /I /Y "%%D" "{app_dir}\\%%~nxD" >nul 2>&1
        )
    )
)

:: Xoa thu muc tam
echo Don dep...
rmdir /S /Q "{app_dir}\\_update_tmp" >nul 2>&1

:: Start ban moi
echo Khoi dong ban moi...
start "" "{app_dir}\\{exe_name}"

:: Tu xoa bat file
echo Cap nhat thanh cong!
timeout /t 2 /nobreak >nul
del /F /Q "%~f0" >nul 2>&1
exit
'''
    
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    
    # Launch batch script (detached) rồi thoát app
    import subprocess
    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
        close_fds=True
    )


def _get_app_dir() -> str:
    """Lấy thư mục chứa exe hiện tại."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
