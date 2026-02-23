"""Centralized path resolution — đảm bảo tất cả file data nằm cạnh EXE."""
import os
import sys
from pathlib import Path

_app_dir: Path | None = None


def get_app_dir() -> Path:
    """Lấy thư mục chứa exe (hoặc main.py khi dev).
    
    Nuitka onefile: __nuitka_binary_dir = thư mục chứa .exe thực tế
    Nuitka standalone / PyInstaller: sys.executable parent
    Dev: CWD (main.py đã chdir rồi)
    """
    global _app_dir
    if _app_dir is not None:
        return _app_dir

    # Nuitka onefile inject __nuitka_binary_dir vào __main__
    try:
        import __main__
        nbd = getattr(__main__, '__nuitka_binary_dir', None)
        if nbd:
            _app_dir = Path(nbd)
            return _app_dir
    except Exception:
        pass

    # Nuitka standalone hoặc PyInstaller
    if getattr(sys, 'frozen', False):
        _app_dir = Path(sys.executable).parent
        return _app_dir

    # Dev mode
    _app_dir = Path.cwd()
    return _app_dir


def data_path(*parts: str) -> Path:
    """Trả về absolute path trong thư mục data/.
    
    Ví dụ: data_path("login_temp.json") → /path/to/exe/data/login_temp.json
           data_path("profiles", "abc") → /path/to/exe/data/profiles/abc
    """
    return get_app_dir() / "data" / Path(*parts)


def output_path(*parts: str) -> Path:
    """Trả về absolute path trong thư mục output/."""
    return get_app_dir() / "output" / Path(*parts) if parts else get_app_dir() / "output"


def ensure_dirs():
    """Tạo các thư mục cần thiết — gọi 1 lần khi app khởi động."""
    for d in [data_path(), data_path("profiles"), output_path()]:
        d.mkdir(parents=True, exist_ok=True)
