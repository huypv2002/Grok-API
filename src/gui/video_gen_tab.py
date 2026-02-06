"""Video Generation Tab - Clean Modern UI with Multi-Tab Support"""
import json
import asyncio
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTextEdit, QComboBox, QPushButton, QMessageBox, QCheckBox, QSpinBox,
    QFileDialog, QLabel, QTableWidget, QTableWidgetItem, QLineEdit,
    QHeaderView, QSplitter, QFrame, QTabWidget, QProgressBar, QScrollArea
)
from PySide6.QtCore import Signal, QThread, Qt, QTimer, QTime
from PySide6.QtGui import QColor, QFont
from ..core.account_manager import AccountManager
from ..core.video_generator import VideoGenerator, MultiTabVideoGenerator, ZENDRIVER_AVAILABLE
from ..core.history_manager import HistoryManager
from ..core.models import VideoSettings

SETTINGS_FILE = Path("data/settings.json")
DEFAULT_OUTPUT_DIR = Path("output")


class AccountWorker(QThread):
    """
    Worker for a single account with multi-tab support.
    1 browser per account, 3 tabs running concurrently.
    """
    status_update = Signal(str, str)  # email, message
    task_completed = Signal(str, object)  # email, VideoTask
    all_finished = Signal(str)  # email
    
    def __init__(self, account, prompts, settings, num_tabs=3, headless=True):
        super().__init__()
        self.account = account
        self.prompts = prompts
        self.settings = settings
        self.num_tabs = num_tabs
        self.headless = headless
        self._stopped = False
        self._generator = None
    
    def run(self):
        if self._stopped:
            return
        
        # Run async code in new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._run_async())
        except Exception as e:
            self.status_update.emit(self.account.email, f"❌ Error: {e}")
        finally:
            loop.close()
        
        self.all_finished.emit(self.account.email)
    
    async def _run_async(self):
        """Async main loop"""
        self._generator = MultiTabVideoGenerator(
            account=self.account,
            num_tabs=self.num_tabs,
            headless=self.headless,
            on_status=lambda email, msg: self.status_update.emit(email, msg)
        )
        
        try:
            # Start browser
            if not await self._generator.start():
                self.status_update.emit(
                    self.account.email,
                    "❌ Failed to start browser"
                )
                return
            
            # Generate videos
            def on_task_complete(task):
                self.task_completed.emit(self.account.email, task)
            
            await self._generator.generate_batch(
                self.prompts,
                self.settings,
                on_task_complete
            )
            
        finally:
            await self._generator.stop()
    
    def stop(self):
        self._stopped = True
        if self._generator:
            self._generator._running = False


class VideoWorker(QThread):
    """Legacy single-video worker (kept for compatibility)"""
    status_update = Signal(str, str)
    finished = Signal(str, object)
    
    def __init__(self, account, prompt, settings, headless=True):
        super().__init__()
        self.account = account
        self.prompt = prompt
        self.settings = settings
        self.headless = headless
        self.stopped = False
    
    def run(self):
        if self.stopped:
            return
        generator = VideoGenerator()
        task = generator.generate_video(
            self.account, self.prompt, self.settings,
            lambda msg: self.status_update.emit(self.account.email, msg),
            headless=self.headless
        )
        self.finished.emit(self.account.email, task)
    
    def stop(self):
        self.stopped = True


class GlassFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_dark = True
        self._apply_style()
    
    def set_dark(self, dark):
        self.is_dark = dark
        self._apply_style()
    
    def _apply_style(self):
        if self.is_dark:
            self.setStyleSheet("""
                GlassFrame {
                    background: rgba(25, 35, 55, 220);
                    border: 1px solid rgba(80, 120, 200, 60);
                    border-radius: 10px;
                }
            """)
        else:
            self.setStyleSheet("""
                GlassFrame {
                    background: rgba(255, 255, 255, 220);
                    border: 1px solid rgba(100, 150, 200, 80);
                    border-radius: 10px;
                }
            """)


class StatBox(QFrame):
    def __init__(self, title, color="#3498db"):
        super().__init__()
        self.color = color
        self.is_dark = True
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        
        self.value_label = QLabel("0")
        self.value_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.value_label.setAlignment(Qt.AlignCenter)
        
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Segoe UI", 9))
        self.title_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)
        
        self._apply_style()
    
    def set_dark(self, dark):
        self.is_dark = dark
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet(f"""
            StatBox {{
                background: rgba(30, 40, 60, 200);
                border: 2px solid {self.color};
                border-radius: 8px;
            }}
        """)
        self.value_label.setStyleSheet(f"color: {self.color}; background: transparent;")
        self.title_label.setStyleSheet("color: white; background: transparent;")
    
    def set_value(self, v):
        self.value_label.setText(str(v))


