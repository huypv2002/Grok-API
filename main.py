#!/usr/bin/env python3
"""X Grok Multi-Account Video Generator - Entry Point"""
import sys
import os
import traceback
import logging
from pathlib import Path
from datetime import datetime


def get_app_dir() -> Path:
    """Lấy thư mục gốc của app (nơi chứa exe hoặc main.py)."""
    if getattr(sys, 'frozen', False):
        # Nuitka/PyInstaller: exe location
        return Path(sys.executable).parent
    else:
        # Dev mode: script location
        return Path(__file__).parent


def setup_environment():
    """Setup CWD, tạo thư mục cần thiết, cấu hình logging."""
    app_dir = get_app_dir()
    os.chdir(app_dir)

    # Tạo thư mục cần thiết
    Path("data").mkdir(exist_ok=True)
    Path("output").mkdir(exist_ok=True)

    # Setup logging ra file
    log_file = app_dir / "crash.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ]
    )
    logging.info(f"App started | dir={app_dir} | frozen={getattr(sys, 'frozen', False)}")


def main():
    setup_environment()

    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
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
    except Exception as e:
        # Ghi lỗi ra file
        err_msg = traceback.format_exc()
        logging.error(f"FATAL CRASH:\n{err_msg}")

        # Cố hiện MessageBox cho user biết
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None, "Lỗi khởi động",
                f"Ứng dụng gặp lỗi:\n\n{str(e)}\n\nChi tiết xem file crash.log"
            )
        except Exception:
            pass

        # Ghi ra crash.log nếu logging chưa setup
        try:
            with open("crash.log", "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"CRASH at {datetime.now().isoformat()}\n")
                f.write(err_msg)
        except Exception:
            pass

        sys.exit(1)
