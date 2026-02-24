"""Path resolution đơn giản cho cả dev mode và Nuitka onefile Windows."""
import os
import sys
from pathlib import Path

_app_dir: Path | None = None


def get_app_dir() -> Path:
    """Lấy thư mục gốc chứa data/ và output/.
    
    Standalone mode: sys.executable nằm cạnh data/, không cần __nuitka_binary_dir
    Dev mode: dùng __main__.__file__.parent
    """
    global _app_dir
    if _app_dir is not None:
        return _app_dir

    # 1. Frozen exe (Nuitka standalone / PyInstaller) - sys.executable = exe thật
    if getattr(sys, 'frozen', False):
        _app_dir = Path(sys.executable).resolve().parent
        return _app_dir

    # 2. Nuitka onefile fallback: __nuitka_binary_dir
    try:
        import __main__ as _m
        nbd = getattr(_m, '_NUITKA_BINARY_DIR', None)
        if nbd:
            p = Path(str(nbd))
            if p.exists():
                _app_dir = p
                return _app_dir
    except Exception:
        pass

    # 3. Dev mode
    try:
        import __main__ as _m2
        f = getattr(_m2, '__file__', None)
        if f:
            _app_dir = Path(f).resolve().parent
            return _app_dir
    except Exception:
        pass

    _app_dir = Path.cwd()
    return _app_dir


def reset_app_dir():
    """Reset cached app_dir."""
    global _app_dir
    _app_dir = None


def data_path(*parts: str) -> Path:
    """Trả về path trong data/."""
    if parts:
        return get_app_dir() / "data" / Path(*parts)
    return get_app_dir() / "data"


def output_path(*parts: str) -> Path:
    """Trả về path trong output/."""
    if parts:
        return get_app_dir() / "output" / Path(*parts)
    return get_app_dir() / "output"


def ensure_dirs():
    """Tạo thư mục và file JSON mặc định. Raise RuntimeError nếu fail."""
    app = get_app_dir()

    # Tạo thư mục
    for d in [data_path(), data_path("profiles"), output_path()]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Không thể tạo thư mục: {d}\nLỗi: {e}")

    # Tạo file JSON mặc định (chỉ khi chưa tồn tại)
    defaults = {
        "accounts.json": '{"accounts": []}',
        "login_temp.json": "{}",
        "settings.json": "{}",
        "cf_clearance_cache.json": "{}",
    }
    for fname, content in defaults.items():
        fpath = data_path(fname)
        try:
            if not fpath.exists():
                fpath.write_text(content, encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"Không thể tạo file: {fpath}\nLỗi: {e}")


def get_debug_info() -> str:
    """Debug info cho logging."""
    lines = [
        f"app_dir: {get_app_dir()}",
        f"data_path: {data_path()}",
        f"output_path: {output_path()}",
        f"sys.executable: {sys.executable}",
        f"sys.frozen: {getattr(sys, 'frozen', False)}",
        f"os.getcwd(): {os.getcwd()}",
    ]
    try:
        import __main__ as _m
        lines.append(f"_NUITKA_BINARY_DIR: {getattr(_m, '_NUITKA_BINARY_DIR', 'NOT SET')}")
    except Exception:
        pass
    return "\n".join(lines)
