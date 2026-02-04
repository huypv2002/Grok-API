"""Video Generation Tab - Beautiful UI for Grok Video Generator"""
import json
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTextEdit, QComboBox, QPushButton, QProgressBar,
    QGroupBox, QMessageBox, QCheckBox, QSpinBox,
    QFileDialog, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QFrame, QScrollArea,
    QSizePolicy, QTabWidget
)
from PySide6.QtCore import Signal, QThread, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from ..core.account_manager import AccountManager
from ..core.video_generator import VideoGenerator
from ..core.history_manager import HistoryManager
from ..core.models import VideoSettings

SETTINGS_FILE = Path("data/settings.json")


class VideoWorker(QThread):
    status_update = Signal(str, str)
    progress_update = Signal(str, int)
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
            self.account,
            self.prompt,
            self.settings,
            lambda msg: self.status_update.emit(self.account.email, msg),
            headless=self.headless
        )
        self.finished.emit(self.account.email, task)
    
    def stop(self):
        self.stopped = True


class StatsWidget(QFrame):
    """Widget hiển thị thống kê"""
    def __init__(self, title, value="0", color="#3498db"):
        super().__init__()
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: 6px;
            }}
            QLabel {{
                color: white;
            }}
        """)
        self.setFixedHeight(60)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        
        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.value_label.setAlignment(Qt.AlignCenter)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 9))
        title_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.value_label)
        layout.addWidget(title_label)
    
    def set_value(self, value):
        self.value_label.setText(str(value))


class VideoGenTab(QWidget):
    video_completed = Signal()
    
    def __init__(self, account_manager: AccountManager, video_generator, history_manager: HistoryManager):
        super().__init__()
        self.account_manager = account_manager
        self.history_manager = history_manager
        self.workers = {}
        self.prompt_queue = []
        self.completed_prompts = []
        self.failed_prompts = []
        self.current_prompt_index = 0
        
        self._setup_ui()
        self.refresh_accounts()
        self._load_settings()
        
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_stats)
        self.stats_timer.start(1000)
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        # === Stats Bar ===
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(8)
        
        self.stat_total = StatsWidget("Tổng", "0", "#3498db")
        self.stat_running = StatsWidget("Đang chạy", "0", "#f39c12")
        self.stat_completed = StatsWidget("Xong", "0", "#27ae60")
        self.stat_failed = StatsWidget("Lỗi", "0", "#e74c3c")
        
        stats_layout.addWidget(self.stat_total)
        stats_layout.addWidget(self.stat_running)
        stats_layout.addWidget(self.stat_completed)
        stats_layout.addWidget(self.stat_failed)
        
        main_layout.addLayout(stats_layout)
        
        # === Main Splitter ===
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        
        # --- LEFT: Settings Panel (scrollable) ---
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(280)
        left_scroll.setMaximumWidth(400)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(4, 4, 4, 4)
        
        # Prompt Input
        prompt_group = QGroupBox("📝 Prompts")
        prompt_layout = QVBoxLayout(prompt_group)
        prompt_layout.setSpacing(4)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Nhập prompt (mỗi dòng 1 prompt)...")
        self.prompt_input.setMinimumHeight(80)
        self.prompt_input.setMaximumHeight(120)
        prompt_layout.addWidget(self.prompt_input)
        
        btn_row = QHBoxLayout()
        import_btn = QPushButton("📂 Import TXT")
        import_btn.clicked.connect(self._import_prompts)
        clear_btn = QPushButton("🗑️ Xóa")
        clear_btn.clicked.connect(lambda: self.prompt_input.clear())
        btn_row.addWidget(import_btn)
        btn_row.addWidget(clear_btn)
        prompt_layout.addLayout(btn_row)
        
        left_layout.addWidget(prompt_group)
        
        # Video Settings
        settings_group = QGroupBox("⚙️ Cài đặt")
        settings_form = QFormLayout(settings_group)
        settings_form.setSpacing(6)
        
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["16:9", "9:16", "1:1"])
        
        self.length_combo = QComboBox()
        self.length_combo.addItems(["6 giây", "10 giây"])
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["720p", "1080p"])
        
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(2)
        
        self.headless_check = QCheckBox("Minimize browser")
        self.headless_check.setChecked(True)
        
        settings_form.addRow("Tỷ lệ:", self.aspect_combo)
        settings_form.addRow("Thời lượng:", self.length_combo)
        settings_form.addRow("Chất lượng:", self.resolution_combo)
        settings_form.addRow("Đa luồng:", self.concurrent_spin)
        settings_form.addRow("", self.headless_check)
        
        left_layout.addWidget(settings_group)
        
        # Account Selection
        account_group = QGroupBox("👤 Accounts")
        account_layout = QVBoxLayout(account_group)
        account_layout.setSpacing(4)
        
        self.account_table = QTableWidget()
        self.account_table.setColumnCount(3)
        self.account_table.setHorizontalHeaderLabels(["✓", "Email", "Status"])
        self.account_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.account_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.account_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.account_table.setColumnWidth(0, 30)
        self.account_table.setColumnWidth(2, 70)
        self.account_table.setMinimumHeight(100)
        self.account_table.setMaximumHeight(150)
        account_layout.addWidget(self.account_table)
        
        acc_btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Chọn tất cả")
        select_all_btn.clicked.connect(self._select_all_accounts)
        select_none_btn = QPushButton("Bỏ chọn")
        select_none_btn.clicked.connect(self._select_none_accounts)
        acc_btn_row.addWidget(select_all_btn)
        acc_btn_row.addWidget(select_none_btn)
        account_layout.addLayout(acc_btn_row)
        
        left_layout.addWidget(account_group)
        
        # Control Buttons
        ctrl_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶️ Bắt đầu")
        self.start_btn.setStyleSheet("QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 8px; border-radius: 4px; } QPushButton:hover { background-color: #2ecc71; } QPushButton:disabled { background-color: #95a5a6; }")
        self.start_btn.clicked.connect(self._start_generation)
        
        self.stop_btn = QPushButton("⏹️ Dừng")
        self.stop_btn.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; font-weight: bold; padding: 8px; border-radius: 4px; } QPushButton:hover { background-color: #c0392b; } QPushButton:disabled { background-color: #95a5a6; }")
        self.stop_btn.clicked.connect(self._stop_generation)
        self.stop_btn.setEnabled(False)
        
        ctrl_layout.addWidget(self.start_btn)
        ctrl_layout.addWidget(self.stop_btn)
        
        left_layout.addLayout(ctrl_layout)
        
        save_btn = QPushButton("💾 Lưu Settings")
        save_btn.clicked.connect(self._save_settings)
        left_layout.addWidget(save_btn)
        
        left_layout.addStretch()
        
        left_scroll.setWidget(left_widget)
        splitter.addWidget(left_scroll)
        
        # --- RIGHT: Progress Panel ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(6)
        right_layout.setContentsMargins(4, 4, 4, 4)
        
        # Tabs
        tabs = QTabWidget()
        
        # Tab: Queue
        queue_tab = QWidget()
        queue_layout = QVBoxLayout(queue_tab)
        queue_layout.setContentsMargins(4, 4, 4, 4)
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(3)
        self.queue_table.setHorizontalHeaderLabels(["#", "Prompt", "Status"])
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue_table.setColumnWidth(0, 30)
        self.queue_table.setColumnWidth(2, 100)
        queue_layout.addWidget(self.queue_table)
        tabs.addTab(queue_tab, "📋 Hàng đợi")
        
        # Tab: Running
        running_tab = QWidget()
        running_layout = QVBoxLayout(running_tab)
        running_layout.setContentsMargins(4, 4, 4, 4)
        self.running_table = QTableWidget()
        self.running_table.setColumnCount(3)
        self.running_table.setHorizontalHeaderLabels(["Account", "Prompt", "Status"])
        self.running_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        running_layout.addWidget(self.running_table)
        tabs.addTab(running_tab, "🔄 Đang chạy")
        
        # Tab: Completed
        completed_tab = QWidget()
        completed_layout = QVBoxLayout(completed_tab)
        completed_layout.setContentsMargins(4, 4, 4, 4)
        self.completed_table = QTableWidget()
        self.completed_table.setColumnCount(3)
        self.completed_table.setHorizontalHeaderLabels(["Account", "Prompt", "File"])
        self.completed_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        completed_layout.addWidget(self.completed_table)
        tabs.addTab(completed_tab, "✅ Hoàn thành")
        
        right_layout.addWidget(tabs, stretch=1)
        
        # Log
        log_group = QGroupBox("📜 Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.setStyleSheet("QTextEdit { background-color: #2c3e50; color: #ecf0f1; font-family: monospace; font-size: 10px; }")
        log_layout.addWidget(self.log)
        right_layout.addWidget(log_group)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 500])
        
        main_layout.addWidget(splitter, stretch=1)
    
    def refresh_accounts(self):
        accounts = self.account_manager.get_all_accounts()
        self.account_table.setRowCount(len(accounts))
        
        for i, acc in enumerate(accounts):
            cb = QCheckBox()
            cb.setChecked(acc.status == "logged_in")
            self.account_table.setCellWidget(i, 0, cb)
            self.account_table.setItem(i, 1, QTableWidgetItem(acc.email))
            
            status_item = QTableWidgetItem(acc.status)
            if acc.status == "logged_in":
                status_item.setBackground(QColor("#27ae60"))
                status_item.setForeground(QColor("white"))
            elif acc.status == "error":
                status_item.setBackground(QColor("#e74c3c"))
                status_item.setForeground(QColor("white"))
            self.account_table.setItem(i, 2, status_item)
    
    def _select_all_accounts(self):
        for i in range(self.account_table.rowCount()):
            cb = self.account_table.cellWidget(i, 0)
            if cb: cb.setChecked(True)
    
    def _select_none_accounts(self):
        for i in range(self.account_table.rowCount()):
            cb = self.account_table.cellWidget(i, 0)
            if cb: cb.setChecked(False)
    
    def _import_prompts(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file", "", "Text (*.txt)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    prompts = [l.strip() for l in f if l.strip()]
                self.prompt_input.setPlainText('\n'.join(prompts))
                self._log(f"✅ Imported {len(prompts)} prompts")
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không đọc được: {e}")
    
    def _get_selected_accounts(self):
        selected = []
        for i in range(self.account_table.rowCount()):
            cb = self.account_table.cellWidget(i, 0)
            if cb and cb.isChecked():
                email = self.account_table.item(i, 1).text()
                acc = self.account_manager.get_account(email)
                if acc and acc.status == "logged_in":
                    selected.append(acc)
        return selected
    
    def _start_generation(self):
        text = self.prompt_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Lỗi", "Nhập prompt trước")
            return
        
        prompts = [p.strip() for p in text.split('\n') if p.strip()]
        accounts = self._get_selected_accounts()
        
        if not accounts:
            QMessageBox.warning(self, "Lỗi", "Chọn account đã login")
            return
        
        self.prompt_queue = prompts
        self.completed_prompts = []
        self.failed_prompts = []
        self.current_prompt_index = 0
        
        self.queue_table.setRowCount(len(prompts))
        for i, p in enumerate(prompts):
            self.queue_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            self.queue_table.setItem(i, 1, QTableWidgetItem(p[:60]))
            self.queue_table.setItem(i, 2, QTableWidgetItem("⏳ Chờ"))
        
        self.running_table.setRowCount(0)
        self.completed_table.setRowCount(0)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        max_concurrent = min(self.concurrent_spin.value(), len(accounts))
        self._log(f"🚀 Bắt đầu {len(prompts)} prompts, {max_concurrent} luồng")
        
        for i in range(max_concurrent):
            if i < len(accounts) and self.current_prompt_index < len(prompts):
                self._start_worker(accounts[i], prompts[self.current_prompt_index], self.current_prompt_index)
                self.current_prompt_index += 1
    
    def _start_worker(self, account, prompt, idx):
        aspect = self.aspect_combo.currentText()
        length = int(self.length_combo.currentText().split()[0])
        resolution = self.resolution_combo.currentText()
        
        settings = VideoSettings(aspect_ratio=aspect, video_length=length, resolution=resolution)
        
        if idx < self.queue_table.rowCount():
            self.queue_table.setItem(idx, 2, QTableWidgetItem("🔄 Chạy"))
            self.queue_table.item(idx, 2).setBackground(QColor("#f39c12"))
        
        row = self.running_table.rowCount()
        self.running_table.insertRow(row)
        self.running_table.setItem(row, 0, QTableWidgetItem(account.email))
        self.running_table.setItem(row, 1, QTableWidgetItem(prompt[:40]))
        self.running_table.setItem(row, 2, QTableWidgetItem("Starting..."))
        self.running_table.item(row, 0).setData(Qt.UserRole, idx)
        
        worker = VideoWorker(account, prompt, settings, self.headless_check.isChecked())
        worker.status_update.connect(self._on_status)
        worker.finished.connect(self._on_finished)
        self.workers[account.email] = worker
        worker.start()
        
        self._log(f"▶️ [{account.email}] {prompt[:30]}...")
    
    def _on_status(self, email, msg):
        for i in range(self.running_table.rowCount()):
            if self.running_table.item(i, 0).text() == email:
                self.running_table.setItem(i, 2, QTableWidgetItem(msg[:30]))
                break
    
    def _on_finished(self, email, task):
        idx = -1
        for i in range(self.running_table.rowCount()):
            if self.running_table.item(i, 0).text() == email:
                idx = self.running_table.item(i, 0).data(Qt.UserRole)
                self.running_table.removeRow(i)
                break
        
        if idx >= 0 and idx < self.queue_table.rowCount():
            if task.status == "completed":
                self.queue_table.setItem(idx, 2, QTableWidgetItem("✅ Xong"))
                self.queue_table.item(idx, 2).setBackground(QColor("#27ae60"))
                self.completed_prompts.append(task)
                
                row = self.completed_table.rowCount()
                self.completed_table.insertRow(row)
                self.completed_table.setItem(row, 0, QTableWidgetItem(email))
                self.completed_table.setItem(row, 1, QTableWidgetItem(task.prompt[:40]))
                self.completed_table.setItem(row, 2, QTableWidgetItem(Path(task.output_path).name if task.output_path else ""))
                
                self._log(f"✅ [{email}] Done: {task.prompt[:25]}...")
            else:
                self.queue_table.setItem(idx, 2, QTableWidgetItem(f"❌ Lỗi"))
                self.queue_table.item(idx, 2).setBackground(QColor("#e74c3c"))
                self.failed_prompts.append(task)
                self._log(f"❌ [{email}] {task.error_message[:40]}")
        
        if task.status == "completed":
            self.history_manager.add_history(task)
            self.video_completed.emit()
        
        if email in self.workers:
            del self.workers[email]
        
        if self.current_prompt_index < len(self.prompt_queue):
            acc = self.account_manager.get_account(email)
            if acc and acc.status == "logged_in":
                self._start_worker(acc, self.prompt_queue[self.current_prompt_index], self.current_prompt_index)
                self.current_prompt_index += 1
        
        if not self.workers:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._log(f"🎉 Done! {len(self.completed_prompts)} OK, {len(self.failed_prompts)} failed")
    
    def _stop_generation(self):
        for w in self.workers.values():
            w.stop()
        self.workers.clear()
        self.running_table.setRowCount(0)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._log("⏹️ Stopped")
    
    def _update_stats(self):
        self.stat_total.set_value(len(self.prompt_queue))
        self.stat_running.set_value(len(self.workers))
        self.stat_completed.set_value(len(self.completed_prompts))
        self.stat_failed.set_value(len(self.failed_prompts))
    
    def _save_settings(self):
        s = {
            "aspect": self.aspect_combo.currentIndex(),
            "length": self.length_combo.currentIndex(),
            "resolution": self.resolution_combo.currentIndex(),
            "headless": self.headless_check.isChecked(),
            "concurrent": self.concurrent_spin.value()
        }
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(s, indent=2))
        self._log("💾 Settings saved!")
    
    def _load_settings(self):
        if SETTINGS_FILE.exists():
            try:
                s = json.loads(SETTINGS_FILE.read_text())
                self.aspect_combo.setCurrentIndex(s.get("aspect", 0))
                self.length_combo.setCurrentIndex(s.get("length", 0))
                self.resolution_combo.setCurrentIndex(s.get("resolution", 0))
                self.headless_check.setChecked(s.get("headless", True))
                self.concurrent_spin.setValue(s.get("concurrent", 2))
            except: pass
    
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
