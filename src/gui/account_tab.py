"""Account Tab - Manage X.AI accounts with Modern UI"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QDialog, QFormLayout, QLineEdit, QMessageBox,
    QHeaderView, QTextEdit, QGroupBox, QLabel, QFrame
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
        result = self.session_manager.login(
            self.account, 
            self.password,
            lambda msg: self.status_update.emit(msg)
        )
        self.finished.emit(result)


class AccountDialog(QDialog):
    def __init__(self, parent=None, email="", password=""):
        super().__init__(parent)
        self.setWindowTitle("Thêm/Sửa Account")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #dcdde1;
                border-radius: 4px;
            }
            QPushButton {
                padding: 8px 20px;
            }
        """)
        
        layout = QFormLayout(self)
        layout.setSpacing(15)
        
        self.email_input = QLineEdit(email)
        self.email_input.setPlaceholderText("example@email.com")
        self.password_input = QLineEdit(password)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("••••••••")
        
        layout.addRow("📧 Email:", self.email_input)
        layout.addRow("🔒 Password:", self.password_input)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("💾 Lưu")
        save_btn.setStyleSheet("background-color: #27ae60; color: white;")
        cancel_btn = QPushButton("❌ Hủy")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addRow(btn_layout)
    
    def get_data(self):
        return self.email_input.text(), self.password_input.text()


class AccountTab(QWidget):
    account_changed = Signal()
    
    def __init__(self, account_manager: AccountManager, session_manager: SessionManager):
        super().__init__()
        self.account_manager = account_manager
        self.session_manager = session_manager
        self.login_worker = None
        self._setup_ui()
        self._refresh_table()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Stats bar
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background-color: #3498db;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                color: white;
            }
        """)
        stats_layout = QHBoxLayout(stats_frame)
        
        self.total_label = QLabel("Tổng: 0")
        self.total_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.logged_in_label = QLabel("Đã đăng nhập: 0")
        self.logged_in_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        stats_layout.addWidget(self.total_label)
        stats_layout.addStretch()
        stats_layout.addWidget(self.logged_in_label)
        
        layout.addWidget(stats_frame)
        
        # Account table
        table_group = QGroupBox("📋 Danh sách Accounts")
        table_layout = QVBoxLayout(table_group)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Email", "Trạng thái", "Đăng nhập lần cuối", "Lỗi"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        table_layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ Thêm Account")
        add_btn.setStyleSheet("background-color: #27ae60; color: white;")
        edit_btn = QPushButton("✏️ Sửa")
        delete_btn = QPushButton("🗑️ Xóa")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        login_btn = QPushButton("🔑 Đăng nhập")
        login_btn.setStyleSheet("background-color: #3498db; color: white;")
        login_all_btn = QPushButton("🔑 Đăng nhập tất cả")
        
        add_btn.clicked.connect(self._add_account)
        edit_btn.clicked.connect(self._edit_account)
        delete_btn.clicked.connect(self._delete_account)
        login_btn.clicked.connect(self._login_account)
        login_all_btn.clicked.connect(self._login_all_accounts)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(login_btn)
        btn_layout.addWidget(login_all_btn)
        btn_layout.addStretch()
        
        table_layout.addLayout(btn_layout)
        layout.addWidget(table_group)
        
        # Log area
        log_group = QGroupBox("📜 Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        self.log.setStyleSheet("""
            QTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                font-family: Consolas, monospace;
            }
        """)
        log_layout.addWidget(self.log)
        
        layout.addWidget(log_group)
    
    def _refresh_table(self):
        accounts = self.account_manager.get_all_accounts()
        self.table.setRowCount(len(accounts))
        
        logged_in_count = 0
        
        for i, acc in enumerate(accounts):
            # Email
            self.table.setItem(i, 0, QTableWidgetItem(acc.email))
            
            # Status
            status_item = QTableWidgetItem(acc.status)
            if acc.status == "logged_in":
                status_item.setBackground(QColor("#27ae60"))
                status_item.setForeground(QColor("white"))
                logged_in_count += 1
            elif acc.status == "error":
                status_item.setBackground(QColor("#e74c3c"))
                status_item.setForeground(QColor("white"))
            else:
                status_item.setBackground(QColor("#f39c12"))
                status_item.setForeground(QColor("white"))
            self.table.setItem(i, 1, status_item)
            
            # Last login
            last_login = acc.last_login.strftime("%Y-%m-%d %H:%M") if acc.last_login else "-"
            self.table.setItem(i, 2, QTableWidgetItem(last_login))
            
            # Error
            self.table.setItem(i, 3, QTableWidgetItem(acc.error_message or "-"))
        
        # Update stats
        self.total_label.setText(f"Tổng: {len(accounts)}")
        self.logged_in_label.setText(f"Đã đăng nhập: {logged_in_count}")
    
    def _add_account(self):
        dialog = AccountDialog(self)
        if dialog.exec() == QDialog.Accepted:
            email, password = dialog.get_data()
            if email and password:
                self.account_manager.add_account(email, password)
                self._refresh_table()
                self.account_changed.emit()
                self._log(f"✅ Đã thêm account: {email}")
    
    def _edit_account(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Lỗi", "Chọn account để sửa")
            return
        
        email = self.table.item(row, 0).text()
        account = self.account_manager.get_account(email)
        if account:
            password = self.account_manager.get_password(email)
            dialog = AccountDialog(self, email, password or "")
            if dialog.exec() == QDialog.Accepted:
                new_email, new_password = dialog.get_data()
                if new_password:
                    self.account_manager.update_account(email, password=new_password)
                self._refresh_table()
                self._log(f"✅ Đã cập nhật account: {email}")
    
    def _delete_account(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Lỗi", "Chọn account để xóa")
            return
        
        email = self.table.item(row, 0).text()
        reply = QMessageBox.question(
            self, "Xác nhận", f"Xóa account {email}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.account_manager.delete_account(email)
            self._refresh_table()
            self.account_changed.emit()
            self._log(f"🗑️ Đã xóa account: {email}")
    
    def _login_account(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Lỗi", "Chọn account để đăng nhập")
            return
        
        email = self.table.item(row, 0).text()
        self._do_login(email)
    
    def _login_all_accounts(self):
        accounts = self.account_manager.get_all_accounts()
        for acc in accounts:
            if acc.status != "logged_in":
                self._do_login(acc.email)
                break  # Login one at a time
    
    def _do_login(self, email):
        account = self.account_manager.get_account(email)
        password = self.account_manager.get_password(email)
        
        if not account or not password:
            return
        
        self._log(f"🔑 Đang đăng nhập {email}...")
        
        self.login_worker = LoginWorker(self.session_manager, account, password)
        self.login_worker.status_update.connect(self._log)
        self.login_worker.finished.connect(lambda success: self._on_login_finished(email, success))
        self.login_worker.start()
    
    def _on_login_finished(self, email, success):
        if success:
            self._log(f"✅ Đăng nhập thành công: {email}")
        else:
            self._log(f"❌ Đăng nhập thất bại: {email}")
        self.account_manager.save_to_storage()
        self._refresh_table()
        self.account_changed.emit()
    
    def _log(self, msg):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {msg}")
