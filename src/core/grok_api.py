"""
Grok API - Video generation via CDP Fetch Intercept.

Approach (proven working):
1. Browser mở /imagine → app tự generate x-statsig-id mỗi request
2. Enter prompt + submit → app gọi conversations/new với statsig mới
3. CDP Fetch intercept → thay body với video settings
4. Server nhận statsig mới + body mới → 200

x-statsig-id KHÔNG reusable — mỗi request cần statsig mới từ app.
curl_cffi chrome133a/136 chỉ work với statsig chưa dùng (one-time).
→ CDP intercept là approach duy nhất hoạt động ổn định.
"""
import asyncio
import json
import time
import re
import os
import base64
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict

try:
    import zendriver
    from zendriver import cdp
    ZENDRIVER_AVAILABLE = True
except ImportError:
    ZENDRIVER_AVAILABLE = False

from .cf_solver import get_chrome_user_agent, CF_SOLVER_AVAILABLE

# API endpoints
API_BASE = "https://grok.com"
CREATE_VIDEO_URL = f"{API_BASE}/rest/media/post/create"
CREATE_LINK_URL = f"{API_BASE}/rest/media/post/create-link"
CONVERSATIONS_URL = f"{API_BASE}/rest/app-chat/conversations/new"
IMAGINE_URL = f"{API_BASE}/imagine"

# Video download URL template
VIDEO_DOWNLOAD_URL = "https://imagine-public.x.ai/imagine-public/share-videos/{post_id}.mp4?cache=1&dl=1"

OUTPUT_DIR = Path("output")
USER_AGENT = get_chrome_user_agent() if CF_SOLVER_AVAILABLE else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"


async def cdp_mouse_click(tab, x: float, y: float):
    """CDP mouse click — Radix UI cần pointer events thật."""
    await tab.send(cdp.input_.dispatch_mouse_event(type_="mouseMoved", x=x, y=y))
    await asyncio.sleep(0.05)
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mousePressed", x=x, y=y,
        button=cdp.input_.MouseButton.LEFT, click_count=1,
    ))
    await asyncio.sleep(0.05)
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mouseReleased", x=x, y=y,
        button=cdp.input_.MouseButton.LEFT, click_count=1,
    ))


class GrokCDPClient:
    """
    Grok video generation via CDP Fetch Intercept.
    
    Browser mở /imagine, app tự handle x-statsig-id + TLS.
    CDP intercept thay body conversations/new với video settings.
    """

    def __init__(self):
        self.browser: Optional[zendriver.Browser] = None
        self.tab = None
        self._running = False

    async def start(self, cookies: dict, headless: bool = False,
                    on_status: Optional[Callable] = None) -> bool:
        """Start browser, inject cookies, solve CF, navigate to /imagine.
        
        Dùng CloudflareSolver config để có anti-detection patches.
        """
        if not ZENDRIVER_AVAILABLE:
            if on_status: on_status("❌ zendriver not installed")
            return False

        if on_status: on_status("🚀 Starting browser...")

        # Dùng CloudflareSolver để tận dụng stealth patches
        from .cf_solver import CloudflareSolver as _CFS
        self._solver = _CFS(
            user_agent=USER_AGENT,
            timeout=90,
            headless=headless,
        )
        await self._solver.driver.start()
        await self._solver._inject_stealth_patches()
        
        self.browser = self._solver.driver
        self.tab = self.browser.main_tab

        # Inject cookies
        await self.browser.get("https://grok.com/favicon.ico")
        await asyncio.sleep(1)
        for name, value in cookies.items():
            if name == "cf_clearance":
                continue
            try:
                await self.tab.send(cdp.network.set_cookie(
                    name=name, value=value, domain=".grok.com",
                    path="/", secure=True,
                    http_only=name in ["sso", "sso-rw"],
                ))
            except:
                pass

        # Navigate + solve CF
        await self.browser.get("https://grok.com")
        await asyncio.sleep(3)

        has_cf = any(
            c.to_json()["name"] == "cf_clearance"
            for c in await self.browser.cookies.get_all()
        )
        if has_cf:
            if on_status: on_status("✅ cf_clearance present")
        else:
            if on_status: on_status("🔐 Solving Cloudflare...")
            solved = await self._solve_cf(on_status)
            if not solved:
                if on_status: on_status("❌ Cloudflare failed")
                return False

        # Navigate to /imagine
        if on_status: on_status("🌐 Navigating to /imagine...")
        await self.browser.get(IMAGINE_URL)
        await asyncio.sleep(5)

        # Check login
        url = await self.tab.evaluate("window.location.href")
        if "sign-in" in url or "accounts.x.ai" in url:
            if on_status: on_status("❌ Session expired")
            return False

        self._running = True
        if on_status: on_status("✅ Browser ready")
        return True

    async def _solve_cf(self, on_status: Optional[Callable] = None) -> bool:
        """Solve Cloudflare challenge."""
        from zendriver.cdp.emulation import UserAgentBrandVersion, UserAgentMetadata
        from zendriver.core.element import Element
        import user_agents

        device = user_agents.parse(USER_AGENT)
        metadata = UserAgentMetadata(
            architecture="x86", bitness="64",
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
            mobile=False, model="", platform=device.os.family,
            platform_version=device.os.version_string,
            full_version=device.browser.version_string, wow64=False,
        )
        self.tab.feed_cdp(cdp.network.set_user_agent_override(
            USER_AGENT, user_agent_metadata=metadata
        ))

        last_click = 0
        for i in range(90):
            if any(c.to_json()["name"] == "cf_clearance"
                   for c in await self.browser.cookies.get_all()):
                if on_status: on_status(f"✅ CF solved after {i}s")
                return True
            now = time.time()
            if now - last_click >= 5:
                last_click = now
                try:
                    wi = await self.tab.find("input")
                    if wi and wi.parent and wi.parent.shadow_roots:
                        ce = Element(wi.parent.shadow_roots[0], self.tab, wi.parent.tree)
                        ce = ce.children[0]
                        if isinstance(ce, Element) and "display: none;" not in ce.attrs.get("style", ""):
                            await asyncio.sleep(1)
                            await ce.get_position()
                            await ce.mouse_click()
                except:
                    pass
            await asyncio.sleep(1)
        return False

