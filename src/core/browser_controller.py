"""Browser Controller - Simple undetected ChromeDriver (cross-platform)"""
import time
import os
import sys
import subprocess
import logging
import platform
from typing import Optional
from pathlib import Path
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

LOGIN_URL = "https://accounts.x.ai/sign-in?redirect=grok-com&email=true"

# Window position counter
_window_index = 0

# Lazy-init flag for chromedriver
_chromedriver_installed = False


def _get_profiles_dir() -> Path:
    """Get profiles directory — absolute path cạnh exe."""
    from .paths import data_path
    return data_path("profiles")


def _detect_chrome_version_windows() -> Optional[int]:
    """Detect Chrome version on Windows via registry or file version."""
    try:
        import winreg
        # Try HKLM first (system-wide install), then HKCU (user install)
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for subkey in [
                r"SOFTWARE\Google\Chrome\BLBeacon",
                r"SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome",
            ]:
                try:
                    key = winreg.OpenKey(hive, subkey)
                    version_str, _ = winreg.QueryValueEx(key, "version")
                    winreg.CloseKey(key)
                    major = int(version_str.split('.')[0])
                    logger.info(f"[BROWSER] Chrome version (registry): {major} ({version_str})")
                    return major
                except (FileNotFoundError, OSError, ValueError):
                    continue
    except ImportError:
        pass  # Not on Windows

    # Fallback: try running chrome.exe --version
    chrome_paths_win = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for chrome_path in chrome_paths_win:
        if os.path.exists(chrome_path):
            try:
                result = subprocess.run(
                    [chrome_path, '--version'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    version_str = result.stdout.strip().split()[-1]
                    major = int(version_str.split('.')[0])
                    logger.info(f"[BROWSER] Chrome version (exe): {major} ({version_str})")
                    return major
            except Exception:
                continue
    return None


def _detect_chrome_version_mac() -> Optional[int]:
    """Detect Chrome version on macOS."""
    try:
        result = subprocess.run(
            ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            version_str = result.stdout.strip().split()[-1]
            major = int(version_str.split('.')[0])
            logger.info(f"[BROWSER] Chrome version (macOS): {major}")
            return major
    except Exception:
        pass
    return None


def _detect_chrome_version_linux() -> Optional[int]:
    """Detect Chrome version on Linux."""
    for cmd in ['google-chrome', 'google-chrome-stable', 'chromium-browser', 'chromium']:
        try:
            result = subprocess.run(
                [cmd, '--version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version_str = result.stdout.strip().split()[-1]
                major = int(version_str.split('.')[0])
                logger.info(f"[BROWSER] Chrome version (Linux): {major}")
                return major
        except Exception:
            continue
    return None


def detect_chrome_version() -> int:
    """Detect installed Chrome version — cross-platform.
    Returns major version number, or 131 as fallback."""
    system = platform.system()
    version = None

    if system == "Windows":
        version = _detect_chrome_version_windows()
    elif system == "Darwin":
        version = _detect_chrome_version_mac()
    elif system == "Linux":
        version = _detect_chrome_version_linux()

    if version:
        return version

    logger.warning("[BROWSER] Could not detect Chrome version, using fallback 131")
    return 131


def _ensure_chromedriver():
    """Install chromedriver if needed — called once at runtime, not import time."""
    global _chromedriver_installed
    if _chromedriver_installed:
        return

    try:
        import chromedriver_autoinstaller
        chromedriver_autoinstaller.install()
        logger.info("[BROWSER] chromedriver installed/verified via autoinstaller")
    except Exception as e:
        logger.warning(f"[BROWSER] chromedriver_autoinstaller failed: {e}")

    _chromedriver_installed = True



class BrowserController:
    def __init__(self, fingerprint_id: str):
        self.fingerprint_id = fingerprint_id
        self.driver = None
        self.profile_dir = _get_profiles_dir() / fingerprint_id

    def open_browser(self, headless: bool = False, small_window: bool = True):
        """Open Chrome browser — cross-platform, Nuitka-safe."""
        import undetected_chromedriver as uc

        global _window_index

        # Ensure chromedriver is available (lazy init)
        _ensure_chromedriver()

        # Create profile directory
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        profile_path = str(self.profile_dir)

        # Detect Chrome version — cross-platform
        chrome_version = detect_chrome_version()
        logger.info(f"[BROWSER] Profile: {self.fingerprint_id}, Chrome: {chrome_version}, Headless: {headless}")

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(f"[BROWSER] Creating driver (attempt {attempt + 1}/{max_retries})...")

                options = uc.ChromeOptions()
                options.add_argument("--no-first-run")
                options.add_argument("--no-service-autorun")
                options.add_argument("--password-store=basic")
                options.add_argument("--disable-popup-blocking")

                if headless:
                    options.add_argument("--disable-gpu")
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                elif small_window:
                    options.add_argument("--window-size=400,300")
                    options.add_argument("--window-position=0,0")

                # Nuitka-safe: set driver_executable_path to None to let uc find/download it
                # Also set browser_executable_path to None for auto-detection
                self.driver = uc.Chrome(
                    options=options,
                    user_data_dir=profile_path,
                    version_main=chrome_version,
                    headless=headless,
                    driver_executable_path=None,  # Let uc handle it
                )

                time.sleep(3)

                if self.driver:
                    try:
                        url = self.driver.current_url
                        logger.info(f"[BROWSER] Ready! URL: {url}")
                        break
                    except Exception as e:
                        logger.error(f"[BROWSER] Driver test failed: {e}")
                        last_error = e
                        if attempt < max_retries - 1:
                            try:
                                self.driver.quit()
                            except Exception:
                                pass
                            self.driver = None
                            time.sleep(2)
                            continue

            except Exception as e:
                logger.error(f"[BROWSER] Driver creation failed (attempt {attempt + 1}): {e}")
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(3)

        if not self.driver:
            error_msg = f"Failed to create browser after {max_retries} attempts: {last_error}"
            logger.error(f"[BROWSER] {error_msg}")
            # Write to crash.log for debugging
            try:
                crash_path = Path("crash.log")
                with open(crash_path, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().isoformat()}] BROWSER LAUNCH FAILED\n")
                    f.write(f"  Chrome version: {chrome_version}\n")
                    f.write(f"  Profile: {profile_path}\n")
                    f.write(f"  Headless: {headless}\n")
                    f.write(f"  Error: {last_error}\n")
                    f.write(f"  Platform: {platform.system()} {platform.release()}\n")
                    f.write(f"  Python: {sys.version}\n")
                    f.write(f"  CWD: {os.getcwd()}\n")
                    import traceback
                    f.write(f"  Traceback: {traceback.format_exc()}\n")
            except Exception:
                pass
            raise Exception(error_msg)

        # Set window position
        if small_window and self.driver and not headless:
            try:
                offset = (_window_index % 5) * 10
                self.driver.set_window_position(offset, offset)
                self.driver.set_window_size(400, 300)
                _window_index += 1
            except Exception:
                pass

        logger.info("[BROWSER] Browser opened successfully!")
        return self.driver

    def navigate_to(self, url: str, wait_time: int = 5) -> None:
        if self.driver:
            logger.info(f"[NAV] Navigating to: {url}")
            self.driver.get(url)
            time.sleep(wait_time)
            current_url = self.driver.current_url
            logger.info(f"[NAV] Current URL: {current_url}")
            self._debug_screenshot("after_navigate")

    def fill_input(self, selector: str, value: str, by: str = By.CSS_SELECTOR) -> None:
        if self.driver:
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((by, selector))
            )
            element.clear()
            element.send_keys(value)

    def click_button(self, selector: str, by: str = By.CSS_SELECTOR) -> None:
        if self.driver:
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((by, selector))
            )
            element.click()

    def wait_for_element(self, selector: str, timeout: int = 30, by: str = By.CSS_SELECTOR) -> bool:
        if self.driver:
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, selector))
                )
                return True
            except Exception:
                return False
        return False

    def get_cookies(self) -> dict:
        """Lấy cookies từ TẤT CẢ domains qua CDP (không chỉ domain hiện tại).
        
        Selenium driver.get_cookies() chỉ trả cookies của domain hiện tại.
        Khi browser ở grok.com, sẽ KHÔNG thấy cookies sso/sso-rw từ .x.ai.
        CDP Network.getAllCookies trả về cookies cross-domain.
        """
        if self.driver:
            try:
                # CDP lấy ALL cookies từ mọi domain (bao gồm .x.ai, .x.com, .grok.com)
                result = self.driver.execute_cdp_cmd('Network.getAllCookies', {})
                all_cookies = result.get('cookies', [])
                
                # Chỉ lấy cookies từ các domain liên quan
                relevant_domains = ['.x.ai', 'x.ai', '.grok.com', 'grok.com', '.x.com', 'x.com', 'accounts.x.ai']
                cookies = {}
                for c in all_cookies:
                    domain = c.get('domain', '')
                    if any(domain.endswith(d) or domain == d for d in relevant_domains):
                        cookies[c['name']] = c['value']
                
                logger.info(f"[COOKIES] CDP getAllCookies: {len(all_cookies)} total, {len(cookies)} relevant. Keys: {list(cookies.keys())}")
                return cookies
            except Exception as e:
                logger.warning(f"[COOKIES] CDP getAllCookies failed, fallback to driver.get_cookies(): {e}")
                # Fallback về cách cũ nếu CDP fail
                cookies = self.driver.get_cookies()
                return {c['name']: c['value'] for c in cookies}
        return {}

    def set_cookies(self, cookies: dict, domain: str = ".grok.com") -> None:
        if self.driver:
            for name, value in cookies.items():
                try:
                    self.driver.add_cookie({
                        'name': name,
                        'value': str(value),
                        'domain': domain,
                        'path': '/'
                    })
                except Exception as e:
                    logger.warning(f"[COOKIES] Cookie error {name}: {e}")

    def close_browser(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def get_current_url(self) -> str:
        if self.driver:
            try:
                return self.driver.current_url
            except Exception:
                return ""
        return ""

    def get_page_source(self) -> str:
        if self.driver:
            try:
                return self.driver.page_source
            except Exception:
                return ""
        return ""

    def find_element(self, selector: str, by: str = By.CSS_SELECTOR):
        if self.driver:
            try:
                return self.driver.find_element(by, selector)
            except Exception:
                return None
        return None

    def find_elements(self, selector: str, by: str = By.CSS_SELECTOR):
        if self.driver:
            try:
                return self.driver.find_elements(by, selector)
            except Exception:
                return []
        return []

    def execute_script(self, script: str, *args):
        if self.driver:
            try:
                return self.driver.execute_script(script, *args)
            except Exception:
                return None
        return None

    def send_keys(self, keys: str) -> None:
        if self.driver:
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(self.driver)
            actions.send_keys(keys)
            actions.perform()

    def screenshot(self, filename: str = "screenshot.png") -> str:
        if self.driver:
            from .paths import data_path
            path = data_path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.driver.save_screenshot(str(path))
            logger.info(f"[SCREENSHOT] Saved: {path}")
            return str(path)
        return ""

    def _debug_screenshot(self, prefix: str = "debug") -> str:
        if self.driver:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"debug_{prefix}_{timestamp}.png"
            return self.screenshot(filename)
        return ""

    def debug_page_info(self) -> dict:
        info = {
            "url": "", "title": "", "cookies_count": 0,
            "page_length": 0, "has_cf_challenge": False, "has_turnstile": False,
        }
        if self.driver:
            try:
                info["url"] = self.driver.current_url
                info["title"] = self.driver.title
                cookies = self.get_cookies()
                info["cookies_count"] = len(cookies)
                info["has_cf_clearance"] = "cf_clearance" in cookies
                page_source = self.driver.page_source
                info["page_length"] = len(page_source)
                info["has_cf_challenge"] = "Just a moment" in page_source or "Checking your browser" in page_source
                info["has_turnstile"] = "turnstile" in page_source.lower() or "challenges.cloudflare.com" in page_source
            except Exception as e:
                logger.error(f"[DEBUG] Error getting page info: {e}")
        return info

    def handle_turnstile(self, timeout: int = 60) -> bool:
        if not self.driver:
            return False

        logger.info(f"[TURNSTILE] Starting turnstile handler (timeout={timeout}s)")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                turnstile_selectors = [
                    'iframe[src*="challenges.cloudflare.com"]',
                    'iframe[src*="turnstile"]',
                    '#cf-turnstile-response',
                    '.cf-turnstile',
                ]

                turnstile_found = False
                for selector in turnstile_selectors:
                    elements = self.find_elements(selector)
                    if elements:
                        turnstile_found = True
                        break

                if not turnstile_found:
                    logger.info("[TURNSTILE] No turnstile found - challenge passed!")
                    return True

                try:
                    iframes = self.driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="challenges.cloudflare.com"]')
                    if iframes:
                        self.driver.switch_to.frame(iframes[0])
                        checkbox = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]')
                        if checkbox:
                            checkbox[0].click()
                        self.driver.switch_to.default_content()
                except Exception:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass

                time.sleep(2)

            except Exception as e:
                logger.error(f"[TURNSTILE] Error: {e}")
                time.sleep(1)

        logger.warning("[TURNSTILE] Timeout - challenge not passed")
        return False

    def refresh_cf_clearance(self, timeout: int = 60) -> Optional[str]:
        """Refresh cf_clearance by navigating to grok.com."""
        if not self.driver:
            return None

        logger.info("[CF] Starting cf_clearance refresh...")

        try:
            self.driver.get("https://grok.com")
        except Exception as e:
            logger.error(f"[CF] Navigation error: {e}")

        start_time = time.time()
        check_count = 0

        while time.time() - start_time < timeout:
            check_count += 1
            elapsed = int(time.time() - start_time)

            try:
                page_source = self.driver.page_source

                if "Just a moment" in page_source or "Checking your browser" in page_source:
                    logger.info(f"[CF] Challenge page detected, waiting... ({elapsed}s)")
                    if check_count % 5 == 0:
                        self._debug_screenshot(f"cf_challenge_{elapsed}s")
                    self.handle_turnstile(timeout=5)
                    time.sleep(2)
                    continue

                cookies = self.get_cookies()
                cf_clearance = cookies.get('cf_clearance')

                if cf_clearance:
                    logger.info(f"[CF] SUCCESS! Got cf_clearance: {cf_clearance[:30]}...")
                    return cf_clearance

                time.sleep(2)

            except Exception as e:
                logger.error(f"[CF] Error during check: {e}")
                time.sleep(1)

        logger.error(f"[CF] FAILED to get cf_clearance after {timeout}s")
        return None
