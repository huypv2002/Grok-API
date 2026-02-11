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
    for d in ["data", "data/profiles", "output"]:
        os.makedirs(d, exist_ok=True)

    # 3. Log startup info (debug cho EXE)
    try:
        import platform
        import datetime
        with open(os.path.join("data", "startup.log"), "w", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] App starting\n")
            f.write(f"  app_dir: {app_dir}\n")
            f.write(f"  cwd: {os.getcwd()}\n")
            f.write(f"  sys.executable: {sys.executable}\n")
            f.write(f"  frozen: {getattr(sys, 'frozen', False)}\n")
            f.write(f"  platform: {platform.system()} {platform.release()} {platform.machine()}\n")
            f.write(f"  python: {sys.version}\n")
            try:
                nbd = __nuitka_binary_dir  # type: ignore[name-defined]
                f.write(f"  __nuitka_binary_dir: {nbd}\n")
            except NameError:
                f.write(f"  __nuitka_binary_dir: N/A (dev mode)\n")
            # Log data dir contents
            f.write(f"  data/ exists: {os.path.isdir('data')}\n")
            f.write(f"  data/accounts.json exists: {os.path.isfile('data/accounts.json')}\n")
            f.write(f"  data/.key exists: {os.path.isfile('data/.key')}\n")
    except Exception:
        pass

    # 4. Import và chạy app — bắt lỗi import riêng để debug
    try:
        from PySide6.QtWidgets import QApplication, QDialog
    except Exception as e:
        write_crash_log(f"PySide6 import failed: {e}")
        show_error_box("Lỗi PySide6", f"Không thể import PySide6:\n{e}")
        sys.exit(1)

    # Tạo QApplication TRƯỚC để có thể hiện MessageBox nếu import sau fail
    app = QApplication(sys.argv)
    app.setApplicationName("X Grok Video Generator")

    try:
        from src.gui.login_dialog import AppLoginDialog
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        write_crash_log(f"Login dialog import failed:\n{err}")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Lỗi khởi động",
                             f"Không thể load Login Dialog:\n\n{e}\n\nXem file crash.log")
        sys.exit(1)

    # Hiện form đăng nhập app trước
    login = AppLoginDialog()
    if login.exec() != QDialog.Accepted:
        sys.exit(0)

    # Import MainWindow SAU khi login OK — nặng hơn, nhiều dependency hơn
    try:
        from src.gui import MainWindow
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        write_crash_log(f"MainWindow import failed:\n{err}")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Lỗi khởi động",
                             f"Không thể load MainWindow:\n\n{e}\n\nXem file crash.log")
        sys.exit(1)

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
