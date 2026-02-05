"""Video Generation Tab - Clean Modern UI with Multi-Tab Support"""
import json
import asyncio
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTextEdit, QComboBox, QPushButton, QMessageBox, QCheckBox, QSpinBox,
    QFileDialog, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QFrame, QTabWidget
)
from PySide6.QtCore import Signal, QThread, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from ..core.account_manager import AccountManager
from ..core.video_generator import VideoGenerator, MultiTabVideoGenerator, ZENDRIVER_AVAILABLE
from ..core.history_manager import HistoryManager
from ..core.models import VideoSettings

SETTINGS_FILE = Path("data/settings.json")


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
        
        self.stat_total = StatBox("Total", "#3498db")
        self.stat_running = StatBox("Running", "#f39c12")
        self.stat_done = StatBox("Done", "#27ae60")
        self.stat_failed = StatBox("Failed", "#e74c3c")
        
        for s in [self.stat_total, self.stat_running, self.stat_done, self.stat_failed]:
            s.setFixedHeight(65)
            stats_row.addWidget(s)
        
        layout.addLayout(stats_row)
        
        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # LEFT panel
        left = GlassFrame()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(12)
        
        # Prompt
        self.prompt_title = QLabel("📝 Prompts")
        self.prompt_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        left_layout.addWidget(self.prompt_title)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Nhập prompt (mỗi dòng 1 prompt)...")
        self.prompt_input.setMaximumHeight(120)
        left_layout.addWidget(self.prompt_input)
        
        btn_row = QHBoxLayout()
        self.import_btn = QPushButton("📂 Import")
        self.clear_btn = QPushButton("🗑️ Clear")
        self.import_btn.clicked.connect(self._import_prompts)
        self.clear_btn.clicked.connect(lambda: self.prompt_input.clear())
        btn_row.addWidget(self.import_btn)
        btn_row.addWidget(self.clear_btn)
        left_layout.addLayout(btn_row)
        
        # Settings
        self.settings_title = QLabel("⚙️ Settings")
        self.settings_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        left_layout.addWidget(self.settings_title)
        
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)
        
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["16:9", "9:16", "1:1"])
        self.aspect_combo.setMinimumWidth(120)
        
        self.length_combo = QComboBox()
        self.length_combo.addItems(["6 giây", "10 giây"])
        self.length_combo.setMinimumWidth(120)
        
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 3)
        self.thread_spin.setValue(3)
        self.thread_spin.setMinimumWidth(120)
        self.thread_spin.setToolTip("Số tab per account (1-3)")
        
        self.headless_check = QCheckBox("Headless mode")
        self.headless_check.setChecked(True)
        
        self.ratio_label = QLabel("Tỷ lệ:")
        self.length_label = QLabel("Thời lượng:")
        self.thread_label = QLabel("Tabs/Account:")
        
        form.addRow(self.ratio_label, self.aspect_combo)
        form.addRow(self.length_label, self.length_combo)
        form.addRow(self.thread_label, self.thread_spin)
        form.addRow("", self.headless_check)
        
        left_layout.addLayout(form)
        
        # Accounts
        self.acc_title = QLabel("👤 Accounts")
        self.acc_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        left_layout.addWidget(self.acc_title)
        
        self.acc_table = QTableWidget()
        self.acc_table.setColumnCount(3)
        self.acc_table.setHorizontalHeaderLabels(["✓", "Email", "Status"])
        self.acc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.acc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.acc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.acc_table.setColumnWidth(0, 35)
        self.acc_table.setColumnWidth(2, 80)
        self.acc_table.setMaximumHeight(120)
        left_layout.addWidget(self.acc_table)
        
        # Control buttons
        ctrl_row = QHBoxLayout()
        self.start_btn = QPushButton("▶️ Start")
        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        ctrl_row.addWidget(self.start_btn)
        ctrl_row.addWidget(self.stop_btn)
        left_layout.addLayout(ctrl_row)
        
        left_layout.addStretch()
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
        self.queue_table.setHorizontalHeaderLabels(["#", "Prompt", "Status"])
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue_table.setColumnWidth(0, 35)
        self.queue_table.setColumnWidth(2, 90)
        queue_l.addWidget(self.queue_table)
        self.tabs.addTab(queue_w, "📋 Queue")
        
        # Running tab
        run_w = QWidget()
        run_l = QVBoxLayout(run_w)
        run_l.setContentsMargins(5, 5, 5, 5)
        self.run_table = QTableWidget()
        self.run_table.setColumnCount(3)
        self.run_table.setHorizontalHeaderLabels(["Account", "Prompt", "Status"])
        self.run_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        run_l.addWidget(self.run_table)
        self.tabs.addTab(run_w, "🔄 Running")
        
        # Done tab
        done_w = QWidget()
        done_l = QVBoxLayout(done_w)
        done_l.setContentsMargins(5, 5, 5, 5)
        self.done_table = QTableWidget()
        self.done_table.setColumnCount(3)
        self.done_table.setHorizontalHeaderLabels(["Account", "Prompt", "File"])
        self.done_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        done_l.addWidget(self.done_table)
        self.tabs.addTab(done_w, "✅ Done")
        
        right_layout.addWidget(self.tabs, stretch=1)
        
        # Log
        self.log_title = QLabel("📜 Log")
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
                    self.ratio_label, self.length_label, self.thread_label]:
            lbl.setStyleSheet(f"color: {text_color}; background: transparent;")
        
        self.prompt_input.setStyleSheet(input_style)
        self.aspect_combo.setStyleSheet(input_style)
        self.length_combo.setStyleSheet(input_style)
        self.thread_spin.setStyleSheet(input_style)
        self.headless_check.setStyleSheet(check_style)
        
        for tbl in [self.acc_table, self.queue_table, self.run_table, self.done_table]:
            tbl.setStyleSheet(table_style)
        
        for btn in [self.import_btn, self.clear_btn]:
            btn.setStyleSheet(btn_style)
        
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
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "Text (*.txt)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    prompts = [l.strip() for l in f if l.strip()]
                self.prompt_input.setPlainText('\n'.join(prompts))
                self._log(f"✅ Imported {len(prompts)} prompts")
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
    
    def _start(self):
        """Start multi-tab video generation"""
        text = self.prompt_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Error", "Enter prompts first")
            return
        
        prompts = [p.strip() for p in text.split('\n') if p.strip()]
        accounts = self._get_selected_accounts()
        
        if not accounts:
            QMessageBox.warning(self, "Error", "Select logged-in accounts")
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
            self.queue_table.setItem(i, 2, QTableWidgetItem("⏳ Wait"))
        
        self.run_table.setRowCount(0)
        self.done_table.setRowCount(0)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
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
        settings = VideoSettings(aspect_ratio=aspect, video_length=length)
        
        # Mark prompts as running
        for idx in self.account_prompt_idx[account.email]:
            if idx < self.queue_table.rowCount():
                self.queue_table.setItem(idx, 2, QTableWidgetItem("🔄 Queue"))
                self.queue_table.item(idx, 2).setBackground(QColor("#f39c12"))
        
        # Add to running table
        row = self.run_table.rowCount()
        self.run_table.insertRow(row)
        self.run_table.setItem(row, 0, QTableWidgetItem(account.email))
        self.run_table.setItem(row, 1, QTableWidgetItem(f"{len(prompts)} prompts"))
        self.run_table.setItem(row, 2, QTableWidgetItem(f"Starting {num_tabs} tabs..."))
        
        # Create and start worker
        worker = AccountWorker(
            account, prompts, settings,
            num_tabs=num_tabs,
            headless=self.headless_check.isChecked()
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
                self.queue_table.setItem(idx, 2, QTableWidgetItem("✅ Done"))
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
                self.queue_table.setItem(idx, 2, QTableWidgetItem("❌ Fail"))
                self.queue_table.item(idx, 2).setBackground(QColor("#e74c3c"))
                self.failed_prompts.append(task)
                self._log(f"❌ [{email}] {task.error_message[:30]}")
        
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
            self._log(f"🎉 All done! {len(self.completed_prompts)} OK, {len(self.failed_prompts)} failed")
    
    def _stop(self):
        """Stop all account workers"""
        for worker in self.account_workers.values():
            worker.stop()
        self.account_workers.clear()
        self.run_table.setRowCount(0)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._log("⏹️ Stopped")
    
    def _update_stats(self):
        self.stat_total.set_value(len(self.prompt_queue))
        self.stat_running.set_value(len(self.account_workers))
        self.stat_done.set_value(len(self.completed_prompts))
        self.stat_failed.set_value(len(self.failed_prompts))
    
    def _load_settings(self):
        if SETTINGS_FILE.exists():
            try:
                s = json.loads(SETTINGS_FILE.read_text())
                self.aspect_combo.setCurrentIndex(s.get("aspect", 0))
                self.length_combo.setCurrentIndex(s.get("length", 0))
                self.headless_check.setChecked(s.get("headless", True))
                self.thread_spin.setValue(min(s.get("concurrent", 2), 3))
            except:
                pass
    
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
