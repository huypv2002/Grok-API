# Lazy imports — tránh crash nếu dependency chain fail
# MainWindow import kéo theo video_gen_tab → video_generator → cf_solver → zendriver
# Nếu zendriver hoặc sub-dependency thiếu, toàn bộ app crash trước khi hiện UI

def __getattr__(name):
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    if name == "AccountTab":
        from .account_tab import AccountTab
        return AccountTab
    if name == "VideoGenTab":
        from .video_gen_tab import VideoGenTab
        return VideoGenTab
    if name == "HistoryTab":
        from .history_tab import HistoryTab
        return HistoryTab
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