class VideoGenTab(QWidget):
    video_completed = Signal()
    
    def __init__(self, account_manager: AccountManager, video_generator, history_manager: HistoryManager):
        super().__init__()
        self.account_manager = account_manager
        self.history_manager = history_manager
        self.account_workers: dict = {}  # email -> AccountWorker
        self.prompt_queue = []
        self.completed_prompts = []
        self.failed_prompts = []
        self.current_idx = 0
        self.is_dark = True
        
        # Track prompts per account
        self.account_prompts: dict = {}  # email -> list of prompts
        self.account_prompt_idx: dict = {}  # email -> current index in queue table
        
        # Output folder & batch tracking
        self._output_dir = str(DEFAULT_OUTPUT_DIR)
        self._current_batch_name = ""  # subfolder name (from TXT filename)
        self._batch_queue: list = []  # list of (batch_name, [prompts]) for folder import
        
        self._setup_ui()
        self.refresh_accounts()
        self._load_settings()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_stats)
        self.timer.start(500)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        
        self.stat_total = StatBox("Tổng", "#3498db")
        self.stat_running = StatBox("Đang chạy", "#f39c12")
        self.stat_done = StatBox("Xong", "#27ae60")
        self.stat_failed = StatBox("Lỗi", "#e74c3c")
        
        for s in [self.stat_total, self.stat_running, self.stat_done, self.stat_failed]:
            s.setFixedHeight(65)
            stats_row.addWidget(s)
        
        layout.addLayout(stats_row)
        
        # Progress bar area
        progress_frame = GlassFrame()
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(15, 10, 15, 10)
        progress_layout.setSpacing(6)
        
        # Top row: status text + elapsed time
        progress_top = QHBoxLayout()
        self.progress_status = QLabel("✅ Sẵn sàng")
        self.progress_status.setFont(QFont("Segoe UI", 10))
        self.progress_percent = QLabel("")
        self.progress_percent.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.progress_percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.elapsed_label = QLabel("")
        self.elapsed_label.setFont(QFont("Segoe UI", 9))
        self.elapsed_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_top.addWidget(self.progress_status, stretch=1)
        progress_top.addWidget(self.progress_percent)
        progress_top.addWidget(self.elapsed_label)
        progress_layout.addLayout(progress_top)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        # Bottom row: step detail (hidden - removed debug label)
        self.progress_detail = QLabel("")
        self.progress_detail.setFont(QFont("Segoe UI", 9))
        self.progress_detail.setVisible(False)  # Hide debug label
        
        self.progress_frame = progress_frame
        layout.addWidget(progress_frame)
        
        # Elapsed time tracking
        self._start_time = None
        self._elapsed_timer = QTimer()
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        
        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # LEFT panel — wrapped in scroll area
        left = GlassFrame()
        left_main_layout = QVBoxLayout(left)
        left_main_layout.setContentsMargins(0, 0, 0, 0)
        left_main_layout.setSpacing(0)
        
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(40, 50, 70, 100);
                width: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(80, 120, 200, 150);
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(100, 140, 220, 200);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        left_inner = QWidget()
        left_inner.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_inner)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(10)
        
        # Prompt
        self.prompt_title = QLabel("📝 Prompts")
        self.prompt_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        left_layout.addWidget(self.prompt_title)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Nhập prompt (mỗi dòng 1 prompt)...")
        self.prompt_input.setMaximumHeight(120)
        left_layout.addWidget(self.prompt_input)
        
        btn_row = QHBoxLayout()
        self.import_btn = QPushButton("📄 Nhập TXT")
        self.import_folder_btn = QPushButton("📂 Nhập Folder")
        self.clear_btn = QPushButton("🗑️ Xóa")
        self.import_btn.clicked.connect(self._import_prompts)
        self.import_folder_btn.clicked.connect(self._import_folder)
        self.clear_btn.clicked.connect(lambda: self.prompt_input.clear())
        self.import_btn.setToolTip("Nhập 1 file TXT → tạo subfolder trùng tên")
        self.import_folder_btn.setToolTip("Chọn folder chứa nhiều file TXT → mỗi file = 1 batch")
        btn_row.addWidget(self.import_btn)
        btn_row.addWidget(self.import_folder_btn)
        btn_row.addWidget(self.clear_btn)
        left_layout.addLayout(btn_row)
        
        # Output folder
        self.output_title = QLabel("📂 Thư mục xuất:")
        self.output_title.setFont(QFont("Segoe UI", 10))
        left_layout.addWidget(self.output_title)
        
        output_row = QHBoxLayout()
        self.output_input = QLineEdit()
        self.output_input.setText(str(DEFAULT_OUTPUT_DIR))
        self.output_input.setReadOnly(True)
        self.output_input.setFont(QFont("Consolas", 9))
        self.output_input.setMaximumHeight(28)
        self.output_browse_btn = QPushButton("📁")
        self.output_browse_btn.setFixedSize(28, 28)
        self.output_browse_btn.setCursor(Qt.PointingHandCursor)
        self.output_browse_btn.clicked.connect(self._browse_output)
        output_row.addWidget(self.output_input, stretch=1)
        output_row.addWidget(self.output_browse_btn)
        left_layout.addLayout(output_row)
        
        # Batch info label (shows when importing folder)
        self.batch_info = QLabel("")
        self.batch_info.setFont(QFont("Segoe UI", 9))
        self.batch_info.setWordWrap(True)
        left_layout.addWidget(self.batch_info)
        
        # Settings
        self.settings_title = QLabel("⚙️ Cài đặt")
        self.settings_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        left_layout.addWidget(self.settings_title)
        
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)
        
        # Tỷ lệ khung hình (5 options from Grok UI)
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["2:3", "3:2", "1:1", "9:16", "16:9"])
        self.aspect_combo.setCurrentIndex(4)  # default 16:9
        self.aspect_combo.setMinimumWidth(120)
        
        # Thời lượng video
        self.length_combo = QComboBox()
        self.length_combo.addItems(["6 giây", "10 giây"])
        self.length_combo.setMinimumWidth(120)
        
        # Độ phân giải
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["480p", "720p"])
        self.resolution_combo.setMinimumWidth(120)
        
        # Tabs per account
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 3)
        self.thread_spin.setValue(3)
        self.thread_spin.setMinimumWidth(120)
        self.thread_spin.setToolTip("Số tab mỗi tài khoản (1-3)")
        
        self.ratio_label = QLabel("Tỷ lệ:")
        self.length_label = QLabel("Thời lượng:")
        self.resolution_label = QLabel("Phân giải:")
        self.thread_label = QLabel("Tab/TK:")
        
        form.addRow(self.ratio_label, self.aspect_combo)
        form.addRow(self.length_label, self.length_combo)
        form.addRow(self.resolution_label, self.resolution_combo)
        form.addRow(self.thread_label, self.thread_spin)
        
        left_layout.addLayout(form)
        
        # Accounts
        self.acc_title = QLabel("👤 Tài khoản")
        self.acc_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        left_layout.addWidget(self.acc_title)
        
        self.acc_table = QTableWidget()
        self.acc_table.setColumnCount(3)
        self.acc_table.setHorizontalHeaderLabels(["✓", "Email", "Trạng thái"])
        self.acc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.acc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.acc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.acc_table.setColumnWidth(0, 35)
        self.acc_table.setColumnWidth(2, 80)
        self.acc_table.setMaximumHeight(120)
        left_layout.addWidget(self.acc_table)
        
        # Control buttons
        ctrl_row = QHBoxLayout()
        self.start_btn = QPushButton("▶️ Bắt đầu")
        self.stop_btn = QPushButton("⏹️ Dừng")
        self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        ctrl_row.addWidget(self.start_btn)
        ctrl_row.addWidget(self.stop_btn)
        left_layout.addLayout(ctrl_row)
        
        left_layout.addStretch()
        
        # Set scroll area content and add to left panel
        left_scroll.setWidget(left_inner)
        left_main_layout.addWidget(left_scroll)
        self.left_scroll = left_scroll  # Store reference for theme updates
        
        splitter.addWidget(left)
        
        # RIGHT panel
        right = GlassFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)
        
        self.tabs = QTabWidget()
        
        # Queue tab
        queue_w = QWidget()
        queue_l = QVBoxLayout(queue_w)
        queue_l.setContentsMargins(5, 5, 5, 5)
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(3)
        self.queue_table.setHorizontalHeaderLabels(["#", "Prompt", "Trạng thái"])
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue_table.setColumnWidth(0, 35)
        self.queue_table.setColumnWidth(2, 90)
        queue_l.addWidget(self.queue_table)
        self.tabs.addTab(queue_w, "📋 Hàng đợi")
        
        # Running tab
        run_w = QWidget()
        run_l = QVBoxLayout(run_w)
        run_l.setContentsMargins(5, 5, 5, 5)
        self.run_table = QTableWidget()
        self.run_table.setColumnCount(3)
        self.run_table.setHorizontalHeaderLabels(["Tài khoản", "Prompt", "Trạng thái"])
        self.run_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        run_l.addWidget(self.run_table)
        self.tabs.addTab(run_w, "🔄 Đang chạy")
        
        # Done tab
        done_w = QWidget()
        done_l = QVBoxLayout(done_w)
        done_l.setContentsMargins(5, 5, 5, 5)
        self.done_table = QTableWidget()
        self.done_table.setColumnCount(3)
        self.done_table.setHorizontalHeaderLabels(["Tài khoản", "Prompt", "File"])
        self.done_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        done_l.addWidget(self.done_table)
        self.tabs.addTab(done_w, "✅ Hoàn thành")
        
        right_layout.addWidget(self.tabs, stretch=1)
        
        # Log
        self.log_title = QLabel("📜 Nhật ký")
        self.log_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        right_layout.addWidget(self.log_title)
        
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        right_layout.addWidget(self.log)
        
        splitter.addWidget(right)
        splitter.setSizes([350, 550])
        
        self.left_card = left
        self.right_card = right
        
        layout.addWidget(splitter, stretch=1)
        
        self._apply_theme()

    
    def set_dark_mode(self, is_dark):
        self.is_dark = is_dark
        self._apply_theme()
    
    def _apply_theme(self):
        self.left_card.set_dark(self.is_dark)
        self.right_card.set_dark(self.is_dark)
        
        for s in [self.stat_total, self.stat_running, self.stat_done, self.stat_failed]:
            s.set_dark(self.is_dark)
        
        if self.is_dark:
            text_color = "white"
            input_style = """
                QTextEdit {
                    background: rgba(35, 45, 65, 220);
                    color: white;
                    border: 1px solid rgba(80, 120, 200, 80);
                    border-radius: 6px;
                    padding: 8px;
                }
                QComboBox {
                    background: rgba(35, 45, 65, 220);
                    color: white;
                    border: 1px solid rgba(80, 120, 200, 80);
                    border-radius: 6px;
                    padding: 6px 10px;
                    min-height: 20px;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 20px;
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background: rgb(35, 45, 65);
                    color: white;
                    selection-background-color: rgb(80, 120, 200);
                    border: 1px solid rgba(80, 120, 200, 80);
                }
                QSpinBox {
                    background: rgba(35, 45, 65, 220);
                    color: white;
                    border: 1px solid rgba(80, 120, 200, 80);
                    border-radius: 6px;
                    padding: 6px 10px;
                    min-height: 20px;
                }
            """
            table_style = """
                QTableWidget {
                    background: rgba(20, 30, 50, 180);
                    color: white;
                    border: 1px solid rgba(80, 120, 200, 50);
                    border-radius: 6px;
                    gridline-color: rgba(80, 120, 200, 30);
                }
                QTableWidget::item { padding: 5px; }
                QTableWidget::item:selected { background: rgba(80, 120, 200, 100); }
                QHeaderView::section {
                    background: rgba(40, 50, 70, 220);
                    color: white;
                    border: none;
                    padding: 6px;
                    font-weight: bold;
                }
            """
            btn_style = """
                QPushButton {
                    background: rgba(45, 55, 75, 220);
                    color: white;
                    border: 1px solid rgba(80, 120, 200, 80);
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 12px;
                }
                QPushButton:hover { background: rgba(55, 65, 85, 240); }
            """
            log_style = """
                QTextEdit {
                    background: rgba(10, 15, 25, 220);
                    color: #0f0;
                    border: 1px solid rgba(0, 200, 0, 40);
                    border-radius: 6px;
                    font-family: Consolas, monospace;
                    font-size: 11px;
                    padding: 6px;
                }
            """
            tab_style = """
                QTabWidget::pane { background: transparent; border: none; }
                QTabBar::tab {
                    background: rgba(40, 50, 70, 180);
                    color: rgba(255, 255, 255, 0.7);
                    border: none;
                    padding: 8px 14px;
                    margin-right: 3px;
                    border-radius: 6px 6px 0 0;
                }
                QTabBar::tab:selected { background: rgba(60, 80, 120, 220); color: white; }
            """
            check_style = "QCheckBox { color: white; }"
        else:
            text_color = "#333"
            input_style = """
                QTextEdit {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 8px;
                }
                QComboBox {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 6px 10px;
                    min-height: 20px;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 20px;
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background: white;
                    color: #333;
                    selection-background-color: rgb(80, 120, 200);
                    border: 1px solid rgba(100, 150, 200, 100);
                }
                QSpinBox {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 6px 10px;
                    min-height: 20px;
                }
            """
            table_style = """
                QTableWidget {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 80);
                    border-radius: 6px;
                    gridline-color: rgba(100, 150, 200, 50);
                }
                QTableWidget::item { padding: 5px; }
                QTableWidget::item:selected { background: rgba(80, 120, 200, 100); }
                QHeaderView::section {
                    background: rgba(240, 245, 255, 250);
                    color: #333;
                    border: none;
                    padding: 6px;
                    font-weight: bold;
                }
            """
            btn_style = """
                QPushButton {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 12px;
                }
                QPushButton:hover { background: #f5f5f5; }
            """
            log_style = """
                QTextEdit {
                    background: rgba(20, 30, 50, 240);
                    color: #0f0;
                    border: 1px solid rgba(0, 150, 0, 50);
                    border-radius: 6px;
                    font-family: Consolas, monospace;
                    font-size: 11px;
                    padding: 6px;
                }
            """
            tab_style = """
                QTabWidget::pane { background: transparent; border: none; }
                QTabBar::tab {
                    background: rgba(240, 245, 255, 200);
                    color: rgba(0, 0, 0, 0.6);
                    border: none;
                    padding: 8px 14px;
                    margin-right: 3px;
                    border-radius: 6px 6px 0 0;
                }
                QTabBar::tab:selected { background: white; color: #333; }
            """
            check_style = "QCheckBox { color: #333; }"
        
        # Apply styles
        for lbl in [self.prompt_title, self.settings_title, self.acc_title, self.log_title,
                    self.ratio_label, self.length_label, self.resolution_label, self.thread_label,
                    self.output_title, self.batch_info]:
            lbl.setStyleSheet(f"color: {text_color}; background: transparent;")
        
        self.prompt_input.setStyleSheet(input_style)
        self.aspect_combo.setStyleSheet(input_style)
        self.length_combo.setStyleSheet(input_style)
        self.resolution_combo.setStyleSheet(input_style)
        self.thread_spin.setStyleSheet(input_style)
        for tbl in [self.acc_table, self.queue_table, self.run_table, self.done_table]:
            tbl.setStyleSheet(table_style)
        
        for btn in [self.import_btn, self.import_folder_btn, self.clear_btn]:
            btn.setStyleSheet(btn_style)
        
        self.output_input.setStyleSheet(f"""
            QLineEdit {{
                background: {'rgba(35, 45, 65, 220)' if self.is_dark else 'white'};
                color: {text_color};
                border: 1px solid {'rgba(80, 120, 200, 80)' if self.is_dark else 'rgba(100, 150, 200, 100)'};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)
        self.output_browse_btn.setStyleSheet(btn_style)
        
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #27ae60, stop:1 #2ecc71);
                color: white; border: none; border-radius: 6px; padding: 10px 20px; font-weight: bold;
            }
            QPushButton:hover { background: #2ecc71; }
            QPushButton:disabled { background: #666; color: #999; }
        """)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e74c3c, stop:1 #c0392b);
                color: white; border: none; border-radius: 6px; padding: 10px 20px; font-weight: bold;
            }
            QPushButton:hover { background: #c0392b; }
            QPushButton:disabled { background: #666; color: #999; }
        """)
        
        self.log.setStyleSheet(log_style)
        self.tabs.setStyleSheet(tab_style)
        
        # Scroll area styling
        if self.is_dark:
            scroll_style = """
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical {
                    background: rgba(40, 50, 70, 100);
                    width: 8px;
                    border-radius: 4px;
                    margin: 2px;
                }
                QScrollBar::handle:vertical {
                    background: rgba(80, 120, 200, 150);
                    border-radius: 4px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background: rgba(100, 140, 220, 200);
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        else:
            scroll_style = """
                QScrollArea { background: transparent; border: none; }
                QScrollBar:vertical {
                    background: rgba(200, 210, 230, 150);
                    width: 8px;
                    border-radius: 4px;
                    margin: 2px;
                }
                QScrollBar::handle:vertical {
                    background: rgba(100, 150, 200, 180);
                    border-radius: 4px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background: rgba(80, 130, 180, 220);
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        if hasattr(self, 'left_scroll'):
            self.left_scroll.setStyleSheet(scroll_style)
        
        # Progress bar styling
        self.progress_frame.set_dark(self.is_dark)
        self.progress_status.setStyleSheet(f"color: {text_color}; background: transparent;")
        self.progress_percent.setStyleSheet(f"color: {text_color}; background: transparent;")
        self.elapsed_label.setStyleSheet(f"color: rgba({'255,255,255,0.5' if self.is_dark else '0,0,0,0.4'}); background: transparent;")
        
        if self.is_dark:
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background: rgba(20, 30, 50, 200);
                    border: 1px solid rgba(80, 120, 200, 60);
                    border-radius: 9px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #3498db, stop:0.5 #2ecc71, stop:1 #27ae60);
                    border-radius: 8px;
                }
            """)
        else:
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background: rgba(200, 215, 240, 200);
                    border: 1px solid rgba(100, 150, 200, 80);
                    border-radius: 9px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #3498db, stop:0.5 #2ecc71, stop:1 #27ae60);
                    border-radius: 8px;
                }
            """)

    
    def refresh_accounts(self):
        accounts = self.account_manager.get_all_accounts()
        self.acc_table.setRowCount(len(accounts))
        
        for i, acc in enumerate(accounts):
            cb = QCheckBox()
            cb.setChecked(acc.status == "logged_in")
            self.acc_table.setCellWidget(i, 0, cb)
            self.acc_table.setItem(i, 1, QTableWidgetItem(acc.email))
            
            status_item = QTableWidgetItem(acc.status)
            if acc.status == "logged_in":
                status_item.setBackground(QColor("#27ae60"))
                status_item.setForeground(QColor("white"))
            self.acc_table.setItem(i, 2, status_item)
    
    def _get_selected_accounts(self):
        selected = []
        for i in range(self.acc_table.rowCount()):
            cb = self.acc_table.cellWidget(i, 0)
            if cb and cb.isChecked():
                email = self.acc_table.item(i, 1).text()
                acc = self.account_manager.get_account(email)
                if acc and acc.status == "logged_in":
                    selected.append(acc)
        return selected
    
    def _import_prompts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file", "", "Text (*.txt)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    prompts = [l.strip() for l in f if l.strip()]
                self.prompt_input.setPlainText('\n'.join(prompts))
                self._log(f"✅ Đã nhập {len(prompts)} prompt")
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", str(e))

    def _import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn folder chứa file TXT")
        if folder:
            try:
                from pathlib import Path
                txt_files = sorted(Path(folder).glob("*.txt"))
                if not txt_files:
                    QMessageBox.warning(self, "Lỗi", "Không tìm thấy file .txt trong folder")
                    return
                all_prompts = []
                for f in txt_files:
                    lines = [l.strip() for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
                    all_prompts.extend(lines)
                self.prompt_input.setPlainText('\n'.join(all_prompts))
                self._log(f"✅ Đã nhập {len(all_prompts)} prompt từ {len(txt_files)} file")
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", str(e))

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất video")
        if folder:
            self._output_dir = folder
            self.output_input.setText(folder)
            self._log(f"📂 Output: {folder}")

    def _start(self):
        """Start multi-tab video generation"""
        text = self.prompt_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Lỗi", "Nhập prompt trước")
            return
        
        prompts = [p.strip() for p in text.split('\n') if p.strip()]
        accounts = self._get_selected_accounts()
        
        if not accounts:
            QMessageBox.warning(self, "Lỗi", "Chọn tài khoản đã đăng nhập")
            return
        
        # Reset state
        self.prompt_queue = prompts
        self.completed_prompts = []
        self.failed_prompts = []
        self.current_idx = 0
        self.account_prompts = {}
        self.account_prompt_idx = {}
        
        # Setup queue table
        self.queue_table.setRowCount(len(prompts))
        for i, p in enumerate(prompts):
            self.queue_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self.queue_table.setItem(i, 1, QTableWidgetItem(p[:50]))
            self.queue_table.setItem(i, 2, QTableWidgetItem("⏳ Chờ"))
        
        self.run_table.setRowCount(0)
        self.done_table.setRowCount(0)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # Reset progress bar
        self.progress_bar.setRange(0, len(prompts))
        self.progress_bar.setValue(0)
        self.progress_status.setText("🚀 Đang khởi tạo...")
        self.progress_percent.setText(f"0/{len(prompts)} — 0%")
        self.progress_detail.setText("")
        self._start_time = QTime.currentTime()
        self._elapsed_timer.start(1000)
        
        num_tabs = self.thread_spin.value()
        
        # Distribute prompts across accounts
        # Each account gets prompts in round-robin fashion
        for i, acc in enumerate(accounts):
            self.account_prompts[acc.email] = []
            self.account_prompt_idx[acc.email] = []
        
        for idx, prompt in enumerate(prompts):
            acc_idx = idx % len(accounts)
            acc = accounts[acc_idx]
            self.account_prompts[acc.email].append(prompt)
            self.account_prompt_idx[acc.email].append(idx)
        
        total_concurrent = len(accounts) * num_tabs
        self._log(f"🚀 Starting {len(prompts)} prompts")
        self._log(f"   {len(accounts)} accounts × {num_tabs} tabs = {total_concurrent} concurrent")
        
        # Start one AccountWorker per account
        for acc in accounts:
            if self.account_prompts[acc.email]:
                self._start_account_worker(acc, num_tabs)
    
    def _start_account_worker(self, account, num_tabs):
        """Start a multi-tab worker for an account"""
        prompts = self.account_prompts[account.email]
        
        if not prompts:
            return
        
        aspect = self.aspect_combo.currentText()
        length = int(self.length_combo.currentText().split()[0])
        resolution = self.resolution_combo.currentText()
        settings = VideoSettings(aspect_ratio=aspect, video_length=length, resolution=resolution)
        
        # Mark prompts as running
        for idx in self.account_prompt_idx[account.email]:
            if idx < self.queue_table.rowCount():
                self.queue_table.setItem(idx, 2, QTableWidgetItem("🔄 Đợi"))
                self.queue_table.item(idx, 2).setBackground(QColor("#f39c12"))
        
        # Add to running table
        row = self.run_table.rowCount()
        self.run_table.insertRow(row)
        self.run_table.setItem(row, 0, QTableWidgetItem(account.email))
        self.run_table.setItem(row, 1, QTableWidgetItem(f"{len(prompts)} prompts"))
        self.run_table.setItem(row, 2, QTableWidgetItem(f"Khởi tạo {num_tabs} tab..."))
        
        # Create and start worker
        worker = AccountWorker(
            account, prompts, settings,
            num_tabs=num_tabs,
            headless=True
        )
        worker.status_update.connect(self._on_account_status)
        worker.task_completed.connect(self._on_task_completed)
        worker.all_finished.connect(self._on_account_finished)
        
        self.account_workers[account.email] = worker
        worker.start()
        
        self._log(f"▶️ [{account.email}] {len(prompts)} prompts, {num_tabs} tabs")
    
    def _on_account_status(self, email, msg):
        """Handle status update from account worker"""
        # Update running table
        for i in range(self.run_table.rowCount()):
            if self.run_table.item(i, 0) and self.run_table.item(i, 0).text() == email:
                # Extract short message
                short_msg = msg.split(']')[-1].strip()[:40] if ']' in msg else msg[:40]
                self.run_table.setItem(i, 2, QTableWidgetItem(short_msg))
                break
        
        # Update queue table status for current account's prompts
        self._update_queue_status_from_msg(email, msg)
        
        # Update progress status text based on step keywords
        if any(kw in msg for kw in ['Starting', 'Khởi tạo', '🚀']):
            self.progress_status.setText("🚀 Đang khởi tạo browser...")
        elif any(kw in msg for kw in ['Cloudflare', '🔐', 'cf_clearance']):
            self.progress_status.setText("� Đang giải Cloudflare...")
        elif any(kw in msg for kw in ['🍪', 'cookie', 'Injecting']):
            self.progress_status.setText("🍪 Đang thiết lập session...")
        elif any(kw in msg for kw in ['Video mode', '🎬', 'Selecting']):
            self.progress_status.setText("� Đang chọn chế độ Video...")
        elif any(kw in msg for kw in ['prompt', '✏️', 'Entering']):
            self.progress_status.setText("✏️ Đang nhập prompt...")
        elif any(kw in msg for kw in ['Submit', '📤']):
            self.progress_status.setText("📤 Đang gửi yêu cầu...")
        elif any(kw in msg for kw in ['Waiting', '⏳', 'Rendering', 'post ID']):
            self.progress_status.setText("⏳ Đang tạo video...")
        elif any(kw in msg for kw in ['Download', '📥', 'Tải']):
            self.progress_status.setText("📥 Đang tải video...")
        elif any(kw in msg for kw in ['share', '�']):
            self.progress_status.setText("� Đang tạo link chia sẻ...")
    
    def _update_queue_status_from_msg(self, email, msg):
        """Update queue table status based on worker message"""
        if email not in self.account_prompt_idx:
            return
        
        indices = self.account_prompt_idx.get(email, [])
        if not indices:
            return
        
        # Parse Tab ID from message like "[Tab1]", "[Tab2]", "[Tab3]"
        import re
        tab_match = re.search(r'\[Tab(\d+)\]', msg)
        
        if tab_match:
            # Message has Tab ID - update specific prompt based on tab
            tab_num = int(tab_match.group(1)) - 1  # Tab1 = index 0
            if tab_num < len(indices):
                idx = indices[tab_num]
            else:
                return
        else:
            # No Tab ID (browser-level message) - update all pending prompts
            # Determine status based on message keywords
            status_text = None
            status_color = None
            
            if any(kw in msg for kw in ['Starting', '🚀', 'browser']):
                status_text = "🚀 Khởi tạo"
                status_color = "#3498db"
            elif any(kw in msg for kw in ['Cloudflare', '🔐', 'cf_']):
                status_text = "🔐 CF Check"
                status_color = "#9b59b6"
            elif any(kw in msg for kw in ['🍪', 'cookie', 'Inject']):
                status_text = "🍪 Session"
                status_color = "#e67e22"
            elif any(kw in msg for kw in ['Browser ready', '✅ Browser']):
                status_text = "✅ Sẵn sàng"
                status_color = "#27ae60"
            
            if status_text:
                # Update all prompts for this account
                for idx in indices:
                    if idx < self.queue_table.rowCount():
                        item = QTableWidgetItem(status_text)
                        if status_color:
                            item.setBackground(QColor(status_color))
                            item.setForeground(QColor("white"))
                        self.queue_table.setItem(idx, 2, item)
            return
        
        # Tab-specific message - update only that prompt
        if idx >= self.queue_table.rowCount():
            return
        
        # Determine status based on message keywords
        status_text = None
        status_color = None
        
        if any(kw in msg for kw in ['▶️ Starting', 'Starting:']):
            status_text = "▶️ Bắt đầu"
            status_color = "#3498db"
        elif any(kw in msg for kw in ['Video mode', '🎬', 'Selecting']):
            status_text = "🎬 Chọn mode"
            status_color = "#1abc9c"
        elif any(kw in msg for kw in ['⚙️', 'Applying settings']):
            status_text = "⚙️ Cài đặt"
            status_color = "#9b59b6"
        elif any(kw in msg for kw in ['prompt', '✏️', 'Entering']):
            status_text = "✏️ Nhập prompt"
            status_color = "#3498db"
        elif any(kw in msg for kw in ['Submit', '📤']):
            status_text = "📤 Gửi"
            status_color = "#f39c12"
        elif any(kw in msg for kw in ['post ID', 'Post ID', '✅ Post']):
            status_text = "🆔 Có Post ID"
            status_color = "#2ecc71"
        elif any(kw in msg for kw in ['Rendering', 'render', '⏳']):
            # Extract time if available
            time_match = re.search(r'\((\d+)s\)', msg)
            if time_match:
                status_text = f"⏳ {time_match.group(1)}s"
            else:
                status_text = "⏳ Rendering"
            status_color = "#f39c12"
        elif any(kw in msg for kw in ['share', '🔗']):
            status_text = "🔗 Share"
            status_color = "#9b59b6"
        elif any(kw in msg for kw in ['Download', '📥', 'Downloading']):
            status_text = "📥 Tải xuống"
            status_color = "#3498db"
        elif any(kw in msg for kw in ['✅ Downloaded', '✅ Done']):
            status_text = "✅ Xong"
            status_color = "#27ae60"
        elif any(kw in msg for kw in ['Ready', '🔄 Ready']):
            status_text = "🔄 Tiếp tục"
            status_color = "#1abc9c"
        
        if status_text:
            item = QTableWidgetItem(status_text)
            if status_color:
                item.setBackground(QColor(status_color))
                item.setForeground(QColor("white"))
            self.queue_table.setItem(idx, 2, item)
    
    def _on_task_completed(self, email, task):
        """Handle individual task completion"""
        # Find the queue index for this prompt
        idx = -1
        if email in self.account_prompt_idx:
            for i, prompt_idx in enumerate(self.account_prompt_idx[email]):
                if i < len(self.account_prompts.get(email, [])):
                    if self.account_prompts[email][i] == task.prompt:
                        idx = prompt_idx
                        # Remove from tracking
                        self.account_prompts[email].pop(i)
                        self.account_prompt_idx[email].pop(i)
                        break
        
        # Update queue table
        if idx >= 0 and idx < self.queue_table.rowCount():
            if task.status == "completed":
                self.queue_table.setItem(idx, 2, QTableWidgetItem("✅ Xong"))
                self.queue_table.item(idx, 2).setBackground(QColor("#27ae60"))
                self.completed_prompts.append(task)
                
                # Add to done table
                row = self.done_table.rowCount()
                self.done_table.insertRow(row)
                self.done_table.setItem(row, 0, QTableWidgetItem(email))
                self.done_table.setItem(row, 1, QTableWidgetItem(task.prompt[:40]))
                self.done_table.setItem(row, 2, QTableWidgetItem(task.post_id or ""))
                
                self._log(f"✅ [{email}] {task.post_id}")
            else:
                self.queue_table.setItem(idx, 2, QTableWidgetItem("❌ Lỗi"))
                self.queue_table.item(idx, 2).setBackground(QColor("#e74c3c"))
                self.failed_prompts.append(task)
                self._log(f"❌ [{email}] {task.error_message[:30]}")
        
        # Update progress bar
        done_count = len(self.completed_prompts) + len(self.failed_prompts)
        total = len(self.prompt_queue)
        self.progress_bar.setValue(done_count)
        pct = int(done_count * 100 / total) if total > 0 else 0
        self.progress_percent.setText(f"{done_count}/{total} — {pct}%")
        
        if task.status == "completed":
            self.progress_status.setText(f"✅ Hoàn thành {done_count}/{total}")
        else:
            self.progress_status.setText(f"⚠️ Lỗi — {done_count}/{total} xong")
        
        # Save to history
        if task.status == "completed":
            self.history_manager.add_history(task)
            self.video_completed.emit()
    
    def _on_account_finished(self, email):
        """Handle when an account worker finishes all its prompts"""
        # Remove from running table
        for i in range(self.run_table.rowCount()):
            if self.run_table.item(i, 0) and self.run_table.item(i, 0).text() == email:
                self.run_table.removeRow(i)
                break
        
        # Clean up worker
        if email in self.account_workers:
            del self.account_workers[email]
        
        self._log(f"🏁 [{email}] Finished")
        
        # Check if all workers are done
        if not self.account_workers:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._elapsed_timer.stop()
            
            # Final progress state
            total = len(self.prompt_queue)
            done = len(self.completed_prompts)
            failed = len(self.failed_prompts)
            self.progress_bar.setValue(total)
            self.progress_percent.setText(f"{done + failed}/{total} — 100%")
            if failed == 0:
                self.progress_status.setText(f"🎉 Hoàn thành tất cả! {done} video")
            else:
                self.progress_status.setText(f"� Xong: {done} thành công, {failed} lỗi")
            
            self._log(f"🎉 All done! {done} OK, {failed} failed")
    
    def _stop(self):
        """Stop all account workers"""
        for worker in self.account_workers.values():
            worker.stop()
        self.account_workers.clear()
        self.run_table.setRowCount(0)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._elapsed_timer.stop()
        
        # Reset progress
        done = len(self.completed_prompts)
        failed = len(self.failed_prompts)
        total = len(self.prompt_queue)
        pct = int((done + failed) * 100 / total) if total > 0 else 0
        self.progress_status.setText(f"⏹️ Đã dừng — {done + failed}/{total} ({pct}%)")
        
        self._log("⏹️ Stopped")
    
    def _update_stats(self):
        self.stat_total.set_value(len(self.prompt_queue))
        self.stat_running.set_value(len(self.account_workers))
        self.stat_done.set_value(len(self.completed_prompts))
        self.stat_failed.set_value(len(self.failed_prompts))
    
    def _update_elapsed(self):
        """Update elapsed time display"""
        if self._start_time:
            elapsed = self._start_time.secsTo(QTime.currentTime())
            mins = elapsed // 60
            secs = elapsed % 60
            self.elapsed_label.setText(f"⏱ {mins:02d}:{secs:02d}")
    
    def _load_settings(self):
        if SETTINGS_FILE.exists():
            try:
                s = json.loads(SETTINGS_FILE.read_text())
                self.aspect_combo.setCurrentIndex(s.get("aspect", 4))
                self.length_combo.setCurrentIndex(s.get("length", 0))
                self.resolution_combo.setCurrentIndex(s.get("resolution", 0))
                self.thread_spin.setValue(min(s.get("concurrent", 2), 3))
            except:
                pass
        
        # Connect signals to save settings when changed
        self.aspect_combo.currentIndexChanged.connect(self._save_settings)
        self.length_combo.currentIndexChanged.connect(self._save_settings)
        self.resolution_combo.currentIndexChanged.connect(self._save_settings)
        self.thread_spin.valueChanged.connect(self._save_settings)
    
    def _save_settings(self):
        """Save current settings to file"""
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            settings = {
                "aspect": self.aspect_combo.currentIndex(),
                "length": self.length_combo.currentIndex(),
                "resolution": self.resolution_combo.currentIndex(),
                "concurrent": self.thread_spin.value()
            }
            SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
        except Exception as e:
            print(f"Failed to save settings: {e}")
    
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
