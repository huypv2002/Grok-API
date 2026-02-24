"""Centralized path resolution cho Nuitka onefile trên Windows.

Ưu tiên: tạo data/ cạnh file .exe thật.
Fallback: %LOCALAPPDATA%/GrokVideoGenerator/ (Windows) hoặc ~/.GrokVideoGenerator/ (khác).

QUAN TRỌNG - Nuitka onefile:
  - sys.executable = đường dẫn tới file .exe GỐC (ĐÚNG)
  - __file__, __main__ = temp extraction dir (SAI cho data storage)
  - __nuitka_binary_dir = thư mục chứa .exe (ĐÚNG, nhưng không phải lúc nào cũng có)
  
Vì vậy luôn dùng sys.executable làm anchor chính.
"""
import os
import sys
from pathlib import Path

_app_dir: Path | None = None

# Tên app cho fallback dir
_APP_NAME = "GrokVideoGenerator"


def _get_exe_dir() -> Path:
    """Lấy thư mục chứa file .exe thật (KHÔNG phải temp dir).
    
    Nuitka onefile: sys.executable = path tới .exe gốc trên disk
    Nuitka standalone: sys.executable = path tới .exe 
    Dev mode: thư mục chứa main.py (hoặc CWD)
    """
    if getattr(sys, 'frozen', False):
        # frozen = True cho cả Nuitka standalone, onefile, và PyInstaller
        # sys.executable luôn trỏ tới file .exe GỐC, không phải temp
        return Path(sys.executable).resolve().parent
    
    # Dev mode - dùng __file__ của main.py nếu có, fallback CWD
    try:
        import __main__
        main_file = getattr(__main__, '__file__', None)
        if main_file:
            return Path(main_file).resolve().parent
    except Exception:
        pass
    
    return Path.cwd()


def _can_write_dir(directory: Path) -> bool:
    """Test quyền ghi thực tế vào 1 thư mục."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        test = directory / ".write_test_grok"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        return True
    except Exception:
        return False


def get_app_dir() -> Path:
    """Trả về thư mục gốc chứa data/ và output/.
    
    1. Thử cạnh exe trước
    2. Fallback: %LOCALAPPDATA%/GrokVideoGenerator (Windows)
                 ~/.GrokVideoGenerator (Mac/Linux)
    """
    global _app_dir
    if _app_dir is not None:
        return _app_dir

    exe_dir = _get_exe_dir()

    # Ưu tiên 1: cạnh exe
    if _can_write_dir(exe_dir / "data"):
        _app_dir = exe_dir
        return _app_dir

    # Ưu tiên 2: fallback OS-specific
    if sys.platform == "win32":
        # %LOCALAPPDATA% tốt hơn %APPDATA% vì không sync qua roaming profile
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            fallback = Path(base) / _APP_NAME
        else:
            fallback = Path.home() / "AppData" / "Local" / _APP_NAME
    else:
        fallback = Path.home() / f".{_APP_NAME}"

    if _can_write_dir(fallback / "data"):
        _app_dir = fallback
        return _app_dir

    # Ưu tiên 3: home dir (last resort)
    fallback_home = Path.home() / _APP_NAME
    fallback_home.mkdir(parents=True, exist_ok=True)
    _app_dir = fallback_home
    return _app_dir


def data_path(*parts: str) -> Path:
    """Trả về absolute path trong thư mục data/."""
    if parts:
        return get_app_dir() / "data" / Path(*parts)
    return get_app_dir() / "data"


def output_path(*parts: str) -> Path:
    """Trả về absolute path trong thư mục output/."""
    if parts:
        return get_app_dir() / "output" / Path(*parts)
    return get_app_dir() / "output"


def ensure_dirs():
    """Tạo tất cả thư mục và file JSON mặc định.
    
    Raises RuntimeError nếu thất bại.
    """
    app_dir = get_app_dir()

    # Tạo thư mục
    for d in [data_path(), data_path("profiles"), output_path()]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"Không thể tạo thư mục: {d}\n"
                f"App dir: {app_dir}\n"
                f"Lỗi: {e}"
            )

    # Tạo file JSON mặc định
    defaults = {
        data_path("accounts.json"): "[]",
        data_path("login_temp.json"): "{}",
        data_path("settings.json"): "{}",
        data_path("cf_clearance_cache.json"): "{}",
    }
    for fpath, content in defaults.items():
        try:
            if not fpath.exists():
                fpath.write_text(content, encoding="utf-8")
        except OSError as e:
            raise RuntimeError(
                f"Không thể tạo file: {fpath}\n"
                f"Lỗi: {e}"
            )
