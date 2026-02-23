"""History Tab - Modern UI with Dark/Light Theme"""
import os
import subprocess
import sys
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox, QLabel, QFrame,
    QLineEdit, QComboBox, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from ..core.history_manager import HistoryManager
from ..core.video_generator import VideoGenerator


class DownloadWorker(QThread):
    status_update = Signal(str)
    finished = Signal(str, str)
    
    def __init__(self, task_id, post_id, email, prompt, cookies=None):
        super().__init__()
        self.task_id = task_id
        self.post_id = post_id
        self.email = email
        self.prompt = prompt
        self.cookies = cookies  # Account cookies for authentication
    
    def run(self):
        try:
            output_path = self._download_sync()
            self.finished.emit(self.task_id, output_path or "")
        except Exception as e:
            self.status_update.emit(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self.finished.emit(self.task_id, "")
    
    def _download_sync(self):
        """
        Download video using zendriver browser with CDP download behavior.
        
        Strategy:
        1. Open browser and navigate to video URL
        2. Set CDP download behavior to allow downloads
        3. Navigate to video URL with dl=1 to trigger download
        """
        import asyncio
        return asyncio.run(self._download_async())
    
    async def _download_async(self):
        """Async download using zendriver"""
        import zendriver
        from zendriver import cdp
        from ..core.cf_solver import get_chrome_user_agent
        from ..core.video_generator import OUTPUT_DIR, VIDEO_DOWNLOAD_URL
        import os
        import glob
        
        video_url = VIDEO_DOWNLOAD_URL.format(post_id=self.post_id)
        user_agent = get_chrome_user_agent()
        
        self.status_update.emit("🔄 Starting browser for download...")
        
        # Create browser
        config = zendriver.Config(headless=True)
        config.add_argument(f"--user-agent={user_agent}")
        
        browser = zendriver.Browser(config)
        await browser.start()
        
        try:
            # Step 1: Inject cookies
            self.status_update.emit("🍪 Injecting cookies...")
            await browser.main_tab.get("https://grok.com/favicon.ico")
            await asyncio.sleep(1)
            
            if self.cookies:
                for name, value in self.cookies.items():
                    try:
                        await browser.main_tab.send(
                            cdp.network.set_cookie(
                                name=name,
                                value=value,
                                domain=".grok.com",
                                path="/",
                                secure=True,
                                http_only=name in ['sso', 'sso-rw'],
                            )
                        )
                    except:
                        pass
            
            # Step 2: Navigate to video URL to get __cf_bm cookie
            self.status_update.emit("🌐 Getting download cookie...")
            await browser.get(video_url, new_tab=True)
            await asyncio.sleep(5)
            
            # Step 3: Set download behavior
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            await browser.main_tab.send(cdp.browser.set_download_behavior(
                behavior="allow",
                download_path=str(OUTPUT_DIR.absolute())
            ))
            
            # Step 4: Navigate to download URL
            download_url = f"{video_url}&dl=1" if '?' in video_url else f"{video_url}?dl=1"
            self.status_update.emit("📥 Downloading video...")
            await browser.main_tab.get(download_url)
            
            # Wait for download to complete
            for i in range(60):  # Max 5 minutes
                await asyncio.sleep(5)
                
                # Check for downloaded file
                mp4_files = glob.glob(str(OUTPUT_DIR / "*.mp4"))
                if mp4_files:
                    newest = max(mp4_files, key=os.path.getctime)
                    size = os.path.getsize(newest)
                    
                    # Check if download is complete (file size stable)
                    if size > 10000:
                        await asyncio.sleep(2)
                        new_size = os.path.getsize(newest)
                        if new_size == size:  # Size stable = download complete
                            size_mb = size / (1024 * 1024)
                            self.status_update.emit(f"✅ Downloaded: {os.path.basename(newest)} ({size_mb:.1f} MB)")
                            return newest
                
                if i % 6 == 0:
                    self.status_update.emit(f"⏳ Downloading... ({i * 5}s)")
            
            self.status_update.emit("❌ Download timeout")
            return None
            
        except Exception as e:
            self.status_update.emit(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            await browser.stop()


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


class StatCard(QFrame):
    def __init__(self, title, value="0", color="#3498db"):
        super().__init__()
        self.color = color
        self.is_dark = True
        self._setup_ui(title)
        self._apply_style()
    
    def _setup_ui(self, title):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(4)
        
        self.value_label = QLabel("0")
        self.value_label.setFont(QFont("Segoe UI", 22, QFont.Bold))
        self.value_label.setAlignment(Qt.AlignCenter)
        
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Segoe UI", 10))
        self.title_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)
    
    def set_dark(self, dark):
        self.is_dark = dark
        self._apply_style()
    
    def _apply_style(self):
        if self.is_dark:
            self.setStyleSheet(f"""
                StatCard {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(30, 40, 60, 200), stop:1 rgba(40, 50, 70, 200));
                    border: 1px solid {self.color};
                    border-radius: 10px;
                }}
            """)
            self.value_label.setStyleSheet(f"color: {self.color};")
            self.title_label.setStyleSheet("color: white;")
        else:
            self.setStyleSheet(f"""
                StatCard {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(255, 255, 255, 230), stop:1 rgba(245, 248, 255, 230));
                    border: 1px solid {self.color};
                    border-radius: 10px;
                }}
            """)
            self.value_label.setStyleSheet(f"color: {self.color};")
            self.title_label.setStyleSheet("color: #333;")
    
    def set_value(self, value):
        self.value_label.setText(str(value))


class HistoryTab(QWidget):
    def __init__(self, history_manager: HistoryManager):
        super().__init__()
        self.history_manager = history_manager
        self.download_workers = {}
        self.all_tasks = []
        self.is_dark = True
        self._setup_ui()
        self.refresh()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Stats
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        
        self.stat_total = StatCard("📊 Total", "0", "#3498db")
        self.stat_completed = StatCard("✅ Success", "0", "#27ae60")
        self.stat_failed = StatCard("❌ Failed", "0", "#e74c3c")
        self.stat_today = StatCard("📅 Today", "0", "#9b59b6")
        
        for stat in [self.stat_total, self.stat_completed, self.stat_failed, self.stat_today]:
            stat.setFixedHeight(70)
            stats_layout.addWidget(stat)
        
        layout.addLayout(stats_layout)
        
        # Filter card
        filter_card = GlassFrame()
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(15, 12, 15, 12)
        filter_layout.setSpacing(12)
        
        self.search_label = QLabel("🔍 Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Prompt or email...")
        self.search_input.textChanged.connect(self._filter_table)
        
        self.status_label = QLabel("Status:")
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Success", "Failed"])
        self.status_filter.currentIndexChanged.connect(self._filter_table)
        
        filter_layout.addWidget(self.search_label)
        filter_layout.addWidget(self.search_input, stretch=1)
        filter_layout.addWidget(self.status_label)
        filter_layout.addWidget(self.status_filter)
        
        self.filter_card = filter_card
        layout.addWidget(filter_card)
        
        # Table card
        table_card = GlassFrame()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(15, 15, 15, 15)
        table_layout.setSpacing(12)
        
        self.table_title = QLabel("📋 Video History")
        self.table_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        table_layout.addWidget(self.table_title)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Time", "Account", "Prompt", "Status", "File", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(5, 100)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)  # Enable multi-select
        self.table.doubleClicked.connect(self._open_video)
        table_layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.download_btn = QPushButton("⬇️ Download")
        self.open_btn = QPushButton("▶️ Play")
        self.folder_btn = QPushButton("📂 Folder")
        self.export_btn = QPushButton("📥 Export")
        self.select_all_btn = QPushButton("☑️ Select All")
        self.delete_btn = QPushButton("🗑️ Delete")
        
        self.refresh_btn.clicked.connect(self.refresh)
        self.download_btn.clicked.connect(self._download_selected)
        self.open_btn.clicked.connect(self._open_video)
        self.folder_btn.clicked.connect(self._open_folder)
        self.export_btn.clicked.connect(self._export_csv)
        self.select_all_btn.clicked.connect(self._toggle_select_all)
        self.delete_btn.clicked.connect(self._delete_selected)
        
        for btn in [self.refresh_btn, self.download_btn, self.open_btn, 
                    self.folder_btn, self.export_btn, self.select_all_btn, self.delete_btn]:
            btn.setCursor(Qt.PointingHandCursor)
            btn_layout.addWidget(btn)
        
        btn_layout.addStretch()
        table_layout.addLayout(btn_layout)
        
        self.status_label_bottom = QLabel("")
        table_layout.addWidget(self.status_label_bottom)
        
        self.table_card = table_card
        layout.addWidget(table_card, stretch=1)
        
        self._apply_theme()
    
    def set_dark_mode(self, is_dark):
        self.is_dark = is_dark
        self._apply_theme()
    
    def _apply_theme(self):
        for stat in [self.stat_total, self.stat_completed, self.stat_failed, self.stat_today]:
            stat.set_dark(self.is_dark)
        
        self.filter_card.set_dark(self.is_dark)
        self.table_card.set_dark(self.is_dark)
        
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
            input_style = """
                QLineEdit, QComboBox {
                    background: rgba(40, 50, 70, 200);
                    color: white;
                    border: 1px solid rgba(100, 150, 255, 80);
                    border-radius: 6px;
                    padding: 8px;
                }
            """
            btn_style = """
                QPushButton {
                    background: rgba(50, 60, 80, 200);
                    color: white;
                    border: 1px solid rgba(100, 150, 255, 80);
                    border-radius: 6px;
                    padding: 8px 14px;
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
            input_style = """
                QLineEdit, QComboBox {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 8px;
                }
            """
            btn_style = """
                QPushButton {
                    background: white;
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 6px;
                    padding: 8px 14px;
                    font-size: 12px;
                }
                QPushButton:hover { background: #f5f5f5; }
            """
        
        for label in [self.search_label, self.status_label, self.table_title, self.status_label_bottom]:
            label.setStyleSheet(f"color: {text_color};")
        
        self.table.setStyleSheet(table_style)
        self.search_input.setStyleSheet(input_style)
        self.status_filter.setStyleSheet(input_style)
        
        for btn in [self.refresh_btn, self.export_btn]:
            btn.setStyleSheet(btn_style)
        
        self.select_all_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1abc9c, stop:1 #16a085);
                color: white; border: none; border-radius: 6px; padding: 8px 14px;
            }
            QPushButton:hover { background: #16a085; }
        """)
        
        self.download_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9b59b6, stop:1 #8e44ad);
                color: white; border: none; border-radius: 6px; padding: 8px 14px;
            }
            QPushButton:hover { background: #8e44ad; }
        """)
        self.open_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #27ae60, stop:1 #2ecc71);
                color: white; border: none; border-radius: 6px; padding: 8px 14px;
            }
            QPushButton:hover { background: #2ecc71; }
        """)
        self.folder_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3498db, stop:1 #2980b9);
                color: white; border: none; border-radius: 6px; padding: 8px 14px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e74c3c, stop:1 #c0392b);
                color: white; border: none; border-radius: 6px; padding: 8px 14px;
            }
            QPushButton:hover { background: #c0392b; }
        """)

    
    def refresh(self):
        self.all_tasks = self.history_manager.get_all_history()
        self._update_table(self.all_tasks)
        self._update_stats()
    
    def _update_table(self, tasks):
        self.table.setRowCount(len(tasks))
        
        for i, task in enumerate(tasks):
            time_str = task.created_at.strftime("%m-%d %H:%M") if task.created_at else "-"
            time_item = QTableWidgetItem(time_str)
            time_item.setData(Qt.UserRole, task.id)
            self.table.setItem(i, 0, time_item)
            
            email_short = task.account_email.split('@')[0][:12]
            self.table.setItem(i, 1, QTableWidgetItem(email_short))
            
            prompt_short = task.prompt[:50] + "..." if len(task.prompt) > 50 else task.prompt
            prompt_item = QTableWidgetItem(prompt_short)
            prompt_item.setToolTip(task.prompt)
            self.table.setItem(i, 2, prompt_item)
            
            if task.status == "completed":
                status_item = QTableWidgetItem("✅")
                status_item.setBackground(QColor("#27ae60"))
            else:
                status_item = QTableWidgetItem("❌")
                status_item.setBackground(QColor("#e74c3c"))
                if task.error_message:
                    status_item.setToolTip(task.error_message)
            status_item.setForeground(QColor("white"))
            self.table.setItem(i, 3, status_item)
            
            if task.output_path and os.path.exists(task.output_path):
                file_item = QTableWidgetItem("📁 " + os.path.basename(task.output_path)[:20])
                file_item.setToolTip(task.output_path)
                file_item.setBackground(QColor("#27ae60"))
                file_item.setForeground(QColor("white"))
            else:
                file_item = QTableWidgetItem("-")
            self.table.setItem(i, 4, file_item)
            
            if task.output_path and os.path.exists(task.output_path):
                action_item = QTableWidgetItem("✅ Ready")
                action_item.setBackground(QColor("#27ae60"))
            elif task.media_url:
                action_item = QTableWidgetItem("⬇️ Download")
                action_item.setBackground(QColor("#f39c12"))
            else:
                action_item = QTableWidgetItem("-")
            action_item.setForeground(QColor("white"))
            self.table.setItem(i, 5, action_item)
    
    def _update_stats(self):
        total = len(self.all_tasks)
        completed = sum(1 for t in self.all_tasks if t.status == "completed")
        failed = sum(1 for t in self.all_tasks if t.status == "failed")
        today = datetime.now().date()
        today_count = sum(1 for t in self.all_tasks if t.created_at and t.created_at.date() == today)
        
        self.stat_total.set_value(total)
        self.stat_completed.set_value(completed)
        self.stat_failed.set_value(failed)
        self.stat_today.set_value(today_count)
    
    def _filter_table(self):
        search = self.search_input.text().lower()
        status = self.status_filter.currentText()
        
        filtered = []
        for task in self.all_tasks:
            if search and search not in task.prompt.lower() and search not in task.account_email.lower():
                continue
            if status == "Success" and task.status != "completed":
                continue
            if status == "Failed" and task.status != "failed":
                continue
            filtered.append(task)
        
        self._update_table(filtered)
    
    def _open_folder(self):
        from ..core.paths import output_path
        output_dir = str(output_path())
        os.makedirs(output_dir, exist_ok=True)
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
        path_item = self.table.item(row, 4)
        if path_item:
            file_path = path_item.toolTip()
            if file_path and os.path.exists(file_path):
                if sys.platform == "darwin":
                    subprocess.run(["open", file_path])
                elif sys.platform == "win32":
                    subprocess.run(["start", "", file_path], shell=True)
                else:
                    subprocess.run(["xdg-open", file_path])
    
    def _export_csv(self):
        if not self.all_tasks:
            QMessageBox.information(self, "Info", "No data to export")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "history.csv", "CSV (*.csv)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("Time,Account,Prompt,Status,File\n")
                    for task in self.all_tasks:
                        time_str = task.created_at.strftime("%Y-%m-%d %H:%M") if task.created_at else ""
                        prompt = task.prompt.replace('"', '""')
                        f.write(f'"{time_str}","{task.account_email}","{prompt}","{task.status}","{task.output_path or ""}"\n')
                QMessageBox.information(self, "Success", f"Exported {len(self.all_tasks)} records")
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
    
    def _delete_selected(self):
        """Delete multiple selected records"""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Error", "Select records to delete")
            return
        
        # Get all task IDs from selected rows
        task_ids = []
        for index in selected_rows:
            row = index.row()
            item = self.table.item(row, 0)
            if item:
                task_id = item.data(Qt.UserRole)
                if task_id:
                    task_ids.append(task_id)
        
        if not task_ids:
            return
        
        # Confirmation dialog
        count = len(task_ids)
        msg = f"Delete {count} record{'s' if count > 1 else ''}?"
        if QMessageBox.question(self, "Confirm Delete", msg, 
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            # Delete all selected records
            deleted = 0
            for task_id in task_ids:
                try:
                    self.history_manager.delete_history(task_id)
                    deleted += 1
                except Exception as e:
                    print(f"Error deleting {task_id}: {e}")
            
            self.status_label_bottom.setText(f"🗑️ Deleted {deleted} record{'s' if deleted > 1 else ''}")
            self.refresh()
    
    def _toggle_select_all(self):
        """Toggle select all / deselect all"""
        if self.table.selectionModel().selectedRows():
            # If any rows selected, deselect all
            self.table.clearSelection()
            self.select_all_btn.setText("☑️ Select All")
        else:
            # Select all rows
            self.table.selectAll()
            self.select_all_btn.setText("☐ Deselect")
    
    def _download_selected(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Error", "Select a video to download")
            return
        task_id = self.table.item(row, 0).data(Qt.UserRole)
        task = next((t for t in self.all_tasks if t.id == task_id), None)
        if not task:
            return
        if task.output_path and os.path.exists(task.output_path):
            QMessageBox.information(self, "Info", "Video already downloaded")
            return
        if not task.media_url:
            QMessageBox.warning(self, "Error", "No URL available")
            return
        self._start_download(task)
    
    def _start_download(self, task):
        if task.id in self.download_workers:
            return
        
        # Extract post_id from media_url or use post_id directly
        post_id = task.post_id
        if not post_id and task.media_url:
            import re
            match = re.search(r'/([a-f0-9-]{36})\.mp4', task.media_url)
            if match:
                post_id = match.group(1)
        
        if not post_id:
            QMessageBox.warning(self, "Error", "No post ID available")
            return
        
        # Get cookies from task (saved during generation)
        cookies = task.account_cookies
        
        worker = DownloadWorker(task.id, post_id, task.account_email, task.prompt, cookies)
        worker.status_update.connect(lambda msg: self.status_label_bottom.setText(f"⬇️ {msg}"))
        worker.finished.connect(self._on_download_done)
        self.download_workers[task.id] = worker
        worker.start()
        self.status_label_bottom.setText(f"⬇️ Downloading: {task.prompt[:30]}...")
    
    def _on_download_done(self, task_id, output_path):
        if task_id in self.download_workers:
            del self.download_workers[task_id]
        if output_path:
            self.history_manager.update_output_path(task_id, output_path)
            self.status_label_bottom.setText(f"✅ Downloaded: {os.path.basename(output_path)}")
        else:
            self.status_label_bottom.setText("❌ Download failed")
        self.refresh()
