# Lazy imports — tránh crash nếu zendriver/selenium thiếu khi build EXE
# Import chain: video_generator → cf_solver → zendriver (có thể fail)

def __getattr__(name):
    if name in ("Account", "VideoSettings", "VideoTask", "ImageSettings", "ImageTask"):
        from .models import Account, VideoSettings, VideoTask, ImageSettings, ImageTask
        return locals()[name]
    if name == "AccountManager":
        from .account_manager import AccountManager
        return AccountManager
    if name in ("encrypt_password", "decrypt_password"):
        from .encryption import encrypt_password, decrypt_password
        return locals()[name]
    if name == "SessionManager":
        from .session_manager import SessionManager
        return SessionManager
    if name == "BrowserController":
        from .browser_controller import BrowserController
        return BrowserController
    if name == "VideoGenerator":
        from .video_generator import VideoGenerator
        return VideoGenerator
    if name == "MultiTabImageGenerator":
        from .image_generator import MultiTabImageGenerator
        return MultiTabImageGenerator
    if name == "HistoryManager":
        from .history_manager import HistoryManager
        return HistoryManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
