"""Main Window - PySide6 GUI with Modern Design"""
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QStatusBar, QLabel, QHBoxLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from .account_tab import AccountTab
from .video_gen_tab import VideoGenTab
from .history_tab import HistoryTab
from ..core.account_manager import AccountManager
from ..core.session_manager import SessionManager
from ..core.history_manager import HistoryManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 X Grok Multi-Account Video Generator")
        self.setMinimumSize(1200, 800)
        
        # Apply modern stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f6fa;
            }
            QTabWidget::pane {
                border: 1px solid #dcdde1;
                background-color: white;
                border-radius: 5px;
            }
            QTabBar::tab {
                background-color: #dcdde1;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: white;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #ecf0f1;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dcdde1;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                padding: 8px 15px;
                border-radius: 4px;
                border: 1px solid #dcdde1;
                background-color: white;
            }
            QPushButton:hover {
                background-color: #ecf0f1;
            }
            QTableWidget {
                border: 1px solid #dcdde1;
                border-radius: 5px;
                gridline-color: #ecf0f1;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #f5f6fa;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QComboBox, QSpinBox {
                padding: 5px;
                border: 1px solid #dcdde1;
                border-radius: 4px;
            }
            QTextEdit {
                border: 1px solid #dcdde1;
                border-radius: 4px;
            }
        """)
        
        # Initialize managers
        self.account_manager = AccountManager()
        self.session_manager = SessionManager()
        self.history_manager = HistoryManager()
        
        # Setup UI
        self._setup_ui()
    
    def _setup_ui(self):
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        
        # Create tabs
        self.account_tab = AccountTab(self.account_manager, self.session_manager)
        self.video_gen_tab = VideoGenTab(self.account_manager, None, self.history_manager)
        self.history_tab = HistoryTab(self.history_manager)
        
        # Add tabs with icons
        self.tabs.addTab(self.account_tab, "👤 Quản lý Account")
        self.tabs.addTab(self.video_gen_tab, "🎬 Tạo Video")
        self.tabs.addTab(self.history_tab, "📜 Lịch sử")
        
        layout.addWidget(self.tabs)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Status bar widgets
        self.status_label = QLabel("Ready")
        self.account_count_label = QLabel()
        self._update_account_count()
        
        self.status_bar.addWidget(self.status_label)
        self.status_bar.addPermanentWidget(self.account_count_label)
        
        # Connect signals
        self.account_tab.account_changed.connect(self._on_account_changed)
        self.video_gen_tab.video_completed.connect(self._on_video_completed)
        
        # Timer to update status
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(5000)
    
    def _on_account_changed(self):
        self.video_gen_tab.refresh_accounts()
        self._update_account_count()
    
    def _on_video_completed(self):
        self.history_tab.refresh()
    
    def _update_account_count(self):
        accounts = self.account_manager.get_all_accounts()
        logged_in = sum(1 for a in accounts if a.status == "logged_in")
        self.account_count_label.setText(f"Accounts: {logged_in}/{len(accounts)} logged in")
    
    def _update_status(self):
        workers = len(self.video_gen_tab.workers)
        if workers > 0:
            self.status_label.setText(f"🔄 Đang chạy {workers} task(s)...")
        else:
            self.status_label.setText("✅ Ready")
    
    def closeEvent(self, event):
        # Stop all workers
        self.video_gen_tab._stop_generation()
        self.history_manager.close()
        event.accept()
