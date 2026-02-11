"""Cloudflare Solver - Auto refresh cf_clearance cookie

Hỗ trợ Windows headless mode với anti-detection patches:
- CDP patches: navigator.webdriver, plugins, languages, platform
- WebGL vendor/renderer override
- Screen/window dimensions cho headless
- UserAgentMetadata set TRƯỚC navigation
- Chrome flags chống headless detection
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Callable

try:
    import latest_user_agents
    import user_agents
    import zendriver
    from zendriver import cdp
    from zendriver.cdp.emulation import UserAgentBrandVersion, UserAgentMetadata
    from zendriver.cdp.network import T_JSON_DICT, Cookie
    from zendriver.core.element import Element
    CF_SOLVER_AVAILABLE = True
except ImportError:
    CF_SOLVER_AVAILABLE = False

# Cache file for cf_clearance
CF_CACHE_FILE = Path("data/cf_clearance_cache.json")

# Fixed user agent — platform-aware for Windows/macOS
import platform as _platform

_CURRENT_OS = _platform.system()

def _build_fixed_user_agent() -> str:
    """Build fixed Chrome UA string matching the current OS."""
    if _CURRENT_OS == "Windows":
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
    elif _CURRENT_OS == "Darwin":
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
    else:
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"

FIXED_USER_AGENT = _build_fixed_user_agent()

# JS injection script — chạy TRƯỚC mọi page load
# Patch navigator.webdriver, plugins, languages, permissions, WebGL, etc.
_STEALTH_JS = r"""
// === navigator.webdriver ===
Object.defineProperty(navigator, 'webdriver', {get: () => false});

// === navigator.plugins — fake Chrome plugins ===
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
            {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
        ];
        plugins.length = 3;
        return plugins;
    }
});

// === navigator.languages ===
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

// === navigator.platform — match UA ===
Object.defineProperty(navigator, 'platform', {
    get: () => {
        const ua = navigator.userAgent;
        if (ua.includes('Win')) return 'Win32';
        if (ua.includes('Mac')) return 'MacIntel';
        return 'Linux x86_64';
    }
});

// === navigator.hardwareConcurrency ===
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});

// === navigator.deviceMemory ===
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

// === navigator.maxTouchPoints (desktop = 0) ===
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});

// === navigator.connection ===
if (!navigator.connection) {
    Object.defineProperty(navigator, 'connection', {
        get: () => ({effectiveType: '4g', rtt: 50, downlink: 10, saveData: false})
    });
}

// === Permissions API — deny "notifications" query detection ===
const origQuery = window.Permissions?.prototype?.query;
if (origQuery) {
    window.Permissions.prototype.query = function(params) {
        if (params?.name === 'notifications') {
            return Promise.resolve({state: Notification.permission});
        }
        return origQuery.call(this, params);
    };
}

// === WebGL vendor/renderer override ===
const getParameterOrig = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Google Inc. (NVIDIA)';  // UNMASKED_VENDOR_WEBGL
    if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';  // UNMASKED_RENDERER_WEBGL
    return getParameterOrig.call(this, param);
};
const getParameterOrig2 = WebGL2RenderingContext.prototype.getParameter;
WebGL2RenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Google Inc. (NVIDIA)';
    if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';
    return getParameterOrig2.call(this, param);
};

// === chrome.runtime — fake it ===
if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) {
    window.chrome.runtime = {
        connect: function() {},
        sendMessage: function() {},
    };
}

// === window.outerWidth/outerHeight — match inner (headless leaks 0) ===
if (window.outerWidth === 0 || window.outerHeight === 0) {
    Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth});
    Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 85});
}

// === screen dimensions ===
if (screen.width === 0 || screen.height === 0) {
    Object.defineProperty(screen, 'width', {get: () => 1920});
    Object.defineProperty(screen, 'height', {get: () => 1080});
    Object.defineProperty(screen, 'availWidth', {get: () => 1920});
    Object.defineProperty(screen, 'availHeight', {get: () => 1040});
    Object.defineProperty(screen, 'colorDepth', {get: () => 24});
    Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
}

