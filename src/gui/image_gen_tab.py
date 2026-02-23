"""Image Generation Tab - Text-to-Image UI with Multi-Tab Support"""
import os
import asyncio
import threading
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTextEdit, QComboBox, QPushButton, QMessageBox, QCheckBox,
    QFileDialog, QLabel, QTableWidget, QTableWidgetItem, QLineEdit,
    QHeaderView, QSplitter, QFrame, QTabWidget, QProgressBar, QScrollArea
)
from PySide6.QtCore import Signal, QThread, Qt, QTimer, QTime
from PySide6.QtGui import QColor, QFont

from ..core.account_manager import AccountManager
from ..core.image_generator import MultiTabImageGenerator, ZENDRIVER_AVAILABLE
from ..core.history_manager import HistoryManager
from ..core.models import ImageSettings, ImageTask


SETTINGS_FILE = Path("data/settings.json")
DEFAULT_OUTPUT_DIR = Path("output/images")


# Shared prompt queue for all workers — ensures natural order
class SharedPromptQueue:
    """Thread-safe queue để các account lấy prompt theo thứ tự."""
    def __init__(self, prompts: list):
        self._prompts = list(enumerate(prompts))  # [(index, prompt), ...]
        self._lock = threading.Lock()
    
    def get_next(self):
        """Lấy prompt tiếp theo. Returns (index, prompt) or None if empty."""
        with self._lock:
            if self._prompts:
                return self._prompts.pop(0)
            return None
    
    def is_empty(self):
        with self._lock:
            return len(self._prompts) == 0


class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class ImageAccountWorker(QThread):
    """Worker cho 1 account — lấy prompt từ shared queue theo thứ tự."""
    status_update = Signal(str, str)  # email, message
    task_completed = Signal(str, int, object)  # email, prompt_index, ImageTask
    all_finished = Signal(str)  # email

    def __init__(self, account, shared_queue, settings, output_dir, headless=True):
        super().__init__()
        self.account = account
        self.shared_queue = shared_queue  # SharedPromptQueue
        self.settings = settings
        self.output_dir = output_dir
        self.headless = headless
        self._stopped = False
        self._generator = None

    def run(self):
        if self._stopped:
            return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_async())
        except Exception as e:
            self.status_update.emit(self.account.email, f"❌ Lỗi: {e}")
        finally:
            loop.close()
        self.all_finished.emit(self.account.email)

    async def _run_async(self):
        self._generator = MultiTabImageGenerator(
            account=self.account,
            num_tabs=1,  # 1 tab per account for simplicity
            headless=self.headless,
            on_status=lambda email, msg: self.status_update.emit(email, msg)
        )
        try:
            if not await self._generator.start():
                self.status_update.emit(self.account.email, "❌ Không khởi động được trình duyệt")
                return

            # Lấy prompt từ shared queue theo thứ tự
            while not self._stopped and not self.shared_queue.is_empty():
                item = self.shared_queue.get_next()
                if item is None:
                    break
                
                prompt_idx, prompt_data = item
                
                # prompt_data can be (prompt, subfolder, stt) or just prompt string
                if isinstance(prompt_data, tuple):
                    prompt, subfolder, stt = prompt_data
                else:
                    prompt = prompt_data
                    subfolder = None
                    stt = prompt_idx + 1
                
                self.status_update.emit(self.account.email, f"▶️ Prompt {prompt_idx+1}: {prompt[:30]}...")
                
                # Build output path with subfolder
                if subfolder:
                    actual_output_dir = str(Path(self.output_dir) / subfolder)
                else:
                    actual_output_dir = self.output_dir
                
                # Build custom filename: {stt}_{prompt_short}.jpg
                import re
                prompt_short = re.sub(r'[^\w\s]', '', prompt)[:30].replace(' ', '_')
                custom_filename = f"{stt}_{prompt_short}"
                
                task = await self._generator.generate_images_on_tab(
                    tab_id=0,
                    prompt=prompt,
                    settings=self.settings,
                    output_dir=actual_output_dir,
                    custom_filename=custom_filename
                )
                self.task_completed.emit(self.account.email, prompt_idx, task)
                
        finally:
            await self._generator.stop()

    def stop(self):
        self._stopped = True
        if self._generator:
            self._generator._running = False


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


