"""Video Generator - Browser automation for Grok video generation using zendriver"""
import asyncio
import time
import re
import os
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List, Tuple

from .models import Account, VideoSettings, VideoTask
from .cf_solver import (
    CloudflareSolver, ChallengePlatform, CF_SOLVER_AVAILABLE,
    get_chrome_user_agent
)

try:
    import zendriver
    from zendriver import cdp
    ZENDRIVER_AVAILABLE = True
except ImportError:
    ZENDRIVER_AVAILABLE = False

IMAGINE_URL = "https://grok.com/imagine"
from .paths import output_path as _output_path
OUTPUT_DIR = _output_path()
VIDEO_DOWNLOAD_URL = "https://imagine-public.x.ai/imagine-public/share-videos/{post_id}.mp4?cache=1"


class VideoGenerator:
    def __init__(self):
        self.solver: Optional[CloudflareSolver] = None
    
    def generate_video(
        self,
        account: Account,
        prompt: str,
        settings: VideoSettings,
        on_status: Optional[Callable] = None,
        headless: bool = False
    ) -> VideoTask:
        """Generate video using zendriver (single browser for everything)"""
        return asyncio.run(self._generate_video_async(
            account, prompt, settings, on_status, headless
        ))
    
    async def _generate_video_async(
        self,
        account: Account,
        prompt: str,
        settings: VideoSettings,
        on_status: Optional[Callable] = None,
        headless: bool = False
    ) -> VideoTask:
        """Async video generation with zendriver"""
        task = VideoTask(
            account_email=account.email,
            prompt=prompt,
            settings=settings,
            status="creating"
        )
        
        if not CF_SOLVER_AVAILABLE:
            task.status = "failed"
            task.error_message = "zendriver not installed"
            return task

        user_agent = get_chrome_user_agent()
        
        try:
            if on_status:
                on_status("🔄 Starting browser...")
            
            async with CloudflareSolver(
                user_agent=user_agent,
                timeout=60,
                headless=headless,
            ) as solver:
                self.solver = solver
                
                # Step 1: Inject cookies
                if account.cookies:
                    if on_status:
                        on_status("🍪 Injecting cookies...")
                    
                    await solver.driver.get("https://grok.com/favicon.ico")
                    await asyncio.sleep(1)
                    
                    for name, value in account.cookies.items():
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
                
                # Step 2: Navigate to imagine and handle Cloudflare
                if on_status:
                    on_status("🌐 Going to Grok Imagine...")
                
                await solver.driver.get(IMAGINE_URL)
                await asyncio.sleep(3)
                
                # Check and solve Cloudflare
                cf_passed = await self._handle_cloudflare(solver, on_status)
                if not cf_passed:
                    task.status = "failed"
                    task.error_message = "Cloudflare challenge failed"
                    return task
                
                # Check login status
                current_url = await solver.driver.main_tab.evaluate("window.location.href")
                if 'sign-in' in current_url or 'accounts.x.ai' in current_url:
                    task.status = "failed"
                    task.error_message = "Session expired. Please login again."
                    return task
                
                await asyncio.sleep(2)
                
                # Step 3: Select Video mode
                if on_status:
                    on_status("🎬 Selecting Video mode...")
                print(">>> Step 3: Selecting Video mode...")
                await self._select_video_mode(solver, on_status)
                await asyncio.sleep(2)
                
                # Step 4: Enter prompt
                print(f">>> Step 4: Entering prompt: {prompt[:40]}...")
                if on_status:
                    on_status(f"✏️ Entering prompt: {prompt[:40]}...")
                if not await self._enter_prompt(solver, prompt, on_status):
                    task.status = "failed"
                    task.error_message = "Failed to enter prompt"
                    return task
                
                await asyncio.sleep(1)
                
                # Step 5: Submit
                print(">>> Step 5: Submitting...")
                if on_status:
                    on_status("📤 Submitting...")
                await self._submit_prompt(solver, on_status)
                await asyncio.sleep(3)
                
                # Step 6: Wait for post ID
                print(">>> Step 6: Waiting for post ID...")
                if on_status:
                    on_status("⏳ Waiting for post ID...")
                
                # Debug: save screenshot
                try:
                    screenshot_data = await solver.driver.main_tab.send(cdp.page.capture_screenshot())
                    if screenshot_data:
                        from .paths import data_path
                        debug_path = data_path(f"debug_zendriver_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                        debug_path.parent.mkdir(exist_ok=True)
                        with open(debug_path, 'wb') as f:
                            f.write(base64.b64decode(screenshot_data))
                except:
                    pass
                
                post_id = await self._wait_for_post_id(solver, on_status, timeout=30)
                print(f">>> Post ID result: {post_id}")
                
                if not post_id:
                    task.status = "failed"
                    task.error_message = "Could not get post ID"
                    return task
                
                task.post_id = post_id
                task.media_url = VIDEO_DOWNLOAD_URL.format(post_id=post_id)
                
                print(f">>> Video URL = {task.media_url}")
                if on_status:
                    on_status(f"✅ Post ID: {post_id}")
                
                # Mark as completed immediately - video will be downloaded from History tab
                task.status = "completed"
                task.completed_at = datetime.now()
                if on_status:
                    on_status(f"✅ Video queued! Post ID: {post_id}")
                    on_status("📋 Download from History tab when ready")
                
                # Navigate back to /imagine for next video immediately
                print(">>> Navigating back to /imagine...")
                if on_status:
                    on_status("🔄 Ready for next video...")
                await solver.driver.get(IMAGINE_URL)
                await asyncio.sleep(2)
                
                return task
                
        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            if on_status:
                on_status(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return task

    async def _handle_cloudflare(
        self, solver: CloudflareSolver, on_status: Optional[Callable]
    ) -> bool:
        """Handle Cloudflare challenge"""
        html = await solver.driver.main_tab.get_content()
        cf_indicators = ['Just a moment', 'Checking your browser', 'challenge-platform', 'cf-turnstile']
        
        if not any(ind in html for ind in cf_indicators):
            if on_status:
                on_status("✅ No Cloudflare challenge")
            return True
        
        if on_status:
            on_status("🔐 Cloudflare detected, solving...")
        
        # Set user agent metadata
        await solver.set_user_agent_metadata(await solver.get_user_agent())
        
        # Detect challenge type
        challenge = await solver.detect_challenge()
        
        if challenge:
            if on_status:
                on_status(f"🔐 Challenge type: {challenge.value}")
            try:
                await solver.solve_challenge()
            except Exception as e:
                if on_status:
                    on_status(f"⚠️ Solve error: {e}")
        
        # Wait for cf_clearance
        for i in range(60):
            cookies = await solver.get_cookies()
            if solver.extract_clearance_cookie(cookies):
                if on_status:
                    on_status("✅ Cloudflare passed!")
                return True
            await asyncio.sleep(1)
            if i % 10 == 0 and on_status:
                on_status(f"⏳ Waiting... ({i}s)")
        
        if on_status:
            on_status("❌ Cloudflare timeout")
        return False
    
    async def _select_video_mode(
        self, solver: CloudflareSolver, on_status: Optional[Callable]
    ) -> None:
        """Select Video mode in the UI - improved version"""
        try:
            print("🎬 [VIDEO MODE] Starting video mode selection...")
            
            # Wait for page to fully load - wait for trigger button to appear
            trigger_info = None
            for wait_attempt in range(10):
                await asyncio.sleep(1)
                trigger_info = await solver.driver.main_tab.evaluate("""
                    (function() {
                        var trigger = document.querySelector('#model-select-trigger');
                        if (trigger) {
                            var rect = trigger.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return {
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                    found: true,
                                    text: trigger.textContent.substring(0, 30)
                                };
                            }
                        }
                        return {found: false, attempt: """ + str(wait_attempt) + """};
                    })()
                """)
                if trigger_info and trigger_info.get('found'):
                    break
                print(f"   Waiting for trigger... attempt {wait_attempt + 1}")
            
            print(f"   Trigger info: {trigger_info}")
            
            # Click trigger if found
            if trigger_info and trigger_info.get('found'):
                x, y = trigger_info['x'], trigger_info['y']
                
                # Use JS click first (more reliable)
                await solver.driver.main_tab.evaluate("""
                    (function() {
                        var trigger = document.querySelector('#model-select-trigger');
                        if (trigger) trigger.click();
                    })()
                """)
                print(f"   JS click on trigger")
                await asyncio.sleep(1.5)
            
            # Check menu state
            menu_state = await solver.driver.main_tab.evaluate("""
                (function() {
                    var menu = document.querySelector('[data-radix-menu-content][data-state="open"]') ||
                               document.querySelector('[role="menu"][data-state="open"]');
                    if (menu) {
                        var items = menu.querySelectorAll('[role="menuitem"]');
                        return {open: true, itemCount: items.length};
                    }
                    return {open: false};
                })()
            """)
            print(f"   Menu state: {menu_state}")
            
            # If menu not open, try CDP click
            if not menu_state.get('open') and trigger_info and trigger_info.get('found'):
                print("   Menu not open, trying CDP click...")
                x, y = trigger_info['x'], trigger_info['y']
                await solver.driver.main_tab.send(cdp.input_.dispatch_mouse_event(
                    type_="mousePressed", x=x, y=y,
                    button=cdp.input_.MouseButton.LEFT, click_count=1
                ))
                await asyncio.sleep(0.1)
                await solver.driver.main_tab.send(cdp.input_.dispatch_mouse_event(
                    type_="mouseReleased", x=x, y=y,
                    button=cdp.input_.MouseButton.LEFT, click_count=1
                ))
                await asyncio.sleep(1.5)
                
                menu_state = await solver.driver.main_tab.evaluate("""
                    (function() {
                        var menu = document.querySelector('[data-radix-menu-content][data-state="open"]') ||
                                   document.querySelector('[role="menu"][data-state="open"]');
                        return menu ? {open: true} : {open: false};
                    })()
                """)
                print(f"   After CDP click: {menu_state}")

            # Step 2: Find and click Video option
            print("🎬 [VIDEO MODE] Step 2: Finding Video option...")
            
            video_option = await solver.driver.main_tab.evaluate("""
                (function() {
                    // Find all menu items
                    var items = document.querySelectorAll('[role="menuitem"]');
                    
                    for (var item of items) {
                        // Check for Video text
                        var text = item.textContent || '';
                        if (text.includes('Video') && text.includes('Tạo một video')) {
                            var rect = item.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return {
                                    found: true,
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                    text: text.substring(0, 30)
                                };
                            }
                        }
                        
                        // Check for play icon (polygon SVG)
                        var svg = item.querySelector('svg');
                        if (svg && svg.querySelector('polygon')) {
                            var rect = item.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return {
                                    found: true,
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                    text: 'Video (polygon icon)'
                                };
                            }
                        }
                    }
                    
                    return {found: false, reason: 'NO_VIDEO_OPTION', itemCount: items.length};
                })()
            """)
            print(f"   Video option: {video_option}")
            
            if video_option and video_option.get('found'):
                # Use JS click on Video option
                click_result = await solver.driver.main_tab.evaluate("""
                    (function() {
                        var items = document.querySelectorAll('[role="menuitem"]');
                        for (var item of items) {
                            var text = item.textContent || '';
                            if (text.includes('Video') && text.includes('Tạo một video')) {
                                item.click();
                                return 'clicked Video menuitem';
                            }
                            // Also check for polygon SVG (play icon)
                            var svg = item.querySelector('svg');
                            if (svg && svg.querySelector('polygon')) {
                                item.click();
                                return 'clicked Video by polygon icon';
                            }
                        }
                        return 'no video option found';
                    })()
                """)
                print(f"   Click result: {click_result}")
            else:
                # Fallback: keyboard navigation
                print("   Video not found, trying keyboard navigation...")
                await solver.driver.main_tab.send(cdp.input_.dispatch_key_event(
                    type_="keyDown", key="ArrowDown", code="ArrowDown", windows_virtual_key_code=40
                ))
                await solver.driver.main_tab.send(cdp.input_.dispatch_key_event(
                    type_="keyUp", key="ArrowDown", code="ArrowDown", windows_virtual_key_code=40
                ))
                await asyncio.sleep(0.3)
                await solver.driver.main_tab.send(cdp.input_.dispatch_key_event(
                    type_="keyDown", key="Enter", code="Enter", windows_virtual_key_code=13
                ))
                await solver.driver.main_tab.send(cdp.input_.dispatch_key_event(
                    type_="keyUp", key="Enter", code="Enter", windows_virtual_key_code=13
                ))
                print("   Sent ArrowDown + Enter")
            
            await asyncio.sleep(1)
            
            # Verify final mode
            verify = await solver.driver.main_tab.evaluate("""
                (function() {
                    var trigger = document.querySelector('#model-select-trigger') ||
                                  document.querySelector('button[aria-haspopup="menu"]');
                    if (!trigger) return 'NO_TRIGGER';
                    
                    var svg = trigger.querySelector('svg');
                    if (svg) {
                        if (svg.querySelector('polygon')) return 'VIDEO_MODE_OK';
                        if (svg.querySelector('rect')) return 'IMAGE_MODE';
                    }
                    
                    var text = trigger.textContent || '';
                    if (text.includes('Video')) return 'VIDEO_MODE_OK';
                    if (text.includes('Image') || text.includes('Ảnh')) return 'IMAGE_MODE';
                    
                    return 'UNKNOWN';
                })()
            """)
            print(f"   ✅ Final mode: {verify}")
            
            if on_status:
                on_status(f"   Mode: {verify}")
                
        except Exception as e:
            print(f"⚠️ Mode select error: {e}")
            import traceback
            traceback.print_exc()

    async def _enter_prompt(
        self, solver: CloudflareSolver, prompt: str, on_status: Optional[Callable]
    ) -> bool:
        """Enter prompt in editor"""
        try:
            escaped_prompt = prompt.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
            
            js = f"""
            (function() {{
                var editor = document.querySelector('div.tiptap.ProseMirror') ||
                             document.querySelector('div[contenteditable="true"]') ||
                             document.querySelector('.ProseMirror') ||
                             document.querySelector('textarea');
                
                if (!editor) return 'no_editor';
                
                editor.focus();
                
                if (editor.tagName === 'TEXTAREA') {{
                    editor.value = '{escaped_prompt}';
                    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                    return 'textarea_filled';
                }}
                
                editor.innerHTML = '<p>{escaped_prompt}</p>';
                editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                return 'editor_filled';
            }})()
            """
            result = await solver.driver.main_tab.evaluate(js)
            if on_status:
                on_status(f"   Prompt result: {result}")
            return 'filled' in result
        except Exception as e:
            if on_status:
                on_status(f"⚠️ Prompt error: {e}")
            return False
    
    async def _submit_prompt(self, solver: CloudflareSolver, on_status: Optional[Callable] = None) -> None:
        """Click submit button"""
        try:
            js = """
            (function() {
                var btn = document.querySelector('button[type="submit"]');
                if (!btn) {
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var label = b.getAttribute('aria-label') || b.textContent || '';
                        if (label.includes('Send') || label.includes('Gửi') || label.includes('Submit')) {
                            btn = b;
                            break;
                        }
                    }
                }
                if (btn && !btn.disabled) {
                    btn.click();
                    return 'clicked';
                }
                return 'no_button_or_disabled';
            })()
            """
            result = await solver.driver.main_tab.evaluate(js)
            if on_status:
                on_status(f"   Submit result: {result}")
        except Exception as e:
            if on_status:
                on_status(f"⚠️ Submit error: {e}")
    
    async def _wait_for_post_id(
        self, solver: CloudflareSolver, on_status: Optional[Callable], timeout: int = 30
    ) -> Optional[str]:
        """Wait for post ID in URL"""
        pattern = r'/imagine/post/([a-f0-9-]{36})'
        
        for _ in range(timeout):
            url = await solver.driver.main_tab.evaluate("window.location.href")
            match = re.search(pattern, url)
            if match:
                return match.group(1)
            await asyncio.sleep(1)
        return None
    
    async def _wait_for_video_ready(
        self, solver: CloudflareSolver, on_status: Optional[Callable], timeout: int = 600
    ) -> bool:
        """Wait for video to be ready"""
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                js = """
                (function() {
                    var c = document.querySelector('div.flex.flex-row.border');
                    if (c && !c.classList.contains('pointer-events-none')) return true;
                    return false;
                })()
                """
                ready = await solver.driver.main_tab.evaluate(js)
                if ready:
                    if on_status:
                        on_status("✅ Video ready!")
                    return True
                
                elapsed = int(time.time() - start)
                if on_status and elapsed % 30 == 0:
                    on_status(f"⏳ Generating... ({elapsed}s)")
            except:
                pass
            await asyncio.sleep(3)
        return False
    
    async def _click_share_button(self, solver: CloudflareSolver) -> bool:
        """Click share button"""
        try:
            js = """
            (function() {
                var btn = document.querySelector('button[aria-label*="share" i]') ||
                          document.querySelector('button[aria-label*="chia sẻ"]');
                if (!btn) {
                    var svg = document.querySelector('svg.lucide-share');
                    if (svg) btn = svg.closest('button');
                }
                if (btn && !btn.disabled) {
                    btn.click();
                    return true;
                }
                return false;
            })()
            """
            return await solver.driver.main_tab.evaluate(js) or False
        except:
            return False

    async def _download_video(
        self,
        solver: CloudflareSolver,
        url: str,
        email: str,
        prompt: str,
        on_status: Optional[Callable]
    ) -> Optional[str]:
        """Download video using requests with browser cookies"""
        if not url:
            return None
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        email_short = email.split("@")[0][:10]
        prompt_short = re.sub(r'[^\w\s]', '', prompt)[:20].replace(' ', '_')
        filename = f"{ts}_{email_short}_{prompt_short}.mp4"
        path = OUTPUT_DIR / filename
        
        try:
            import requests
            
            # Get cookies from browser - already dict format
            cookies_list = await solver.get_cookies()
            cookies_dict = {}
            for c in cookies_list:
                # cookies_list is list of dicts
                if isinstance(c, dict):
                    cookies_dict[c['name']] = c['value']
                else:
                    cookies_dict[c.name] = c.value
            
            if on_status:
                on_status(f"📥 Downloading video...")
            
            headers = {
                'User-Agent': await solver.get_user_agent(),
                'Referer': 'https://grok.com/',
            }
            
            response = requests.get(url, cookies=cookies_dict, headers=headers, timeout=120, stream=True)
            
            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and on_status and downloaded % (1024 * 1024) < 8192:
                                pct = int(downloaded * 100 / total_size)
                                on_status(f"📥 Downloading... {pct}%")
                
                if path.exists() and os.path.getsize(path) > 10000:
                    if on_status:
                        size_mb = os.path.getsize(path) / (1024 * 1024)
                        on_status(f"✅ Downloaded: {filename} ({size_mb:.1f} MB)")
                    return str(path)
                else:
                    if on_status:
                        on_status(f"⚠️ File too small or empty")
                    return None
            else:
                if on_status:
                    on_status(f"⚠️ Download failed: HTTP {response.status_code}")
                return None
            
        except Exception as e:
            if on_status:
                on_status(f"⚠️ Download error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def close(self):
        """Close browser (handled by context manager)"""
        pass
    
    def download_video_from_url(
        self, url: str, email: str, prompt: str, on_status: Optional[Callable] = None
    ) -> Optional[str]:
        """Download video from URL (for History tab)"""
        return asyncio.run(self._download_from_url_async(url, email, prompt, on_status))
    
    async def _download_from_url_async(
        self, url: str, email: str, prompt: str, on_status: Optional[Callable]
    ) -> Optional[str]:
        """Async download from URL using requests"""
        if not url:
            return None
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        email_short = email.split("@")[0][:10]
        prompt_short = re.sub(r'[^\w\s]', '', prompt)[:20].replace(' ', '_')
        filename = f"{ts}_{email_short}_{prompt_short}.mp4"
        path = OUTPUT_DIR / filename
        
        if on_status:
            on_status("📥 Downloading video...")
        
        try:
            import requests
            
            headers = {
                'User-Agent': get_chrome_user_agent(),
                'Referer': 'https://grok.com/',
            }
            
            response = requests.get(url, headers=headers, timeout=120, stream=True)
            
            if response.status_code == 200:
                with open(path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                if path.exists() and os.path.getsize(path) > 10000:
                    if on_status:
                        size_mb = os.path.getsize(path) / (1024 * 1024)
                        on_status(f"✅ Downloaded: {filename} ({size_mb:.1f} MB)")
                    return str(path)
            
            if on_status:
                on_status(f"❌ Failed: HTTP {response.status_code}")
            return None
                
        except Exception as e:
            if on_status:
                on_status(f"❌ Error: {e}")
            return None



class MultiTabVideoGenerator:
    """
    Multi-tab video generator - 1 browser per account, 3 tabs concurrent.
    Example: 2 accounts = 2 browsers × 3 tabs = 6 concurrent video generations.
    """
    
    def __init__(
        self,
        account: Account,
        num_tabs: int = 3,
        headless: bool = True,
        on_status: Optional[Callable] = None
    ):
        self.account = account
        self.num_tabs = num_tabs
        self.headless = headless
        self.on_status = on_status
        
        self.browser: Optional[zendriver.Browser] = None
        self.config: Optional[zendriver.Config] = None  # Store config for user_data_dir
        self.tabs: List[Any] = []  # List of tab objects
        self.tab_ready: List[bool] = []  # Track which tabs are ready
        self._running = True
        self._user_data_dir: Optional[str] = None  # Browser profile directory
        self._auto_video_disabled = False  # Track if auto-video setting was disabled (image mode)
    
    def _log(self, msg: str, tab_id: int = -1):
        """Log message with optional tab ID"""
        prefix = f"[{self.account.email[:15]}]"
        if tab_id >= 0:
            prefix += f"[Tab{tab_id+1}]"
        full_msg = f"{prefix} {msg}"
        print(full_msg)
        if self.on_status:
            self.on_status(self.account.email, full_msg)
    
    async def start(self) -> bool:
        """Start browser and create tabs.
        
        Dùng CloudflareSolver config + stealth patches cho Windows headless.
        """
        if not ZENDRIVER_AVAILABLE:
            self._log("❌ zendriver not installed")
            return False
        
        try:
            self._log("🚀 Starting browser...")
            
            # Dùng CloudflareSolver để tạo browser config có anti-detection
            user_agent = get_chrome_user_agent()
            self._solver_helper = CloudflareSolver(
                user_agent=user_agent,
                timeout=90,
                headless=self.headless,
            )
            # Ensure browser is created in async context
            await self._solver_helper.ensure_browser()
            self.browser = self._solver_helper.driver
            self.config = self.browser.config if hasattr(self.browser, 'config') else None
            
            # Start browser + inject stealth patches
            await self.browser.start()
            await self._solver_helper._inject_stealth_patches()
            
            # Verify browser started correctly
            if not self.browser.main_tab:
                self._log("❌ Browser started but main_tab is None, retrying...")
                await asyncio.sleep(2)
                try:
                    await self.browser.stop()
                except:
                    pass
                # Retry with fresh solver
                self._solver_helper = CloudflareSolver(
                    user_agent=user_agent,
                    timeout=90,
                    headless=self.headless,
                )
                await self._solver_helper.ensure_browser()
                self.browser = self._solver_helper.driver
                await self.browser.start()
                await self._solver_helper._inject_stealth_patches()
                await asyncio.sleep(1)
                if not self.browser.main_tab:
                    self._log("❌ main_tab still None after retry")
                    return False
            
            # Save user_data_dir for later use in downloads
            try:
                self._user_data_dir = self._solver_helper.driver.config.user_data_dir
            except:
                self._user_data_dir = None
            self._log(f"   Browser profile: {self._user_data_dir}")
            
            # Step 1: Inject cookies to main_tab first
            self._log("🍪 Injecting cookies...")
            try:
                await self.browser.main_tab.get("https://grok.com/favicon.ico")
            except Exception as e:
                self._log(f"⚠️ Favicon navigation error: {e}, retrying...")
                await asyncio.sleep(2)
                await self.browser.main_tab.get("https://grok.com/favicon.ico")
            await asyncio.sleep(1)
            
            if self.account.cookies:
                for name, value in self.account.cookies.items():
                    if name != 'cf_clearance':
                        try:
                            await self.browser.main_tab.send(
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
            
            # Step 2: Navigate main_tab to /imagine and handle Cloudflare
            self._log("🌐 Going to Grok Imagine...")
            await self.browser.main_tab.get(IMAGINE_URL)
            await asyncio.sleep(3)
            
            # Check and solve Cloudflare on main_tab
            cf_passed = await self._handle_cloudflare_on_tab(self.browser.main_tab)
            if not cf_passed:
                self._log("❌ Cloudflare challenge failed")
                return False
            
            # Check login status
            current_url = await self.browser.main_tab.evaluate("window.location.href")
            if 'sign-in' in current_url or 'accounts.x.ai' in current_url:
                self._log("❌ Session expired. Please login again.")
                return False
            
            await asyncio.sleep(2)
            
            # Step 3: Create additional tabs (main_tab is tab 0)
            self.tabs = [self.browser.main_tab]
            self.tab_ready = [True]
            
            for i in range(1, self.num_tabs):
                self._log(f"📑 Creating Tab {i+1}...")
                new_tab = await self.browser.get(IMAGINE_URL, new_tab=True)
                await asyncio.sleep(2)
                self.tabs.append(new_tab)
                self.tab_ready.append(True)
            
            self._log(f"✅ Browser ready with {len(self.tabs)} tabs")
            return True
            
        except Exception as e:
            self._log(f"❌ Start error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def stop(self):
        """Stop browser"""
        self._running = False
        if self.browser:
            try:
                await self.browser.stop()
            except:
                pass
            self.browser = None
        self.tabs = []
        self.tab_ready = []
    
    async def _handle_cloudflare_on_tab(self, tab) -> bool:
        """Handle Cloudflare challenge on a specific tab.
        Retry click turnstile nhiều lần thay vì chỉ 1 lần.
        Dùng CloudflareSolver.set_user_agent_metadata cho UA metadata chính xác."""
        try:
            html = await tab.get_content()
            cf_indicators = ['Just a moment', 'Checking your browser', 'challenge-platform', 'cf-turnstile']
            
            if not any(ind in html for ind in cf_indicators):
                self._log("✅ No Cloudflare challenge")
                return True
            
            self._log("🔐 Cloudflare detected, solving...")
            
            # Set user agent metadata — dùng helper từ CloudflareSolver
            user_agent = get_chrome_user_agent()
            try:
                await self._solver_helper.set_user_agent_metadata(user_agent)
                self._log("   Set user agent metadata (platform-aware)")
            except Exception as e:
                self._log(f"   ⚠️ UA metadata error: {e}")
            
            # Detect challenge type
            challenge_type = None
            for platform_value in ['non-interactive', 'managed', 'interactive']:
                if f"cType: '{platform_value}'" in html:
                    challenge_type = platform_value
                    break
            
            if challenge_type:
                self._log(f"   Challenge type: {challenge_type}")
            
            # Try to solve interactive challenge (click turnstile)
            # Retry click mỗi 10s thay vì chỉ 1 lần
            last_click_time = 0
            
            # Wait for cf_clearance cookie — retry click turnstile mỗi 10s
            for i in range(90):
                # Check cookie trước
                cookies = await self.browser.cookies.get_all()
                for c in cookies:
                    if c.name == "cf_clearance":
                        self._log("✅ Cloudflare passed!")
                        return True
                
                # Thử click turnstile mỗi 10s — dùng CDP mouse events cho Windows
                import time as _time
                now = _time.time()
                if now - last_click_time >= 10:
                    last_click_time = now
                    try:
                        from zendriver.core.element import Element
                        
                        widget_input = await tab.find("input")
                        
                        if widget_input and widget_input.parent and widget_input.parent.shadow_roots:
                            challenge = Element(
                                widget_input.parent.shadow_roots[0],
                                tab,
                                widget_input.parent.tree,
                            )
                            challenge = challenge.children[0]
                            
                            if (
                                isinstance(challenge, Element)
                                and "display: none;" not in challenge.attrs.get("style", "")
                            ):
                                self._log(f"   Clicking turnstile... ({i}s)")
                                await asyncio.sleep(1)
                                try:
                                    await challenge.get_position()
                                    # CDP mouse click — đáng tin cậy hơn trên Windows headless
                                    pos = challenge.position
                                    if pos and hasattr(pos, 'x') and hasattr(pos, 'y'):
                                        x = pos.x + (pos.width / 2 if hasattr(pos, 'width') else 10)
                                        y = pos.y + (pos.height / 2 if hasattr(pos, 'height') else 10)
                                        await tab.send(cdp.input_.dispatch_mouse_event(
                                            type_="mouseMoved", x=x, y=y,
                                        ))
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
                                    else:
                                        await challenge.mouse_click()
                                except Exception as e:
                                    self._log(f"   ⚠️ Click error: {e}")
                                    try:
                                        await challenge.mouse_click()
                                    except:
                                        pass
                    except Exception as e:
                        if i == 0:
                            self._log(f"   ⚠️ Turnstile error: {e}")
                
                await asyncio.sleep(1)
                if i % 10 == 0 and i > 0:
                    self._log(f"⏳ Waiting for cf_clearance... ({i}s)")
            
            self._log("❌ Cloudflare timeout")
            return False
            
        except Exception as e:
            self._log(f"⚠️ CF check error: {e}")
            import traceback
            traceback.print_exc()
            return True  # Continue anyway
    
    # ==================== Image-to-Video Methods ====================
    
    async def _disable_auto_video_on_tab(self, tab, tab_id: int) -> bool:
        """
        Tắt "Bật Tạo Video Tự Động" trong Settings → Hành vi.
        Chỉ cần chạy 1 lần per browser session.
        Flow: Avatar → Cài đặt → Hành vi → toggle off → close dialog
        """
        if self._auto_video_disabled:
            return True
        
        self._log("⚙️ Disabling auto video generation...", tab_id)
        
        # Step 1: Click avatar button (bottom-left) via CDP
        avatar_pos = await tab.evaluate("""
            (function() {
                var container = document.querySelector('div.absolute.bottom-3');
                if (container) {
                    var btn = container.querySelector('button[aria-haspopup="menu"]');
                    if (btn) {
                        var rect = btn.getBoundingClientRect();
                        return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
                var btns = document.querySelectorAll('button[aria-haspopup="menu"]');
                for (var b of btns) {
                    var span = b.querySelector('span.rounded-full');
                    if (span) {
                        var rect = b.getBoundingClientRect();
                        if (rect.width > 0) return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
                return {found: false};
            })()
        """)
        if not avatar_pos or not avatar_pos.get('found'):
            self._log("⚠️ Avatar button not found, skipping", tab_id)
            return False
        
        x, y = avatar_pos['x'], avatar_pos['y']
        await tab.send(cdp.input_.dispatch_mouse_event(
            type_="mousePressed", x=x, y=y, button=cdp.input_.MouseButton.LEFT, click_count=1))
        await asyncio.sleep(0.05)
        await tab.send(cdp.input_.dispatch_mouse_event(
            type_="mouseReleased", x=x, y=y, button=cdp.input_.MouseButton.LEFT, click_count=1))
        await asyncio.sleep(1.5)
        
        # Step 2: Click "Cài đặt" / "Settings" menuitem
        for attempt in range(5):
            menu_info = await tab.evaluate("""
                (function() {
                    var menu = document.querySelector('[role="menu"]');
                    if (!menu) return {status: 'no_menu'};
                    var items = menu.querySelectorAll('[role="menuitem"]');
                    for (var item of items) {
                        var text = (item.textContent || '').trim();
                        if (text === 'Cài đặt' || text === 'Settings' || text.includes('Cài đặt') || text.includes('Settings')) {
                            var rect = item.getBoundingClientRect();
                            return {status: 'found', x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                        }
                    }
                    return {status: 'not_matched'};
                })()
            """)
            if menu_info and menu_info.get('status') == 'found':
                mx, my = menu_info['x'], menu_info['y']
                await tab.send(cdp.input_.dispatch_mouse_event(
                    type_="mousePressed", x=mx, y=my, button=cdp.input_.MouseButton.LEFT, click_count=1))
                await asyncio.sleep(0.05)
                await tab.send(cdp.input_.dispatch_mouse_event(
                    type_="mouseReleased", x=mx, y=my, button=cdp.input_.MouseButton.LEFT, click_count=1))
                break
            await asyncio.sleep(0.5)
        else:
            self._log("⚠️ Settings menu not found", tab_id)
            await tab.send(cdp.input_.dispatch_key_event(type_="keyDown", key="Escape"))
            return False
        
        await asyncio.sleep(1.5)
        
        # Step 3: Click "Hành vi" / "Behavior" tab
        await tab.evaluate("""
            (function() {
                var dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return;
                var buttons = dialog.querySelectorAll('button');
                for (var btn of buttons) {
                    var text = (btn.textContent || '').trim();
                    if (text.includes('Hành vi') || text.includes('Behavior')) {
                        btn.click(); return;
                    }
                }
            })()
        """)
        await asyncio.sleep(1)
        
        # Step 4: Toggle off auto video
        result = await tab.evaluate("""
            (function() {
                var dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return {error: 'no dialog'};
                var switches = dialog.querySelectorAll('button[role="switch"]');
                for (var sw of switches) {
                    var row = sw.closest('.flex') || sw.parentElement;
                    var labelId = sw.getAttribute('aria-labelledby');
                    var text = '';
                    if (labelId) { var el = document.getElementById(labelId); if (el) text = el.textContent; }
                    if (!text && row) text = row.textContent || '';
                    if (text.includes('Video Tự Động') || text.includes('Auto Video') ||
                        text.includes('Tạo Video') || text.includes('Generate Video')) {
                        if (sw.getAttribute('data-state') === 'checked') {
                            sw.click();
                            return {toggled: true};
                        }
                        return {toggled: false, msg: 'already off'};
                    }
                }
                return {error: 'switch not found'};
            })()
        """)
        self._log(f"   Auto video toggle: {result}", tab_id)
        
        # Step 5: Close dialog
        await asyncio.sleep(0.5)
        await tab.evaluate("""
            (function() {
                var dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return;
                var close = dialog.querySelector('button[aria-label="Close"]') ||
                            dialog.querySelector('button[aria-label="Đóng"]');
                if (!close) {
                    var btns = dialog.querySelectorAll('button');
                    for (var b of btns) {
                        if (b.querySelector('svg.lucide-x') || 
                            (b.querySelector('.sr-only') && ['Đóng','Close'].includes(b.querySelector('.sr-only').textContent.trim()))) {
                            close = b; break;
                        }
                    }
                }
                if (close) close.click();
            })()
        """)
        await asyncio.sleep(1)
        
        self._auto_video_disabled = True
        self._log("✅ Auto video disabled", tab_id)
        return True
    
    async def _upload_image_on_tab(self, tab, image_path: str, tab_id: int) -> bool:
        """Upload ảnh bằng CDP DOM.setFileInputFiles"""
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            self._log(f"❌ Image not found: {abs_path}", tab_id)
            return False
        
        self._log(f"📤 Uploading: {os.path.basename(abs_path)}", tab_id)
        
        # Tìm file input
        file_input_info = await tab.evaluate("""
            (function() {
                var inputs = document.querySelectorAll('input[type="file"]');
                return inputs.length > 0 ? {found: true, count: inputs.length} : {found: false};
            })()
        """)
        
        if not file_input_info or not file_input_info.get('found'):
            # Click upload button to trigger file input creation
            await tab.evaluate("""
                (function() {
                    var btns = document.querySelectorAll('button');
                    for (var btn of btns) {
                        var label = btn.getAttribute('aria-label') || btn.textContent || '';
                        if (label.includes('Tải lên hình ảnh') || label.includes('Upload')) {
                            btn.click(); return 'clicked';
                        }
                    }
                })()
            """)
            await asyncio.sleep(1)
            file_input_info = await tab.evaluate("""
                (function() {
                    var inputs = document.querySelectorAll('input[type="file"]');
                    return inputs.length > 0 ? {found: true} : {found: false};
                })()
            """)
        
        if not file_input_info or not file_input_info.get('found'):
            self._log("❌ Cannot find file input", tab_id)
            return False
        
        # Get node ID and set file
        doc = await tab.send(cdp.dom.get_document())
        file_node_id = await tab.send(cdp.dom.query_selector(doc.node_id, 'input[type="file"]'))
        if not file_node_id:
            self._log("❌ Cannot get file input node ID", tab_id)
            return False
        
        await tab.send(cdp.dom.set_file_input_files(files=[abs_path], node_id=file_node_id))
        self._log("✅ File uploaded via CDP", tab_id)
        await asyncio.sleep(3)
        return True
    
    async def _wait_for_post_redirect(self, tab, tab_id: int, timeout: int = 30) -> Optional[str]:
        """Chờ redirect từ /imagine → /imagine/post/{uuid} sau upload ảnh"""
        pattern = r'/imagine/post/([a-f0-9-]{36})'
        for i in range(timeout):
            if not self._running:
                return None
            url = await tab.evaluate("window.location.href")
            match = re.search(pattern, url)
            if match:
                return match.group(1)
            await asyncio.sleep(1)
            if i % 5 == 0:
                self._log(f"   Waiting for redirect... ({i}s)", tab_id)
        return None
    
    async def _fill_prompt_and_submit_on_post_page(self, tab, prompt: str, settings: VideoSettings, tab_id: int) -> bool:
        """
        Post page flow (sau upload ảnh):
        1. Fill prompt vào TEXTAREA
        2. Click "Tùy chọn Video" → mở settings panel
        3. Chọn settings (duration, resolution) — KHÔNG có aspect ratio trên post page
        4. Click "Tạo video" (CDP click) — đây là nút submit
        """
        # Step 1: Fill prompt
        escaped = prompt.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
        fill_result = await tab.evaluate(f"""
            (function() {{
                var textarea = document.querySelector('textarea');
                if (textarea) {{
                    textarea.focus();
                    var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    nativeSet.call(textarea, '{escaped}');
                    textarea.dispatchEvent(new Event('input', {{bubbles: true}}));
                    textarea.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled_textarea';
                }}
                var editor = document.querySelector('div.tiptap.ProseMirror') ||
                             document.querySelector('div[contenteditable="true"]');
                if (editor) {{
                    editor.focus();
                    editor.innerHTML = '<p>{escaped}</p>';
                    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                    return 'filled_prosemirror';
                }}
                return 'no_editor';
            }})()
        """)
        self._log(f"   Prompt: {fill_result}", tab_id)
        if 'no_editor' in fill_result:
            return False
        await asyncio.sleep(1)
        
        # Step 2: Click "Tùy chọn Video" button (CDP click for Radix UI)
        btn_pos = await tab.evaluate("""
            (function() {
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var label = b.getAttribute('aria-label') || '';
                    if (label === 'Tùy chọn Video' || label === 'Video options' || label === 'Video Options') {
                        var rect = b.getBoundingClientRect();
                        return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
                return {found: false};
            })()
        """)
        
        if btn_pos and btn_pos.get('found'):
            bx, by = btn_pos['x'], btn_pos['y']
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mousePressed", x=bx, y=by, button=cdp.input_.MouseButton.LEFT, click_count=1))
            await asyncio.sleep(0.05)
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mouseReleased", x=bx, y=by, button=cdp.input_.MouseButton.LEFT, click_count=1))
            self._log("   Tùy chọn Video: opened", tab_id)
            await asyncio.sleep(1.5)
            
            # Step 3: Select settings (duration + resolution only, NO aspect ratio on post page)
            # Settings buttons are inside a Radix popover panel
            # Use JS click (not CDP) for toggle buttons inside popover, then verify
            duration_label = f"{settings.video_length}s"
            resolution_label = settings.resolution
            
            for label in [duration_label, resolution_label]:
                # First try: find and JS click within popover panel
                click_result = await tab.evaluate(f"""
                    (function() {{
                        // Find popover panel
                        var popover = document.querySelector('[data-radix-popper-content-wrapper]');
                        if (!popover) {{
                            var panels = document.querySelectorAll('[data-state="open"]');
                            for (var p of panels) {{
                                if (p.querySelectorAll('button').length >= 2) {{ popover = p; break; }}
                            }}
                        }}
                        var scope = popover || document;
                        var buttons = scope.querySelectorAll('button');
                        for (var btn of buttons) {{
                            var ariaLabel = btn.getAttribute('aria-label') || '';
                            var text = btn.textContent.trim();
                            if (ariaLabel === '{label}' || text === '{label}') {{
                                btn.click();
                                return {{clicked: true, method: 'js', inPopover: !!popover}};
                            }}
                        }}
                        return {{clicked: false}};
                    }})()
                """)
                
                if click_result and click_result.get('clicked'):
                    self._log(f"   Setting {label}: ✅ (JS click, popover={click_result.get('inPopover')})", tab_id)
                else:
                    # Fallback: CDP click on any matching button
                    pos = await tab.evaluate(f"""
                        (function() {{
                            var buttons = document.querySelectorAll('button');
                            for (var btn of buttons) {{
                                var ariaLabel = btn.getAttribute('aria-label') || '';
                                var text = btn.textContent.trim();
                                if (ariaLabel === '{label}' || text === '{label}') {{
                                    var rect = btn.getBoundingClientRect();
                                    return {{found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2}};
                                }}
                            }}
                            return {{found: false}};
                        }})()
                    """)
                    if pos and pos.get('found'):
                        sx, sy = pos['x'], pos['y']
                        await tab.send(cdp.input_.dispatch_mouse_event(
                            type_="mousePressed", x=sx, y=sy, button=cdp.input_.MouseButton.LEFT, click_count=1))
                        await asyncio.sleep(0.05)
                        await tab.send(cdp.input_.dispatch_mouse_event(
                            type_="mouseReleased", x=sx, y=sy, button=cdp.input_.MouseButton.LEFT, click_count=1))
                        self._log(f"   Setting {label}: ✅ (CDP fallback)", tab_id)
                    else:
                        self._log(f"   Setting {label}: not found", tab_id)
                await asyncio.sleep(0.5)
                
                # Check if panel is still open, re-open if closed
                panel_open = await tab.evaluate("""
                    (function() {
                        var popover = document.querySelector('[data-radix-popper-content-wrapper]');
                        if (popover) return true;
                        var panels = document.querySelectorAll('[data-state="open"]');
                        for (var p of panels) {
                            if (p.querySelectorAll('button').length >= 2) return true;
                        }
                        return false;
                    })()
                """)
                if not panel_open:
                    self._log("   Panel closed, re-opening...", tab_id)
                    # Re-click "Tùy chọn Video"
                    reopen = await tab.evaluate("""
                        (function() {
                            var btns = document.querySelectorAll('button');
                            for (var b of btns) {
                                var label = b.getAttribute('aria-label') || '';
                                if (label === 'Tùy chọn Video' || label === 'Video options') {
                                    var rect = b.getBoundingClientRect();
                                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                                }
                            }
                            return {found: false};
                        })()
                    """)
                    if reopen and reopen.get('found'):
                        rx, ry = reopen['x'], reopen['y']
                        await tab.send(cdp.input_.dispatch_mouse_event(
                            type_="mousePressed", x=rx, y=ry, button=cdp.input_.MouseButton.LEFT, click_count=1))
                        await asyncio.sleep(0.05)
                        await tab.send(cdp.input_.dispatch_mouse_event(
                            type_="mouseReleased", x=rx, y=ry, button=cdp.input_.MouseButton.LEFT, click_count=1))
                        await asyncio.sleep(1)
        else:
            self._log("   ⚠️ 'Tùy chọn Video' not found, submitting directly", tab_id)
        
        # Step 4: Click "Tạo video" button (CDP click) — this IS the submit
        await asyncio.sleep(0.5)
        return await self._click_create_video_button(tab, tab_id)
    
    async def _click_create_video_button(self, tab, tab_id: int) -> bool:
        """Click nút 'Tạo video' bằng CDP mouse click"""
        create_pos = await tab.evaluate("""
            (function() {
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var label = b.getAttribute('aria-label') || '';
                    var text = (b.textContent || '').trim();
                    if (label === 'Tạo video' || label === 'Create video' || label === 'Generate video' ||
                        text === 'Tạo video' || text === 'Create video') {
                        var rect = b.getBoundingClientRect();
                        return {found: true, disabled: b.disabled, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
                return {found: false};
            })()
        """)
        
        if not create_pos or not create_pos.get('found'):
            self._log("❌ 'Tạo video' button not found", tab_id)
            return False
        
        # Wait for enabled
        if create_pos.get('disabled'):
            for w in range(15):
                await asyncio.sleep(1)
                create_pos = await tab.evaluate("""
                    (function() {
                        var btns = document.querySelectorAll('button');
                        for (var b of btns) {
                            var label = b.getAttribute('aria-label') || '';
                            if (label === 'Tạo video' || label === 'Create video') {
                                var rect = b.getBoundingClientRect();
                                return {found: true, disabled: b.disabled, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                            }
                        }
                        return {found: false};
                    })()
                """)
                if create_pos and not create_pos.get('disabled'):
                    break
        
        if not create_pos or create_pos.get('disabled'):
            self._log("❌ 'Tạo video' still disabled", tab_id)
            return False
        
        cx, cy = create_pos['x'], create_pos['y']
        await tab.send(cdp.input_.dispatch_mouse_event(
            type_="mousePressed", x=cx, y=cy, button=cdp.input_.MouseButton.LEFT, click_count=1))
        await asyncio.sleep(0.05)
        await tab.send(cdp.input_.dispatch_mouse_event(
            type_="mouseReleased", x=cx, y=cy, button=cdp.input_.MouseButton.LEFT, click_count=1))
        self._log("✅ Tạo video: CDP clicked!", tab_id)
        return True
    
    async def generate_image_to_video_on_tab(
        self,
        tab_id: int,
        prompt: str,
        image_path: str,
        settings: VideoSettings,
        retry_count: int = 0,
        custom_output_dir: Optional[str] = None,
        custom_filename: Optional[str] = None
    ) -> VideoTask:
        """
        Image-to-Video flow trên 1 tab:
        1. Navigate /imagine → disable auto-video (1 lần)
        2. Upload image → wait redirect → /imagine/post/{uuid}
        3. Fill prompt → Tùy chọn Video → settings → Tạo video
        4. Wait render → share → download
        Retry toàn bộ flow nếu bất kỳ bước nào thất bại (kể cả download).
        """
        MAX_RETRIES = 3
        task = VideoTask(
            account_email=self.account.email,
            prompt=prompt,
            image_path=image_path,
            settings=settings,
            status="creating"
        )
        
        if tab_id >= len(self.tabs):
            task.status = "failed"
            task.error_message = f"Invalid tab_id: {tab_id}"
            return task
        
        tab = self.tabs[tab_id]
        
        try:
            self.tab_ready[tab_id] = False
            
            # Step 1: Navigate to /imagine
            current_url = await tab.evaluate("window.location.href")
            if '/imagine' not in current_url or '/post/' in current_url:
                self._log("🔄 Navigating to /imagine...", tab_id)
                await tab.get(IMAGINE_URL)
                await asyncio.sleep(2)
            
            # Step 2: Disable auto-video (once per session)
            if not self._auto_video_disabled:
                await self._disable_auto_video_on_tab(tab, tab_id)
            
            # Step 3: Upload image
            self._log(f"📤 Uploading: {os.path.basename(image_path)}", tab_id)
            if not await self._upload_image_on_tab(tab, image_path, tab_id):
                task.status = "failed"
                task.error_message = "Upload failed"
                self.tab_ready[tab_id] = True
                return task
            
            # Step 4: Wait for redirect to /imagine/post/{uuid}
            self._log("⏳ Waiting for post redirect...", tab_id)
            upload_post_id = await self._wait_for_post_redirect(tab, tab_id, timeout=30)
            if not upload_post_id:
                if retry_count < MAX_RETRIES:
                    self._log("⚠️ No redirect, retrying...", tab_id)
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                    self.tab_ready[tab_id] = True
                    return await self.generate_image_to_video_on_tab(tab_id, prompt, image_path, settings, retry_count + 1, custom_output_dir, custom_filename)
                task.status = "failed"
                task.error_message = "No redirect after upload"
                self.tab_ready[tab_id] = True
                return task
            
            self._log(f"✅ Upload Post ID: {upload_post_id}", tab_id)
            await asyncio.sleep(2)
            
            # Step 5: Wait for editor, fill prompt, select settings, click Tạo video
            editor_found = False
            for w in range(10):
                has = await tab.evaluate("""
                    (function() {
                        return !!(document.querySelector('textarea') || 
                                  document.querySelector('div.tiptap.ProseMirror'));
                    })()
                """)
                if has:
                    editor_found = True
                    break
                await asyncio.sleep(1)
            
            if not editor_found:
                task.status = "failed"
                task.error_message = "Editor not found on post page"
                self.tab_ready[tab_id] = True
                return task
            
            self._log("✏️ Filling prompt + settings...", tab_id)
            if not await self._fill_prompt_and_submit_on_post_page(tab, prompt, settings, tab_id):
                if retry_count < MAX_RETRIES:
                    self._log("⚠️ Submit failed, retrying...", tab_id)
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                    self.tab_ready[tab_id] = True
                    return await self.generate_image_to_video_on_tab(tab_id, prompt, image_path, settings, retry_count + 1, custom_output_dir, custom_filename)
                task.status = "failed"
                task.error_message = "Failed to submit on post page"
                self.tab_ready[tab_id] = True
                return task
            
            await asyncio.sleep(3)
            
            # Step 6: Wait for new post ID (video generation creates new post)
            self._log("⏳ Waiting for video post ID...", tab_id)
            new_post_id = None
            for i in range(60):
                if not self._running:
                    break
                try:
                    url = await tab.evaluate("window.location.href")
                except Exception:
                    break
                match = re.search(r'/imagine/post/([a-f0-9-]{36})', url)
                if match:
                    pid = match.group(1)
                    if pid != upload_post_id:
                        new_post_id = pid
                        break
                await asyncio.sleep(1)
                if i % 10 == 0 and i > 0:
                    self._log(f"   Waiting... ({i}s)", tab_id)
            
            post_id = new_post_id or upload_post_id
            task.post_id = post_id
            task.media_url = VIDEO_DOWNLOAD_URL.format(post_id=post_id)
            self._log(f"✅ Post ID: {post_id}", tab_id)
            
            # Step 7: Wait for video render
            self._log("⏳ Waiting for video render...", tab_id)
            video_status = await self._wait_for_video_ready_on_tab(tab, tab_id, timeout=150)
            
            if video_status == 'rejected':
                if retry_count < MAX_RETRIES:
                    self._log("🔄 Video rejected, retrying...", tab_id)
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                    self.tab_ready[tab_id] = True
                    return await self.generate_image_to_video_on_tab(tab_id, prompt, image_path, settings, retry_count + 1, custom_output_dir, custom_filename)
                task.status = "failed"
                task.error_message = "Video rejected"
                self.tab_ready[tab_id] = True
                return task
            
            if video_status == 'ready':
                # Share + Download
                self._log("🔗 Creating share link...", tab_id)
                await self._click_share_button_on_tab(tab, tab_id)
                await asyncio.sleep(3)
                
                # Download với retry riêng (thử download lại 2 lần trước khi retry toàn bộ flow)
                self._log("📥 Downloading video...", tab_id)
                output_path = None
                for dl_attempt in range(3):
                    output_path = await self._download_video_on_tab(tab, task, tab_id, custom_output_dir, custom_filename)
                    if output_path:
                        break
                    if dl_attempt < 2:
                        self._log(f"⚠️ Download failed, retrying download ({dl_attempt + 1}/2)...", tab_id)
                        await asyncio.sleep(3)
                
                if output_path:
                    task.output_path = output_path
                    task.status = "completed"
                    task.completed_at = datetime.now()
                    task.user_data_dir = self._user_data_dir
                    task.account_cookies = self.account.cookies
                    self._log(f"✅ Downloaded: {os.path.basename(output_path)}", tab_id)
                else:
                    # Download thất bại sau 3 lần → retry toàn bộ flow
                    if retry_count < MAX_RETRIES:
                        self._log(f"❌ Download failed after 3 attempts, retrying full flow ({retry_count + 1}/{MAX_RETRIES})...", tab_id)
                        await tab.get(IMAGINE_URL)
                        await asyncio.sleep(2)
                        self.tab_ready[tab_id] = True
                        return await self.generate_image_to_video_on_tab(tab_id, prompt, image_path, settings, retry_count + 1, custom_output_dir, custom_filename)
                    task.status = "failed"
                    task.error_message = "Download failed after all retries"
                    self._log("❌ Download thất bại sau tất cả retries", tab_id)
            elif video_status == 'timeout':
                if retry_count < MAX_RETRIES:
                    self._log(f"⏰ Render timeout, retrying ({retry_count + 1}/{MAX_RETRIES})...", tab_id)
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                    self.tab_ready[tab_id] = True
                    return await self.generate_image_to_video_on_tab(tab_id, prompt, image_path, settings, retry_count + 1, custom_output_dir, custom_filename)
                task.status = "failed"
                task.error_message = "Render timeout after all retries"
                self._log("❌ Render timeout sau tất cả retries", tab_id)
            elif video_status == 'stopped':
                task.status = "failed"
                task.error_message = "Generation stopped"
                self.tab_ready[tab_id] = True
                return task
            
            # Navigate back for next
            self._log("🔄 Ready for next video...", tab_id)
            await tab.get(IMAGINE_URL)
            await asyncio.sleep(1.5)
            self.tab_ready[tab_id] = True
            return task
            
        except Exception as e:
            self._log(f"❌ Error: {e}", tab_id)
            import traceback
            traceback.print_exc()
            # Retry on unexpected exception
            if retry_count < MAX_RETRIES:
                self._log(f"🔄 Retrying after error ({retry_count + 1}/{MAX_RETRIES})...", tab_id)
                try:
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                except:
                    pass
                self.tab_ready[tab_id] = True
                return await self.generate_image_to_video_on_tab(tab_id, prompt, image_path, settings, retry_count + 1, custom_output_dir, custom_filename)
            task.status = "failed"
            task.error_message = str(e)
            self.tab_ready[tab_id] = True
            return task
    
    # ==================== Original Text-to-Video Methods ====================
    
    async def generate_on_tab(
        self,
        tab_id: int,
        prompt: str,
        settings: VideoSettings,
        retry_count: int = 0,
        custom_output_dir: Optional[str] = None,
        custom_filename: Optional[str] = None
    ) -> VideoTask:
        """Generate video on a specific tab with retry support"""
        MAX_RETRIES = 3
        
        task = VideoTask(
            account_email=self.account.email,
            prompt=prompt,
            settings=settings,
            status="creating"
        )
        
        if tab_id >= len(self.tabs):
            task.status = "failed"
            task.error_message = f"Invalid tab_id: {tab_id}"
            return task
        
        tab = self.tabs[tab_id]
        
        try:
            # Mark tab as busy
            self.tab_ready[tab_id] = False
            
            # Step 1: Make sure we're on /imagine
            current_url = await tab.evaluate("window.location.href")
            if '/imagine' not in current_url or '/post/' in current_url:
                self._log("🔄 Navigating to /imagine...", tab_id)
                await tab.get(IMAGINE_URL)
                await asyncio.sleep(2)
            
            # Step 2: Select Video mode and apply settings
            self._log("🎬 Selecting Video mode...", tab_id)
            await self._select_video_mode_on_tab(tab, tab_id, settings)
            await asyncio.sleep(1.5)
            
            # Step 3: Enter prompt
            self._log(f"✏️ Entering prompt: {prompt[:30]}...", tab_id)
            if not await self._enter_prompt_on_tab(tab, prompt, tab_id):
                task.status = "failed"
                task.error_message = "Failed to enter prompt"
                self.tab_ready[tab_id] = True
                return task
            
            await asyncio.sleep(0.5)
            
            # Step 4: Submit
            self._log("📤 Submitting...", tab_id)
            await self._submit_prompt_on_tab(tab, tab_id)
            await asyncio.sleep(2)
            
            # Step 5: Wait for post ID
            self._log("⏳ Waiting for post ID...", tab_id)
            post_id = await self._wait_for_post_id_on_tab(tab, timeout=30)
            
            if not post_id:
                # RETRY LOGIC: If failed to get post ID, retry once
                if retry_count < MAX_RETRIES:
                    self._log(f"⚠️ No post ID, retrying ({retry_count + 1}/{MAX_RETRIES})...", tab_id)
                    # Navigate back to /imagine and retry
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                    self.tab_ready[tab_id] = True
                    return await self.generate_on_tab(tab_id, prompt, settings, retry_count + 1, custom_output_dir, custom_filename)
                
                task.status = "failed"
                task.error_message = "Could not get post ID"
                self.tab_ready[tab_id] = True
                return task
            
            task.post_id = post_id
            task.media_url = VIDEO_DOWNLOAD_URL.format(post_id=post_id)
            
            self._log(f"✅ Post ID: {post_id}", tab_id)
            
            # Step 6: STAY on post page and wait for video to render
            self._log("⏳ Waiting for video to render...", tab_id)
            video_status = await self._wait_for_video_ready_on_tab(tab, tab_id, timeout=150)
            
            # Handle rejected video - retry with same prompt
            if video_status == 'rejected':
                if retry_count < MAX_RETRIES:
                    self._log(f"🔄 Video bị từ chối, thử lại ({retry_count + 1}/{MAX_RETRIES})...", tab_id)
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                    self.tab_ready[tab_id] = True
                    return await self.generate_on_tab(tab_id, prompt, settings, retry_count + 1, custom_output_dir, custom_filename)
                else:
                    task.status = "failed"
                    task.error_message = "Video bị từ chối sau khi thử lại"
                    self.tab_ready[tab_id] = True
                    return task
            
            if video_status == 'ready':
                # Step 7: Click share button to create share link (makes video downloadable)
                self._log("🔗 Creating share link...", tab_id)
                await self._click_share_button_on_tab(tab, tab_id)
                await asyncio.sleep(3)
                
                # Step 8: Download video — retry download 3 lần trước khi retry toàn bộ flow
                self._log("📥 Downloading video...", tab_id)
                output_path = None
                for dl_attempt in range(3):
                    output_path = await self._download_video_on_tab(tab, task, tab_id, custom_output_dir, custom_filename)
                    if output_path:
                        break
                    if dl_attempt < 2:
                        self._log(f"⚠️ Download failed, retrying download ({dl_attempt + 1}/2)...", tab_id)
                        await asyncio.sleep(3)
                
                if output_path:
                    task.output_path = output_path
                    task.status = "completed"
                    task.completed_at = datetime.now()
                    task.user_data_dir = self._user_data_dir
                    task.account_cookies = self.account.cookies
                    self._log(f"✅ Downloaded: {os.path.basename(output_path)}", tab_id)
                else:
                    # Download thất bại → retry toàn bộ generation flow
                    if retry_count < MAX_RETRIES:
                        self._log(f"❌ Download failed after 3 attempts, retrying full flow ({retry_count + 1}/{MAX_RETRIES})...", tab_id)
                        await tab.get(IMAGINE_URL)
                        await asyncio.sleep(2)
                        self.tab_ready[tab_id] = True
                        return await self.generate_on_tab(tab_id, prompt, settings, retry_count + 1, custom_output_dir, custom_filename)
                    task.status = "failed"
                    task.error_message = "Download failed after all retries"
                    self._log("❌ Download thất bại sau tất cả retries", tab_id)
            elif video_status == 'timeout':
                # RETRY on timeout: refresh tab and regenerate
                if retry_count < MAX_RETRIES:
                    self._log(f"⏰ Render timeout (>150s), retrying ({retry_count + 1}/{MAX_RETRIES})...", tab_id)
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                    self.tab_ready[tab_id] = True
                    return await self.generate_on_tab(tab_id, prompt, settings, retry_count + 1, custom_output_dir, custom_filename)
                else:
                    task.status = "failed"
                    task.error_message = "Render timeout after all retries"
                    self._log("❌ Render timeout sau tất cả retries", tab_id)
            elif video_status == 'stopped':
                task.status = "failed"
                task.error_message = "Generation stopped"
                self.tab_ready[tab_id] = True
                return task
            
            # Save metadata nếu chưa set status (trường hợp completed đã set ở trên)
            if task.status not in ("completed", "failed"):
                task.status = "failed"
                task.error_message = "Unknown error"
            
            # Step 9: Navigate back to /imagine for next video
            self._log("🔄 Ready for next video...", tab_id)
            await tab.get(IMAGINE_URL)
            await asyncio.sleep(1.5)
            
            # Mark tab as ready
            self.tab_ready[tab_id] = True
            
            return task
            
        except Exception as e:
            self._log(f"❌ Error: {e}", tab_id)
            import traceback
            traceback.print_exc()
            # Retry on unexpected exception
            if retry_count < MAX_RETRIES:
                self._log(f"🔄 Retrying after error ({retry_count + 1}/{MAX_RETRIES})...", tab_id)
                try:
                    await tab.get(IMAGINE_URL)
                    await asyncio.sleep(2)
                except:
                    pass
                self.tab_ready[tab_id] = True
                return await self.generate_on_tab(tab_id, prompt, settings, retry_count + 1, custom_output_dir, custom_filename)
            task.status = "failed"
            task.error_message = str(e)
            self.tab_ready[tab_id] = True
            return task
    
    async def _wait_for_video_ready_on_tab(self, tab, tab_id: int, timeout: int = 150) -> str:
        """
        Wait for video to be ready on post page.
        Returns:
            'ready' - video is ready for download
            'rejected' - video was rejected (eye-off icon visible)
            'timeout' - timeout waiting for video
            'stopped' - generation was stopped
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if not self._running:
                return 'stopped'
            
            status = await tab.evaluate("""
                (function() {
                    // Check for rejected video (eye-off icon)
                    var eyeOffIcon = document.querySelector('svg.lucide-eye-off');
                    if (eyeOffIcon) {
                        return {ready: false, type: 'rejected', rejected: true};
                    }
                    
                    // Find the download button
                    var downloadBtn = document.querySelector('button[aria-label="Tải xuống"]');
                    if (!downloadBtn) {
                        var icons = document.querySelectorAll('svg.lucide-download');
                        for (var icon of icons) {
                            var btn = icon.closest('button');
                            if (btn) {
                                downloadBtn = btn;
                                break;
                            }
                        }
                    }
                    
                    if (!downloadBtn) {
                        return {ready: false, type: 'no_download_btn'};
                    }
                    
                    // Find parent container with border class
                    var container = downloadBtn.closest('div.flex.flex-row.border');
                    if (!container) {
                        container = downloadBtn.parentElement;
                        while (container && !container.classList.contains('border')) {
                            container = container.parentElement;
                        }
                    }
                    
                    if (!container) {
                        return {ready: false, type: 'no_container'};
                    }
                    
                    // Check for generating state
                    var classes = container.className || '';
                    if (classes.includes('opacity-50') || classes.includes('pointer-events-none')) {
                        return {ready: false, type: 'generating'};
                    }
                    
                    return {ready: true, type: 'ready'};
                })()
            """)
            
            # Check for rejected video
            if status and status.get('rejected'):
                self._log("⚠️ Video bị từ chối (eye-off icon)", tab_id)
                return 'rejected'
            
            if status and status.get('ready'):
                self._log("✅ Video ready!", tab_id)
                return 'ready'
            
            elapsed = int(time.time() - start_time)
            if elapsed % 30 == 0 and elapsed > 0:
                self._log(f"⏳ Rendering... ({elapsed}s)", tab_id)
            
            await asyncio.sleep(3)
        
        return 'timeout'
    
    async def _click_share_button_on_tab(self, tab, tab_id: int) -> bool:
        """Click share button to create share link"""
        try:
            result = await tab.evaluate("""
                (function() {
                    var shareBtn = document.querySelector('button[aria-label="Tạo link chia sẻ"]');
                    
                    if (!shareBtn) {
                        var icons = document.querySelectorAll('svg.lucide-share');
                        for (var icon of icons) {
                            var btn = icon.closest('button');
                            if (btn) {
                                shareBtn = btn;
                                break;
                            }
                        }
                    }
                    
                    if (shareBtn && !shareBtn.disabled) {
                        shareBtn.click();
                        return {clicked: true};
                    }
                    return {clicked: false};
                })()
            """)
            return result and result.get('clicked', False)
        except Exception as e:
            self._log(f"⚠️ Share click error: {e}", tab_id)
            return False
    
    async def _download_video_on_tab(self, tab, task: VideoTask, tab_id: int, custom_output_dir: Optional[str] = None, custom_filename: Optional[str] = None) -> Optional[str]:
        """
        Smart CDP download với retry.
        
        Strategy:
        - Mở tab mới → set_download_behavior → navigate to download URL
        - Check file mỗi 2s (nhanh hơn 5s cũ)
        - Nếu không thấy file sau 30s → close tab, thử lại (tối đa 3 CDP attempts)
        - Mỗi attempt thử cả URL gốc và URL có &dl=1
        - Tìm file theo post_id pattern, không dùng newest
        
        Args:
            custom_output_dir: Custom output directory (default: OUTPUT_DIR)
            custom_filename: Custom filename (default: {post_id}.mp4)
        """
        import glob
        
        video_url = task.media_url
        post_id = task.post_id
        if not video_url or not post_id:
            self._log("⚠️ Missing video URL or post_id", tab_id)
            return None
        
        # Use custom output dir or default
        output_dir = Path(custom_output_dir) if custom_output_dir else OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Use custom filename or default to post_id.mp4
        filename = custom_filename if custom_filename else f"{post_id}.mp4"
        expected_file = output_dir / filename
        
        # Also check default Downloads folder (Chrome may download there)
        downloads_dir = Path.home() / "Downloads"
        search_dirs = [output_dir, downloads_dir] if output_dir != downloads_dir else [output_dir]
        
        # Nếu file đã tồn tại (từ attempt trước hoặc lần chạy trước), return luôn
        if expected_file.exists():
            size = os.path.getsize(expected_file)
            if size > 10000:
                self._log(f"✅ File already exists: {filename} ({size//1024}KB)", tab_id)
                return str(expected_file)
        
        # Cũng check file có chứa post_id trong tất cả search dirs
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for pattern in [f"*{post_id}*.mp4", f"*{post_id[:8]}*.mp4"]:
                matches = glob.glob(str(search_dir / pattern))
                for match_file in matches:
                    if os.path.exists(match_file):
                        size = os.path.getsize(match_file)
                        if size > 10000:
                            # Move to expected location
                            if match_file != str(expected_file):
                                try:
                                    import shutil
                                    shutil.move(match_file, str(expected_file))
                                    self._log(f"✅ File moved: {filename} ({size//1024}KB)", tab_id)
                                    return str(expected_file)
                                except Exception as e:
                                    self._log(f"✅ File found: {os.path.basename(match_file)} ({size//1024}KB)", tab_id)
                                    return match_file
                            else:
                                self._log(f"✅ File already exists: {filename} ({size//1024}KB)", tab_id)
                                return match_file
        
        MAX_CDP_ATTEMPTS = 3
        
        for attempt in range(MAX_CDP_ATTEMPTS):
            download_tab = None
            try:
                # Alternate giữa URL có dl=1 và không — đôi khi server respond khác nhau
                if attempt % 2 == 0:
                    dl_url = f"{video_url}&dl=1" if '?' in video_url else f"{video_url}?dl=1"
                else:
                    dl_url = video_url
                
                if attempt > 0:
                    self._log(f"🔄 CDP download attempt {attempt + 1}/{MAX_CDP_ATTEMPTS}...", tab_id)
                else:
                    self._log(f"   Downloading video...", tab_id)
                
                # Mở tab mới → navigate để lấy __cf_bm cookie
                download_tab = await self.browser.get(video_url, new_tab=True)
                await asyncio.sleep(2)
                
                # Set download behavior to custom output dir
                try:
                    await download_tab.send(cdp.browser.set_download_behavior(
                        behavior="allow",
                        download_path=str(output_dir.absolute())
                    ))
                except Exception as e:
                    self._log(f"   set_download_behavior error: {e}", tab_id)
                
                # Trigger download
                self._log(f"   Triggering download...", tab_id)
                await download_tab.get(dl_url)
                
                # Check file nhanh — mỗi 2s, timeout 30s per attempt
                found_path = await self._wait_for_download_file(post_id, tab_id, timeout=30, output_dir=output_dir, expected_filename=filename)
                
                # Close download tab
                try:
                    await download_tab.close()
                except:
                    pass
                download_tab = None
                
                if found_path:
                    self._log(f"✅ Downloaded: {os.path.basename(found_path)}", tab_id)
                    return found_path
                
                # Attempt failed, sẽ retry
                if attempt < MAX_CDP_ATTEMPTS - 1:
                    self._log(f"⚠️ Download not found after 30s, will retry...", tab_id)
                    await asyncio.sleep(2)
                    
            except Exception as e:
                self._log(f"⚠️ Download attempt {attempt + 1} error: {e}", tab_id)
                if download_tab:
                    try:
                        await download_tab.close()
                    except:
                        pass
                if attempt < MAX_CDP_ATTEMPTS - 1:
                    await asyncio.sleep(2)
        
        self._log(f"❌ Download failed after {MAX_CDP_ATTEMPTS} CDP attempts", tab_id)
        return None
    
    async def _wait_for_download_file(self, post_id: str, tab_id: int, timeout: int = 30, output_dir: Path = None, expected_filename: str = None) -> Optional[str]:
        """
        Check file download mỗi 2s, return path nếu tìm thấy.
        Tìm theo post_id pattern — tránh lẫn giữa các tab.
        Cũng check file mới nhất trong folder nếu không tìm thấy theo post_id.
        
        Args:
            output_dir: Custom output directory (default: OUTPUT_DIR)
            expected_filename: Expected filename to rename to (default: {post_id}.mp4)
        """
        import glob
        
        # Use custom output dir or default
        out_dir = output_dir if output_dir else OUTPUT_DIR
        filename = expected_filename if expected_filename else f"{post_id}.mp4"
        expected_file = out_dir / filename
        
        # Also check default Downloads folder (Chrome may download there)
        downloads_dir = Path.home() / "Downloads"
        search_dirs = [out_dir, downloads_dir] if out_dir != downloads_dir else [out_dir]
        
        elapsed = 0
        last_log = 0
        start_time = time.time()
        
        while elapsed < timeout:
            await asyncio.sleep(2)
            elapsed += 2
            
            # Check exact expected file
            if expected_file.exists():
                size = os.path.getsize(expected_file)
                if size > 10000:
                    # Chờ thêm 1s rồi check size stable
                    await asyncio.sleep(1)
                    new_size = os.path.getsize(expected_file)
                    if new_size == size:
                        return str(expected_file)
                    # File đang download, chờ tiếp
                    continue
            
            # Check in all search directories
            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue
                    
                # Check nếu có file .crdownload (đang download)
                crdownload = search_dir / f"{filename}.crdownload"
                crdownload_postid = search_dir / f"{post_id}.mp4.crdownload"
                if crdownload.exists() or crdownload_postid.exists():
                    # File đang download, chờ tiếp
                    if elapsed - last_log >= 10:
                        self._log(f"   File downloading... ({elapsed}s)", tab_id)
                        last_log = elapsed
                    continue
                
                # Fallback: tìm file có chứa post_id
                for pattern in [f"*{post_id}*", f"*{post_id[:8]}*"]:
                    matches = glob.glob(str(search_dir / pattern))
                    for match_file in matches:
                        if match_file.endswith('.mp4') and os.path.exists(match_file):
                            size = os.path.getsize(match_file)
                            if size > 10000:
                                await asyncio.sleep(1)
                                if os.path.getsize(match_file) == size:
                                    # Move to expected location if different
                                    if match_file != str(expected_file):
                                        try:
                                            import shutil
                                            # Ensure target dir exists
                                            expected_file.parent.mkdir(parents=True, exist_ok=True)
                                            shutil.move(match_file, str(expected_file))
                                            return str(expected_file)
                                        except Exception as e:
                                            self._log(f"   Move error: {e}", tab_id)
                                            return match_file
                                    return match_file
            
            # Fallback 2: Check file mới nhất được tạo sau khi bắt đầu download
            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue
                try:
                    mp4_files = list(search_dir.glob("*.mp4"))
                    recent_files = [f for f in mp4_files if f.stat().st_mtime > start_time]
                    if recent_files:
                        # Lấy file mới nhất
                        newest = max(recent_files, key=lambda f: f.stat().st_mtime)
                        size = os.path.getsize(newest)
                        if size > 10000:
                            await asyncio.sleep(1)
                            if os.path.getsize(newest) == size:
                                # Move về đúng vị trí expected nếu khác
                                if str(newest) != str(expected_file):
                                    try:
                                        import shutil
                                        expected_file.parent.mkdir(parents=True, exist_ok=True)
                                        shutil.move(str(newest), str(expected_file))
                                        return str(expected_file)
                                    except Exception as e:
                                        self._log(f"   Move error: {e}", tab_id)
                                        return str(newest)
                                return str(newest)
                except Exception as e:
                    pass
            
            # Log mỗi 10s
            if elapsed - last_log >= 10:
                self._log(f"   Waiting for download... ({elapsed}s)", tab_id)
                last_log = elapsed
        
        return None
    
    async def _select_video_mode_on_tab(self, tab, tab_id: int, settings: VideoSettings = None) -> None:
        """Select Video mode and apply settings on a specific tab"""
        try:
            # Wait for trigger button
            trigger_info = None
            for wait_attempt in range(10):
                await asyncio.sleep(0.5)
                trigger_info = await tab.evaluate("""
                    (function() {
                        var trigger = document.querySelector('#model-select-trigger');
                        if (trigger) {
                            var rect = trigger.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return {
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                    found: true
                                };
                            }
                        }
                        return {found: false};
                    })()
                """)
                if trigger_info and trigger_info.get('found'):
                    break
            
            if not trigger_info or not trigger_info.get('found'):
                self._log("⚠️ Trigger not found", tab_id)
                return
            
            # Click trigger with JS
            await tab.evaluate("""
                (function() {
                    var trigger = document.querySelector('#model-select-trigger');
                    if (trigger) trigger.click();
                })()
            """)
            await asyncio.sleep(1)
            
            # Check menu state
            menu_state = await tab.evaluate("""
                (function() {
                    var menu = document.querySelector('[data-radix-menu-content][data-state="open"]') ||
                               document.querySelector('[role="menu"][data-state="open"]');
                    return menu ? {open: true} : {open: false};
                })()
            """)
            
            # If menu not open, try CDP click
            if not menu_state.get('open'):
                x, y = trigger_info['x'], trigger_info['y']
                await tab.send(cdp.input_.dispatch_mouse_event(
                    type_="mousePressed", x=x, y=y,
                    button=cdp.input_.MouseButton.LEFT, click_count=1
                ))
                await asyncio.sleep(0.1)
                await tab.send(cdp.input_.dispatch_mouse_event(
                    type_="mouseReleased", x=x, y=y,
                    button=cdp.input_.MouseButton.LEFT, click_count=1
                ))
                await asyncio.sleep(1)
            
            # Apply video settings BEFORE clicking Video option
            if settings:
                await self._apply_video_settings_in_menu(tab, tab_id, settings)
                await asyncio.sleep(0.5)
            
            # Click Video option — semantic: role="menuitem" chứa text "Video"
            await tab.evaluate("""
                (function() {
                    var menu = document.querySelector('[role="menu"][data-state="open"]');
                    var scope = menu || document;
                    var items = scope.querySelectorAll('[role="menuitem"]');
                    for (var item of items) {
                        var spans = item.querySelectorAll('span');
                        for (var span of spans) {
                            var text = span.textContent.trim();
                            if (text === 'Video') {
                                item.click();
                                return 'clicked Video';
                            }
                        }
                    }
                    return 'not found';
                })()
            """)
            await asyncio.sleep(0.5)
            
        except Exception as e:
            self._log(f"⚠️ Mode select error: {e}", tab_id)
    
    async def _apply_video_settings_in_menu(self, tab, tab_id: int, settings: VideoSettings) -> None:
        """Apply video settings (duration, resolution, aspect ratio) in the open menu.
        
        Grok menu re-render sau mỗi click → cần chờ menu ổn định trước khi click tiếp.
        Dùng JS click + wait for menu re-open pattern.
        """
        try:
            duration_label = f"{settings.video_length}s"
            resolution_label = settings.resolution
            aspect_label = settings.aspect_ratio
            
            self._log(f"⚙️ Applying settings: {duration_label}, {resolution_label}, {aspect_label}", tab_id)
            
            async def wait_for_menu_open(timeout: float = 3.0) -> bool:
                """Chờ menu [data-state='open'] xuất hiện sau re-render."""
                for _ in range(int(timeout / 0.3)):
                    is_open = await tab.evaluate("""
                        (function() {
                            var menu = document.querySelector('[role="menu"][data-state="open"]');
                            return menu ? true : false;
                        })()
                    """)
                    if is_open:
                        return True
                    await asyncio.sleep(0.3)
                return False
            
            async def click_setting_button(aria_label: str, name: str) -> bool:
                """Click button bằng aria-label trong menu đang mở. Retry nếu menu chưa sẵn sàng."""
                for attempt in range(8):
                    result = await tab.evaluate("""
                        (function(targetLabel) {
                            var menu = document.querySelector('[role="menu"][data-state="open"]');
                            if (!menu) return {status: 'no_menu'};
                            var buttons = menu.querySelectorAll('button[aria-label]');
                            for (var btn of buttons) {
                                if (btn.getAttribute('aria-label') === targetLabel) {
                                    btn.click();
                                    return {status: 'clicked', label: targetLabel};
                                }
                            }
                            return {status: 'not_found', count: buttons.length};
                        })""" + f"('{aria_label}')")
                    
                    if result and result.get('status') == 'clicked':
                        self._log(f"   {name}: {aria_label} ✓", tab_id)
                        return True
                    
                    # Menu chưa mở hoặc button chưa render → chờ
                    await asyncio.sleep(0.5)
                
                self._log(f"   {name}: {aria_label} not found", tab_id)
                return False
            
            # 1. Duration — click xong Grok re-render menu (đóng rồi mở lại)
            await click_setting_button(duration_label, "Duration")
            await asyncio.sleep(1.5)  # Chờ menu re-render xong
            
            # Menu có thể đã đóng sau click duration → cần mở lại
            menu_open = await wait_for_menu_open(2.0)
            if not menu_open:
                # Re-open menu bằng click trigger
                self._log(f"   Menu closed after duration click, re-opening...", tab_id)
                await tab.evaluate("""
                    (function() {
                        var trigger = document.querySelector('#model-select-trigger');
                        if (trigger) trigger.click();
                    })()
                """)
                await asyncio.sleep(1.0)
                await wait_for_menu_open(2.0)
            
            # 2. Resolution
            await click_setting_button(resolution_label, "Resolution")
            await asyncio.sleep(1.0)
            
            menu_open = await wait_for_menu_open(2.0)
            if not menu_open:
                self._log(f"   Menu closed after resolution click, re-opening...", tab_id)
                await tab.evaluate("""
                    (function() {
                        var trigger = document.querySelector('#model-select-trigger');
                        if (trigger) trigger.click();
                    })()
                """)
                await asyncio.sleep(1.0)
                await wait_for_menu_open(2.0)
            
            # 3. Aspect ratio
            await click_setting_button(aspect_label, "Aspect")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            self._log(f"⚠️ Settings error: {e}", tab_id)
    
    async def _enter_prompt_on_tab(self, tab, prompt: str, tab_id: int) -> bool:
        """Enter prompt on a specific tab"""
        try:
            escaped_prompt = prompt.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
            
            js = f"""
            (function() {{
                var editor = document.querySelector('div.tiptap.ProseMirror') ||
                             document.querySelector('div[contenteditable="true"]') ||
                             document.querySelector('.ProseMirror') ||
                             document.querySelector('textarea');
                
                if (!editor) return 'no_editor';
                
                editor.focus();
                
                if (editor.tagName === 'TEXTAREA') {{
                    editor.value = '{escaped_prompt}';
                    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                    return 'textarea_filled';
                }}
                
                editor.innerHTML = '<p>{escaped_prompt}</p>';
                editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                return 'editor_filled';
            }})()
            """
            result = await tab.evaluate(js)
            return 'filled' in result
        except Exception as e:
            self._log(f"⚠️ Prompt error: {e}", tab_id)
            return False
    
    async def _submit_prompt_on_tab(self, tab, tab_id: int) -> None:
        """Submit prompt on a specific tab"""
        try:
            js = """
            (function() {
                var btn = document.querySelector('button[type="submit"]');
                if (!btn) {
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var label = b.getAttribute('aria-label') || b.textContent || '';
                        if (label.includes('Send') || label.includes('Gửi') || label.includes('Submit')) {
                            btn = b;
                            break;
                        }
                    }
                }
                if (btn && !btn.disabled) {
                    btn.click();
                    return 'clicked';
                }
                return 'no_button';
            })()
            """
            await tab.evaluate(js)
        except Exception as e:
            self._log(f"⚠️ Submit error: {e}", tab_id)
    
    async def _wait_for_post_id_on_tab(self, tab, timeout: int = 30) -> Optional[str]:
        """Wait for post ID on a specific tab"""
        pattern = r'/imagine/post/([a-f0-9-]{36})'
        
        for _ in range(timeout):
            if not self._running:
                return None
            url = await tab.evaluate("window.location.href")
            match = re.search(pattern, url)
            if match:
                return match.group(1)
            await asyncio.sleep(1)
        return None
    
    async def generate_batch(
        self,
        prompts,
        settings: VideoSettings,
        on_task_complete: Optional[Callable] = None,
        max_retries: int = 3,
        output_dir: Optional[str] = None
    ) -> List[VideoTask]:
        """
        Generate multiple videos concurrently using all tabs.
        
        Args:
            prompts: List of str (text-to-video) OR List of Tuple (prompt, image_path, subfolder, stt)
            settings: Video settings
            on_task_complete: Callback when each task completes
            max_retries: Number of retries for failed tasks (default 3)
            output_dir: Base output directory for videos
        
        Retry logic:
        - Task status "failed" → retry
        - Task status "completed" nhưng không có output_path → coi như failed, retry
        """
        results: List[VideoTask] = []
        
        # Normalize prompts to list of (prompt, image_path, subfolder, stt)
        normalized = []
        for p in prompts:
            if isinstance(p, tuple):
                if len(p) == 4:
                    # (prompt, image_path, subfolder, stt)
                    normalized.append(p)
                elif len(p) == 2:
                    # Legacy (prompt, image_path) → add None subfolder and auto stt
                    normalized.append((p[0], p[1], None, len(normalized) + 1))
                else:
                    normalized.append((p[0], None, None, len(normalized) + 1))
            else:
                normalized.append((p, None, None, len(normalized) + 1))  # text-only
        
        prompt_queue = list(normalized)
        retry_queue: List[Tuple[Tuple[str, Optional[str], Optional[str], int], int]] = []  # (item, retry_count)
        active_tasks: Dict[int, Tuple[asyncio.Task, Tuple[str, Optional[str], Optional[str], int], int]] = {}
        
        mode = "Image→Video" if any(img for _, img, _, _ in normalized) else "Text→Video"
        self._log(f"📋 Starting batch ({mode}): {len(normalized)} prompts, {len(self.tabs)} tabs")
        
        while prompt_queue or retry_queue or active_tasks:
            if not self._running:
                for task_info in active_tasks.values():
                    task_info[0].cancel()
                break
            
            # Start new tasks on ready tabs
            for tab_id in range(len(self.tabs)):
                if tab_id not in active_tasks and self.tab_ready[tab_id]:
                    item = None
                    retry_count = 0
                    
                    if retry_queue:
                        item, retry_count = retry_queue.pop(0)
                        self._log(f"🔄 Retrying ({retry_count}/{max_retries}): {item[0][:30]}...", tab_id)
                    elif prompt_queue:
                        item = prompt_queue.pop(0)
                        self._log(f"▶️ Starting: {item[0][:30]}...", tab_id)
                    
                    if item:
                        prompt_text, image_path, subfolder, stt = item
                        # Build custom filename: {stt}_{prompt_short}.mp4
                        prompt_short = re.sub(r'[^\w\s]', '', prompt_text)[:30].replace(' ', '_')
                        custom_filename = f"{stt}_{prompt_short}.mp4"
                        # Build output path with subfolder
                        if output_dir and subfolder:
                            custom_output_dir = str(Path(output_dir) / subfolder)
                        elif output_dir:
                            custom_output_dir = output_dir
                        else:
                            custom_output_dir = str(OUTPUT_DIR)
                        
                        if image_path:
                            # Image-to-video flow
                            task = asyncio.create_task(
                                self.generate_image_to_video_on_tab(
                                    tab_id, prompt_text, image_path, settings,
                                    custom_output_dir=custom_output_dir,
                                    custom_filename=custom_filename
                                )
                            )
                        else:
                            # Text-to-video flow
                            task = asyncio.create_task(
                                self.generate_on_tab(
                                    tab_id, prompt_text, settings,
                                    custom_output_dir=custom_output_dir,
                                    custom_filename=custom_filename
                                )
                            )
                        active_tasks[tab_id] = (task, item, retry_count)
            
            # Wait for any task to complete
            if active_tasks:
                tasks_only = [t[0] for t in active_tasks.values()]
                done, _ = await asyncio.wait(
                    tasks_only, timeout=1.0, return_when=asyncio.FIRST_COMPLETED
                )
                
                for completed_task in done:
                    completed_tab_id = None
                    item_used = None
                    retry_count = 0
                    
                    for tid, (t, item, r) in list(active_tasks.items()):
                        if t == completed_task:
                            completed_tab_id = tid
                            item_used = item
                            retry_count = r
                            del active_tasks[tid]
                            break
                    
                    try:
                        video_task = completed_task.result()
                        
                        # Kiểm tra thực sự thành công: phải có output_path (file đã download)
                        actually_failed = (
                            video_task.status == "failed" or
                            (video_task.status == "completed" and not video_task.output_path)
                        )
                        
                        if actually_failed and retry_count < max_retries and item_used:
                            reason = video_task.error_message or "no output file"
                            self._log(f"⚠️ Failed ({reason}), will retry ({retry_count + 1}/{max_retries})", completed_tab_id or -1)
                            retry_queue.append((item_used, retry_count + 1))
                        else:
                            results.append(video_task)
                            if on_task_complete:
                                on_task_complete(video_task)
                            if video_task.status == "completed" and video_task.output_path:
                                self._log(f"✅ Done: {video_task.post_id}", completed_tab_id or -1)
                            else:
                                self._log(f"❌ Failed: {video_task.error_message or 'no output file'}", completed_tab_id or -1)
                    except Exception as e:
                        self._log(f"❌ Task error: {e}")
                        if retry_count < max_retries and item_used:
                            retry_queue.append((item_used, retry_count + 1))
            else:
                await asyncio.sleep(0.5)
        
        success_count = len([r for r in results if r.status == 'completed' and r.output_path])
        fail_count = len(results) - success_count
        self._log(f"🎉 Batch complete: {success_count}/{len(results)} OK" + (f", {fail_count} failed" if fail_count else ""))
        return results


def run_multi_tab_generation(
    account: Account,
    prompts,
    settings: VideoSettings,
    num_tabs: int = 3,
    headless: bool = True,
    on_status: Optional[Callable] = None,
    on_task_complete: Optional[Callable] = None
) -> List[VideoTask]:
    """
    Synchronous wrapper for multi-tab video generation.
    
    Args:
        account: Account to use
        prompts: List[str] or List[Tuple[str, Optional[str]]] (prompt, image_path)
        settings: Video settings
        num_tabs: Number of tabs (max 3)
        headless: Run headless
        on_status: Status callback (email, message)
        on_task_complete: Callback when each task completes
    """
    return asyncio.run(_run_multi_tab_async(
        account, prompts, settings, num_tabs, headless, on_status, on_task_complete
    ))


async def _run_multi_tab_async(
    account: Account,
    prompts,
    settings: VideoSettings,
    num_tabs: int = 3,
    headless: bool = True,
    on_status: Optional[Callable] = None,
    on_task_complete: Optional[Callable] = None
) -> List[VideoTask]:
    """Async multi-tab generation"""
    generator = MultiTabVideoGenerator(
        account=account,
        num_tabs=min(num_tabs, 3),  # Max 3 tabs
        headless=headless,
        on_status=on_status
    )
    
    try:
        if not await generator.start():
            return [VideoTask(
                account_email=account.email,
                prompt=p,
                settings=settings,
                status="failed",
                error_message="Failed to start browser"
            ) for p in prompts]
        
        results = await generator.generate_batch(prompts, settings, on_task_complete)
        return results
        
    finally:
        await generator.stop()
