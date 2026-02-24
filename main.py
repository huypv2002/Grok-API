#!/usr/bin/env python3
"""X Grok Multi-Account Video Generator - Entry Point"""
import sys
import os

# === BƯỚC 1: Capture __nuitka_binary_dir NGAY LẬP TỨC ===
_NUITKA_BINARY_DIR = None
try:
    _NUITKA_BINARY_DIR = __nuitka_binary_dir  # type: ignore[name-defined]
except NameError:
    pass

# === BƯỚC 2: Crash log vào %TEMP% - LUÔN HOẠT ĐỘNG trên Windows ===
def _write_temp_log(msg):
    """Ghi log vào %TEMP% - nơi luôn ghi được trên Windows."""
    try:
        import datetime
        tmp = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~")
        log_path = os.path.join(tmp, "GrokVideoGenerator_crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass

# === BƯỚC 3: Python 3.13 compat ===
try:
    import distutils  # noqa: F401
except ModuleNotFoundError:
    try:
        import setuptools._distutils as _d
        sys.modules["distutils"] = _d
        import importlib
        sys.modules["distutils.version"] = importlib.import_module("setuptools._distutils.version")
    except ImportError:
        pass


def get_app_dir():
    """Lấy thư mục chứa exe."""
    if _NUITKA_BINARY_DIR:
        return str(_NUITKA_BINARY_DIR)
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def main():
    app_dir = get_app_dir()
    
    # Ghi startup log vào %TEMP% để debug
    _write_temp_log(f"=== STARTUP ===\n  app_dir: {app_dir}\n  sys.executable: {sys.executable}\n  _NUITKA_BINARY_DIR: {_NUITKA_BINARY_DIR}")

    # Chuyển CWD về thư mục exe
    os.chdir(app_dir)

    # Tạo thư mục data/ và file JSON
    try:
        from src.core.paths import ensure_dirs, reset_app_dir
        reset_app_dir()
        ensure_dirs()
    except Exception as e:
        _write_temp_log(f"ensure_dirs FAILED: {e}")
        _show_error("Lỗi khởi tạo", f"Không thể tạo thư mục data:\n\n{e}\n\nApp dir: {app_dir}")
        sys.exit(1)

    _write_temp_log("ensure_dirs OK")

    # Import PySide6
    try:
        from PySide6.QtWidgets import QApplication, QDialog
    except Exception as e:
        _write_temp_log(f"PySide6 import FAILED: {e}")
        _show_error("Lỗi PySide6", f"Không thể import PySide6:\n{e}")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("X Grok Video Generator")

    # Login dialog
    try:
        from src.gui.login_dialog import AppLoginDialog
        login = AppLoginDialog()
        if login.exec() != QDialog.Accepted:
            sys.exit(0)
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        _write_temp_log(f"Login FAILED:\n{err}")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Lỗi đăng nhập", f"{e}\n\nXem %TEMP%\\GrokVideoGenerator_crash.log")
        sys.exit(1)

    # Main window
    try:
        from src.gui import MainWindow
        window = MainWindow()
        window.show()
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        _write_temp_log(f"MainWindow FAILED:\n{err}")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Lỗi khởi động", f"{e}\n\nXem %TEMP%\\GrokVideoGenerator_crash.log")
        sys.exit(1)

    _write_temp_log("App started OK")
    result = app.exec()
    os._exit(result)


def _show_error(title, msg):
    """Hiện MessageBox lỗi trên Windows."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
    except Exception:
        print(f"ERROR: {title}: {msg}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        err = traceback.format_exc()
        _write_temp_log(f"FATAL:\n{err}")
        _show_error("Lỗi nghiêm trọng", f"{err}\n\nXem %TEMP%\\GrokVideoGenerator_crash.log")
        sys.exit(1)
