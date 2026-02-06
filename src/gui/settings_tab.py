"""Settings Tab - Output folder + Cloudflare D1 connection"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QFileDialog, QMessageBox, QTextEdit
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QFont, QColor
from ..core.d1_manager import D1Manager


class D1Worker(QThread):
    """Worker thread for D1 operations."""
    status_update = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, d1: D1Manager, action: str):
        super().__init__()
        self.d1 = d1
        self.action = action
    
    def run(self):
        if self.action == "test":
            ok, msg = self.d1.test_connection()
            self.finished.emit(ok, msg)
        elif self.action == "create":
            ok, msg = self.d1.create_database()
            if ok:
                ok2, msg2 = self.d1.init_tables()
                msg = f"{msg}\n{msg2}"
                ok = ok and ok2
            self.finished.emit(ok, msg)
        elif self.action == "init_tables":
            ok, msg = self.d1.init_tables()
            self.finished.emit(ok, msg)


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
                    background: rgba(30, 40, 60, 180);
                    border: 1px solid rgba(100, 150, 255, 50);
                    border-radius: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                GlassFrame {
                    background: rgba(255, 255, 255, 200);
                    border: 1px solid rgba(100, 150, 200, 80);
                    border-radius: 12px;
                }
            """)


class SettingsTab(QWidget):
    output_dir_changed = Signal(str)
    
    def __init__(self, d1_manager: D1Manager):
        super().__init__()
        self.d1 = d1_manager
        self.is_dark = True
        self._worker = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # === OUTPUT FOLDER SECTION ===
        output_card = GlassFrame()
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(20, 15, 20, 15)
        output_layout.setSpacing(10)
        
        self.output_title = QLabel("📂 Thư mục xuất video")
        self.output_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        output_layout.addWidget(self.output_title)
        
        self.output_desc = QLabel(
            "Chọn thư mục gốc để lưu video. Khi import file TXT, video sẽ được lưu vào subfolder trùng tên file.\n"
            "Ví dụ: import 'cats.txt' → video lưu vào 'output/cats/'"
        )
        self.output_desc.setWordWrap(True)
        self.output_desc.setFont(QFont("Segoe UI", 10))
        output_layout.addWidget(self.output_desc)
        
        dir_row = QHBoxLayout()
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("output")
        self.output_input.setText("output")
        self.output_input.setReadOnly(True)
        self.output_input.setFont(QFont("Consolas", 11))
        
        self.browse_btn = QPushButton("📁 Chọn thư mục")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse_output)
        
        dir_row.addWidget(self.output_input, stretch=1)
        dir_row.addWidget(self.browse_btn)
        output_layout.addLayout(dir_row)
        
        self.output_card = output_card
        layout.addWidget(output_card)
        
        # === CLOUDFLARE D1 SECTION ===
        d1_card = GlassFrame()
        d1_layout = QVBoxLayout(d1_card)
        d1_layout.setContentsMargins(20, 15, 20, 15)
        d1_layout.setSpacing(10)
        
        self.d1_title = QLabel("☁️ Cloudflare D1 Database")
        self.d1_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        d1_layout.addWidget(self.d1_title)
        
        self.d1_desc = QLabel(
            "Kết nối Cloudflare D1 để đồng bộ accounts và lịch sử video lên cloud.\n"
            "Yêu cầu: wrangler đã cài đặt và đăng nhập (wrangler login)."
        )
        self.d1_desc.setWordWrap(True)
        self.d1_desc.setFont(QFont("Segoe UI", 10))
        d1_layout.addWidget(self.d1_desc)
        
        # Database name
        db_row = QHBoxLayout()
        self.db_label = QLabel("Database:")
        self.db_label.setFont(QFont("Segoe UI", 10))
        self.db_input = QLineEdit()
        self.db_input.setText("grok-video-db")
        self.db_input.setFont(QFont("Consolas", 11))
        self.db_input.setPlaceholderText("tên database D1")
        db_row.addWidget(self.db_label)
        db_row.addWidget(self.db_input, stretch=1)
        d1_layout.addLayout(db_row)
        
        # Status indicator
        status_row = QHBoxLayout()
        self.d1_status_icon = QLabel("⚪")
        self.d1_status_icon.setFont(QFont("Segoe UI", 14))
        self.d1_status_text = QLabel("Chưa kết nối")
        self.d1_status_text.setFont(QFont("Segoe UI", 10))
        status_row.addWidget(self.d1_status_icon)
        status_row.addWidget(self.d1_status_text, stretch=1)
        d1_layout.addLayout(status_row)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        self.test_btn = QPushButton("🔌 Kiểm tra kết nối")
        self.test_btn.setCursor(Qt.PointingHandCursor)
        self.test_btn.clicked.connect(self._test_d1)
        
        self.create_btn = QPushButton("➕ Tạo Database")
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.clicked.connect(self._create_d1)
        
        self.init_btn = QPushButton("🗄️ Tạo Tables")
        self.init_btn.setCursor(Qt.PointingHandCursor)
        self.init_btn.clicked.connect(self._init_tables)
        
        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.create_btn)
        btn_row.addWidget(self.init_btn)
        btn_row.addStretch()
        d1_layout.addLayout(btn_row)
        
        # D1 Log
        self.d1_log = QTextEdit()
        self.d1_log.setReadOnly(True)
        self.d1_log.setMaximumHeight(120)
        self.d1_log.setFont(QFont("Consolas", 10))
        d1_layout.addWidget(self.d1_log)
        
        self.d1_card = d1_card
        layout.addWidget(d1_card)
        
        layout.addStretch()
        self._apply_theme()
    
    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất video", self.output_input.text())
        if folder:
            self.output_input.setText(folder)
            self.output_dir_changed.emit(folder)
            self._d1_log(f"📂 Đã chọn: {folder}")
    
    def get_output_dir(self) -> str:
        return self.output_input.text() or "output"
    
    def _test_d1(self):
        self.d1.database_name = self.db_input.text().strip() or "grok-video-db"
        self._set_d1_status("🔄", "Đang kiểm tra...")
        self._d1_log("🔌 Kiểm tra kết nối D1...")
        self._run_d1_action("test")
    
    def _create_d1(self):
        self.d1.database_name = self.db_input.text().strip() or "grok-video-db"
        self._set_d1_status("🔄", "Đang tạo database...")
        self._d1_log("➕ Tạo database D1...")
        self._run_d1_action("create")
    
    def _init_tables(self):
        self.d1.database_name = self.db_input.text().strip() or "grok-video-db"
        self._set_d1_status("🔄", "Đang tạo tables...")
        self._d1_log("🗄️ Tạo tables...")
        self._run_d1_action("init_tables")
    
    def _run_d1_action(self, action: str):
        self.test_btn.setEnabled(False)
        self.create_btn.setEnabled(False)
        self.init_btn.setEnabled(False)
        
        self._worker = D1Worker(self.d1, action)
        self._worker.finished.connect(self._on_d1_done)
        self._worker.start()
    
    def _on_d1_done(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        self.create_btn.setEnabled(True)
        self.init_btn.setEnabled(True)
        
        if ok:
            self._set_d1_status("🟢", msg)
            self._d1_log(f"✅ {msg}")
        else:
            self._set_d1_status("🔴", msg)
            self._d1_log(f"❌ {msg}")
    
    def _set_d1_status(self, icon: str, text: str):
        self.d1_status_icon.setText(icon)
        self.d1_status_text.setText(text)
    
    def _d1_log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.d1_log.append(f"[{ts}] {msg}")
    
    def set_dark_mode(self, is_dark):
        self.is_dark = is_dark
        self._apply_theme()
    
    def _apply_theme(self):
        self.output_card.set_dark(self.is_dark)
        self.d1_card.set_dark(self.is_dark)
        
        if self.is_dark:
            tc = "white"
            input_style = """
                QLineEdit {
                    background: rgba(40, 50, 70, 200);
                    color: white;
                    border: 1px solid rgba(100, 150, 255, 80);
                    border-radius: 6px;
                    padding: 8px 12px;
                }
            """
            btn_style = """
                QPushButton {
                    background: rgba(50, 60, 80, 200);
                    color: white;
                    border: 1px solid rgba(100, 150, 255, 80);
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 12px;
                }
                QPushButton:hover { background: rgba(60, 70, 90, 220); }
            """
            log_style = """
                QTextEdit {
                    background: rgba(10, 15, 25, 200);
                    color: #0f0;
                    border: 1px solid rgba(0, 255, 0, 30);
                    border-radius: 6px;
                    padding: 8px;
                }
            """
        else:
            tc = "#333"
            input_style = """
                QLineEdit {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 8px 12px;
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
                QPushButton:hover { background: #f0f0f0; }
            """
            log_style = """
                QTextEdit {
                    background: rgba(20, 30, 50, 230);
                    color: #0f0;
                    border: 1px solid rgba(0, 100, 0, 50);
                    border-radius: 6px;
                    padding: 8px;
                }
            """
        
        for lbl in [self.output_title, self.output_desc, self.d1_title, self.d1_desc,
                     self.db_label, self.d1_status_text, self.d1_status_icon]:
            lbl.setStyleSheet(f"color: {tc}; background: transparent;")
        
        self.output_input.setStyleSheet(input_style)
        self.db_input.setStyleSheet(input_style)
        self.d1_log.setStyleSheet(log_style)
        
        for btn in [self.test_btn, self.create_btn, self.init_btn]:
            btn.setStyleSheet(btn_style)
        
        self.browse_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3498db, stop:1 #2980b9);
                color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