class ImageGenTab(QWidget):
    """Tab tạo ảnh — Text-to-Image generation."""
    image_completed = Signal()

    def __init__(self, account_manager: AccountManager, history_manager: HistoryManager):
        super().__init__()
        self.account_manager = account_manager
        self.history_manager = history_manager
        self.account_workers: dict = {}  # email -> ImageAccountWorker
        self.prompt_queue = []
        self.completed_tasks = []
        self.failed_tasks = []
        self.is_dark = True

        self._output_dir = str(DEFAULT_OUTPUT_DIR)
        self._start_time = None

        self._setup_ui()
        self.refresh_accounts()

        self.timer = QTimer()
        self.timer.timeout.connect(self._update_stats)
        self.timer.start(500)

        self._elapsed_timer = QTimer()
        self._elapsed_timer.timeout.connect(self._update_elapsed)

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

        # Progress bar
        progress_frame = GlassFrame()
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(15, 10, 15, 10)
        progress_layout.setSpacing(6)

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

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.progress_bar)

        self.progress_frame = progress_frame
        layout.addWidget(progress_frame)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # LEFT panel
        left = GlassFrame()
        left_main_layout = QVBoxLayout(left)
        left_main_layout.setContentsMargins(0, 0, 0, 0)
        left_main_layout.setSpacing(0)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(40, 50, 70, 100); width: 8px; border-radius: 4px; margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(80, 120, 200, 150); border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        left_inner = QWidget()
        left_inner.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_inner)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(10)

        # Prompt input
        self.prompt_title = QLabel("📝 Prompts")
        self.prompt_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        left_layout.addWidget(self.prompt_title)

        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Nhập prompt (mỗi dòng 1 prompt)...")
        self.prompt_input.setMaximumHeight(120)
        left_layout.addWidget(self.prompt_input)

        btn_row = QHBoxLayout()
        self.import_btn = QPushButton("📄 Nhập TXT")
        self.import_folder_btn = QPushButton("📁 Nhập Folder")
        self.clear_btn = QPushButton("🗑️ Xóa")
        self.import_btn.clicked.connect(self._import_prompts)
        self.import_folder_btn.clicked.connect(self._import_folder)
        self.clear_btn.clicked.connect(lambda: self.prompt_input.clear())
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

        # Settings
        self.settings_title = QLabel("⚙️ Cài đặt")
        self.settings_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        left_layout.addWidget(self.settings_title)

        # Aspect ratio selector
        aspect_row = QHBoxLayout()
        self.aspect_label = QLabel("Tỷ lệ khung hình:")
        self.aspect_label.setFont(QFont("Segoe UI", 10))
        self.aspect_combo = NoScrollComboBox()
        self.aspect_combo.addItems(["2:3 (Dọc)", "3:2 (Ngang)", "1:1 (Vuông)", "9:16 (Story)", "16:9 (Wide)"])
        self.aspect_combo.setCurrentIndex(1)  # Default 3:2
        self.aspect_combo.setFixedWidth(130)
        aspect_row.addWidget(self.aspect_label)
        aspect_row.addWidget(self.aspect_combo)
        aspect_row.addStretch()
        left_layout.addLayout(aspect_row)

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
        left_scroll.setWidget(left_inner)
        left_main_layout.addWidget(left_scroll)
        self.left_scroll = left_scroll

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
        self.done_table.setColumnCount(4)
        self.done_table.setHorizontalHeaderLabels(["#", "Prompt", "Tài khoản", "Thư mục"])
        self.done_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.done_table.setColumnWidth(0, 45)
        self.done_table.setColumnWidth(2, 120)
        self.done_table.setColumnWidth(3, 120)
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

        # === Overlay "đang phát triển" ===
        self._overlay = QWidget(self)
        self._overlay.setStyleSheet("""
            background: rgba(0, 0, 0, 160);
            border-radius: 10px;
        """)
        overlay_layout = QVBoxLayout(self._overlay)
        overlay_layout.setAlignment(Qt.AlignCenter)
        overlay_label = QLabel("🚧 Chức năng đang tiếp tục phát triển\nVui lòng đợi bạn nhé! 🙏")
        overlay_label.setAlignment(Qt.AlignCenter)
        overlay_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        overlay_label.setStyleSheet("color: white; background: transparent;")
        overlay_label.setWordWrap(True)
        overlay_layout.addWidget(overlay_label)
        self._overlay.raise_()

    # ==================== Theme ====================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_overlay'):
            self._overlay.setGeometry(self.rect())

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
                QTextEdit, QSpinBox {
                    background: rgba(35, 45, 65, 220); color: white;
                    border: 1px solid rgba(80, 120, 200, 80); border-radius: 6px; padding: 8px;
                }
            """
            table_style = """
                QTableWidget {
                    background: rgba(20, 30, 50, 180); color: white;
                    border: 1px solid rgba(80, 120, 200, 50); border-radius: 6px;
                    gridline-color: rgba(80, 120, 200, 30);
                }
                QTableWidget::item { padding: 5px; }
                QTableWidget::item:selected { background: rgba(80, 120, 200, 100); }
                QHeaderView::section {
                    background: rgba(40, 50, 70, 220); color: white;
                    border: none; padding: 6px; font-weight: bold;
                }
            """
            btn_style = """
                QPushButton {
                    background: rgba(45, 55, 75, 220); color: white;
                    border: 1px solid rgba(80, 120, 200, 80); border-radius: 6px;
                    padding: 8px 16px; font-size: 12px;
                }
                QPushButton:hover { background: rgba(55, 65, 85, 240); }
            """
            log_style = """
                QTextEdit {
                    background: rgba(10, 15, 25, 220); color: #0f0;
                    border: 1px solid rgba(0, 200, 0, 40); border-radius: 6px;
                    font-family: Consolas, monospace; font-size: 11px; padding: 6px;
                }
            """
            tab_style = """
                QTabWidget::pane { background: transparent; border: none; }
                QTabBar::tab {
                    background: rgba(40, 50, 70, 180); color: rgba(255,255,255,0.7);
                    border: none; padding: 8px 14px; margin-right: 3px; border-radius: 6px 6px 0 0;
                }
                QTabBar::tab:selected { background: rgba(60, 80, 120, 220); color: white; }
            """
            line_edit_style = """
                QLineEdit {
                    background: rgba(35, 45, 65, 220); color: white;
                    border: 1px solid rgba(80, 120, 200, 80); border-radius: 6px; padding: 4px 8px;
                }
            """
            progress_style = """
                QProgressBar {
                    background: rgba(30, 40, 60, 200); border: 1px solid rgba(80, 120, 200, 60);
                    border-radius: 9px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #3498db, stop:1 #2ecc71);
                    border-radius: 8px;
                }
            """
        else:
            text_color = "#333"
            input_style = """
                QTextEdit, QSpinBox {
                    background: white; color: #333;
                    border: 1px solid rgba(100, 150, 200, 100); border-radius: 6px; padding: 8px;
                }
            """
            table_style = """
                QTableWidget {
                    background: white; color: #333;
                    border: 1px solid rgba(100, 150, 200, 80); border-radius: 6px;
                    gridline-color: rgba(100, 150, 200, 50);
                }
                QTableWidget::item { padding: 5px; }
                QTableWidget::item:selected { background: rgba(80, 120, 200, 100); }
                QHeaderView::section {
                    background: rgba(240, 245, 255, 250); color: #333;
                    border: none; padding: 6px; font-weight: bold;
                }
            """
            btn_style = """
                QPushButton {
                    background: white; color: #333;
                    border: 1px solid rgba(100, 150, 200, 100); border-radius: 6px;
                    padding: 8px 16px; font-size: 12px;
                }
                QPushButton:hover { background: #f5f5f5; }
            """
            log_style = """
                QTextEdit {
                    background: rgba(20, 30, 50, 240); color: #0f0;
                    border: 1px solid rgba(0, 150, 0, 50); border-radius: 6px;
                    font-family: Consolas, monospace; font-size: 11px; padding: 6px;
                }
            """
            tab_style = """
                QTabWidget::pane { background: transparent; border: none; }
                QTabBar::tab {
                    background: rgba(240, 245, 255, 200); color: rgba(0,0,0,0.7);
                    border: none; padding: 8px 14px; margin-right: 3px; border-radius: 6px 6px 0 0;
                }
                QTabBar::tab:selected { background: white; color: #333; }
            """
            line_edit_style = """
                QLineEdit {
                    background: white; color: #333;
                    border: 1px solid rgba(100, 150, 200, 100); border-radius: 6px; padding: 4px 8px;
                }
            """
            progress_style = """
                QProgressBar {
                    background: rgba(230, 235, 245, 200); border: 1px solid rgba(100, 150, 200, 80);
                    border-radius: 9px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #3498db, stop:1 #2ecc71);
                    border-radius: 8px;
                }
            """

        # Apply styles
        for label in [self.prompt_title, self.output_title, self.settings_title,
                      self.acc_title, self.log_title, self.aspect_label]:
            label.setStyleSheet(f"color: {text_color}; background: transparent;")

        self.progress_status.setStyleSheet(f"color: {text_color}; background: transparent;")
        self.progress_percent.setStyleSheet(f"color: {text_color}; background: transparent;")
        self.elapsed_label.setStyleSheet(f"color: {text_color}; background: transparent;")

        self.prompt_input.setStyleSheet(input_style)
        self.output_input.setStyleSheet(line_edit_style)

        # Combo box style
        if self.is_dark:
            combo_style = """
                QComboBox {
                    background: rgba(35, 45, 65, 220); color: white;
                    border: 1px solid rgba(80, 120, 200, 80); border-radius: 6px;
                    padding: 4px 8px;
                }
                QComboBox::drop-down { border: none; width: 20px; }
                QComboBox::down-arrow { image: none; border-left: 5px solid transparent;
                    border-right: 5px solid transparent; border-top: 6px solid white; }
                QComboBox QAbstractItemView {
                    background: rgba(35, 45, 65, 240); color: white;
                    selection-background-color: rgba(80, 120, 200, 150);
                }
            """
        else:
            combo_style = """
                QComboBox {
                    background: white; color: #333;
                    border: 1px solid rgba(100, 150, 200, 100); border-radius: 6px;
                    padding: 4px 8px;
                }
                QComboBox::drop-down { border: none; width: 20px; }
                QComboBox::down-arrow { image: none; border-left: 5px solid transparent;
                    border-right: 5px solid transparent; border-top: 6px solid #333; }
                QComboBox QAbstractItemView {
                    background: white; color: #333;
                    selection-background-color: rgba(80, 120, 200, 100);
                }
            """
        self.aspect_combo.setStyleSheet(combo_style)

        for table in [self.queue_table, self.run_table, self.done_table, self.acc_table]:
            table.setStyleSheet(table_style)

        for btn in [self.import_btn, self.import_folder_btn, self.clear_btn, self.start_btn, self.stop_btn,
                    self.output_browse_btn]:
            btn.setStyleSheet(btn_style)

        self.log.setStyleSheet(log_style)
        self.tabs.setStyleSheet(tab_style)
        self.progress_bar.setStyleSheet(progress_style)
        self.progress_frame.set_dark(self.is_dark)

    # ==================== Account Management ====================

    def refresh_accounts(self):
        accounts = self.account_manager.get_all_accounts()
        self.acc_table.setRowCount(len(accounts))
        for i, acc in enumerate(accounts):
            cb = QCheckBox()
            if acc.status == "logged_in":
                cb.setChecked(True)
            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.acc_table.setCellWidget(i, 0, cb_widget)
            self.acc_table.setItem(i, 1, QTableWidgetItem(acc.email))
            status_text = "✅" if acc.status == "logged_in" else "❌"
            self.acc_table.setItem(i, 2, QTableWidgetItem(status_text))

    def _get_selected_accounts(self):
        accounts = self.account_manager.get_all_accounts()
        selected = []
        for i in range(self.acc_table.rowCount()):
            cb_widget = self.acc_table.cellWidget(i, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                if cb and cb.isChecked() and i < len(accounts):
                    selected.append(accounts[i])
        return selected

    # ==================== Import / Output ====================

    def _import_prompts(self):
        """Import single TXT file - creates subfolder with same name"""
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file TXT", "", "Text Files (*.txt)")
        if path:
            try:
                from pathlib import Path as P
                txt_path = P(path)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.prompt_input.setPlainText(content)
                lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
                
                # Store batch info: single file = single batch
                subfolder_name = txt_path.stem  # filename without .txt
                self._batch_queue = [(subfolder_name, lines)]
                
                self._log(f"📄 Đã nhập {len(lines)} prompt từ {subfolder_name}.txt")
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không thể đọc file: {e}")

    def _import_folder(self):
        """Import folder chứa nhiều file TXT - mỗi file = 1 batch với subfolder riêng"""
        folder = QFileDialog.getExistingDirectory(self, "Chọn folder chứa file TXT")
        if not folder:
            return
        
        try:
            from pathlib import Path as P
            folder_path = P(folder)
            txt_files = sorted(folder_path.glob("*.txt"))
            
            if not txt_files:
                QMessageBox.warning(self, "Lỗi", "Không tìm thấy file TXT trong folder!")
                return
            
            # Build batch queue: [(subfolder_name, [prompts]), ...]
            self._batch_queue = []
            all_prompts = []
            total_count = 0
            
            for txt_file in txt_files:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
                if lines:
                    subfolder_name = txt_file.stem  # filename without .txt
                    self._batch_queue.append((subfolder_name, lines))
                    all_prompts.extend(lines)
                    total_count += len(lines)
            
            # Show in prompt input
            self.prompt_input.setPlainText('\n'.join(all_prompts))
            
            self._log(f"📁 Đã nhập {total_count} prompt từ {len(self._batch_queue)} file TXT")
            
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể đọc folder: {e}")

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất")
        if folder:
            self._output_dir = folder
            self.output_input.setText(folder)

    # ==================== Start / Stop ====================

    def _start(self):
        """Start image generation."""
        # Get prompts
        text = self.prompt_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập prompt!")
            return

        # Build prompt list with subfolder info
        # Check if we have batch info from file import
        if hasattr(self, '_batch_queue') and self._batch_queue:
            # Build items with subfolder info from batch queue
            all_items = []
            for subfolder_name, prompts in self._batch_queue:
                for idx, prompt in enumerate(prompts, start=1):
                    all_items.append((prompt, subfolder_name, idx))
        else:
            # Simple text input - no subfolder
            prompts = [l.strip() for l in text.split('\n') if l.strip()]
            all_items = [(p, None, i+1) for i, p in enumerate(prompts)]
        
        if not all_items:
            QMessageBox.warning(self, "Lỗi", "Không có prompt hợp lệ!")
            return

        # Get selected accounts
        selected = self._get_selected_accounts()
        if not selected:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn ít nhất 1 tài khoản đã đăng nhập!")
            return

        logged_in = [a for a in selected if a.status == "logged_in" and a.cookies]
        if not logged_in:
            QMessageBox.warning(self, "Lỗi", "Không có tài khoản nào đã đăng nhập!")
            return

        # Settings
        aspect_text = self.aspect_combo.currentText().split()[0]  # "3:2 (Ngang)" -> "3:2"
        self._current_settings = ImageSettings(aspect_ratio=aspect_text)
        self._current_output_dir = self._output_dir

        # Create subfolders (quick operation)
        base_output = Path(self._current_output_dir)
        base_output.mkdir(parents=True, exist_ok=True)
        subfolders_created = set()
        for item in all_items:
            subfolder = item[1]  # subfolder name
            if subfolder and subfolder not in subfolders_created:
                subfolder_path = base_output / subfolder
                subfolder_path.mkdir(parents=True, exist_ok=True)
                subfolders_created.add(subfolder)
        if subfolders_created:
            self._log(f"📁 Tạo {len(subfolders_created)} subfolder: {', '.join(sorted(subfolders_created)[:5])}...")

        # Reset state
        self.completed_tasks = []
        self.failed_tasks = []
        self.prompt_queue = all_items  # list of (prompt, subfolder, stt)
        self.account_workers = {}

        # Populate queue table
        total = len(all_items)
        self.queue_table.setRowCount(total)
        for i, item in enumerate(all_items):
            prompt = item[0]
            self.queue_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.queue_table.setItem(i, 1, QTableWidgetItem(prompt[:80]))
            self.queue_table.setItem(i, 2, QTableWidgetItem("⏳ Chờ"))

        self.run_table.setRowCount(0)
        self.done_table.setRowCount(0)

        # Shared queue — tất cả accounts lấy prompt theo thứ tự từ đây
        self.shared_queue = SharedPromptQueue(all_items)

        # UI state - update immediately
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_status.setText(f"🚀 Đang khởi tạo {len(logged_in)} tài khoản...")
        self._start_time = datetime.now()
        self._elapsed_timer.start(1000)

        # Store pending accounts for staggered start
        self._pending_accounts = list(logged_in)
        self._log(f"🚀 Bắt đầu {total} ảnh với {len(logged_in)} tài khoản")
        
        # Start first worker immediately, others with delay
        if self._pending_accounts:
            acc = self._pending_accounts.pop(0)
            self._start_single_worker(acc)
            
            # Schedule remaining workers with 3s delay each
            for i, acc in enumerate(self._pending_accounts):
                QTimer.singleShot((i + 1) * 3000, lambda a=acc: self._start_single_worker(a))
            self._pending_accounts = []

    def _start_single_worker(self, account):
        """Start a single worker for an account - called from QTimer"""
        if account.email in self.account_workers:
            return  # Already started
            
        worker = ImageAccountWorker(
            account=account,
            shared_queue=self.shared_queue,
            settings=self._current_settings,
            output_dir=self._current_output_dir,
            headless=True
        )
        worker.status_update.connect(self._on_status_update)
        worker.task_completed.connect(self._on_task_completed)
        worker.all_finished.connect(self._on_worker_finished)
        self.account_workers[account.email] = worker
        worker.start()
        self._log(f"🚀 Đã khởi chạy {account.email}")
        self.progress_status.setText(f"🔄 Đang chạy {len(self.account_workers)} tài khoản...")

    def _stop(self):
        """Stop all workers."""
        for worker in self.account_workers.values():
            worker.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_status.setText("⏹️ Đã dừng")
        self._elapsed_timer.stop()
        self._log("⏹️ Đã dừng tất cả")

    # ==================== Signal Handlers ====================

    def _on_status_update(self, email: str, message: str):
        """Handle status update from worker."""
        self._log(message)

        # Update running table
        found = False
        for row in range(self.run_table.rowCount()):
            item = self.run_table.item(row, 0)
            if item and item.text() == email:
                self.run_table.setItem(row, 2, QTableWidgetItem(message[-60:]))
                found = True
                break
        if not found:
            row = self.run_table.rowCount()
            self.run_table.insertRow(row)
            self.run_table.setItem(row, 0, QTableWidgetItem(email))
            self.run_table.setItem(row, 1, QTableWidgetItem("..."))
            self.run_table.setItem(row, 2, QTableWidgetItem(message[-60:]))

    def _on_task_completed(self, email: str, prompt_idx: int, task):
        """Handle completed image task."""
        if not isinstance(task, ImageTask):
            return

        if task.status == "completed" and task.output_paths:
            self.completed_tasks.append(task)

            # Add to done table
            row = self.done_table.rowCount()
            self.done_table.insertRow(row)
            self.done_table.setItem(row, 0, QTableWidgetItem(f"#{prompt_idx+1}"))
            self.done_table.setItem(row, 1, QTableWidgetItem(task.prompt[:60]))
            self.done_table.setItem(row, 2, QTableWidgetItem(email))
            self.done_table.setItem(row, 3, QTableWidgetItem(task.output_dir or ""))

            # Save to history
            try:
                self.history_manager.add_image_history(task)
            except Exception as e:
                print(f"History save error: {e}")

            self.image_completed.emit()
        else:
            self.failed_tasks.append(task)

        # Update queue table status by prompt_idx
        if 0 <= prompt_idx < self.queue_table.rowCount():
            status_item = self.queue_table.item(prompt_idx, 2)
            if status_item:
                if task.status == "completed":
                    status_item.setText("✅ Xong")
                else:
                    status_item.setText("❌ Lỗi")

    def _on_worker_finished(self, email: str):
        """Handle worker finished."""
        if email in self.account_workers:
            del self.account_workers[email]

        # Remove from running table
        for row in range(self.run_table.rowCount() - 1, -1, -1):
            item = self.run_table.item(row, 0)
            if item and item.text() == email:
                self.run_table.removeRow(row)

        self._log(f"✅ Hoàn thành: {email}")

        if not self.account_workers:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._elapsed_timer.stop()
            total = len(self.completed_tasks) + len(self.failed_tasks)
            self.progress_status.setText(
                f"✅ Hoàn thành: {len(self.completed_tasks)}/{total} prompts"
            )
            self.progress_bar.setValue(100)

    # ==================== Stats & Elapsed ====================

    def _update_stats(self):
        total = len(self.prompt_queue)
        done = len(self.completed_tasks)
        failed = len(self.failed_tasks)
        running = total - done - failed if total > 0 else 0

        self.stat_total.set_value(total)
        self.stat_running.set_value(max(0, running))
        self.stat_done.set_value(done)
        self.stat_failed.set_value(failed)

        if total > 0:
            pct = int((done + failed) * 100 / total)
            self.progress_bar.setValue(pct)
            self.progress_percent.setText(f"{pct}%")

    def _update_elapsed(self):
        if self._start_time:
            elapsed = datetime.now() - self._start_time
            mins = int(elapsed.total_seconds()) // 60
            secs = int(elapsed.total_seconds()) % 60
            self.elapsed_label.setText(f"⏱️ {mins:02d}:{secs:02d}")

    # ==================== Logging ====================

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        # Auto-scroll
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())
