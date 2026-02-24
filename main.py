#!/usr/bin/env python3
"""X Grok Multi-Account Video Generator - Entry Point"""
import sys
import os

# === Nuitka onefile: __nuitka_binary_dir là global var trong __main__ ===
# Phải capture NGAY ĐÂY ở module level, trước khi bất kỳ function nào chạy
_NUITKA_BINARY_DIR = None
try:
    # noinspection PyUnresolvedReferences
    _NUITKA_BINARY_DIR = __nuitka_binary_dir  # type: ignore[name-defined]
except NameError:
    pass

# === Python 3.13 compat: distutils bị xóa khỏi stdlib ===
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
    """Lấy thư mục chứa exe thật.
    
    Nuitka onefile: __nuitka_binary_dir (captured at module level) = thư mục chứa .exe GỐC
    Nuitka standalone / PyInstaller: sys.executable.parent
    Dev: __file__.parent
    """
    # Nuitka onefile - đây là cách DUY NHẤT đáng tin cậy
    if _NUITKA_BINARY_DIR:
        return str(_NUITKA_BINARY_DIR)
    # Frozen (standalone hoặc PyInstaller)
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
    # 0. Debug ngay lập tức — ghi file cạnh exe bằng pure os
    app_dir = get_app_dir()
    
    # Ghi debug log TRƯỚC mọi thứ khác
    try:
        import datetime
        debug_path = os.path.join(app_dir, "debug_startup.log")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] === STARTUP DEBUG ===\n")
            f.write(f"  app_dir (from get_app_dir): {app_dir}\n")
            f.write(f"  sys.executable: {sys.executable}\n")
            f.write(f"  sys.frozen: {getattr(sys, 'frozen', False)}\n")
            f.write(f"  os.getcwd(): {os.getcwd()}\n")
            f.write(f"  sys.argv: {sys.argv}\n")
            f.write(f"  sys.platform: {sys.platform}\n")
            try:
                f.write(f"  __nuitka_binary_dir: {__nuitka_binary_dir}\n")  # type: ignore
            except NameError:
                f.write(f"  __nuitka_binary_dir: NOT DEFINED\n")
            f.write(f"  LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'N/A')}\n")
            f.write(f"  APPDATA: {os.environ.get('APPDATA', 'N/A')}\n")
    except Exception as e:
        # Nếu không ghi được cạnh exe → thử ghi vào Desktop
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop", "grok_debug.log")
            with open(desktop, "w", encoding="utf-8") as f:
                f.write(f"CANNOT WRITE TO APP DIR: {app_dir}\n")
                f.write(f"Error: {e}\n")
                f.write(f"sys.executable: {sys.executable}\n")
                f.write(f"sys.frozen: {getattr(sys, 'frozen', False)}\n")
        except Exception:
            pass

    # 1. Chuyển CWD về thư mục chứa exe
    os.chdir(app_dir)

    # 2. Tạo thư mục cần thiết — nếu fail thì hiện lỗi rõ ràng
    from src.core.paths import ensure_dirs, data_path
    from src.core.paths import get_app_dir as get_resolved_app_dir
    try:
        ensure_dirs()
    except RuntimeError as e:
        write_crash_log(f"ensure_dirs() failed:\n{e}")
        show_error_box("Lỗi khởi tạo dữ liệu", str(e))
        sys.exit(1)

    # 3. Log startup info
    resolved_app_dir = get_resolved_app_dir()
    try:
        import platform
        startup_log = str(data_path("startup.log"))
        with open(startup_log, "w", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] App started OK\n")
            f.write(f"  exe_dir: {app_dir}\n")
            f.write(f"  resolved_app_dir: {resolved_app_dir}\n")
            f.write(f"  using_fallback: {str(resolved_app_dir) != app_dir}\n")
            f.write(f"  data_dir: {data_path()}\n")
            f.write(f"  output_dir: {str(data_path()).replace('data', 'output')}\n")
            f.write(f"  platform: {platform.system()} {platform.release()}\n")
            f.write(f"  python: {sys.version}\n")
            f.write(f"  accounts.json exists: {data_path('accounts.json').exists()}\n")
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
                             f"Không thể load Login Dialog:\n\n{e}\n\nXem file crash.log để biết chi tiết.")
        sys.exit(1)

    # Hiện form đăng nhập app trước
    try:
        login = AppLoginDialog()
        result = login.exec()
        if result != QDialog.Accepted:
            sys.exit(0)
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        write_crash_log(f"Login dialog exec failed:\n{err}")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Lỗi đăng nhập",
                             f"Lỗi khi hiện form đăng nhập:\n\n{e}\n\nXem file crash.log")
        sys.exit(1)

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
