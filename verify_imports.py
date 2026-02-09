"""Verify all required imports before Nuitka build."""
import sys

print(f"Python {sys.version}")

modules = [
    # Qt
    "PySide6", "PySide6.QtWidgets", "PySide6.QtCore", "PySide6.QtGui",
    # HTTP
    "httpx", "httpcore", "certifi", "anyio", "sniffio", "h11", "idna",
    "requests", "urllib3", "charset_normalizer",
    # Crypto
    "cryptography", "cryptography.fernet", "cffi", "_cffi_backend",
    # Data
    "pydantic",
    # Browser automation
    "selenium", "selenium.webdriver",
    "undetected_chromedriver",
    "zendriver", "websockets",
    # Utils
    "emoji", "grapheme", "latest_user_agents", "user_agents",
    # Stdlib (sanity check)
    "sqlite3", "ctypes", "asyncio", "hashlib", "uuid", "json",
    "dataclasses", "pathlib", "logging", "subprocess", "glob",
    "platform", "math", "random", "base64", "re", "os",
    # Python 3.13 compat
    "setuptools", "setuptools._distutils",
]

errors = []
for mod in modules:
    try:
        __import__(mod)
        print(f"  OK: {mod}")
    except ImportError as e:
        print(f"  FAIL: {mod} -> {e}")
        errors.append(f"{mod}: {e}")

if errors:
    print(f"\n=== {len(errors)} MISSING MODULES ===")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)

print(f"\nAll {len(modules)} modules OK!")
