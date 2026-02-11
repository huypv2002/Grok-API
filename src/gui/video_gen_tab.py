"""Video Generation Tab - Clean Modern UI with Multi-Tab Support + Image-to-Video"""
import json
import re
import os
import asyncio
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTextEdit, QComboBox, QPushButton, QMessageBox, QCheckBox,
    QFileDialog, QLabel, QTableWidget, QTableWidgetItem, QLineEdit,
    QHeaderView, QSplitter, QFrame, QTabWidget, QProgressBar, QScrollArea,
    QButtonGroup, QRadioButton, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Signal, QThread, Qt, QTimer, QTime, QSize
from PySide6.QtGui import QColor, QFont, QPixmap, QIcon

from ..core.account_manager import AccountManager
from ..core.video_generator import VideoGenerator, MultiTabVideoGenerator, ZENDRIVER_AVAILABLE
from ..core.history_manager import HistoryManager


class NoScrollComboBox(QComboBox):
    """ComboBox chỉ cho phép click chọn, không thay đổi giá trị khi scroll."""
    def wheelEvent(self, event):
        event.ignore()  # Bỏ qua scroll event
from ..core.models import VideoSettings


def natural_sort_key(s):
    """Natural sort key: '2.jpg' < '10.jpg' (not lexicographic)"""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(s))]


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}

SETTINGS_FILE = Path("data/settings.json")
DEFAULT_OUTPUT_DIR = Path("output")


