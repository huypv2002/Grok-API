"""App Login Dialog - Xác thực qua D1 API, lưu login_temp.json, animation tinh hà 3D"""
import json
import math
import random
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QPointF, QThread, Signal
from PySide6.QtGui import QFont, QPainter, QLinearGradient, QRadialGradient, QColor, QPen

LOGIN_TEMP_FILE = Path("data/login_temp.json")
AUTH_API_URL = "https://grok-auth-api.kh431248.workers.dev/login"


class AuthWorker(QThread):
    """Worker xác thực qua D1 API."""
    finished = Signal(bool, str)

    def __init__(self, username, password):
        super().__init__()
        self.username = username
        self.password = password

    def run(self):
        import httpx
        try:
            r = httpx.post(AUTH_API_URL, json={
                "username": self.username,
                "password": self.password
            }, timeout=10)
            data = r.json()
            if data.get("ok"):
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, data.get("error", "Sai tài khoản hoặc mật khẩu"))
        except Exception as e:
            self.finished.emit(False, f"Lỗi kết nối: {e}")


class _Star:
    def __init__(self, x, y, size, speed, color, is_galaxy=False):
        self.x, self.y = x, y
        self.z = 1.0
        self.size, self.speed = size, speed
        self.color = color
        self.angle = random.uniform(0, math.pi * 2)
        self.is_galaxy = is_galaxy
        self.rotation = 0

    def update(self, w, h):
        self.angle += self.speed * 0.012
        self.x += math.sin(self.angle) * 0.5
        self.y += math.cos(self.angle * 0.6) * 0.3
        self.z = 0.4 + 0.6 * math.sin(self.angle * 0.35)
        if self.is_galaxy:
            self.rotation += self.speed * 0.4
        if self.x < -30: self.x = w + 30
        if self.x > w + 30: self.x = -30
        if self.y < -30: self.y = h + 30
        if self.y > h + 30: self.y = -30


class AppLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔐 Đăng nhập")
        self.setFixedSize(460, 400)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._worker = None

        # Particles
        self._stars = []
        self._init_stars()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

        self._setup_ui()
        self._load_temp()

    def _init_stars(self):
        w, h = 460, 400
        for _ in range(25):
            s = _Star(
                random.randint(0, w), random.randint(0, h),
                random.uniform(0.8, 2.5), random.uniform(0.3, 1.2),
                QColor(180, 210, 255, random.randint(50, 140))
            )
            self._stars.append(s)
        for _ in range(3):
            colors = [QColor(140, 90, 190, 35), QColor(90, 140, 210, 35), QColor(170, 110, 170, 35)]
            s = _Star(
                random.randint(50, w - 50), random.randint(50, h - 50),
                random.uniform(12, 28), random.uniform(0.15, 0.6),
                random.choice(colors), True
            )
            self._stars.append(s)

    def _tick(self):
        for s in self._stars:
            s.update(self.width(), self.height())
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, QColor(5, 8, 18))
        g.setColorAt(0.3, QColor(10, 15, 30))
        g.setColorAt(0.7, QColor(8, 12, 25))
        g.setColorAt(1, QColor(12, 18, 35))
        p.fillRect(self.rect(), g)

        for s in self._stars:
            sz = s.size * s.z
            alpha = int(s.color.alpha() * s.z)
            alpha = max(0, min(255, alpha))
            col = QColor(s.color.red(), s.color.green(), s.color.blue(), alpha)

            if s.is_galaxy:
                p.save()
                p.translate(s.x, s.y)
                p.rotate(s.rotation)
                core = QRadialGradient(0, 0, sz * 1.5)
                core.setColorAt(0, col)
                core.setColorAt(0.3, QColor(col.red(), col.green(), col.blue(), alpha // 2))
                core.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
                p.setBrush(core)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(0, 0), sz * 1.5, sz * 0.8)
                arm_col = QColor(col.red(), col.green(), col.blue(), alpha // 3)
                p.setPen(QPen(arm_col, 1))
                for arm in range(2):
                    off = arm * math.pi
                    for i in range(15):
                        t = i / 15.0 * math.pi * 2
                        r = sz * 0.3 + t * sz * 0.12
                        px = math.cos(t + off) * r
                        py = math.sin(t + off) * r * 0.5
                        ds = 1 + (1 - i / 15.0) * 1.5
                        p.setBrush(arm_col)
                        p.drawEllipse(QPointF(px, py), ds, ds)
                p.restore()
            else:
                glow = QRadialGradient(s.x, s.y, sz * 3)
                glow.setColorAt(0, QColor(col.red(), col.green(), col.blue(), alpha // 2))
                glow.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
                p.setBrush(glow)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(s.x, s.y), sz * 3, sz * 3)
                p.setBrush(col)
                p.drawEllipse(QPointF(s.x, s.y), sz, sz)

        # Nebula
        if self._stars:
            for i in range(2):
                cx = self.width() * (i + 1) / 3
                cy = self.height() / 2 + math.sin(self._stars[0].angle + i) * 30
                neb = QRadialGradient(cx, cy, 100)
                neb.setColorAt(0, QColor(100, 50, 150, 12))
                neb.setColorAt(0.5, QColor(50, 100, 150, 6))
                neb.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(neb)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(cx, cy), 100, 70)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(50, 25, 50, 25)

        icon = QLabel("🎬")
        icon.setFont(QFont("Arial", 36))
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("background: transparent;")
        layout.addWidget(icon)

        title = QLabel("Đăng nhập")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; background: transparent;")
        layout.addWidget(title)

        sub = QLabel("Grok Video Generator")
        sub.setFont(QFont("Arial", 10))
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: rgba(255,255,255,0.45); background: transparent;")
        layout.addWidget(sub)

        layout.addSpacing(10)

        inp = """
            QLineEdit {
                background: rgba(25, 35, 55, 220);
                color: white;
                border: 1px solid rgba(100, 150, 255, 70);
                border-radius: 8px;
                padding: 12px 14px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid rgba(100, 150, 255, 180); }
        """

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("👤 Tên đăng nhập")
        self.username_input.setStyleSheet(inp)
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("🔒 Mật khẩu")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet(inp)
        self.password_input.returnPressed.connect(self._on_login)
        layout.addWidget(self.password_input)

        layout.addSpacing(6)

        self.login_btn = QPushButton("🔑 Đăng nhập")
        self.login_btn.setFixedHeight(44)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setFont(QFont("Arial", 13, QFont.Bold))
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3498db, stop:1 #2980b9);
                color: white; border: none; border-radius: 8px;
            }
            QPushButton:hover { background: #2980b9; }
            QPushButton:pressed { background: #2471a3; }
            QPushButton:disabled { background: #555; color: #999; }
        """)
        self.login_btn.clicked.connect(self._on_login)
        layout.addWidget(self.login_btn)

        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #e74c3c; background: transparent; font-size: 11px;")
        layout.addWidget(self.error_label)

        layout.addStretch()

    def _load_temp(self):
        """Load tk/mk từ login_temp.json nếu có → tự fill."""
        if LOGIN_TEMP_FILE.exists():
            try:
                data = json.loads(LOGIN_TEMP_FILE.read_text())
                self.username_input.setText(data.get("username", ""))
                self.password_input.setText(data.get("password", ""))
            except Exception:
                pass

    def _save_temp(self, username, password):
        """Lưu tk/mk plain text vào login_temp.json."""
        LOGIN_TEMP_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOGIN_TEMP_FILE.write_text(json.dumps({
            "username": username,
            "password": password
        }, indent=2))

    def _on_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            self.error_label.setText("Vui lòng nhập đầy đủ thông tin")
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("⏳ Đang xác thực...")
        self.error_label.setText("")

        self._worker = AuthWorker(username, password)
        self._worker.finished.connect(lambda ok, err: self._on_auth_done(ok, err, username, password))
        self._worker.start()

    def _on_auth_done(self, ok, error, username, password):
        self.login_btn.setEnabled(True)
        self.login_btn.setText("🔑 Đăng nhập")

        if ok:
            self._save_temp(username, password)
            self.accept()
        else:
            self.error_label.setText(f"❌ {error}")
            self.password_input.selectAll()
            self.password_input.setFocus()
