#!/usr/bin/env python3
"""X Grok Multi-Account Video Generator - Entry Point"""
import sys
import os
from PySide6.QtWidgets import QApplication
from src.gui import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("X Grok Video Generator")
    window = MainWindow()
    window.show()
    
    # Chạy app
    result = app.exec()
    
    # Force exit để kill tất cả threads/processes
    os._exit(result)

if __name__ == "__main__":
    main()
