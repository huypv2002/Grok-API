# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Grok Video Generator"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Collect all zendriver and PySide6 data
zendriver_datas, zendriver_binaries, zendriver_hiddenimports = collect_all('zendriver')
pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all('PySide6')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=zendriver_binaries + pyside6_binaries,
    datas=[
        ('src', 'src'),
    ] + zendriver_datas + pyside6_datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui', 
        'PySide6.QtWidgets',
        'httpx',
        'httpx._transports',
        'httpx._transports.default',
        'cryptography',
        'cryptography.fernet',
        'selenium',
        'selenium.webdriver',
        'selenium.webdriver.chrome',
        'selenium.webdriver.chrome.service',
        'selenium.webdriver.chrome.options',
        'undetected_chromedriver',
        'zendriver',
        'zendriver.core',
        'zendriver.cdp',
        'asyncio',
        'sqlite3',
        'json',
        'uuid',
        'dataclasses',
    ] + zendriver_hiddenimports + pyside6_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GrokVideoGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if sys.platform == 'win32' else None,
)
