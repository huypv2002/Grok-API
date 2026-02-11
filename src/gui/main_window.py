"""Main Window - Modern UI with 3D Animated Background"""
import json
import math
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QStatusBar, QLabel, QPushButton, QStackedWidget, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QPointF, Property, QPropertyAnimation, QThread, Signal
from PySide6.QtGui import QFont, QPainter, QLinearGradient, QRadialGradient, QColor, QPen
from .account_tab import AccountTab
from .video_gen_tab import VideoGenTab
from .image_gen_tab import ImageGenTab
from .history_tab import HistoryTab
from ..core.account_manager import AccountManager
from ..core.session_manager import SessionManager
from ..core.history_manager import HistoryManager
from ..core.d1_manager import D1Manager


class Particle3D:
    """Galaxy/Star particle for animated background"""
    def __init__(self, x, y, size, speed, color, is_galaxy=False):
        self.x = x
        self.y = y
        self.z = 1.0
        self.size = size
        self.speed = speed
        self.color = color
        self.angle = 0
        self.is_galaxy = is_galaxy
        self.rotation = 0
    
    def update(self, w, h):
        self.angle += self.speed * 0.012
        self.x += math.sin(self.angle) * 0.6
        self.y += math.cos(self.angle * 0.6) * 0.4
        self.z = 0.4 + 0.6 * math.sin(self.angle * 0.35)
        if self.is_galaxy:
            self.rotation += self.speed * 0.5
        if self.x < -50: self.x = w + 50
        if self.x > w + 50: self.x = -50
        if self.y < -50: self.y = h + 50
        if self.y > h + 50: self.y = -50


