#!/usr/bin/env python3
"""X Grok Multi-Account Video Generator - Entry Point"""
import sys
from PySide6.QtWidgets import QApplication
from src.gui import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("X Grok Video Generator")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