class AccountWorker(QThread):
    """
    Worker for a single account with multi-tab support.
    1 browser per account, 3 tabs running concurrently.
    Supports both text-to-video and image-to-video.
    """
    status_update = Signal(str, str)  # email, message
    task_completed = Signal(str, object)  # email, VideoTask
    all_finished = Signal(str)  # email
    
    def __init__(self, account, prompts, settings, output_dir, num_tabs=3, headless=True):
        """
        Args:
            prompts: List of tuples (prompt, image_path, subfolder, stt)
            output_dir: Base output directory
        """
        super().__init__()
        self.account = account
        self.prompts = prompts  # list of (prompt, image_path, subfolder, stt)
        self.settings = settings
        self.output_dir = output_dir
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
                on_task_complete,
                output_dir=self.output_dir
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
        
        # Track which tab is currently processing which queue index
        # key: "email:tab_num" -> queue_idx
        self.tab_current_idx: dict = {}
        
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
        
        # === Mode selector: Text→Video / Image→Video ===
        self._gen_mode = "text"  # "text" or "image"
        
        mode_row = QHBoxLayout()
        self.mode_text_btn = QPushButton("📝 Text → Video")
        self.mode_image_btn = QPushButton("🖼️ Image → Video")
        self.mode_text_btn.setCheckable(True)
        self.mode_image_btn.setCheckable(True)
        self.mode_text_btn.setChecked(True)
        self.mode_text_btn.clicked.connect(lambda: self._switch_mode("text"))
        self.mode_image_btn.clicked.connect(lambda: self._switch_mode("image"))
        mode_row.addWidget(self.mode_text_btn)
        mode_row.addWidget(self.mode_image_btn)
        left_layout.addLayout(mode_row)
        
        # === TEXT MODE: Prompt input ===
        self.text_mode_widget = QWidget()
        self.text_mode_widget.setStyleSheet("background: transparent;")
        text_layout = QVBoxLayout(self.text_mode_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(8)
        
        self.prompt_title = QLabel("📝 Prompts")
        self.prompt_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        text_layout.addWidget(self.prompt_title)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Nhập prompt (mỗi dòng 1 prompt)...")
        self.prompt_input.setMaximumHeight(120)
        text_layout.addWidget(self.prompt_input)
        
        btn_row = QHBoxLayout()
        self.import_btn = QPushButton("📄 Nhập TXT")
        self.import_folder_btn = QPushButton("📂 Nhập Folder")
        self.clear_btn = QPushButton("🗑️ Xóa")
        self.import_btn.clicked.connect(self._import_prompts)
        self.import_folder_btn.clicked.connect(self._import_folder)
        self.clear_btn.clicked.connect(self._clear_prompts)
        self.import_btn.setToolTip("Nhập 1 file TXT → tạo subfolder trùng tên")
        self.import_folder_btn.setToolTip("Chọn folder chứa nhiều file TXT → mỗi file = 1 batch")
        btn_row.addWidget(self.import_btn)
        btn_row.addWidget(self.import_folder_btn)
        btn_row.addWidget(self.clear_btn)
        text_layout.addLayout(btn_row)
        
        left_layout.addWidget(self.text_mode_widget)
        
        # === IMAGE MODE: Folder + TXT pairs ===
        self.image_mode_widget = QWidget()
        self.image_mode_widget.setStyleSheet("background: transparent;")
        self.image_mode_widget.setVisible(False)
        img_layout = QVBoxLayout(self.image_mode_widget)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.setSpacing(8)
        
        img_title = QLabel("🖼️ Ảnh + Prompt")
        img_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        img_layout.addWidget(img_title)
        self._img_title_label = img_title
        
        img_desc = QLabel("Mỗi cặp: 1 folder ảnh + 1 file TXT prompt\nẢnh sắp xếp tự nhiên (1, 2, ..., 10)\nDòng 1 TXT → Ảnh 1, Dòng 2 → Ảnh 2...")
        img_desc.setFont(QFont("Segoe UI", 9))
        img_desc.setWordWrap(True)
        img_layout.addWidget(img_desc)
        self._img_desc_label = img_desc
        
        # Pair list
        self.pair_list = QListWidget()
        self.pair_list.setMaximumHeight(100)
        self.pair_list.setToolTip("Danh sách cặp Folder + TXT")
        img_layout.addWidget(self.pair_list)
        
        pair_btn_row = QHBoxLayout()
        self.add_pair_btn = QPushButton("➕ Thêm cặp")
        self.remove_pair_btn = QPushButton("🗑️ Xóa cặp")
        self.import_pairs_btn = QPushButton("📂 Nhập Folder")
        self.add_pair_btn.clicked.connect(self._add_image_pair)
        self.remove_pair_btn.clicked.connect(self._remove_image_pair)
        self.import_pairs_btn.clicked.connect(self._import_image_folder)
        self.add_pair_btn.setToolTip("Chọn 1 folder ảnh + 1 file TXT")
        self.import_pairs_btn.setToolTip("Chọn folder cha chứa nhiều subfolder\nMỗi subfolder: ảnh + file .txt cùng tên")
        pair_btn_row.addWidget(self.add_pair_btn)
        pair_btn_row.addWidget(self.import_pairs_btn)
        pair_btn_row.addWidget(self.remove_pair_btn)
        img_layout.addLayout(pair_btn_row)
        
        # Summary
        self.pair_summary = QLabel("")
        self.pair_summary.setFont(QFont("Segoe UI", 9))
        self.pair_summary.setWordWrap(True)
        img_layout.addWidget(self.pair_summary)
        
        left_layout.addWidget(self.image_mode_widget)
        
        # Store image pairs: list of (folder_path, txt_path, images_list, prompts_list)
        self._image_pairs = []
        
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
        self.aspect_combo = NoScrollComboBox()
        self.aspect_combo.addItems(["2:3", "3:2", "1:1", "9:16", "16:9"])
        self.aspect_combo.setCurrentIndex(4)  # default 16:9
        self.aspect_combo.setMinimumWidth(120)
        
        # Thời lượng video
        self.length_combo = NoScrollComboBox()
        self.length_combo.addItems(["6 giây", "10 giây"])
        self.length_combo.setMinimumWidth(120)
        
        # Độ phân giải
        self.resolution_combo = NoScrollComboBox()
        self.resolution_combo.addItems(["480p", "720p"])
        self.resolution_combo.setMinimumWidth(120)
        
        self.ratio_label = QLabel("Tỷ lệ:")
        self.length_label = QLabel("Thời lượng:")
        self.resolution_label = QLabel("Phân giải:")
        
        form.addRow(self.ratio_label, self.aspect_combo)
        form.addRow(self.length_label, self.length_combo)
        form.addRow(self.resolution_label, self.resolution_combo)
        
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
        self.queue_table.setColumnCount(4)
        self.queue_table.setHorizontalHeaderLabels(["#", "Prompt", "Ảnh", "Trạng thái"])
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue_table.setColumnWidth(0, 35)
        self.queue_table.setColumnWidth(2, 50)
        self.queue_table.setColumnWidth(3, 90)
        self.queue_table.setIconSize(QSize(40, 40))
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
                    self.ratio_label, self.length_label, self.resolution_label,
                    self.output_title, self.batch_info]:
            lbl.setStyleSheet(f"color: {text_color}; background: transparent;")
        
        self.prompt_input.setStyleSheet(input_style)
        self.aspect_combo.setStyleSheet(input_style)
        self.length_combo.setStyleSheet(input_style)
        self.resolution_combo.setStyleSheet(input_style)
        for tbl in [self.acc_table, self.queue_table, self.run_table, self.done_table]:
            tbl.setStyleSheet(table_style)
        
        # Pair list (image mode) styling
        if self.is_dark:
            self.pair_list.setStyleSheet("""
                QListWidget {
                    background: rgba(20, 30, 50, 180);
                    color: white;
                    border: 1px solid rgba(80, 120, 200, 50);
                    border-radius: 6px;
                    padding: 4px;
                }
                QListWidget::item { padding: 4px 6px; }
                QListWidget::item:selected { background: rgba(80, 120, 200, 100); }
            """)
        else:
            self.pair_list.setStyleSheet("""
                QListWidget {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 80);
                    border-radius: 6px;
                    padding: 4px;
                }
                QListWidget::item { padding: 4px 6px; }
                QListWidget::item:selected { background: rgba(80, 120, 200, 100); }
            """)
        
        for btn in [self.import_btn, self.import_folder_btn, self.clear_btn,
                    self.add_pair_btn, self.remove_pair_btn, self.import_pairs_btn]:
            btn.setStyleSheet(btn_style)
        
        # Mode buttons styling
        mode_active = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3498db, stop:1 #2980b9);
                color: white; border: none; border-radius: 6px; padding: 8px 12px; font-weight: bold;
            }
        """
        mode_inactive = btn_style
        self.mode_text_btn.setStyleSheet(mode_active if self._gen_mode == "text" else mode_inactive)
        self.mode_image_btn.setStyleSheet(mode_active if self._gen_mode == "image" else mode_inactive)
        
        # Image mode labels
        for lbl in [self._img_title_label, self._img_desc_label, self.pair_summary]:
            lbl.setStyleSheet(f"color: {text_color}; background: transparent;")
        
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

    
    # ==================== Mode Switching ====================
    
    def _switch_mode(self, mode):
        """Switch between text and image mode"""
        self._gen_mode = mode
        self.mode_text_btn.setChecked(mode == "text")
        self.mode_image_btn.setChecked(mode == "image")
        self.text_mode_widget.setVisible(mode == "text")
        self.image_mode_widget.setVisible(mode == "image")
        # Hide aspect ratio in image mode (post page doesn't have it)
        self.ratio_label.setVisible(mode == "text")
        self.aspect_combo.setVisible(mode == "text")
        # Update mode button styling (active/inactive)
        self._apply_theme()
    
    # ==================== Image Pair Management ====================
    
    def _add_image_pair(self):
        """Add a folder + TXT pair for image-to-video"""
        # Step 1: Select image folder
        folder = QFileDialog.getExistingDirectory(self, "Chọn folder chứa ảnh")
        if not folder:
            return
        
        # Find images with natural sort
        images = []
        for f in Path(folder).iterdir():
            if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file():
                images.append(f)
        images.sort(key=lambda f: natural_sort_key(f.name))
        
        if not images:
            QMessageBox.warning(self, "Lỗi", f"Không tìm thấy ảnh trong:\n{folder}")
            return
        
        # Step 2: Select TXT file
        txt_path, _ = QFileDialog.getOpenFileName(self, "Chọn file TXT prompt", "", "Text (*.txt)")
        if not txt_path:
            return
        
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                prompts = [l.strip() for l in f if l.strip()]
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không đọc được file TXT:\n{e}")
            return
        
        if not prompts:
            QMessageBox.warning(self, "Lỗi", "File TXT rỗng")
            return
        
        # Validate: number of images vs prompts
        n_img = len(images)
        n_prompt = len(prompts)
        if n_img != n_prompt:
            reply = QMessageBox.question(
                self, "Số lượng không khớp",
                f"Folder có {n_img} ảnh, TXT có {n_prompt} dòng.\n"
                f"Sẽ dùng {min(n_img, n_prompt)} cặp (bỏ phần dư).\n\nTiếp tục?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        count = min(n_img, n_prompt)
        images = images[:count]
        prompts = prompts[:count]
        
        # Store pair
        self._image_pairs.append((folder, txt_path, images, prompts))
        
        # Update list widget
        folder_name = Path(folder).name
        txt_name = Path(txt_path).name
        self.pair_list.addItem(f"📁 {folder_name} + 📄 {txt_name} ({count} cặp)")
        
        self._update_pair_summary()
        self._log(f"✅ Thêm cặp: {folder_name} + {txt_name} ({count} ảnh)")
    
    def _remove_image_pair(self):
        """Remove selected pair"""
        row = self.pair_list.currentRow()
        if row >= 0 and row < len(self._image_pairs):
            self._image_pairs.pop(row)
            self.pair_list.takeItem(row)
            self._update_pair_summary()
    
    def _import_image_folder(self):
        """
        Import nhiều cặp từ 1 folder cha.
        
        Hỗ trợ 2 cấu trúc:
        
        1) Subfolder structure:
           parent/
             subfolder1/        ← ảnh
             subfolder1.txt     ← prompt
             subfolder2/
             subfolder2.txt
        
        2) Flat structure (folder ảnh + TXT cùng cấp):
           parent/
             folder_a/          ← ảnh
             folder_a.txt       ← prompt
             folder_b/
             folder_b.txt
        """
        parent = QFileDialog.getExistingDirectory(self, "Chọn folder cha chứa nhiều cặp (subfolder + TXT)")
        if not parent:
            return
        
        parent_path = Path(parent)
        found_pairs = 0
        
        # Tìm tất cả subfolder có file TXT cùng tên
        for item in sorted(parent_path.iterdir(), key=lambda f: natural_sort_key(f.name)):
            if not item.is_dir():
                continue
            # Skip hidden folders
            if item.name.startswith('.'):
                continue
            
            # Tìm file TXT match: cùng tên subfolder hoặc nằm trong subfolder
            txt_candidates = [
                parent_path / f"{item.name}.txt",           # parent/subfolder.txt
                item / f"{item.name}.txt",                   # subfolder/subfolder.txt
                item / "prompt.txt",                          # subfolder/prompt.txt
                item / "prompts.txt",                         # subfolder/prompts.txt
            ]
            
            txt_path = None
            for candidate in txt_candidates:
                if candidate.exists():
                    txt_path = candidate
                    break
            
            if not txt_path:
                # Tìm bất kỳ file .txt nào trong parent cùng tên
                for f in parent_path.iterdir():
                    if f.suffix.lower() == '.txt' and f.stem.lower() == item.name.lower():
                        txt_path = f
                        break
            
            if not txt_path:
                continue
            
            # Tìm ảnh trong subfolder
            images = []
            for f in item.iterdir():
                if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file():
                    images.append(f)
            images.sort(key=lambda f: natural_sort_key(f.name))
            
            if not images:
                continue
            
            # Đọc prompts
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    prompts = [l.strip() for l in f if l.strip()]
            except:
                continue
            
            if not prompts:
                continue
            
            # Match count
            count = min(len(images), len(prompts))
            images = images[:count]
            prompts = prompts[:count]
            
            # Add pair
            self._image_pairs.append((str(item), str(txt_path), images, prompts))
            self.pair_list.addItem(f"📁 {item.name} + 📄 {txt_path.name} ({count} cặp)")
            found_pairs += 1
        
        if found_pairs > 0:
            self._update_pair_summary()
            self._log(f"✅ Đã nhập {found_pairs} cặp từ folder: {parent_path.name}")
        else:
            QMessageBox.warning(
                self, "Không tìm thấy cặp",
                f"Không tìm thấy cặp subfolder + TXT trong:\n{parent}\n\n"
                f"Cấu trúc cần:\n"
                f"  📁 folder_cha/\n"
                f"    📁 ten_1/  (chứa ảnh)\n"
                f"    📄 ten_1.txt  (chứa prompt)\n"
                f"    📁 ten_2/\n"
                f"    📄 ten_2.txt\n"
                f"    ..."
            )
    
    def _update_pair_summary(self):
        """Update summary label"""
        total = sum(len(imgs) for _, _, imgs, _ in self._image_pairs)
        n_pairs = len(self._image_pairs)
        if n_pairs > 0:
            self.pair_summary.setText(f"📊 {n_pairs} cặp, tổng {total} video")
        else:
            self.pair_summary.setText("")
    
    def _get_image_prompts(self):
        """Get all (prompt, image_path, subfolder_name, stt) tuples from image pairs, in order.
        
        Returns list of tuples:
        - prompt: text prompt
        - image_path: path to source image
        - subfolder_name: name of subfolder (from TXT filename without extension)
        - stt: 1-based index within that TXT file
        """
        from pathlib import Path
        result = []
        for folder, txt, images, prompts in self._image_pairs:
            # Get subfolder name from TXT filename (without .txt extension)
            txt_path = Path(txt)
            subfolder_name = txt_path.stem  # filename without extension
            
            for idx, (img, prompt) in enumerate(zip(images, prompts), start=1):
                result.append((prompt, str(img), subfolder_name, idx))
        return result
    
    # ==================== Account & Settings ====================
    
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
    
    def _clear_prompts(self):
        """Clear prompts and batch info"""
        self.prompt_input.clear()
        self._batch_queue = []
        self.batch_info.setText("")
    
    def _import_prompts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file", "", "Text (*.txt)")
        if path:
            try:
                from pathlib import Path
                txt_path = Path(path)
                with open(path, 'r', encoding='utf-8') as f:
                    prompts = [l.strip() for l in f if l.strip()]
                self.prompt_input.setPlainText('\n'.join(prompts))
                
                # Store batch info: single file = single batch
                subfolder_name = txt_path.stem  # filename without .txt
                self._batch_queue = [(subfolder_name, prompts)]
                self.batch_info.setText(f"📁 Batch: {subfolder_name} ({len(prompts)} prompts)")
                
                self._log(f"✅ Đã nhập {len(prompts)} prompt từ {subfolder_name}.txt")
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", str(e))

    def _import_folder(self):
        """Import folder chứa nhiều file TXT - mỗi file = 1 batch với subfolder riêng"""
        folder = QFileDialog.getExistingDirectory(self, "Chọn folder chứa file TXT")
        if folder:
            try:
                from pathlib import Path
                txt_files = sorted(Path(folder).glob("*.txt"))
                if not txt_files:
                    QMessageBox.warning(self, "Lỗi", "Không tìm thấy file .txt trong folder")
                    return
                
                # Store batch info: list of (subfolder_name, [prompts])
                self._batch_queue = []
                all_prompts = []
                
                for f in txt_files:
                    lines = [l.strip() for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
                    if lines:
                        subfolder_name = f.stem  # filename without .txt
                        self._batch_queue.append((subfolder_name, lines))
                        all_prompts.extend(lines)
                
                self.prompt_input.setPlainText('\n'.join(all_prompts))
                self._log(f"✅ Đã nhập {len(all_prompts)} prompt từ {len(txt_files)} file")
                
                # Show batch info
                batch_info = ", ".join([f"{name}({len(prompts)})" for name, prompts in self._batch_queue])
                self.batch_info.setText(f"📁 Batches: {batch_info}")
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", str(e))

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất video")
        if folder:
            self._output_dir = folder
            self.output_input.setText(folder)
            self._log(f"📂 Output: {folder}")

    def _start(self):
        """Start multi-tab video generation (text or image mode)"""
        from pathlib import Path
        
        # Build prompt list based on mode
        if self._gen_mode == "image":
            # Image mode: get (prompt, image_path, subfolder, stt) tuples
            all_items = self._get_image_prompts()
            if not all_items:
                QMessageBox.warning(self, "Lỗi", "Thêm ít nhất 1 cặp Folder + TXT")
                return
        else:
            # Text mode: get prompts from text input
            text = self.prompt_input.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "Lỗi", "Nhập prompt trước")
                return
            
            # Check if we have batch info from folder import
            if hasattr(self, '_batch_queue') and self._batch_queue:
                # Build items with subfolder info from batch queue
                all_items = []
                for subfolder_name, prompts in self._batch_queue:
                    for idx, prompt in enumerate(prompts, start=1):
                        all_items.append((prompt, None, subfolder_name, idx))
            else:
                # Simple text input - no subfolder
                prompts = [p.strip() for p in text.split('\n') if p.strip()]
                all_items = [(p, None, None, i+1) for i, p in enumerate(prompts)]
        
        accounts = self._get_selected_accounts()
        if not accounts:
            QMessageBox.warning(self, "Lỗi", "Chọn tài khoản đã đăng nhập")
            return
        
        total = len(all_items)
        
        # Create subfolders for each unique subfolder name
        base_output = Path(self._output_dir)
        subfolders_created = set()
        for item in all_items:
            subfolder = item[2]  # subfolder name (from TXT filename)
            if subfolder and subfolder not in subfolders_created:
                subfolder_path = base_output / subfolder
                subfolder_path.mkdir(parents=True, exist_ok=True)
                subfolders_created.add(subfolder)
        if subfolders_created:
            self._log(f"📁 Tạo {len(subfolders_created)} subfolder: {', '.join(sorted(subfolders_created))}")
        
        # Reset state
        self.prompt_queue = all_items  # list of (prompt, image_path, subfolder, stt)
        self.completed_prompts = []
        self.failed_prompts = []
        self.current_idx = 0
        self._processed_indices = set()  # Track which queue indices have been processed
        self._mapped_queue_indices = set()  # Track which queue indices have been mapped to tabs
        self.account_prompts = {}
        self.account_prompt_idx = {}
        self.tab_current_idx = {}
        
        # Setup queue table — 4 columns: #, Prompt, Ảnh, Trạng thái
        self.queue_table.setRowCount(total)
        for i, item in enumerate(all_items):
            prompt = item[0]
            img_path = item[1]
            self.queue_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self.queue_table.setItem(i, 1, QTableWidgetItem(prompt[:50]))
            # Thumbnail ảnh nhỏ thay vì text
            if img_path and os.path.exists(img_path):
                pix = QPixmap(img_path)
                if not pix.isNull():
                    thumb = pix.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    img_item = QTableWidgetItem()
                    img_item.setIcon(QIcon(thumb))
                    img_item.setToolTip(os.path.basename(img_path))
                    self.queue_table.setItem(i, 2, img_item)
                    self.queue_table.setRowHeight(i, 46)
                else:
                    self.queue_table.setItem(i, 2, QTableWidgetItem(os.path.basename(img_path)[:10]))
            else:
                self.queue_table.setItem(i, 2, QTableWidgetItem(""))
            self.queue_table.setItem(i, 3, QTableWidgetItem("⏳ Chờ"))
        
        self.run_table.setRowCount(0)
        self.done_table.setRowCount(0)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # Reset progress bar
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)
        mode_label = "Image→Video" if self._gen_mode == "image" else "Text→Video"
        self.progress_status.setText(f"🚀 Đang khởi tạo ({mode_label})...")
        self.progress_percent.setText(f"0/{total} — 0%")
        self.progress_detail.setText("")
        self._start_time = QTime.currentTime()
        self._elapsed_timer.start(1000)
        
        num_tabs = 3  # Fixed: 3 tabs per account
        
        # Distribute items: round-robin cho mỗi account
        # VD: 9 items, 3 accounts → acc0: [1,4,7], acc1: [2,5,8], acc2: [3,6,9]
        n_acc = len(accounts)
        for acc in accounts:
            self.account_prompts[acc.email] = []
            self.account_prompt_idx[acc.email] = []
        for i, item in enumerate(all_items):
            acc = accounts[i % n_acc]
            self.account_prompts[acc.email].append(item)
            self.account_prompt_idx[acc.email].append(i)
        
        total_concurrent = len(accounts) * num_tabs
        self._log(f"🚀 Starting {total} videos ({mode_label})")
        self._log(f"   {len(accounts)} accounts × {num_tabs} tabs = {total_concurrent} concurrent")
        for acc in accounts:
            idx_list = self.account_prompt_idx[acc.email]
            if idx_list:
                self._log(f"   [{acc.email[:20]}] #{idx_list[0]+1} → #{idx_list[-1]+1} ({len(idx_list)} items)")
        
        # Start one AccountWorker per account — stagger 5s
        self._pending_accounts = []
        for acc in accounts:
            if self.account_prompts[acc.email]:
                self._pending_accounts.append((acc, num_tabs))
        
        if self._pending_accounts:
            acc, tabs = self._pending_accounts.pop(0)
            self._start_account_worker(acc, tabs)
            
            for i, (acc, tabs) in enumerate(self._pending_accounts):
                QTimer.singleShot((i + 1) * 5000, lambda a=acc, t=tabs: self._start_account_worker(a, t))
            self._pending_accounts = []
    
    def _start_account_worker(self, account, num_tabs):
        """Start a multi-tab worker for an account"""
        items = self.account_prompts[account.email]  # list of (prompt, image_path) or (prompt, None)
        
        if not items:
            return
        
        aspect = self.aspect_combo.currentText()
        length = int(self.length_combo.currentText().split()[0])
        resolution = self.resolution_combo.currentText()
        settings = VideoSettings(aspect_ratio=aspect, video_length=length, resolution=resolution)
        
        # Add to running table
        row = self.run_table.rowCount()
        self.run_table.insertRow(row)
        self.run_table.setItem(row, 0, QTableWidgetItem(account.email))
        idx_list = self.account_prompt_idx[account.email]
        self.run_table.setItem(row, 1, QTableWidgetItem(f"#{idx_list[0]+1}→#{idx_list[-1]+1} ({len(items)} items)"))
        self.run_table.setItem(row, 2, QTableWidgetItem(f"Khởi tạo {num_tabs} tab..."))
        
        # Create and start worker — pass items directly (tuples supported by generate_batch)
        worker = AccountWorker(
            account, items, settings, self._output_dir,
            num_tabs=num_tabs,
            headless=True
        )
        worker.status_update.connect(self._on_account_status)
        worker.task_completed.connect(self._on_task_completed)
        worker.all_finished.connect(self._on_account_finished)
        
        self.account_workers[account.email] = worker
        worker.start()
        
        self._log(f"▶️ [{account.email}] #{idx_list[0]+1}→#{idx_list[-1]+1} ({len(items)} items), {num_tabs} tabs")
    
    def _on_account_status(self, email, msg):
        """Handle status update from account worker.
        
        Quy tắc:
        - Browser-level messages (không có [TabN]): chỉ update running table
        - Tab-level messages (có [TabN]): update queue table cho prompt đang xử lý
        """
        import re
        
        # Update running table — luôn luôn
        for i in range(self.run_table.rowCount()):
            if self.run_table.item(i, 0) and self.run_table.item(i, 0).text() == email:
                short_msg = msg.split(']')[-1].strip()[:40] if ']' in msg else msg[:40]
                self.run_table.setItem(i, 2, QTableWidgetItem(short_msg))
                break
        
        # Check if tab-level message
        tab_match = re.search(r'\[Tab(\d+)\]', msg)
        
        if tab_match:
            # Tab-level → update queue table
            self._update_queue_from_tab_msg(email, msg, tab_match)
        
        # Update progress status bar (global)
        if any(kw in msg for kw in ['Cloudflare', '🔐', 'cf_clearance']):
            self.progress_status.setText(f"🔐 [{email[:15]}] Giải Cloudflare...")
        elif any(kw in msg for kw in ['Browser ready', '✅ Browser']):
            self.progress_status.setText(f"✅ [{email[:15]}] Browser sẵn sàng")
        elif '📤' in msg:
            self.progress_status.setText("📤 Đang gửi yêu cầu...")
        elif '⏳' in msg and 'Rendering' in msg:
            self.progress_status.setText("⏳ Đang tạo video...")
        elif '📥' in msg:
            self.progress_status.setText("📥 Đang tải video...")
    
    def _update_queue_from_tab_msg(self, email, msg, tab_match):
        """Update queue table from a tab-specific message.
        
        Logic:
        1. Khi thấy "Starting: <prompt>..." → map tab_key → queue_idx bằng prompt text
        2. Các message sau đó update queue_idx đã map
        3. Prompt chưa được tab nào pick → giữ "⏳ Chờ"
        """
        import re
        
        if email not in self.account_prompt_idx:
            return
        
        indices = self.account_prompt_idx.get(email, [])
        if not indices:
            return
        
        tab_num = int(tab_match.group(1)) - 1
        tab_key = f"{email}:{tab_num}"
        
        # Initialize mapped indices tracking if not exists
        if not hasattr(self, '_mapped_queue_indices'):
            self._mapped_queue_indices = set()
        
        # Detect "Starting:" → map tab to prompt by matching text
        start_match = re.search(r'(?:Starting|Retrying[^:]*): (.+?)\.\.\.', msg)
        if start_match:
            prompt_prefix = start_match.group(1).strip()[:20]
            for qi in indices:
                # Skip already mapped indices
                if qi in self._mapped_queue_indices:
                    continue
                if qi < self.queue_table.rowCount():
                    queue_item = self.queue_table.item(qi, 1)
                    if queue_item and queue_item.text()[:20] == prompt_prefix:
                        self.tab_current_idx[tab_key] = qi
                        self._mapped_queue_indices.add(qi)
                        break
        
        # Get mapped queue index
        idx = self.tab_current_idx.get(tab_key)
        if idx is None or idx >= self.queue_table.rowCount():
            return
        
        # Don't overwrite completed/failed status
        current_status = self.queue_table.item(idx, 3)
        if current_status and current_status.text() in ('✅ Xong', '❌ Lỗi'):
            return
        
        # Map message → status
        status_text = None
        status_color = None
        
        if any(kw in msg for kw in ['▶️ Starting', 'Starting:']):
            status_text = "▶️ Bắt đầu"
            status_color = "#3498db"
        elif '🎬' in msg:
            status_text = "🎬 Chọn mode"
            status_color = "#1abc9c"
        elif '⚙️' in msg:
            status_text = "⚙️ Cài đặt"
            status_color = "#9b59b6"
        elif '✏️' in msg:
            status_text = "✏️ Nhập prompt"
            status_color = "#3498db"
        elif '📤' in msg:
            status_text = "📤 Gửi"
            status_color = "#f39c12"
        elif '✅ Post ID' in msg or '🆔' in msg:
            status_text = "🆔 Post ID"
            status_color = "#2ecc71"
        elif 'Rendering' in msg or ('⏳' in msg and 'render' in msg.lower()):
            time_match = re.search(r'\((\d+)s\)', msg)
            status_text = f"⏳ {time_match.group(1)}s" if time_match else "⏳ Rendering"
            status_color = "#f39c12"
        elif '⏳' in msg and 'video' in msg.lower():
            status_text = "⏳ Chờ render"
            status_color = "#f39c12"
        elif '🔗' in msg:
            status_text = "🔗 Share"
            status_color = "#9b59b6"
        elif '📥' in msg:
            status_text = "📥 Tải xuống"
            status_color = "#3498db"
        elif '✅ Downloaded' in msg:
            status_text = "✅ Xong"
            status_color = "#27ae60"
        elif '✅ Done' in msg:
            status_text = "✅ Xong"
            status_color = "#27ae60"
        elif '🔄 Ready' in msg:
            # Tab finished this prompt, ready for next — don't update queue
            return
        
        if status_text:
            item = QTableWidgetItem(status_text)
            if status_color:
                item.setBackground(QColor(status_color))
                item.setForeground(QColor("white"))
            self.queue_table.setItem(idx, 3, item)
    
    def _on_task_completed(self, email, task):
        """Handle individual task completion.
        
        Tìm queue index bằng prompt text match, skip những item đã xử lý.
        """
        # Initialize processed tracking if not exists
        if not hasattr(self, '_processed_indices'):
            self._processed_indices = set()
        
        # Find the queue index for this prompt by text match
        idx = -1
        if email in self.account_prompt_idx:
            items_list = self.account_prompts.get(email, [])
            indices_list = self.account_prompt_idx.get(email, [])
            for i, (item, qi) in enumerate(zip(items_list, indices_list)):
                # Skip already processed indices
                if qi in self._processed_indices:
                    continue
                # item can be (prompt, image) tuple or str
                p = item[0] if isinstance(item, tuple) else item
                if p == task.prompt:
                    idx = qi
                    self._processed_indices.add(qi)
                    break
        
        # Fallback: search queue table by prompt text (skip processed)
        if idx < 0:
            for qi in range(self.queue_table.rowCount()):
                if qi in self._processed_indices:
                    continue
                queue_item = self.queue_table.item(qi, 1)
                if queue_item and queue_item.text() == task.prompt[:50]:
                    idx = qi
                    self._processed_indices.add(qi)
                    break
        
        # Update queue table (status is column 3 now)
        if idx >= 0 and idx < self.queue_table.rowCount():
            if task.status == "completed":
                item = QTableWidgetItem("✅ Xong")
                item.setBackground(QColor("#27ae60"))
                item.setForeground(QColor("white"))
                self.queue_table.setItem(idx, 3, item)
                self.completed_prompts.append(task)
                
                # Add to done table
                row = self.done_table.rowCount()
                self.done_table.insertRow(row)
                self.done_table.setItem(row, 0, QTableWidgetItem(email))
                self.done_table.setItem(row, 1, QTableWidgetItem(task.prompt[:40]))
                self.done_table.setItem(row, 2, QTableWidgetItem(task.post_id or ""))
                
                self._log(f"✅ [{email[:15]}] #{idx+1} {task.post_id}")
            else:
                item = QTableWidgetItem("❌ Lỗi")
                item.setBackground(QColor("#e74c3c"))
                item.setForeground(QColor("white"))
                self.queue_table.setItem(idx, 3, item)
                self.failed_prompts.append(task)
                self._log(f"❌ [{email[:15]}] #{idx+1} {(task.error_message or '')[:30]}")
        
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
            except:
                pass
        
        # Connect signals to save settings when changed
        self.aspect_combo.currentIndexChanged.connect(self._save_settings)
        self.length_combo.currentIndexChanged.connect(self._save_settings)
        self.resolution_combo.currentIndexChanged.connect(self._save_settings)
    
    def _save_settings(self):
        """Save current settings to file"""
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            settings = {
                "aspect": self.aspect_combo.currentIndex(),
                "length": self.length_combo.currentIndex(),
                "resolution": self.resolution_combo.currentIndex(),
            }
            SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
        except Exception as e:
            print(f"Failed to save settings: {e}")
    
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