class AnimatedBg(QWidget):
    """Animated 3D background widget"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.is_dark = True
        self.particles = []
        self._init_particles()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(30)
    
    def _init_particles(self):
        import random
        self.particles = []
        
        # Stars (small particles)
        for _ in range(30):
            x = random.randint(0, 1200)
            y = random.randint(0, 800)
            size = random.uniform(1, 3)
            speed = random.uniform(0.3, 1.5)
            alpha = random.randint(60, 150)
            if self.is_dark:
                color = QColor(200, 220, 255, alpha)
            else:
                color = QColor(100, 150, 220, alpha // 2)
            self.particles.append(Particle3D(x, y, size, speed, color, False))
        
        # Galaxies (larger spiral-like objects)
        for _ in range(5):
            x = random.randint(100, 1100)
            y = random.randint(100, 700)
            size = random.uniform(15, 35)
            speed = random.uniform(0.2, 0.8)
            alpha = random.randint(30, 70)
            if self.is_dark:
                # Purple/blue galaxy colors
                colors = [
                    QColor(150, 100, 200, alpha),
                    QColor(100, 150, 220, alpha),
                    QColor(180, 120, 180, alpha),
                ]
            else:
                colors = [
                    QColor(100, 80, 150, alpha // 2),
                    QColor(80, 120, 180, alpha // 2),
                ]
            color = random.choice(colors)
            self.particles.append(Particle3D(x, y, size, speed, color, True))
    
    def set_dark(self, dark):
        self.is_dark = dark
        self._init_particles()
    
    def _tick(self):
        for p in self.particles:
            p.update(self.width(), self.height())
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Deep space gradient background
        grad = QLinearGradient(0, 0, self.width(), self.height())
        if self.is_dark:
            grad.setColorAt(0, QColor(5, 8, 18))
            grad.setColorAt(0.3, QColor(10, 15, 30))
            grad.setColorAt(0.7, QColor(8, 12, 25))
            grad.setColorAt(1, QColor(12, 18, 35))
        else:
            grad.setColorAt(0, QColor(235, 240, 250))
            grad.setColorAt(0.5, QColor(225, 235, 248))
            grad.setColorAt(1, QColor(240, 245, 255))
        painter.fillRect(self.rect(), grad)
        
        # Draw particles
        for p in self.particles:
            sz = p.size * p.z
            alpha = int(p.color.alpha() * p.z)
            col = QColor(p.color.red(), p.color.green(), p.color.blue(), alpha)
            
            if p.is_galaxy:
                # Draw galaxy with spiral arms
                self._draw_galaxy(painter, p.x, p.y, sz, col, p.rotation)
            else:
                # Draw star with glow
                glow = QRadialGradient(p.x, p.y, sz * 4)
                glow.setColorAt(0, QColor(col.red(), col.green(), col.blue(), alpha // 2))
                glow.setColorAt(0.5, QColor(col.red(), col.green(), col.blue(), alpha // 4))
                glow.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
                painter.setBrush(glow)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(p.x, p.y), sz * 4, sz * 4)
                
                # Star core
                painter.setBrush(col)
                painter.drawEllipse(QPointF(p.x, p.y), sz, sz)
        
        # Draw faint nebula clouds
        if self.is_dark:
            for i in range(3):
                cx = (self.width() * (i + 1)) / 4
                cy = self.height() / 2 + math.sin(self.particles[0].angle + i) * 50
                nebula = QRadialGradient(cx, cy, 150)
                nebula.setColorAt(0, QColor(100, 50, 150, 15))
                nebula.setColorAt(0.5, QColor(50, 100, 150, 8))
                nebula.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setBrush(nebula)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(cx, cy), 150, 100)
    
    def _draw_galaxy(self, painter, x, y, size, color, rotation):
        """Draw a spiral galaxy"""
        painter.save()
        painter.translate(x, y)
        painter.rotate(rotation)
        
        # Galaxy core glow
        core_glow = QRadialGradient(0, 0, size * 1.5)
        core_glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), color.alpha()))
        core_glow.setColorAt(0.3, QColor(color.red(), color.green(), color.blue(), color.alpha() // 2))
        core_glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(core_glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, 0), size * 1.5, size * 0.8)
        
        # Spiral arms
        arm_color = QColor(color.red(), color.green(), color.blue(), color.alpha() // 3)
        painter.setPen(QPen(arm_color, 1))
        
        for arm in range(2):
            arm_offset = arm * math.pi
            for i in range(20):
                t = i / 20.0 * math.pi * 2
                r = size * 0.3 + t * size * 0.15
                px = math.cos(t + arm_offset) * r
                py = math.sin(t + arm_offset) * r * 0.5
                dot_size = 1 + (1 - i / 20.0) * 2
                painter.setBrush(arm_color)
                painter.drawEllipse(QPointF(px, py), dot_size, dot_size)
        
        painter.restore()


LOGIN_TEMP_FILE = Path("data/login_temp.json")
CHECK_API_URL = "https://grok-auth-api.kh431248.workers.dev/check"


class SubscriptionChecker(QThread):
    """Check gói qua D1 API."""
    result = Signal(bool, str, str)  # ok, plan, error_or_expires

    def __init__(self, username):
        super().__init__()
        self.username = username

    def run(self):
        import httpx
        from .login_dialog import get_machine_id
        try:
            mid = get_machine_id()
            r = httpx.post(CHECK_API_URL, json={
                "username": self.username,
                "machine_id": mid
            }, timeout=10)
            data = r.json()
            if data.get("ok"):
                self.result.emit(True, data.get("plan", ""), data.get("expires_at", ""))
            else:
                error = data.get("error", "Gói đã hết hạn")
                self.result.emit(False, "", error)
        except Exception as e:
            self.result.emit(True, "", "")  # Lỗi mạng → không block user


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 Grok Video Generator")
        self.setMinimumSize(1200, 800)
        self.is_dark = True
        self._logged_in_user = ""
        self._sub_checker = None

        # Load username từ login_temp
        if LOGIN_TEMP_FILE.exists():
            try:
                data = json.loads(LOGIN_TEMP_FILE.read_text())
                self._logged_in_user = data.get("username", "")
            except Exception:
                pass

        # Initialize managers
        self.account_manager = AccountManager()
        self.session_manager = SessionManager()
        self.history_manager = HistoryManager()
        self.d1_manager = D1Manager()

        self._setup_ui()
        self._apply_theme()

        # Subscription monitoring — check mỗi 5 phút
        self._sub_timer = QTimer()
        self._sub_timer.timeout.connect(self._check_subscription)
        self._sub_timer.start(5 * 60 * 1000)  # 5 phút
        # Check ngay lần đầu sau 3 giây
        QTimer.singleShot(3000, self._check_subscription)

    def _check_subscription(self):
        if not self._logged_in_user:
            return
        # Tránh tạo nhiều checker cùng lúc
        if self._sub_checker and self._sub_checker.isRunning():
            return
        self._sub_checker = SubscriptionChecker(self._logged_in_user)
        self._sub_checker.result.connect(self._on_sub_check)
        self._sub_checker.start()

    def _on_sub_check(self, ok, plan, expires_at):
        if not ok:
            self._sub_timer.stop()
            # Phân biệt lý do: hết hạn vs bị khóa
            reason = expires_at if expires_at else "Gói đã hết hạn hoặc tài khoản bị khóa"
            msg = QMessageBox(self)
            msg.setWindowTitle("⚠️ Gói đã hết hạn")
            msg.setText(
                f"⚠️ {reason}\n\n"
                f"Vui lòng liên hệ admin để gia hạn.\n"
                f"Ứng dụng sẽ đóng khi bạn bấm OK."
            )
            msg.setIcon(QMessageBox.Warning)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
            # Xóa login temp và thoát
            if LOGIN_TEMP_FILE.exists():
                LOGIN_TEMP_FILE.unlink()
            import os
            os._exit(0)
    
    def _setup_ui(self):
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Animated background
        self.bg = AnimatedBg(central)
        self.bg.lower()  # Đảm bảo bg nằm dưới cùng
        
        # Content container (raised above bg)
        content = QWidget()
        content.setAttribute(Qt.WA_TranslucentBackground)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 15, 20, 15)
        content_layout.setSpacing(12)
        
        # Header
        header = QHBoxLayout()
        
        self.title = QLabel("🎬 Grok Video Generator")
        self.title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        header.addWidget(self.title)
        
        header.addStretch()
        
        # Theme toggle
        self.theme_btn = QPushButton("🌙 Dark")
        self.theme_btn.setFixedSize(100, 36)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_btn)
        
        content_layout.addLayout(header)
        
        # Tab bar (custom styled)
        tab_bar = QHBoxLayout()
        tab_bar.setSpacing(8)
        
        self.tab_btns = []
        tabs_info = [
            ("👤 Tài khoản", 0),
            ("🎬 Tạo Video", 1),
            ("🖼️ Tạo Ảnh", 2),
            ("📜 Lịch sử", 3),
        ]
        
        for text, idx in tabs_info:
            btn = QPushButton(text)
            btn.setFixedHeight(40)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, i=idx: self._switch_tab(i))
            self.tab_btns.append(btn)
            tab_bar.addWidget(btn)
        
        tab_bar.addStretch()
        content_layout.addLayout(tab_bar)
        
        # Stacked widget for tabs
        self.stack = QStackedWidget()
        
        # Create tabs
        self.account_tab = AccountTab(self.account_manager, self.session_manager)
        self.video_gen_tab = VideoGenTab(self.account_manager, None, self.history_manager)
        self.image_gen_tab = ImageGenTab(self.account_manager, self.history_manager)
        self.history_tab = HistoryTab(self.history_manager)
        
        self.stack.addWidget(self.account_tab)
        self.stack.addWidget(self.video_gen_tab)
        self.stack.addWidget(self.image_gen_tab)
        self.stack.addWidget(self.history_tab)
        
        content_layout.addWidget(self.stack, stretch=1)
        
        # Status bar
        status_layout = QHBoxLayout()
        self.status_label = QLabel("✅ Sẵn sàng")
        self.account_count = QLabel()
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.account_count)
        content_layout.addLayout(status_layout)
        
        main_layout.addWidget(content)
        content.raise_()  # Đảm bảo content nằm trên bg
        
        # Ensure content is above animated background
        content.raise_()
        
        # Connect signals
        self.account_tab.account_changed.connect(self._on_account_changed)
        self.video_gen_tab.video_completed.connect(self._on_video_completed)
        self.image_gen_tab.image_completed.connect(self._on_video_completed)
        
        # Initial state
        self._switch_tab(0)
        self._update_account_count()
        
        # Status timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(3000)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.bg.setGeometry(self.centralWidget().rect())
    
    def _switch_tab(self, idx):
        self.stack.setCurrentIndex(idx)
        self._update_tab_styles()
    
    def _update_tab_styles(self):
        current = self.stack.currentIndex()
        for i, btn in enumerate(self.tab_btns):
            if i == current:
                if self.is_dark:
                    btn.setStyleSheet("""
                        QPushButton {
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #3498db, stop:1 #2980b9);
                            color: white;
                            border: none;
                            border-radius: 8px;
                            padding: 8px 20px;
                            font-weight: bold;
                            font-size: 13px;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #3498db, stop:1 #2980b9);
                            color: white;
                            border: none;
                            border-radius: 8px;
                            padding: 8px 20px;
                            font-weight: bold;
                            font-size: 13px;
                        }
                    """)
            else:
                if self.is_dark:
                    btn.setStyleSheet("""
                        QPushButton {
                            background: rgba(40, 50, 70, 180);
                            color: rgba(255, 255, 255, 0.7);
                            border: 1px solid rgba(100, 150, 255, 50);
                            border-radius: 8px;
                            padding: 8px 20px;
                            font-size: 13px;
                        }
                        QPushButton:hover {
                            background: rgba(50, 60, 80, 200);
                            color: white;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background: rgba(255, 255, 255, 200);
                            color: rgba(0, 0, 0, 0.7);
                            border: 1px solid rgba(100, 150, 200, 100);
                            border-radius: 8px;
                            padding: 8px 20px;
                            font-size: 13px;
                        }
                        QPushButton:hover {
                            background: rgba(255, 255, 255, 250);
                            color: black;
                        }
                    """)

    
    def _toggle_theme(self):
        self.is_dark = not self.is_dark
        self._apply_theme()
    
    def _apply_theme(self):
        self.bg.set_dark(self.is_dark)
        
        if self.is_dark:
            self.theme_btn.setText("🌙 Dark")
            text_color = "white"
            self.theme_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(40, 50, 70, 180);
                    color: white;
                    border: 1px solid rgba(100, 150, 255, 80);
                    border-radius: 8px;
                    font-size: 12px;
                }
                QPushButton:hover { background: rgba(50, 60, 80, 200); }
            """)
        else:
            self.theme_btn.setText("☀️ Light")
            text_color = "#333"
            self.theme_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 200);
                    color: #333;
                    border: 1px solid rgba(100, 150, 200, 100);
                    border-radius: 8px;
                    font-size: 12px;
                }
                QPushButton:hover { background: rgba(255, 255, 255, 250); }
            """)
        
        self.title.setStyleSheet(f"color: {text_color};")
        self.status_label.setStyleSheet(f"color: {text_color};")
        self.account_count.setStyleSheet(f"color: {text_color};")
        
        self._update_tab_styles()
        
        # Update child tabs
        if hasattr(self.account_tab, 'set_dark_mode'):
            self.account_tab.set_dark_mode(self.is_dark)
        if hasattr(self.video_gen_tab, 'set_dark_mode'):
            self.video_gen_tab.set_dark_mode(self.is_dark)
        if hasattr(self.image_gen_tab, 'set_dark_mode'):
            self.image_gen_tab.set_dark_mode(self.is_dark)
        if hasattr(self.history_tab, 'set_dark_mode'):
            self.history_tab.set_dark_mode(self.is_dark)
    
    def _on_account_changed(self):
        self.video_gen_tab.refresh_accounts()
        self.image_gen_tab.refresh_accounts()
        self._update_account_count()
    
    def _on_video_completed(self):
        self.history_tab.refresh()
    
    def _update_account_count(self):
        accounts = self.account_manager.get_all_accounts()
        logged_in = sum(1 for a in accounts if a.status == "logged_in")
        self.account_count.setText(f"👤 {logged_in}/{len(accounts)} tài khoản")
    
    def _update_status(self):
        workers = len(self.video_gen_tab.account_workers) if hasattr(self.video_gen_tab, 'account_workers') else 0
        img_workers = len(self.image_gen_tab.account_workers) if hasattr(self.image_gen_tab, 'account_workers') else 0
        total = workers + img_workers
        if total > 0:
            self.status_label.setText(f"🔄 Đang chạy {total} tác vụ...")
        else:
            self.status_label.setText("✅ Sẵn sàng")
    
    def closeEvent(self, event):
        if hasattr(self.video_gen_tab, '_stop_generation'):
            self.video_gen_tab._stop_generation()
        if hasattr(self.image_gen_tab, '_stop'):
            self.image_gen_tab._stop()
        self.history_manager.close()
        event.accept()
