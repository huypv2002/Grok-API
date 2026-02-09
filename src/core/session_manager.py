"""Session Manager - Login flow and cookie management using undetected_chromedriver"""
import time
import logging
from datetime import datetime
from typing import Optional, Callable
from uuid import uuid4
from selenium.webdriver.common.by import By
from .models import Account
from .browser_controller import BrowserController, LOGIN_URL

logger = logging.getLogger(__name__)

REQUIRED_COOKIES = ['sso', 'sso-rw', 'x-userid', 'cf_clearance']

# Thời gian tối đa chờ sau khi click Login để verify redirect (giây)
LOGIN_VERIFY_TIMEOUT = 120


class SessionManager:
    def __init__(self):
        self.browser_controllers: dict[str, BrowserController] = {}

    def _wait_for_turnstile_clear(self, controller: BrowserController, on_status: Callable = None, timeout: int = 60) -> bool:
        """Chờ cho đến khi KHÔNG còn Turnstile/Cloudflare challenge trên trang.
        Return True nếu trang sạch (không còn challenge), False nếu timeout."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                page_source = controller.get_page_source()
                current_url = controller.get_current_url()

                # Nếu đã redirect khỏi trang login → OK
                if 'grok.com' in current_url and 'accounts.x.ai' not in current_url:
                    return True

                # Check Turnstile iframe
                has_turnstile = False
                iframes = controller.find_elements('iframe[src*="challenges.cloudflare.com"]')
                if iframes:
                    has_turnstile = True

                # Check "Just a moment" / "Checking your browser"
                has_cf_page = (
                    'Just a moment' in page_source
                    or 'Checking your browser' in page_source
                    or 'Verify you are human' in page_source
                )

                if not has_turnstile and not has_cf_page:
                    if on_status:
                        on_status("✅ Không còn Cloudflare challenge")
                    return True

                elapsed = int(time.time() - start)
                if on_status:
                    on_status(f"⏳ Đang chờ Cloudflare... ({elapsed}s)")

                # Thử click turnstile checkbox nếu có
                controller.handle_turnstile(timeout=5)
                time.sleep(2)

            except Exception as e:
                logger.warning(f"[LOGIN] Turnstile check error: {e}")
                time.sleep(2)

        if on_status:
            on_status("⚠️ Timeout chờ Cloudflare challenge")
        return False

    def _verify_login_success(self, controller: BrowserController, on_status: Callable = None, timeout: int = LOGIN_VERIFY_TIMEOUT) -> bool:
        """Sau khi click Login, chờ và verify đã vào được grok.com.
        Không tự đóng browser — chỉ return True/False."""
        start = time.time()
        last_url = ""

        while time.time() - start < timeout:
            try:
                current_url = controller.get_current_url()
                cookies = controller.get_cookies()
                elapsed = int(time.time() - start)

                if current_url != last_url:
                    if on_status:
                        on_status(f"🔗 URL: {current_url}")
                    last_url = current_url

                # Kiểm tra Cloudflare challenge sau login
                page_source = controller.get_page_source()
                has_cf = (
                    'Just a moment' in page_source
                    or 'Checking your browser' in page_source
                    or 'Verify you are human' in page_source
                )
                if has_cf:
                    if on_status:
                        on_status(f"⏳ Cloudflare challenge sau login... ({elapsed}s)")
                    controller.handle_turnstile(timeout=10)
                    time.sleep(3)
                    continue

                # Thành công: đã vào grok.com (không phải trang login)
                is_on_grok = (
                    'grok.com' in current_url
                    and 'accounts.x.ai' not in current_url
                    and '/sign-in' not in current_url
                )

                has_sso = 'sso' in cookies or 'sso-rw' in cookies

                if is_on_grok and has_sso:
                    if on_status:
                        on_status(f"✅ Đã vào grok.com thành công! ({elapsed}s)")
                    return True

                # Vẫn ở trang login → có thể sai password hoặc đang redirect
                if 'accounts.x.ai' in current_url or '/sign-in' in current_url:
                    # Check nếu có thông báo lỗi
                    error_texts = ['Invalid', 'incorrect', 'wrong', 'Sai', 'không đúng']
                    for err in error_texts:
                        if err.lower() in page_source.lower():
                            if on_status:
                                on_status(f"❌ Sai email/password")
                            return False

                if elapsed % 10 == 0 and on_status:
                    on_status(f"⏳ Đang chờ redirect... ({elapsed}s)")

                time.sleep(2)

            except Exception as e:
                logger.warning(f"[LOGIN] Verify error: {e}")
                time.sleep(2)

        if on_status:
            on_status(f"❌ Timeout {timeout}s — không vào được grok.com")
        return False

    def login(self, account: Account, password: str, on_status: Callable = None) -> bool:
        """Full login flow — giải captcha trước khi click, verify vào grok.com trước khi đóng browser."""
        controller = BrowserController(account.fingerprint_id)
        self.browser_controllers[account.email] = controller

        try:
            # === 1. Mở browser ===
            if on_status:
                on_status("🌐 Mở browser...")
            controller.open_browser(headless=False)

            # === 2. Navigate to login page ===
            if on_status:
                on_status("🔗 Đi đến trang đăng nhập...")
            controller.navigate_to(LOGIN_URL, wait_time=5)

            # === 3. Chờ Cloudflare trên trang login (nếu có) ===
            self._wait_for_turnstile_clear(controller, on_status, timeout=60)

            # === 4. Điền email ===
            if on_status:
                on_status("📧 Chờ form email...")
            if not controller.wait_for_element('input[name="email"]', timeout=20):
                raise Exception("Không tìm thấy ô email")

            if on_status:
                on_status(f"📧 Điền email: {account.email}")
            controller.fill_input('input[name="email"]', account.email)
            time.sleep(1)

            # === 5. Chờ Turnstile trước khi click Next ===
            if on_status:
                on_status("🔐 Check captcha trước khi Next...")
            self._wait_for_turnstile_clear(controller, on_status, timeout=60)

            # === 6. Click Next ===
            if on_status:
                on_status("➡️ Click Next...")
            controller.click_button('button[type="submit"]')
            time.sleep(3)

            # === 7. Chờ Turnstile sau khi click Next (có thể xuất hiện lại) ===
            self._wait_for_turnstile_clear(controller, on_status, timeout=60)

            # === 8. Điền password ===
            if on_status:
                on_status("🔒 Chờ ô password...")
            if not controller.wait_for_element('input[name="password"]', timeout=20):
                raise Exception("Không tìm thấy ô password")

            if on_status:
                on_status("🔒 Điền password...")
            controller.fill_input('input[name="password"]', password)
            time.sleep(1)

            # === 9. Chờ Turnstile trước khi click Login ===
            if on_status:
                on_status("🔐 Check captcha trước khi Login...")
            self._wait_for_turnstile_clear(controller, on_status, timeout=60)

            # === 10. Click Login ===
            if on_status:
                on_status("🔑 Click Login...")
            controller.click_button('button[type="submit"]')

            # === 11. VERIFY — chờ vào được grok.com rồi mới đóng browser ===
            if on_status:
                on_status("⏳ Đang verify login... (chờ vào grok.com)")

            success = self._verify_login_success(controller, on_status, timeout=LOGIN_VERIFY_TIMEOUT)

            if success:
                cookies = controller.get_cookies()
                account.cookies = cookies
                account.status = "logged_in"
                account.last_login = datetime.now()
                if on_status:
                    on_status(f"✅ Login thành công! Cookies: {len(cookies)}")
                return True
            else:
                account.status = "error"
                account.error_message = "Không vào được grok.com sau login"
                return False

        except Exception as e:
            account.status = "error"
            account.error_message = str(e)
            if on_status:
                on_status(f"❌ Lỗi: {e}")
            return False
        finally:
            # Luôn đóng browser sau khi xong
            controller.close_browser()

    def login_and_keep_open(self, account: Account, password: str, on_status: Callable = None) -> Optional[BrowserController]:
        """Login và giữ browser mở — dùng cho debug/manual."""
        controller = BrowserController(account.fingerprint_id)
        self.browser_controllers[account.email] = controller

        try:
            if on_status:
                on_status("🌐 Mở browser...")
            controller.open_browser(headless=False)

            if on_status:
                on_status("🔗 Đi đến trang đăng nhập...")
            controller.navigate_to(LOGIN_URL, wait_time=5)

            self._wait_for_turnstile_clear(controller, on_status, timeout=60)

            if on_status:
                on_status("📧 Chờ form email...")
            if not controller.wait_for_element('input[name="email"]', timeout=20):
                raise Exception("Không tìm thấy ô email")

            controller.fill_input('input[name="email"]', account.email)
            time.sleep(1)

            self._wait_for_turnstile_clear(controller, on_status, timeout=60)

            if on_status:
                on_status("➡️ Click Next...")
            controller.click_button('button[type="submit"]')
            time.sleep(3)

            self._wait_for_turnstile_clear(controller, on_status, timeout=60)

            if on_status:
                on_status("🔒 Chờ ô password...")
            if not controller.wait_for_element('input[name="password"]', timeout=20):
                raise Exception("Không tìm thấy ô password")

            controller.fill_input('input[name="password"]', password)
            time.sleep(1)

            self._wait_for_turnstile_clear(controller, on_status, timeout=60)

            if on_status:
                on_status("🔑 Click Login...")
            controller.click_button('button[type="submit"]')

            if on_status:
                on_status("⏳ Đang verify login...")

            success = self._verify_login_success(controller, on_status, timeout=LOGIN_VERIFY_TIMEOUT)

            if success:
                cookies = controller.get_cookies()
                account.cookies = cookies
                account.status = "logged_in"
                account.last_login = datetime.now()
                if on_status:
                    on_status("✅ Login thành công! Browser giữ mở.")
                return controller

            account.status = "error"
            account.error_message = "Không vào được grok.com sau login"
            controller.close_browser()
            return None

        except Exception as e:
            account.status = "error"
            account.error_message = str(e)
            if on_status:
                on_status(f"❌ Lỗi: {e}")
            controller.close_browser()
            return None

    def extract_cookies(self, cookies: dict) -> dict:
        """Extract important cookies"""
        return {k: v for k, v in cookies.items() if k in REQUIRED_COOKIES}

    def is_session_valid(self, account: Account) -> bool:
        """Check if account has valid cookies"""
        if not account.cookies:
            return False
        required = set(REQUIRED_COOKIES)
        return required.issubset(set(account.cookies.keys()))

    def get_headers(self, account: Account) -> dict:
        """Generate headers for API requests — uses fixed UA from cf_solver"""
        from .cf_solver import get_chrome_user_agent
        user_agent = get_chrome_user_agent()

        # Detect platform for sec-ch-ua-platform
        import platform as _platform
        sys_name = _platform.system()
        if sys_name == "Windows":
            ua_platform = '"Windows"'
        elif sys_name == "Darwin":
            ua_platform = '"macOS"'
        else:
            ua_platform = '"Linux"'

        headers = {
            'accept': '*/*',
            'accept-language': 'vi-VN,vi;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://grok.com',
            'referer': 'https://grok.com/imagine',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': ua_platform,
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': user_agent,
            'x-xai-request-id': str(uuid4())
        }
        return headers

    def get_cookie_string(self, account: Account) -> str:
        """Convert cookies dict to cookie header string"""
        if not account.cookies:
            return ""
        return "; ".join([f"{k}={v}" for k, v in account.cookies.items()])