// === Iframe contentWindow detection ===
const origAttachShadow = Element.prototype.attachShadow;
Element.prototype.attachShadow = function() {
    return origAttachShadow.apply(this, arguments);
};
"""


def get_chrome_user_agent() -> str:
    """Get fixed Chrome user agent string to match API requests."""
    return FIXED_USER_AGENT


class ChallengePlatform(Enum):
    """Cloudflare challenge platform types."""
    JAVASCRIPT = "non-interactive"
    MANAGED = "managed"
    INTERACTIVE = "interactive"


class CloudflareSolver:
    """Solve Cloudflare challenges with Zendriver.
    
    Windows headless mode: thêm anti-detection flags + CDP patches.
    macOS headless: hoạt động bình thường không cần patch thêm.
    """

    def __init__(
        self,
        *,
        user_agent: Optional[str] = None,
        timeout: float = 30,
        headless: bool = False,
    ) -> None:
        if not CF_SOLVER_AVAILABLE:
            raise ImportError("zendriver not installed. Run: pip install zendriver latest-user-agents user-agents")
        
        self._headless = headless
        self._user_agent = user_agent or FIXED_USER_AGENT
        self._timeout = timeout
        self._config = None
        self.driver = None  # Lazy init - tạo trong async context
        
    def _build_config(self):
        """Build zendriver config - gọi trước khi tạo Browser"""
        config = zendriver.Config(headless=self._headless)
        config.add_argument(f"--user-agent={self._user_agent}")
        config.add_argument("--mute-audio")
        
        # === Anti-detection Chrome flags ===
        # Quan trọng cho Windows headless — macOS cũng không hại gì
        config.add_argument("--disable-blink-features=AutomationControlled")
        
        if self._headless:
            # Window size cho headless (tránh viewport 0x0)
            config.add_argument("--window-size=1920,1080")
            
            # Flags chống headless detection trên Windows
            if _CURRENT_OS == "Windows":
                config.sandbox = False  # zendriver dùng attribute thay vì --no-sandbox
                config.add_argument("--disable-gpu")
                config.add_argument("--disable-dev-shm-usage")
                config.add_argument("--disable-infobars")
                config.add_argument("--disable-extensions")
                config.add_argument("--disable-popup-blocking")
                config.add_argument("--ignore-certificate-errors")
                config.add_argument("--disable-background-timer-throttling")
                config.add_argument("--disable-backgrounding-occluded-windows")
                config.add_argument("--disable-renderer-backgrounding")
                config.add_argument("--disable-features=IsolateOrigins,site-per-process")
                config.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")
                # Force GPU rendering in headless (giảm fingerprint leak)
                config.add_argument("--use-gl=swiftshader")
                config.add_argument("--use-angle=swiftshader-webgl")
        
        return config
    
    async def ensure_browser(self):
        """Ensure browser is created - MUST call in async context"""
        if self.driver is None:
            config = self._build_config()
            self.driver = zendriver.Browser(config)
        return self.driver

    async def __aenter__(self) -> CloudflareSolver:
        await self.ensure_browser()
        await self.driver.start()
        # Inject stealth patches TRƯỚC mọi navigation
        await self._inject_stealth_patches()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.driver.stop()

    async def _inject_stealth_patches(self) -> None:
        """Inject anti-detection JS + CDP patches TRƯỚC page load.
        
        Quan trọng: phải chạy TRƯỚC navigate() để patches có hiệu lực
        trên mọi frame/page load.
        """
        tab = self.driver.main_tab
        
        # 1. addScriptToEvaluateOnNewDocument — chạy JS trước mọi page
        try:
            await tab.send(cdp.page.add_script_to_evaluate_on_new_document(
                source=_STEALTH_JS
            ))
        except Exception as e:
            logging.warning(f"[CF] Failed to inject stealth JS: {e}")
        
        # 2. Set UserAgentMetadata NGAY — không đợi đến solve_challenge
        await self.set_user_agent_metadata(self._user_agent)
        
        # 3. CDP Emulation — screen metrics cho headless
        if self._headless:
            try:
                await tab.send(cdp.emulation.set_device_metrics_override(
                    width=1920,
                    height=1080,
                    device_scale_factor=1.0,
                    mobile=False,
                    screen_width=1920,
                    screen_height=1080,
                ))
            except Exception as e:
                logging.warning(f"[CF] Failed to set device metrics: {e}")
            
            # Touch emulation OFF (desktop)
            try:
                await tab.send(cdp.emulation.set_touch_emulation_enabled(
                    enabled=False
                ))
            except:
                pass

    @staticmethod
    def _format_cookies(cookies: Iterable[Cookie]) -> List[T_JSON_DICT]:
        return [cookie.to_json() for cookie in cookies]

    @staticmethod
    def extract_clearance_cookie(cookies: Iterable[T_JSON_DICT]) -> Optional[T_JSON_DICT]:
        for cookie in cookies:
            if cookie["name"] == "cf_clearance":
                return cookie
        return None

    async def get_user_agent(self) -> str:
        return await self.driver.main_tab.evaluate("navigator.userAgent")

    async def get_cookies(self) -> List[T_JSON_DICT]:
        return self._format_cookies(await self.driver.cookies.get_all())

    async def set_user_agent_metadata(self, user_agent: str) -> None:
        """Set UA metadata — quan trọng cho CF fingerprint check.
        
        Platform/platformVersion phải match UA string chính xác.
        Windows: platform="Windows", platformVersion="10.0.0"
        macOS: platform="macOS", platformVersion="10.15.7"
        """
        device = user_agents.parse(user_agent)
        
        # Xác định platform + version chính xác từ UA
        if "Windows" in user_agent:
            plat = "Windows"
            plat_ver = "10.0.0"
        elif "Macintosh" in user_agent or "Mac OS" in user_agent:
            plat = "macOS"
            plat_ver = "10.15.7"
        else:
            plat = device.os.family
            plat_ver = device.os.version_string
        
        browser_major = str(device.browser.version[0]) if device.browser.version else "144"
        
        metadata = UserAgentMetadata(
            architecture="x86",
            bitness="64",
            brands=[
                UserAgentBrandVersion(brand="Not)A;Brand", version="8"),
                UserAgentBrandVersion(brand="Chromium", version=browser_major),
                UserAgentBrandVersion(brand="Google Chrome", version=browser_major),
            ],
            full_version_list=[
                UserAgentBrandVersion(brand="Not)A;Brand", version="8.0.0.0"),
                UserAgentBrandVersion(brand="Chromium", version=device.browser.version_string or "144.0.0.0"),
                UserAgentBrandVersion(brand="Google Chrome", version=device.browser.version_string or "144.0.0.0"),
            ],
            mobile=False,
            model="",
            platform=plat,
            platform_version=plat_ver,
            full_version=device.browser.version_string or "144.0.0.0",
            wow64=False,
        )
        self.driver.main_tab.feed_cdp(
            cdp.network.set_user_agent_override(user_agent, user_agent_metadata=metadata)
        )

    async def detect_challenge(self) -> Optional[ChallengePlatform]:
        html = await self.driver.main_tab.get_content()
        for platform in ChallengePlatform:
            if f"cType: '{platform.value}'" in html:
                return platform
        return None

    async def solve_challenge(self) -> None:
        """Solve the Cloudflare challenge on the current page.
        
        Hỗ trợ cả 3 loại: JavaScript (tự giải), Managed (click),
        Interactive (Turnstile widget trong shadow DOM).
        """
        start_timestamp = datetime.now()
        
        while (
            self.extract_clearance_cookie(await self.get_cookies()) is None
            and await self.detect_challenge() is not None
            and (datetime.now() - start_timestamp).seconds < self._timeout
        ):
            widget_input = await self.driver.main_tab.find("input")
            
            if widget_input.parent is None or not widget_input.parent.shadow_roots:
                await asyncio.sleep(0.25)
                continue
            
            challenge = Element(
                widget_input.parent.shadow_roots[0],
                self.driver.main_tab,
                widget_input.parent.tree,
            )
            challenge = challenge.children[0]
            
            if (
                isinstance(challenge, Element)
                and "display: none;" not in challenge.attrs.get("style", "")
            ):
                await asyncio.sleep(1)
                try:
                    await challenge.get_position()
                except Exception:
                    continue
                
                # CDP mouse click thay vì element.mouse_click() — đáng tin cậy hơn trên Windows
                try:
                    pos = challenge.position
                    if pos and hasattr(pos, 'x') and hasattr(pos, 'y'):
                        x = pos.x + (pos.width / 2 if hasattr(pos, 'width') else 10)
                        y = pos.y + (pos.height / 2 if hasattr(pos, 'height') else 10)
                        await self.driver.main_tab.send(cdp.input_.dispatch_mouse_event(
                            type_="mouseMoved", x=x, y=y,
                        ))
                        await asyncio.sleep(0.05)
                        await self.driver.main_tab.send(cdp.input_.dispatch_mouse_event(
                            type_="mousePressed", x=x, y=y,
                            button=cdp.input_.MouseButton.LEFT, click_count=1,
                        ))
                        await asyncio.sleep(0.05)
                        await self.driver.main_tab.send(cdp.input_.dispatch_mouse_event(
                            type_="mouseReleased", x=x, y=y,
                            button=cdp.input_.MouseButton.LEFT, click_count=1,
                        ))
                    else:
                        await challenge.mouse_click()
                except Exception:
                    # Fallback to element click
                    try:
                        await challenge.mouse_click()
                    except:
                        pass


async def _solve_cloudflare_async(
    url: str,
    timeout: float = 30,
    headless: bool = False,
    on_status: Optional[Callable] = None,
    existing_cookies: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Solve Cloudflare challenge and return cookies + user_agent.
    Uses the same approach as giaima/deobfuscator.py
    """
    if not CF_SOLVER_AVAILABLE:
        if on_status:
            on_status("❌ zendriver not installed")
        return None
    
    user_agent = get_chrome_user_agent()
    
    challenge_messages = {
        ChallengePlatform.JAVASCRIPT: "🔐 Solving Cloudflare challenge [JavaScript/non-interactive]...",
        ChallengePlatform.MANAGED: "🔐 Solving Cloudflare challenge [Managed]...",
        ChallengePlatform.INTERACTIVE: "🔐 Solving Cloudflare challenge [Interactive/Turnstile]...",
    }
    
    if on_status:
        on_status(f"🔄 Launching {'headless' if headless else 'headed'} browser...")
    
    try:
        # Use async context manager — __aenter__ injects stealth patches
        async with CloudflareSolver(
            user_agent=user_agent,
            timeout=timeout,
            headless=headless,
        ) as solver:
            
            # Set existing cookies BEFORE navigating to main URL
            if existing_cookies:
                if on_status:
                    on_status(f"🍪 Injecting cookies...")
                
                # Navigate to favicon first to set cookies
                try:
                    if on_status:
                        on_status("🌐 Going to grok.com/favicon.ico...")
                    await solver.driver.get("https://grok.com/favicon.ico")
                    await asyncio.sleep(1)
                except Exception as e:
                    if on_status:
                        on_status(f"⚠️ Favicon: {e}")
                
                # Set cookies via CDP
                for name, value in existing_cookies.items():
                    if name != 'cf_clearance':
                        try:
                            await solver.driver.main_tab.send(
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
                
                if on_status:
                    on_status(f"✅ Cookies set: {[k for k in existing_cookies.keys() if k != 'cf_clearance']}")
            
            # Navigate to main URL
            if on_status:
                on_status(f"🌐 Going to {url}...")
            
            try:
                await solver.driver.get(url)
            except asyncio.TimeoutError:
                if on_status:
                    on_status("⚠️ Page load timeout")
            
            await asyncio.sleep(3)
            
            # Check for cf_clearance
            all_cookies = await solver.get_cookies()
            clearance_cookie = solver.extract_clearance_cookie(all_cookies)
            
            if clearance_cookie is None:
                # UA metadata đã set trong __aenter__, nhưng re-set để chắc chắn
                await solver.set_user_agent_metadata(await solver.get_user_agent())
                
                # Detect challenge type
                challenge_platform = await solver.detect_challenge()
                
                if challenge_platform is None:
                    html = await solver.driver.main_tab.get_content()
                    if 'Just a moment' in html or 'Checking your browser' in html:
                        if on_status:
                            on_status("🔐 Cloudflare detected, waiting...")
                        for i in range(int(timeout)):
                            await asyncio.sleep(1)
                            all_cookies = await solver.get_cookies()
                            clearance_cookie = solver.extract_clearance_cookie(all_cookies)
                            if clearance_cookie:
                                break
                            if i % 5 == 0 and on_status:
                                on_status(f"⏳ Waiting... ({i}s)")
                    else:
                        if on_status:
                            on_status("✅ No Cloudflare challenge")
                else:
                    if on_status:
                        on_status(challenge_messages.get(challenge_platform, f"🔐 Solving [{challenge_platform.value}]..."))
                    
                    try:
                        await solver.solve_challenge()
                    except Exception as e:
                        if on_status:
                            on_status(f"⚠️ Solve error: {e}")
                
                # Get cookies after solving
                all_cookies = await solver.get_cookies()
                clearance_cookie = solver.extract_clearance_cookie(all_cookies)
                
                # Wait more if needed
                if clearance_cookie is None:
                    if on_status:
                        on_status("⏳ Waiting for cf_clearance...")
                    for i in range(15):
                        await asyncio.sleep(1)
                        all_cookies = await solver.get_cookies()
                        clearance_cookie = solver.extract_clearance_cookie(all_cookies)
                        if clearance_cookie:
                            break
            
            user_agent = await solver.get_user_agent()
        
        # Browser closed by context manager
        
        if clearance_cookie is None:
            if on_status:
                on_status("❌ Failed to get cf_clearance")
            return None
        
        # Convert to dict
        cookies_dict = {c["name"]: c["value"] for c in all_cookies}
        if existing_cookies:
            for k, v in existing_cookies.items():
                if k not in cookies_dict:
                    cookies_dict[k] = v
        
        if on_status:
            on_status(f"✅ Got cf_clearance: {clearance_cookie['value'][:30]}...")
        
        return {
            "cookies": cookies_dict,
            "cf_clearance": clearance_cookie["value"],
            "user_agent": user_agent,
            "expires": clearance_cookie.get("expires"),
        }
        
    except Exception as e:
        if on_status:
            on_status(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def solve_cloudflare(
    url: str = "https://grok.com",
    timeout: float = 30,
    headless: bool = False,
    on_status: Optional[Callable] = None,
    existing_cookies: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Synchronous wrapper for solving Cloudflare challenge.
    
    Args:
        url: URL to solve challenge for
        timeout: Timeout in seconds
        headless: Run browser in headless mode
        on_status: Callback for status updates
        existing_cookies: Existing cookies to set (sso, sso-rw, etc.)
    
    Returns:
        Dict with 'cookies', 'cf_clearance', 'user_agent' or None
    """
    return asyncio.run(_solve_cloudflare_async(url, timeout, headless, on_status, existing_cookies))


def save_cf_clearance(data: Dict[str, Any], domain: str = "grok.com") -> None:
    """Save cf_clearance to cache file."""
    CF_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if CF_CACHE_FILE.exists():
            with open(CF_CACHE_FILE, "r") as f:
                cache = json.load(f)
        else:
            cache = {}
    except:
        cache = {}
    
    cache[domain] = {
        "cf_clearance": data.get("cf_clearance"),
        "user_agent": data.get("user_agent"),
        "cookies": data.get("cookies"),
        "timestamp": datetime.now().isoformat(),
    }
    
    with open(CF_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def load_cf_clearance(domain: str = "grok.com") -> Optional[Dict[str, Any]]:
    """Load cf_clearance from cache file."""
    if not CF_CACHE_FILE.exists():
        return None
    
    try:
        with open(CF_CACHE_FILE, "r") as f:
            cache = json.load(f)
        return cache.get(domain)
    except:
        return None


def refresh_cf_clearance_if_needed(
    cookies: dict,
    url: str = "https://grok.com",
    timeout: float = 30,
    headless: bool = False,
    on_status: Optional[Callable] = None,
) -> dict:
    """
    Refresh cf_clearance if missing or expired.
    Returns updated cookies dict.
    """
    if "cf_clearance" in cookies:
        return cookies
    
    if on_status:
        on_status("🔄 cf_clearance missing, refreshing...")
    
    result = solve_cloudflare(url, timeout, headless, on_status)
    
    if result and result.get("cf_clearance"):
        cookies["cf_clearance"] = result["cf_clearance"]
        save_cf_clearance(result)
        if on_status:
            on_status("✅ cf_clearance refreshed!")
    
    return cookies


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    def status(msg):
        print(f"[STATUS] {msg}")
    
    result = solve_cloudflare(
        url="https://grok.com",
        timeout=30,
        headless=False,
        on_status=status,
    )
    
    if result:
        print(f"\n✅ Success!")
        print(f"cf_clearance: {result['cf_clearance'][:50]}...")
        print(f"user_agent: {result['user_agent']}")
        print(f"cookies: {list(result['cookies'].keys())}")
    else:
        print("\n❌ Failed to solve Cloudflare challenge")
