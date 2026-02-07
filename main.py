#!/usr/bin/env python3
"""X Grok Multi-Account Video Generator - Entry Point"""
import sys
import os

# === Python 3.13 compat: distutils bị xóa khỏi stdlib ===
# undetected_chromedriver.patcher dòng 4: import distutils
# Phải patch TRƯỚC khi bất kỳ import nào chạm tới undetected_chromedriver
try:
    import distutils  # noqa: F401
except ModuleNotFoundError:
    import importlib
    try:
        import setuptools._distutils as _distutils_compat
        sys.modules["distutils"] = _distutils_compat
        sys.modules["distutils.version"] = importlib.import_module("setuptools._distutils.version")
    except ImportError:
        pass


def get_app_dir():
    """Lấy thư mục chứa exe (hoặc main.py khi dev).
    
    Nuitka onefile: __nuitka_binary_dir = thư mục chứa file .exe thực tế
    Nuitka standalone: sys.executable = đường dẫn exe
    PyInstaller: sys.executable = đường dẫn exe
    Dev: __file__ = đường dẫn main.py
    """
    # Nuitka onefile inject __nuitka_binary_dir ở module level
    # Đây là thư mục chứa .exe thật, KHÔNG phải temp extraction dir
    try:
        # noinspection PyUnresolvedReferences
        return __nuitka_binary_dir  # type: ignore[name-defined]
    except NameError:
        pass
    # Nuitka standalone hoặc PyInstaller
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # Dev mode
    return os.path.dirname(os.path.abspath(__file__))


def write_crash_log(msg):
    """Ghi crash log - dùng os thuần, không import thêm gì."""
    try:
        import datetime
        log_path = os.path.join(get_app_dir(), "crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{datetime.datetime.now().isoformat()}]\n")
            f.write(msg + "\n")
    except Exception:
        pass


def show_error_box(title, msg):
    """Hiện MessageBox lỗi trên Windows - fallback nếu Qt không load được."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
    except Exception:
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, title, msg)
        except Exception:
            pass


def main():
    # 1. Chuyển CWD về thư mục chứa exe
    app_dir = get_app_dir()
    os.chdir(app_dir)

    # 2. Tạo thư mục cần thiết
    os.makedirs("data", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    # 3. Import và chạy app
    from PySide6.QtWidgets import QApplication, QDialog
    from src.gui.login_dialog import AppLoginDialog
    from src.gui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("X Grok Video Generator")

    # Hiện form đăng nhập app trước
    login = AppLoginDialog()
    if login.exec() != QDialog.Accepted:
        sys.exit(0)

    # Đăng nhập OK → hiện MainWindow
    window = MainWindow()
    window.show()

    result = app.exec()
    os._exit(result)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        err = traceback.format_exc()
        write_crash_log(err)
        show_error_box("Lỗi khởi động", f"Ứng dụng gặp lỗi:\n\n{err}\n\nXem file crash.log")
        sys.exit(1)
