"""Cloudflare Solver - Auto refresh cf_clearance cookie"""
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

# Fixed user agent to match API requests
FIXED_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"


def get_chrome_user_agent() -> str:
    """Get fixed Chrome user agent string to match API requests."""
    return FIXED_USER_AGENT


class ChallengePlatform(Enum):
    """Cloudflare challenge platform types."""
    JAVASCRIPT = "non-interactive"
    MANAGED = "managed"
    INTERACTIVE = "interactive"


class CloudflareSolver:
    """Solve Cloudflare challenges with Zendriver."""

    def __init__(
        self,
        *,
        user_agent: Optional[str] = None,
        timeout: float = 30,
        headless: bool = False,
    ) -> None:
        if not CF_SOLVER_AVAILABLE:
            raise ImportError("zendriver not installed. Run: pip install zendriver latest-user-agents user-agents")
        
        config = zendriver.Config(headless=headless)
        
        if user_agent:
            config.add_argument(f"--user-agent={user_agent}")
        
        # Mute audio to prevent sound in headless mode
        config.add_argument("--mute-audio")
        
        self.driver = zendriver.Browser(config)
        self._timeout = timeout

    async def __aenter__(self) -> CloudflareSolver:
        await self.driver.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.driver.stop()

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
        device = user_agents.parse(user_agent)
        metadata = UserAgentMetadata(
            architecture="x86",
            bitness="64",
            brands=[
                UserAgentBrandVersion(brand="Not)A;Brand", version="8"),
                UserAgentBrandVersion(brand="Chromium", version=str(device.browser.version[0])),
                UserAgentBrandVersion(brand="Google Chrome", version=str(device.browser.version[0])),
            ],
            full_version_list=[
                UserAgentBrandVersion(brand="Not)A;Brand", version="8"),
                UserAgentBrandVersion(brand="Chromium", version=str(device.browser.version[0])),
                UserAgentBrandVersion(brand="Google Chrome", version=str(device.browser.version[0])),
            ],
            mobile=device.is_mobile,
            model=device.device.model or "",
            platform=device.os.family,
            platform_version=device.os.version_string,
            full_version=device.browser.version_string,
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
                await challenge.mouse_click()


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
        # Use async context manager like deobfuscator.py does
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
                # Set user agent metadata before solving
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
