"""Centralized path resolution cho Nuitka onefile trên Windows.

Strategy: tìm thư mục chứa .exe thật bằng mọi cách có thể.
Nuitka onefile: __nuitka_binary_dir được capture trong main.py và truyền qua _NUITKA_BINARY_DIR.
"""
import os
import sys
from pathlib import Path

# === Capture __nuitka_binary_dir từ __main__ (đã được set trong main.py) ===
_NUITKA_BINARY_DIR: Path | None = None
try:
    import __main__ as _main_mod
    _nbd = getattr(_main_mod, '_NUITKA_BINARY_DIR', None)
    if _nbd:
        _NUITKA_BINARY_DIR = Path(str(_nbd))
except Exception:
    pass

_app_dir: Path | None = None
_APP_NAME = "GrokVideoGenerator"


def _get_exe_dir() -> Path:
    """Lấy thư mục chứa .exe thật - thử tất cả cách có thể."""

    # Cách 1: __nuitka_binary_dir (Nuitka onefile - chính xác nhất)
    if _NUITKA_BINARY_DIR and _NUITKA_BINARY_DIR.exists():
        return _NUITKA_BINARY_DIR

    # Cách 2: Re-read từ __main__ (phòng trường hợp paths.py import trước main.py set xong)
    try:
        import __main__ as _m
        nbd = getattr(_m, '_NUITKA_BINARY_DIR', None)
        if nbd:
            p = Path(str(nbd))
            if p.exists():
                return p
    except Exception:
        pass

    # Cách 3: sys.executable - trên Nuitka onefile Windows, đây là path tới .exe gốc
    # (khác với sys.argv[0] có thể là temp path)
    exe = Path(sys.executable).resolve()
    # Nuitka onefile: sys.executable = path tới .exe thật (không phải temp)
    # Nuitka standalone / PyInstaller: sys.executable cũng là exe thật
    if exe.suffix.lower() == '.exe' and exe.exists():
        return exe.parent

    # Cách 4: sys.argv[0]
    if sys.argv and sys.argv[0]:
        p = Path(sys.argv[0]).resolve()
        if p.suffix.lower() == '.exe' and p.exists():
            return p.parent

    # Cách 5: frozen flag
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent

    # Dev mode: __file__ của main.py
    try:
        import __main__ as _m2
        f = getattr(_m2, '__file__', None)
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
        test_dir = exe_dir / "data"
        test_dir.mkdir(parents=True, exist_ok=True)
        # Verify có thể ghi file thật
        test_file = test_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
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


def reset_app_dir():
    """Reset cached app_dir - dùng khi cần re-detect sau khi main.py set _NUITKA_BINARY_DIR."""
    global _app_dir, _NUITKA_BINARY_DIR
    _app_dir = None
    # Re-read từ __main__
    try:
        import __main__ as _m
        nbd = getattr(_m, '_NUITKA_BINARY_DIR', None)
        if nbd:
            _NUITKA_BINARY_DIR = Path(str(nbd))
    except Exception:
        pass


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


def get_debug_info() -> str:
    """Trả về debug info về path resolution - dùng để log."""
    lines = [
        f"_NUITKA_BINARY_DIR (module): {_NUITKA_BINARY_DIR}",
        f"_app_dir (cached): {_app_dir}",
        f"sys.executable: {sys.executable}",
        f"sys.argv[0]: {sys.argv[0] if sys.argv else 'N/A'}",
        f"sys.frozen: {getattr(sys, 'frozen', False)}",
        f"os.getcwd(): {os.getcwd()}",
        f"get_app_dir(): {get_app_dir()}",
        f"data_path(): {data_path()}",
        f"output_path(): {output_path()}",
    ]
    try:
        import __main__ as _m
        lines.append(f"__main__._NUITKA_BINARY_DIR: {getattr(_m, '_NUITKA_BINARY_DIR', 'NOT SET')}")
    except Exception:
        pass
    return "\n".join(lines)
