#!/usr/bin/env python3
"""X Grok Multi-Account Video Generator - Entry Point"""
import sys
import os
from PySide6.QtWidgets import QApplication, QDialog
from src.gui.login_dialog import AppLoginDialog
from src.gui import MainWindow


def main():
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
    main()
