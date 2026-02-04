"""History Tab - View generated videos with Modern UI"""
import os
import subprocess
import sys
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox, QGroupBox, QLabel, QFrame,
    QLineEdit, QComboBox, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from ..core.history_manager import HistoryManager


class StatsWidget(QFrame):
    """Widget hiển thị thống kê"""
    def __init__(self, title, value="0", color="#3498db"):
        super().__init__()
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: 8px;
                padding: 10px;
            }}
            QLabel {{
                color: white;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.value_label.setAlignment(Qt.AlignCenter)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 10))
        title_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.value_label)
        layout.addWidget(title_label)
    
    def set_value(self, value):
        self.value_label.setText(str(value))


class HistoryTab(QWidget):
    def __init__(self, history_manager: HistoryManager):
        super().__init__()
        self.history_manager = history_manager
        self._setup_ui()
        self.refresh()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # === Stats Bar ===
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)
        
        self.stat_total = StatsWidget("Tổng Video", "0", "#3498db")
        self.stat_completed = StatsWidget("Thành công", "0", "#27ae60")
        self.stat_failed = StatsWidget("Thất bại", "0", "#e74c3c")
        self.stat_today = StatsWidget("Hôm nay", "0", "#9b59b6")
        
        stats_layout.addWidget(self.stat_total)
        stats_layout.addWidget(self.stat_completed)
        stats_layout.addWidget(self.stat_failed)
        stats_layout.addWidget(self.stat_today)
        
        layout.addLayout(stats_layout)
        
        # === Filter Section ===
        filter_group = QGroupBox("🔍 Bộ lọc")
        filter_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        filter_layout = QHBoxLayout(filter_group)
        
        filter_layout.addWidget(QLabel("Tìm kiếm:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Nhập prompt hoặc email...")
        self.search_input.textChanged.connect(self._filter_table)
        filter_layout.addWidget(self.search_input)
        
        filter_layout.addWidget(QLabel("Trạng thái:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Tất cả", "Thành công", "Thất bại"])
        self.status_filter.currentIndexChanged.connect(self._filter_table)
        filter_layout.addWidget(self.status_filter)
        
        filter_layout.addStretch()
        
        layout.addWidget(filter_group)
        
        # === Table Section ===
        table_group = QGroupBox("📋 Lịch sử tạo Video")
        table_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        table_layout = QVBoxLayout(table_group)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Thời gian", "Account", "Prompt", "Cài đặt", "Trạng thái", "File"
        ])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._open_video)
        table_layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Làm mới")
        refresh_btn.clicked.connect(self.refresh)
        
        open_folder_btn = QPushButton("📂 Mở thư mục Output")
        open_folder_btn.setStyleSheet("background-color: #3498db; color: white;")
        open_folder_btn.clicked.connect(self._open_output_folder)
        
        open_video_btn = QPushButton("▶️ Mở Video")
        open_video_btn.setStyleSheet("background-color: #27ae60; color: white;")
        open_video_btn.clicked.connect(self._open_video)
        
        export_btn = QPushButton("📥 Export CSV")
        export_btn.clicked.connect(self._export_csv)
        
        delete_btn = QPushButton("🗑️ Xóa")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        delete_btn.clicked.connect(self._delete_selected)
        
        clear_btn = QPushButton("🧹 Xóa tất cả")
        clear_btn.clicked.connect(self._clear_all)
        
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(open_folder_btn)
        btn_layout.addWidget(open_video_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        
        table_layout.addLayout(btn_layout)
        layout.addWidget(table_group)
        
        # Store all tasks for filtering
        self.all_tasks = []
    
    def refresh(self):
        self.all_tasks = self.history_manager.get_all_history()
        self._update_table(self.all_tasks)
        self._update_stats()
    
    def _update_table(self, tasks):
        self.table.setRowCount(len(tasks))
        
        for i, task in enumerate(tasks):
            # Time
            time_str = task.created_at.strftime("%Y-%m-%d %H:%M") if task.created_at else "-"
            time_item = QTableWidgetItem(time_str)
            time_item.setData(Qt.UserRole, task.id)
            self.table.setItem(i, 0, time_item)
            
            # Account
            email_short = task.account_email.split('@')[0] if '@' in task.account_email else task.account_email
            self.table.setItem(i, 1, QTableWidgetItem(email_short))
            
            # Prompt (truncated)
            prompt_short = task.prompt[:60] + "..." if len(task.prompt) > 60 else task.prompt
            prompt_item = QTableWidgetItem(prompt_short)
            prompt_item.setToolTip(task.prompt)  # Full prompt on hover
            self.table.setItem(i, 2, prompt_item)
            
            # Settings
            settings_str = f"{task.settings.aspect_ratio} | {task.settings.video_length}s"
            self.table.setItem(i, 3, QTableWidgetItem(settings_str))
            
            # Status
            if task.status == "completed":
                status_item = QTableWidgetItem("✅ Thành công")
                status_item.setBackground(QColor("#27ae60"))
                status_item.setForeground(QColor("white"))
            else:
                status_item = QTableWidgetItem("❌ Thất bại")
                status_item.setBackground(QColor("#e74c3c"))
                status_item.setForeground(QColor("white"))
                if task.error_message:
                    status_item.setToolTip(task.error_message)
            self.table.setItem(i, 4, status_item)
            
            # File path
            if task.output_path:
                filename = os.path.basename(task.output_path)
                path_item = QTableWidgetItem(filename)
                path_item.setToolTip(task.output_path)
            else:
                path_item = QTableWidgetItem("-")
            self.table.setItem(i, 5, path_item)
    
    def _update_stats(self):
        total = len(self.all_tasks)
        completed = sum(1 for t in self.all_tasks if t.status == "completed")
        failed = sum(1 for t in self.all_tasks if t.status == "failed")
        
        today = datetime.now().date()
        today_count = sum(1 for t in self.all_tasks 
                        if t.created_at and t.created_at.date() == today)
        
        self.stat_total.set_value(total)
        self.stat_completed.set_value(completed)
        self.stat_failed.set_value(failed)
        self.stat_today.set_value(today_count)
    
    def _filter_table(self):
        search_text = self.search_input.text().lower()
        status_filter = self.status_filter.currentText()
        
        filtered = []
        for task in self.all_tasks:
            # Search filter
            if search_text:
                if search_text not in task.prompt.lower() and search_text not in task.account_email.lower():
                    continue
            
            # Status filter
            if status_filter == "Thành công" and task.status != "completed":
                continue
            if status_filter == "Thất bại" and task.status != "failed":
                continue
            
            filtered.append(task)
        
        self._update_table(filtered)
    
    def _open_output_folder(self):
        output_dir = os.path.abspath("output")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        if sys.platform == "darwin":
            subprocess.run(["open", output_dir])
        elif sys.platform == "win32":
            subprocess.run(["explorer", output_dir])
        else:
            subprocess.run(["xdg-open", output_dir])
    
    def _open_video(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        path_item = self.table.item(row, 5)
        if path_item:
            file_path = path_item.toolTip() or path_item.text()
            if file_path and file_path != "-" and os.path.exists(file_path):
                if sys.platform == "darwin":
                    subprocess.run(["open", file_path])
                elif sys.platform == "win32":
                    subprocess.run(["start", "", file_path], shell=True)
                else:
                    subprocess.run(["xdg-open", file_path])
            else:
                QMessageBox.warning(self, "Lỗi", "File không tồn tại")
    
    def _export_csv(self):
        if not self.all_tasks:
            QMessageBox.information(self, "Thông báo", "Không có dữ liệu để export")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Lưu file CSV", "history.csv", "CSV Files (*.csv)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("Thời gian,Account,Prompt,Cài đặt,Trạng thái,File\n")
                    for task in self.all_tasks:
                        time_str = task.created_at.strftime("%Y-%m-%d %H:%M") if task.created_at else ""
                        prompt_escaped = task.prompt.replace('"', '""')
                        settings_str = f"{task.settings.aspect_ratio}|{task.settings.video_length}s"
                        f.write(f'"{time_str}","{task.account_email}","{prompt_escaped}","{settings_str}","{task.status}","{task.output_path or ""}"\n')
                QMessageBox.information(self, "Thành công", f"Đã export {len(self.all_tasks)} records")
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", f"Không thể export: {e}")
    
    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Lỗi", "Chọn record để xóa")
            return
        
        task_id = self.table.item(row, 0).data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "Xác nhận", "Xóa record này?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.history_manager.delete_history(task_id)
            self.refresh()
    
    def _clear_all(self):
        if not self.all_tasks:
            return
        
        reply = QMessageBox.question(
            self, "Xác nhận", 
            f"Xóa tất cả {len(self.all_tasks)} records?\n(Không xóa file video)",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for task in self.all_tasks:
                self.history_manager.delete_history(task.id)
            self.refresh()
