"""Centralized path resolution — đảm bảo tất cả file data nằm cạnh EXE.

Fallback trên Windows: nếu không ghi được cạnh exe → dùng %APPDATA%/GrokVideoGenerator/
"""
import os
import sys
from pathlib import Path

_app_dir: Path | None = None
_data_dir: Path | None = None
_output_dir: Path | None = None


def _get_exe_dir() -> Path:
    """Lấy thư mục chứa exe (hoặc main.py khi dev). Không cache."""
    # Nuitka onefile inject __nuitka_binary_dir vào __main__
    try:
        import __main__
        nbd = getattr(__main__, '__nuitka_binary_dir', None)
        if nbd:
            return Path(nbd)
    except Exception:
        pass

    # Nuitka standalone hoặc PyInstaller
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent

    # Dev mode
    return Path.cwd()


def _can_write(directory: Path) -> bool:
    """Kiểm tra có quyền ghi vào thư mục không."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        test_file = directory / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return True
    except OSError:
        return False


def get_app_dir() -> Path:
    """Lấy thư mục gốc của app (chứa data/ và output/).
    
    Ưu tiên: thư mục cạnh exe.
    Fallback Windows: %APPDATA%/GrokVideoGenerator/
    """
    global _app_dir
    if _app_dir is not None:
        return _app_dir

    exe_dir = _get_exe_dir()

    # Thử ghi cạnh exe trước (cách chuẩn)
    if _can_write(exe_dir / "data"):
        _app_dir = exe_dir
        return _app_dir

    # Fallback: %APPDATA% trên Windows, ~/.local/share trên Linux/Mac
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            fallback = Path(appdata) / "GrokVideoGenerator"
        else:
            fallback = Path.home() / "AppData" / "Roaming" / "GrokVideoGenerator"
    else:
        fallback = Path.home() / ".local" / "share" / "GrokVideoGenerator"

    fallback.mkdir(parents=True, exist_ok=True)
    _app_dir = fallback
    return _app_dir


def data_path(*parts: str) -> Path:
    """Trả về absolute path trong thư mục data/.
    
    Ví dụ: data_path("login_temp.json") → .../data/login_temp.json
           data_path("profiles", "abc") → .../data/profiles/abc
    """
    if parts:
        return get_app_dir() / "data" / Path(*parts)
    return get_app_dir() / "data"


def output_path(*parts: str) -> Path:
    """Trả về absolute path trong thư mục output/."""
    if parts:
        return get_app_dir() / "output" / Path(*parts)
    return get_app_dir() / "output"


def ensure_dirs():
    """Tạo các thư mục và file JSON mặc định — gọi 1 lần khi app khởi động.
    
    Raises RuntimeError nếu không thể tạo thư mục data/.
    """
    app_dir = get_app_dir()  # Đã tự chọn writable dir

    dirs_to_create = [data_path(), data_path("profiles"), output_path()]
    for d in dirs_to_create:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"Không thể tạo thư mục: {d}\n"
                f"App dir: {app_dir}\n"
                f"Chi tiết: {e}"
            )

    # Tạo các file JSON mặc định nếu chưa tồn tại
    _defaults = {
        data_path("accounts.json"): "[]",
        data_path("login_temp.json"): "{}",
        data_path("settings.json"): "{}",
        data_path("cf_clearance_cache.json"): "{}",
    }
    for fpath, content in _defaults.items():
        try:
            if not fpath.exists():
                fpath.write_text(content, encoding="utf-8")
        except OSError as e:
            raise RuntimeError(
                f"Không thể tạo file: {fpath}\n"
                f"Chi tiết: {e}"
            )
