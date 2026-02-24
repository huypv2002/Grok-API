"""Centralized path resolution cho Nuitka onefile trên Windows.

Strategy: tìm thư mục chứa .exe thật bằng mọi cách có thể,
KHÔNG dùng _can_write_dir để chọn path (vì temp dir cũng writable).
Chỉ fallback sang LOCALAPPDATA khi tạo thư mục thực sự thất bại.
"""
import os
import sys
from pathlib import Path

# === Capture __nuitka_binary_dir NGAY ĐÂY ở module level ===
# Nuitka onefile inject biến này vào __main__ globals.
_NUITKA_BINARY_DIR: Path | None = None
try:
    import __main__ as _main_mod
    _nbd = getattr(_main_mod, '_NUITKA_BINARY_DIR', None)  # captured trong main.py
    if _nbd:
        _NUITKA_BINARY_DIR = Path(str(_nbd))
except Exception:
    pass

_app_dir: Path | None = None
_APP_NAME = "GrokVideoGenerator"


def _get_exe_dir() -> Path:
    """Lấy thư mục chứa .exe thật - thử tất cả cách có thể."""

    # Cách 1: __nuitka_binary_dir (Nuitka onefile - chính xác nhất)
    if _NUITKA_BINARY_DIR:
        return _NUITKA_BINARY_DIR

    # Cách 2: sys.argv[0] - path exe được gọi (Windows double-click)
    # Trên Nuitka onefile: sys.argv[0] = path tới .exe gốc
    if sys.argv and sys.argv[0]:
        p = Path(sys.argv[0]).resolve()
        if p.suffix.lower() in ('.exe', '') and p.exists():
            return p.parent

    # Cách 3: sys.executable (frozen mode)
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent

    # Dev mode: __file__ của main.py
    try:
        import __main__ as _m
        f = getattr(_m, '__file__', None)
        if f:
            return Path(f).resolve().parent
    except Exception:
        pass

    return Path.cwd()


def _get_fallback_dir() -> Path:
    """Fallback dir khi không ghi được cạnh exe."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / _APP_NAME
        return Path.home() / "AppData" / "Local" / _APP_NAME
    return Path.home() / f".{_APP_NAME}"


def get_app_dir() -> Path:
    """Trả về thư mục gốc chứa data/ và output/.

    Luôn ưu tiên thư mục cạnh exe.
    Chỉ fallback sang LOCALAPPDATA khi mkdir thực sự fail.
    """
    global _app_dir
    if _app_dir is not None:
        return _app_dir

    exe_dir = _get_exe_dir()

    # Thử tạo data/ cạnh exe
    try:
        (exe_dir / "data").mkdir(parents=True, exist_ok=True)
        _app_dir = exe_dir
        return _app_dir
    except OSError:
        pass

    # Fallback: LOCALAPPDATA / home
    fallback = _get_fallback_dir()
    try:
        (fallback / "data").mkdir(parents=True, exist_ok=True)
        _app_dir = fallback
        return _app_dir
    except OSError:
        pass

    # Last resort: home dir
    last = Path.home() / _APP_NAME
    last.mkdir(parents=True, exist_ok=True)
    _app_dir = last
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
    """Tạo tất cả thư mục và file JSON mặc định."""
    app_dir = get_app_dir()

    for d in [data_path(), data_path("profiles"), output_path()]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Không thể tạo thư mục: {d}\nApp dir: {app_dir}\nLỗi: {e}")

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
            raise RuntimeError(f"Không thể tạo file: {fpath}\nLỗi: {e}")
