"""Account Tab - Modern UI with Dark/Light Theme"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QDialog, QFormLayout, QLineEdit, QMessageBox,
    QHeaderView, QTextEdit, QLabel, QFrame
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QColor, QFont
from ..core.account_manager import AccountManager
from ..core.session_manager import SessionManager


class LoginWorker(QThread):
    status_update = Signal(str)
    finished = Signal(bool)
    
    def __init__(self, session_manager, account, password):
        super().__init__()
        self.session_manager = session_manager
        self.account = account
        self.password = password
    
    def run(self):
        try:
            result = self.session_manager.login(
                self.account, self.password,
                lambda msg: self.status_update.emit(msg)
            )
            self.finished.emit(result)
        except Exception as e:
            self.status_update.emit(f"❌ Browser error: {e}")
            self.account.status = "error"
            self.account.error_message = str(e)
            self.finished.emit(False)


class AccountDialog(QDialog):
    def __init__(self, parent=None, email="", password="", is_dark=True):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Account")
        self.setMinimumWidth(400)
        self.is_dark = is_dark
        self._setup_ui(email, password)
        self._apply_style()
    
    def _setup_ui(self, email, password):
        layout = QFormLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.email_input = QLineEdit(email)
        self.email_input.setPlaceholderText("example@email.com")
        self.password_input = QLineEdit(password)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("••••••••")
        
        self.email_label = QLabel("📧 Email:")
        self.pass_label = QLabel("🔒 Password:")
        
        layout.addRow(self.email_label, self.email_input)
        layout.addRow(self.pass_label, self.password_input)
        
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save")
        self.cancel_btn = QPushButton("❌ Cancel")
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addRow(btn_layout)
    
    def _apply_style(self):
        if self.is_dark:
            self.setStyleSheet("""
                QDialog { background: rgb(25, 35, 55); }
                QLabel { color: white; }
                QLineEdit {
                    background: rgba(40, 50, 70, 200);
                    color: white;
                    border: 1px solid rgba(100, 150, 255, 80);
                    border-radius: 6px;
                    padding: 10px;
                }
                QPushButton {
                    background: rgba(50, 60, 80, 200);
                    color: white;
                    border: 1px solid rgba(100, 150, 255, 80);
                    border-radius: 6px;
                    padding: 10px 20px;
                }
                QPushButton:hover { background: rgba(60, 70, 90, 220); }
            """)
            self.save_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #27ae60, stop:1 #2ecc71);
                    color: white; border: none; border-radius: 6px; padding: 10px 20px;
                }
                QPushButton:hover { background: #2ecc71; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background: rgb(245, 248, 255); }
                QLabel { color: #333; }
                QLineEdit {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 10px;
                }
                QPushButton {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 10px 20px;
                }
                QPushButton:hover { background: #f0f0f0; }
            """)
            self.save_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #27ae60, stop:1 #2ecc71);
                    color: white; border: none; border-radius: 6px; padding: 10px 20px;
                }
            """)
    
    def get_data(self):
        return self.email_input.text(), self.password_input.text()


class GlassFrame(QFrame):
    """Glass-style frame"""
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


class AccountTab(QWidget):
    account_changed = Signal()
    
    def __init__(self, account_manager: AccountManager, session_manager: SessionManager):
        super().__init__()
        self.account_manager = account_manager
        self.session_manager = session_manager
        self.login_worker = None
        self.is_dark = True
        self._setup_ui()
        self._refresh_table()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Stats bar
        stats_frame = GlassFrame()
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(20, 15, 20, 15)
        
        self.total_label = QLabel("📊 Total: 0")
        self.total_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.logged_label = QLabel("✅ Logged in: 0")
        self.logged_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        
        stats_layout.addWidget(self.total_label)
        stats_layout.addStretch()
        stats_layout.addWidget(self.logged_label)
        
        self.stats_frame = stats_frame
        layout.addWidget(stats_frame)
        
        # Table card
        table_card = GlassFrame()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(15, 15, 15, 15)
        table_layout.setSpacing(12)
        
        self.table_title = QLabel("📋 Account List")
        self.table_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        table_layout.addWidget(self.table_title)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Email", "Status", "Last Login", "Error"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(False)
        table_layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.add_btn = QPushButton("➕ Add")
        self.edit_btn = QPushButton("✏️ Edit")
        self.delete_btn = QPushButton("🗑️ Delete")
        self.login_btn = QPushButton("🔑 Login")
        self.login_all_btn = QPushButton("🔑 Login All")
        self.export_btn = QPushButton("📤 Export")
        self.import_btn = QPushButton("📥 Import")
        
        self.add_btn.clicked.connect(self._add_account)
        self.edit_btn.clicked.connect(self._edit_account)
        self.delete_btn.clicked.connect(self._delete_account)
        self.login_btn.clicked.connect(self._login_account)
        self.login_all_btn.clicked.connect(self._login_all)
        self.export_btn.clicked.connect(self._export_temp)
        self.import_btn.clicked.connect(self._import_temp)
        
        for btn in [self.add_btn, self.edit_btn, self.delete_btn, self.login_btn, self.login_all_btn, self.export_btn, self.import_btn]:
            btn.setCursor(Qt.PointingHandCursor)
            btn_layout.addWidget(btn)
        
        btn_layout.addStretch()
        table_layout.addLayout(btn_layout)
        
        self.table_card = table_card
        layout.addWidget(table_card, stretch=1)
        
        # Log card
        log_card = GlassFrame()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(15, 15, 15, 15)
        
        self.log_title = QLabel("📜 Log")
        self.log_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        log_layout.addWidget(self.log_title)
        
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        log_layout.addWidget(self.log)
        
        self.log_card = log_card
        layout.addWidget(log_card)
        
        self._apply_theme()
    
    def set_dark_mode(self, is_dark):
        self.is_dark = is_dark
        self._apply_theme()
    
    def _apply_theme(self):
        # Update frames
        for frame in [self.stats_frame, self.table_card, self.log_card]:
            frame.set_dark(self.is_dark)
        
        if self.is_dark:
            text_color = "white"
            table_style = """
                QTableWidget {
                    background: rgba(20, 30, 50, 150);
                    color: white;
                    border: 1px solid rgba(100, 150, 255, 50);
                    border-radius: 8px;
                    gridline-color: rgba(100, 150, 255, 30);
                }
                QTableWidget::item { padding: 6px; }
                QTableWidget::item:selected { background: rgba(100, 150, 255, 100); }
                QHeaderView::section {
                    background: rgba(40, 50, 70, 200);
                    color: white;
                    border: none;
                    padding: 8px;
                    font-weight: bold;
                }
            """
            log_style = """
                QTextEdit {
                    background: rgba(10, 15, 25, 200);
                    color: #0f0;
                    border: 1px solid rgba(0, 255, 0, 30);
                    border-radius: 6px;
                    font-family: 'Consolas', monospace;
                    font-size: 11px;
                    padding: 8px;
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
        else:
            text_color = "#333"
            table_style = """
                QTableWidget {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 80);
                    border-radius: 8px;
                    gridline-color: rgba(100, 150, 200, 50);
                }
                QTableWidget::item { padding: 6px; }
                QTableWidget::item:selected { background: rgba(100, 150, 255, 100); }
                QHeaderView::section {
                    background: rgba(240, 245, 255, 250);
                    color: #333;
                    border: none;
                    padding: 8px;
                    font-weight: bold;
                }
            """
            log_style = """
                QTextEdit {
                    background: rgba(20, 30, 50, 230);
                    color: #0f0;
                    border: 1px solid rgba(0, 100, 0, 50);
                    border-radius: 6px;
                    font-family: 'Consolas', monospace;
                    font-size: 11px;
                    padding: 8px;
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
        
        for label in [self.total_label, self.logged_label, self.table_title, self.log_title]:
            label.setStyleSheet(f"color: {text_color};")
        
        self.table.setStyleSheet(table_style)
        self.log.setStyleSheet(log_style)
        
        for btn in [self.edit_btn, self.delete_btn, self.login_btn, self.login_all_btn, self.export_btn, self.import_btn]:
            btn.setStyleSheet(btn_style)
        
        # Special buttons
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #27ae60, stop:1 #2ecc71);
                color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e74c3c, stop:1 #c0392b);
                color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3498db, stop:1 #2980b9);
                color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8e44ad, stop:1 #9b59b6);
                color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #9b59b6; }
        """)
        self.import_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e67e22, stop:1 #f39c12);
                color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #f39c12; }
        """)

    
    def _refresh_table(self):
        accounts = self.account_manager.get_all_accounts()
        self.table.setRowCount(len(accounts))
        
        logged_in = 0
        for i, acc in enumerate(accounts):
            self.table.setItem(i, 0, QTableWidgetItem(acc.email))
            
            status_item = QTableWidgetItem(acc.status)
            if acc.status == "logged_in":
                status_item.setBackground(QColor("#27ae60"))
                status_item.setForeground(QColor("white"))
                logged_in += 1
            elif acc.status == "error":
                status_item.setBackground(QColor("#e74c3c"))
                status_item.setForeground(QColor("white"))
            else:
                status_item.setBackground(QColor("#f39c12"))
                status_item.setForeground(QColor("white"))
            self.table.setItem(i, 1, status_item)
            
            last_login = acc.last_login.strftime("%Y-%m-%d %H:%M") if acc.last_login else "-"
            self.table.setItem(i, 2, QTableWidgetItem(last_login))
            self.table.setItem(i, 3, QTableWidgetItem(acc.error_message or "-"))
        
        self.total_label.setText(f"📊 Total: {len(accounts)}")
        self.logged_label.setText(f"✅ Logged in: {logged_in}")
    
    def _add_account(self):
        dialog = AccountDialog(self, is_dark=self.is_dark)
        if dialog.exec() == QDialog.Accepted:
            email, password = dialog.get_data()
            if email and password:
                self.account_manager.add_account(email, password)
                self._refresh_table()
                self.account_changed.emit()
                self._log(f"✅ Added: {email}")
    
    def _edit_account(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Error", "Select an account to edit")
            return
        
        email = self.table.item(row, 0).text()
        account = self.account_manager.get_account(email)
        if account:
            password = self.account_manager.get_password(email)
            dialog = AccountDialog(self, email, password or "", self.is_dark)
            if dialog.exec() == QDialog.Accepted:
                _, new_password = dialog.get_data()
                if new_password:
                    self.account_manager.update_account(email, password=new_password)
                self._refresh_table()
                self._log(f"✅ Updated: {email}")
    
    def _delete_account(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Error", "Select an account to delete")
            return
        
        email = self.table.item(row, 0).text()
        reply = QMessageBox.question(self, "Confirm", f"Delete {email}?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.account_manager.delete_account(email)
            self._refresh_table()
            self.account_changed.emit()
            self._log(f"🗑️ Deleted: {email}")
    
    def _login_account(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Error", "Select an account to login")
            return
        email = self.table.item(row, 0).text()
        self._do_login(email)
    
    def _login_all(self):
        for acc in self.account_manager.get_all_accounts():
            if acc.status != "logged_in":
                self._do_login(acc.email)
                break
    
    def _do_login(self, email):
        account = self.account_manager.get_account(email)
        password = self.account_manager.get_password(email)
        if not account:
            return
        if not password:
            self._log(f"❌ Không giải mã được password cho {email} — key đã thay đổi. Xóa account và thêm lại.")
            QMessageBox.warning(
                self, "Lỗi giải mã",
                f"Không giải mã được password cho {email}.\n\n"
                "File data/.key đã thay đổi hoặc bị mất.\n"
                "Hãy xóa tài khoản này và thêm lại."
            )
            return
        
        self._log(f"🔑 Logging in {email}...")
        self.login_worker = LoginWorker(self.session_manager, account, password)
        self.login_worker.status_update.connect(self._log)
        self.login_worker.finished.connect(lambda ok: self._on_login_done(email, ok))
        self.login_worker.start()
    
    def _on_login_done(self, email, success):
        if success:
            self._log(f"✅ Login success: {email}")
        else:
            self._log(f"❌ Login failed: {email}")
        self.account_manager.save_to_storage()
        self._refresh_table()
        self.account_changed.emit()
    
    def _log(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")

    def _export_temp(self):
        try:
            count = self.account_manager.export_to_temp()
            self._log(f"📤 Exported {count} accounts → data/login_temp.json")
            QMessageBox.information(self, "Export", f"Đã export {count} tài khoản ra data/login_temp.json")
        except Exception as e:
            self._log(f"❌ Export failed: {e}")
            QMessageBox.warning(self, "Error", str(e))

    def _import_temp(self):
        try:
            added, skipped = self.account_manager.import_from_temp()
            self._refresh_table()
            self.account_changed.emit()
            self._log(f"📥 Imported: {added} added, {skipped} skipped (already exist)")
            QMessageBox.information(self, "Import", f"Thêm {added} tài khoản, bỏ qua {skipped} (đã tồn tại)")
        except FileNotFoundError:
            self._log("❌ File data/login_temp.json không tồn tại")
            QMessageBox.warning(self, "Error", "File data/login_temp.json không tồn tại.\nHãy Export trước hoặc tạo file thủ công.")
        except Exception as e:
            self._log(f"❌ Import failed: {e}")
            QMessageBox.warning(self, "Error", str(e))
