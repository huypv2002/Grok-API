"""Image Generator - Browser automation for Grok text-to-image using zendriver.

Flow:
1. Start browser, inject cookies, solve Cloudflare (giống video)
2. Navigate to /imagine (default mode = Image, KHÔNG cần chọn mode)
3. Enter prompt → Submit
4. Chờ ảnh render xong (scrape masonry grid cards)
5. Download ảnh từ base64 src hoặc CDN URL
6. Nếu cần > 4 ảnh → submit lại prompt (mỗi lần tạo 4 ảnh)
"""
import asyncio
import time
import re
import os
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List, Tuple

from .models import Account, ImageSettings, ImageTask
from .cf_solver import (
    CloudflareSolver, CF_SOLVER_AVAILABLE,
    get_chrome_user_agent
)

try:
    import zendriver
    from zendriver import cdp
    ZENDRIVER_AVAILABLE = True
except ImportError:
    ZENDRIVER_AVAILABLE = False

IMAGINE_URL = "https://grok.com/imagine"
OUTPUT_DIR = Path("output")
# 1 prompt = 1 ảnh (lấy ảnh đầu tiên ready)


class MultiTabImageGenerator:
    """
    Multi-tab image generator — 1 browser per account, N tabs concurrent.
    Tương tự MultiTabVideoGenerator nhưng cho image generation.
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
        self.tabs: List[Any] = []
        self.tab_ready: List[bool] = []
        self._running = True
        self._solver_helper = None

    def _log(self, msg: str, tab_id: int = -1):
        prefix = f"[{self.account.email[:15]}]"
        if tab_id >= 0:
            prefix += f"[Tab{tab_id+1}]"
        full_msg = f"{prefix} {msg}"
        print(full_msg)
        if self.on_status:
            self.on_status(self.account.email, full_msg)

    # ==================== Browser Lifecycle ====================

    async def start(self) -> bool:
        """Start browser, inject cookies, solve CF, create tabs."""
        if not ZENDRIVER_AVAILABLE:
            self._log("❌ Thiếu thư viện zendriver")
            return False

        try:
            self._log("🚀 Đang khởi động trình duyệt...")

            user_agent = get_chrome_user_agent()
            self._solver_helper = CloudflareSolver(
                user_agent=user_agent,
                timeout=90,
                headless=self.headless,
            )
            # Ensure browser is created in async context
            await self._solver_helper.ensure_browser()
            self.browser = self._solver_helper.driver

            await self.browser.start()
            await self._solver_helper._inject_stealth_patches()

            if not self.browser.main_tab:
                self._log("❌ Lỗi khởi động trình duyệt, đang thử lại...")
                await asyncio.sleep(2)
                try:
                    await self.browser.stop()
                except:
                    pass
                self._solver_helper = CloudflareSolver(
                    user_agent=user_agent, timeout=90, headless=self.headless,
                )
                await self._solver_helper.ensure_browser()
                self.browser = self._solver_helper.driver
                await self.browser.start()
                await self._solver_helper._inject_stealth_patches()
                await asyncio.sleep(1)
                if not self.browser.main_tab:
                    self._log("❌ Không thể khởi động trình duyệt")
                    return False

            # Inject cookies
            self._log("🍪 Đang thiết lập phiên...")
            try:
                await self.browser.main_tab.get("https://grok.com/favicon.ico")
            except Exception as e:
                print(f"Favicon error: {e}, retrying...")
                await asyncio.sleep(2)
                await self.browser.main_tab.get("https://grok.com/favicon.ico")
            await asyncio.sleep(1)

            if self.account.cookies:
                for name, value in self.account.cookies.items():
                    if name != 'cf_clearance':
                        try:
                            await self.browser.main_tab.send(
                                cdp.network.set_cookie(
                                    name=name, value=value,
                                    domain=".grok.com", path="/",
                                    secure=True,
                                    http_only=name in ['sso', 'sso-rw'],
                                )
                            )
                        except:
                            pass

            # Navigate to /imagine + solve CF
            self._log("🌐 Đang truy cập Grok Imagine...")
            await self.browser.main_tab.get(IMAGINE_URL)
            await asyncio.sleep(3)

            cf_passed = await self._handle_cloudflare_on_tab(self.browser.main_tab)
            if not cf_passed:
                self._log("❌ Không vượt được Cloudflare")
                return False

            # Check login
            current_url = await self.browser.main_tab.evaluate("window.location.href")
            if 'sign-in' in current_url or 'accounts.x.ai' in current_url:
                self._log("❌ Phiên đăng nhập hết hạn, vui lòng đăng nhập lại")
                return False

            await asyncio.sleep(2)

            # Create tabs
            self.tabs = [self.browser.main_tab]
            self.tab_ready = [True]

            for i in range(1, self.num_tabs):
                self._log(f"📑 Đang tạo Tab {i+1}...")
                new_tab = await self.browser.get(IMAGINE_URL, new_tab=True)
                await asyncio.sleep(2)
                self.tabs.append(new_tab)
                self.tab_ready.append(True)

            self._log(f"✅ Trình duyệt sẵn sàng với {len(self.tabs)} tab")
            return True

        except Exception as e:
            self._log(f"❌ Lỗi khởi động: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def stop(self):
        self._running = False
        if self.browser:
            try:
                await self.browser.stop()
            except:
                pass
            self.browser = None
        self.tabs = []
        self.tab_ready = []

    # ==================== Cloudflare ====================

    async def _handle_cloudflare_on_tab(self, tab) -> bool:
        """Handle Cloudflare challenge — copy từ MultiTabVideoGenerator."""
        try:
            html = await tab.get_content()
            cf_indicators = ['Just a moment', 'Checking your browser', 'challenge-platform', 'cf-turnstile']

            if not any(ind in html for ind in cf_indicators):
                self._log("✅ Không có Cloudflare challenge")
                return True

            self._log("🔐 Phát hiện Cloudflare, đang xử lý...")

            user_agent = get_chrome_user_agent()
            try:
                await self._solver_helper.set_user_agent_metadata(user_agent)
            except Exception as e:
                print(f"UA metadata error: {e}")

            last_click_time = 0

            for i in range(90):
                cookies = await self.browser.cookies.get_all()
                for c in cookies:
                    if c.name == "cf_clearance":
                        self._log("✅ Đã vượt Cloudflare!")
                        return True

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
                                tab, widget_input.parent.tree,
                            )
                            challenge = challenge.children[0]
                            if (isinstance(challenge, Element)
                                    and "display: none;" not in challenge.attrs.get("style", "")):
                                self._log(f"🔐 Đang xử lý Cloudflare... ({i}s)")
                                await asyncio.sleep(1)
                                try:
                                    await challenge.get_position()
                                    pos = challenge.position
                                    if pos and hasattr(pos, 'x') and hasattr(pos, 'y'):
                                        x = pos.x + (pos.width / 2 if hasattr(pos, 'width') else 10)
                                        y = pos.y + (pos.height / 2 if hasattr(pos, 'height') else 10)
                                        await tab.send(cdp.input_.dispatch_mouse_event(type_="mouseMoved", x=x, y=y))
                                        await asyncio.sleep(0.05)
                                        await tab.send(cdp.input_.dispatch_mouse_event(
                                            type_="mousePressed", x=x, y=y,
                                            button=cdp.input_.MouseButton.LEFT, click_count=1))
                                        await asyncio.sleep(0.05)
                                        await tab.send(cdp.input_.dispatch_mouse_event(
                                            type_="mouseReleased", x=x, y=y,
                                            button=cdp.input_.MouseButton.LEFT, click_count=1))
                                    else:
                                        await challenge.mouse_click()
                                except Exception:
                                    try:
                                        await challenge.mouse_click()
                                    except:
                                        pass
                    except Exception as e:
                        if i == 0:
                            print(f"Turnstile error: {e}")

                await asyncio.sleep(1)
                if i % 10 == 0 and i > 0:
                    self._log(f"⏳ Đang chờ Cloudflare... ({i}s)")

            self._log("❌ Cloudflare hết thời gian chờ")
            return False

        except Exception as e:
            self._log(f"⚠️ Lỗi kiểm tra Cloudflare")
            return True  # Continue anyway

    # ==================== Image Settings ====================

    async def _select_image_mode_and_settings(self, tab, tab_id: int, settings: ImageSettings) -> None:
        """Open settings menu and apply aspect ratio for image generation"""
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
                self._log("⚠️ Settings trigger not found", tab_id)
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
            
            # Apply aspect ratio setting
            await self._apply_image_settings_in_menu(tab, tab_id, settings)
            await asyncio.sleep(0.3)
            
            # Click Image option to close menu (Image is default, just need to close)
            await tab.evaluate("""
                (function() {
                    var items = document.querySelectorAll('[role="menuitem"]');
                    for (var item of items) {
                        var text = item.textContent || '';
                        if (text.includes('Hình ảnh') && text.includes('Tạo nhiều ảnh')) {
                            item.click();
                            return 'clicked';
                        }
                    }
                    // Click outside to close menu
                    document.body.click();
                    return 'closed';
                })()
            """)
            await asyncio.sleep(0.5)
            
        except Exception as e:
            self._log(f"⚠️ Settings error: {e}", tab_id)

    async def _apply_image_settings_in_menu(self, tab, tab_id: int, settings: ImageSettings) -> None:
        """Apply aspect ratio using semantic locator + CDP mouse event."""
        try:
            aspect_label = settings.aspect_ratio
            
            self._log(f"⚙️ Applying aspect ratio: {aspect_label}", tab_id)
            
            for attempt in range(5):
                # Tìm button bằng aria-label → lấy rect
                info = await tab.evaluate("""
                    (function(targetLabel) {
                        var menu = document.querySelector('[role="menu"][data-state="open"]');
                        var scope = menu || document;
                        var buttons = scope.querySelectorAll('button[aria-label]');
                        for (var btn of buttons) {
                            if (btn.getAttribute('aria-label') === targetLabel) {
                                var rect = btn.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    var isActive = btn.classList.contains('font-semibold') ||
                                                   btn.className.includes('text-primary font-semibold');
                                    return {
                                        found: true,
                                        x: rect.x + rect.width / 2,
                                        y: rect.y + rect.height / 2,
                                        active: isActive
                                    };
                                }
                            }
                        }
                        return {found: false};
                    })""" + f"('{aspect_label}')")
                
                if not info or not info.get('found'):
                    await asyncio.sleep(0.5)
                    continue
                
                if info.get('active'):
                    self._log(f"   Aspect: {aspect_label} (already active)", tab_id)
                    return
                
                # CDP mouse click
                x, y = info['x'], info['y']
                await tab.send(cdp.input_.dispatch_mouse_event(type_="mouseMoved", x=x, y=y))
                await asyncio.sleep(0.05)
                await tab.send(cdp.input_.dispatch_mouse_event(
                    type_="mousePressed", x=x, y=y,
                    button=cdp.input_.MouseButton.LEFT, click_count=1
                ))
                await asyncio.sleep(0.05)
                await tab.send(cdp.input_.dispatch_mouse_event(
                    type_="mouseReleased", x=x, y=y,
                    button=cdp.input_.MouseButton.LEFT, click_count=1
                ))
                await asyncio.sleep(0.5)
                
                # Verify
                verify = await tab.evaluate("""
                    (function(targetLabel) {
                        var menu = document.querySelector('[role="menu"][data-state="open"]');
                        var scope = menu || document;
                        var buttons = scope.querySelectorAll('button[aria-label]');
                        for (var btn of buttons) {
                            if (btn.getAttribute('aria-label') === targetLabel) {
                                return {
                                    active: btn.classList.contains('font-semibold') ||
                                            btn.className.includes('text-primary font-semibold')
                                };
                            }
                        }
                        return {active: false};
                    })""" + f"('{aspect_label}')")
                
                if verify and verify.get('active'):
                    self._log(f"   Aspect: {aspect_label} ✓", tab_id)
                    return
                
                self._log(f"   Aspect: retry {attempt+1}", tab_id)
                await asyncio.sleep(0.5)
            
            self._log(f"   Aspect: fallback JS click", tab_id)
            await tab.evaluate(f"""
                (function() {{
                    var btns = document.querySelectorAll('button[aria-label="{aspect_label}"]');
                    if (btns.length > 0) btns[0].click();
                }})()
            """)
            
        except Exception as e:
            self._log(f"⚠️ Settings error: {e}", tab_id)

    # ==================== Image Generation on Tab ====================

    async def generate_images_on_tab(
        self,
        tab_id: int,
        prompt: str,
        settings: ImageSettings,
        output_dir: str,
        retry_count: int = 0,
        custom_filename: str = None
    ) -> ImageTask:
        """
        Generate 1 image on a specific tab.
        
        Flow:
        1. F5 to /imagine (fresh page)
        2. Enter prompt → Submit
        3. Wait for first image ready
        4. Download 1 image
        
        Args:
            custom_filename: Custom filename prefix (without extension), e.g. "1_prompt_text"
        """
        MAX_RETRIES = 3

        task = ImageTask(
            account_email=self.account.email,
            prompt=prompt,
            settings=settings,
            num_images_requested=1,
            status="creating",
            output_dir=output_dir,
        )

        if tab_id >= len(self.tabs):
            task.status = "failed"
            task.error_message = f"Invalid tab_id: {tab_id}"
            return task

        tab = self.tabs[tab_id]

        try:
            self.tab_ready[tab_id] = False

            # F5 to /imagine — fresh page
            await tab.get(IMAGINE_URL)
            await asyncio.sleep(3)  # Chờ page load đầy đủ

            # Apply aspect ratio settings if not default
            if settings and settings.aspect_ratio != "3:2":
                await self._select_image_mode_and_settings(tab, tab_id, settings)
                await asyncio.sleep(0.5)

            # Enter prompt (Image mode is default)
            self._log(f"✏️ Nhập prompt: {prompt[:40]}...", tab_id)
            if not await self._enter_prompt_on_tab(tab, prompt, tab_id):
                if retry_count < MAX_RETRIES:
                    self._log("⚠️ Lỗi nhập prompt, thử lại...", tab_id)
                    await asyncio.sleep(2)
                    self.tab_ready[tab_id] = True
                    return await self.generate_images_on_tab(tab_id, prompt, settings, output_dir, retry_count + 1, custom_filename)
                task.status = "failed"
                task.error_message = "Failed to enter prompt"
                self.tab_ready[tab_id] = True
                return task

            await asyncio.sleep(0.5)

            # Submit
            self._log("📤 Đang gửi...", tab_id)
            await self._submit_prompt_on_tab(tab, tab_id)
            await asyncio.sleep(5)  # Chờ server xử lý và bắt đầu render ảnh

            # Wait for first image ready
            self._log("⏳ Đang tạo ảnh...", tab_id)
            image_data = await self._wait_for_first_image(tab, tab_id, timeout=90)

            if not image_data:
                if retry_count < MAX_RETRIES:
                    self._log(f"⚠️ Không tìm thấy ảnh, thử lại ({retry_count+1}/{MAX_RETRIES})...", tab_id)
                    await asyncio.sleep(1)
                    self.tab_ready[tab_id] = True
                    return await self.generate_images_on_tab(tab_id, prompt, settings, output_dir, retry_count + 1, custom_filename)
                task.status = "failed"
                task.error_message = "No images generated"
                self.tab_ready[tab_id] = True
                return task

            # Download 1 image
            self._log("📥 Đang tải ảnh...", tab_id)
            downloaded = await self._download_images([image_data], prompt, output_dir, tab_id, custom_filename=custom_filename)

            # Finalize task
            task.output_paths = downloaded
            task.num_images_downloaded = len(downloaded)

            if downloaded:
                task.status = "completed"
                task.completed_at = datetime.now()
                self._log(f"✅ Hoàn thành", tab_id)
            else:
                task.status = "failed"
                task.error_message = "No images downloaded"
                self._log("❌ Không tải được ảnh", tab_id)

            self.tab_ready[tab_id] = True
            return task

        except Exception as e:
            self._log(f"❌ Lỗi: {e}", tab_id)
            import traceback
            traceback.print_exc()
            if retry_count < MAX_RETRIES:
                self._log(f"🔄 Đang thử lại ({retry_count+1}/{MAX_RETRIES})...", tab_id)
                await asyncio.sleep(1)
                self.tab_ready[tab_id] = True
                return await self.generate_images_on_tab(tab_id, prompt, settings, output_dir, retry_count + 1, custom_filename)
            task.status = "failed"
            task.error_message = str(e)
            self.tab_ready[tab_id] = True
            return task

    # ==================== Prompt Entry & Submit ====================

    async def _enter_prompt_on_tab(self, tab, prompt: str, tab_id: int) -> bool:
        """Enter prompt vào editor — giống video generator."""
        try:
            escaped = prompt.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
            result = await tab.evaluate(f"""
                (function() {{
                    var editor = document.querySelector('div.tiptap.ProseMirror') ||
                                 document.querySelector('div[contenteditable="true"]') ||
                                 document.querySelector('.ProseMirror') ||
                                 document.querySelector('textarea');
                    if (!editor) return 'no_editor';
                    editor.focus();
                    if (editor.tagName === 'TEXTAREA') {{
                        editor.value = '{escaped}';
                        editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                        return 'textarea_filled';
                    }}
                    editor.innerHTML = '<p>{escaped}</p>';
                    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                    return 'editor_filled';
                }})()
            """)
            print(f"[Tab{tab_id+1}] Prompt: {result}")
            return 'filled' in str(result)
        except Exception as e:
            self._log(f"⚠️ Lỗi nhập prompt", tab_id)
            print(f"[Tab{tab_id+1}] Prompt error: {e}")
            return False

    async def _submit_prompt_on_tab(self, tab, tab_id: int) -> None:
        """Click submit button."""
        try:
            result = await tab.evaluate("""
                (function() {
                    var btn = document.querySelector('button[type="submit"]');
                    if (!btn) {
                        var btns = document.querySelectorAll('button');
                        for (var b of btns) {
                            var label = b.getAttribute('aria-label') || b.textContent || '';
                            if (label.includes('Send') || label.includes('Gửi') || label.includes('Submit')) {
                                btn = b; break;
                            }
                        }
                    }
                    if (btn && !btn.disabled) {
                        btn.click();
                        return 'clicked';
                    }
                    return 'no_button_or_disabled';
                })()
            """)
            print(f"[Tab{tab_id+1}] Submit: {result}")
        except Exception as e:
            self._log(f"⚠️ Lỗi gửi prompt", tab_id)
            print(f"[Tab{tab_id+1}] Submit error: {e}")

    # ==================== Wait for First Image ====================

    async def _wait_for_first_image(self, tab, tab_id: int, timeout: int = 90) -> Optional[Dict]:
        """
        Chờ ảnh đầu tiên render xong trên trang /imagine.
        
        Cách check ảnh đã render xong:
        1. naturalWidth >= 512 (ảnh thật thường lớn hơn)
        2. Base64 src length > 50000 (ảnh thật ~100KB+, blur ~10KB)
        3. Không có loading/generating indicator trong card
        4. img.complete = true
        
        Returns: Dict với keys: src, width, height hoặc None
        """
        MIN_NATURAL_WIDTH = 512  # Tăng lên để loại bỏ placeholder
        MIN_BASE64_LENGTH = 50000  # ~37KB decoded, ảnh thật thường > 100KB
        start_time = time.time()
        last_status = ""

        while time.time() - start_time < timeout:
            if not self._running:
                return None

            result = await tab.evaluate("""
                (function() {
                    var MIN_W = """ + str(MIN_NATURAL_WIDTH) + """;
                    var MIN_B64_LEN = """ + str(MIN_BASE64_LENGTH) + """;
                    var genImgs = document.querySelectorAll('img[alt="Generated image"]');
                    var debugInfo = [];
                    
                    for (var img of genImgs) {
                        var src = img.src || '';
                        if (!src || src.length < 100) continue;
                        
                        var nw = img.naturalWidth || 0;
                        var nh = img.naturalHeight || 0;
                        var srcLen = src.length;
                        var isComplete = img.complete;
                        
                        // Debug info
                        debugInfo.push({
                            nw: nw,
                            srcLen: srcLen,
                            complete: isComplete
                        });
                        
                        // Check 1: naturalWidth phải đủ lớn
                        if (nw < MIN_W) continue;
                        
                        // Check 2: img.complete phải true
                        if (!isComplete) continue;
                        
                        // Check 3: Base64 length phải đủ lớn (ảnh thật > 50KB base64)
                        if (src.startsWith('data:image/') && srcLen < MIN_B64_LEN) continue;
                        
                        // Check 4: Không có loading indicator trong card
                        var card = img.closest('div[class*="group/media-post-masonry-card"]');
                        if (card) {
                            // Check progress bar hoặc loading text
                            var hasProgress = !!card.querySelector('[role="progressbar"]');
                            var hasGenerating = card.textContent.includes('Generating') || 
                                               card.textContent.includes('Creating') ||
                                               card.textContent.includes('Loading');
                            if (hasProgress || hasGenerating) continue;
                            
                            // Check invisible overlay (thường là loading state)
                            var invisibleDiv = card.querySelector('div.invisible');
                            if (invisibleDiv) continue;
                        }
                        
                        // Ảnh đã ready!
                        return {
                            ready: true,
                            src: src,
                            width: nw,
                            height: nh,
                            srcLen: srcLen
                        };
                    }
                    
                    // Không có ảnh ready, trả về debug info
                    return {
                        ready: false,
                        found: genImgs.length,
                        debug: debugInfo.slice(0, 4)
                    };
                })()
            """)

            if result and result.get('ready'):
                src_kb = result.get('srcLen', 0) // 1024
                print(f"[Tab{tab_id+1}] Image ready: {result.get('width')}x{result.get('height')}, {src_kb}KB")
                self._log(f"✅ Ảnh đã tạo xong", tab_id)
                return result

            # Debug log
            elapsed = int(time.time() - start_time)
            if result and not result.get('ready'):
                found = result.get('found', 0)
                debug = result.get('debug', [])
                status = f"found={found}"
                if debug:
                    # Show first image info
                    d = debug[0]
                    status += f", nw={d.get('nw',0)}, srcLen={d.get('srcLen',0)//1024}KB"
                
                if status != last_status:
                    print(f"[Tab{tab_id+1}] Waiting: {status}, elapsed={elapsed}s")
                    last_status = status

            # Log mỗi 15s cho user
            if elapsed > 0 and elapsed % 15 == 0 and elapsed != getattr(self, '_last_log_elapsed', 0):
                self._last_log_elapsed = elapsed
                self._log(f"⏳ Đang tạo ảnh... ({elapsed}s)", tab_id)

            await asyncio.sleep(2)

        self._log(f"⏰ Hết thời gian chờ", tab_id)
        return None

    # ==================== Download Images ====================

    async def _download_images(
        self,
        image_data: List[Dict],
        prompt: str,
        output_dir: str,
        tab_id: int,
        start_idx: int = 0,
        custom_filename: str = None
    ) -> List[str]:
        """
        Download images từ base64 src hoặc URL.
        
        Args:
            custom_filename: Custom filename prefix (without extension), e.g. "1_prompt_text"
        
        Returns: List of saved file paths
        """
        import requests

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        downloaded = []

        # Build filename
        if custom_filename:
            # Use custom filename: {stt}_{prompt_short}.jpg
            base_filename = custom_filename
        else:
            # Default: timestamp_email_prompt_idx.jpg
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            email_short = self.account.email.split("@")[0][:10]
            prompt_short = re.sub(r'[^\w\s]', '', prompt)[:20].replace(' ', '_')
            base_filename = f"{ts}_{email_short}_{prompt_short}"

        for i, img in enumerate(image_data):
            if not self._running:
                break

            idx = start_idx + i + 1
            # If custom_filename, don't add idx suffix (single image per prompt)
            if custom_filename:
                filename = f"{base_filename}.jpg"
            else:
                filename = f"{base_filename}_{idx}.jpg"
            filepath = Path(output_dir) / filename

            src = img.get('src', '')

            try:
                if src.startswith('data:image/'):
                    # Base64 encoded image
                    # Format: data:image/jpeg;base64,/9j/4AAQ...
                    header, b64data = src.split(',', 1)
                    
                    # Verify: decode và check kích thước thực
                    # Placeholder có naturalWidth nhỏ (64-100px), ảnh thật >= 256px
                    nat_w = img.get('naturalW', img.get('width', 0))
                    if nat_w < 256:
                        print(f"[Tab{tab_id+1}] Skipping placeholder image {idx} (naturalWidth={nat_w})")
                        continue
                    
                    img_bytes = base64.b64decode(b64data)

                    # Determine extension from header
                    if 'png' in header:
                        filename = filename.replace('.jpg', '.png')
                        filepath = Path(output_dir) / filename
                    elif 'webp' in header:
                        filename = filename.replace('.jpg', '.webp')
                        filepath = Path(output_dir) / filename

                    with open(filepath, 'wb') as f:
                        f.write(img_bytes)

                    if filepath.exists() and os.path.getsize(filepath) > 1000:
                        downloaded.append(str(filepath))
                        print(f"[Tab{tab_id+1}] Saved: {filename} ({len(img_bytes)//1024}KB)")
                    else:
                        print(f"[Tab{tab_id+1}] File too small: {filename}")

                elif src.startswith('http'):
                    # URL — download via requests
                    headers = {
                        'User-Agent': get_chrome_user_agent(),
                        'Referer': 'https://grok.com/',
                    }
                    resp = requests.get(src, headers=headers, timeout=30)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        # Detect content type
                        ct = resp.headers.get('content-type', '')
                        if 'png' in ct:
                            filename = filename.replace('.jpg', '.png')
                            filepath = Path(output_dir) / filename
                        elif 'webp' in ct:
                            filename = filename.replace('.jpg', '.webp')
                            filepath = Path(output_dir) / filename

                        with open(filepath, 'wb') as f:
                            f.write(resp.content)
                        downloaded.append(str(filepath))
                        print(f"[Tab{tab_id+1}] Saved URL: {filename} ({len(resp.content)//1024}KB)")
                    else:
                        print(f"[Tab{tab_id+1}] Download failed: HTTP {resp.status_code}")

                elif src.startswith('blob:'):
                    # Blob URL — cần convert qua canvas trong browser
                    print(f"[Tab{tab_id+1}] Blob URL not supported, skipping")

            except Exception as e:
                print(f"[Tab{tab_id+1}] Download error for image {idx}: {e}")

        return downloaded

    # ==================== Batch Generation ====================

    async def generate_batch(
        self,
        prompts: List[str],
        settings: ImageSettings,
        output_dir: str,
        on_task_complete: Optional[Callable] = None,
        max_retries: int = 3
    ) -> List[ImageTask]:
        """
        Generate images for multiple prompts concurrently using all tabs.
        Tương tự video generate_batch.
        """
        results: List[ImageTask] = []
        prompt_queue = list(prompts)
        retry_queue: List[Tuple[str, int]] = []  # (prompt, retry_count)
        active_tasks: Dict[int, Tuple[asyncio.Task, str, int]] = {}

        self._log(f"📋 Bắt đầu tạo ảnh: {len(prompts)} prompt, {len(self.tabs)} tab")

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
                        self._log(f"🔄 Thử lại ({retry_count}/{max_retries}): {item[:30]}...", tab_id)
                    elif prompt_queue:
                        item = prompt_queue.pop(0)
                        self._log(f"▶️ Bắt đầu: {item[:30]}...", tab_id)

                    if item:
                        task = asyncio.create_task(
                            self.generate_images_on_tab(tab_id, item, settings, output_dir)
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
                        image_task = completed_task.result()

                        actually_failed = (
                            image_task.status == "failed" or
                            (image_task.status == "completed" and not image_task.output_paths)
                        )

                        if actually_failed and retry_count < max_retries and item_used:
                            reason = image_task.error_message or "không có ảnh"
                            self._log(f"⚠️ Lỗi ({reason}), thử lại ({retry_count+1}/{max_retries})", completed_tab_id or -1)
                            retry_queue.append((item_used, retry_count + 1))
                        else:
                            results.append(image_task)
                            if on_task_complete:
                                on_task_complete(image_task)
                            if image_task.status == "completed":
                                self._log(f"✅ Xong: {image_task.num_images_downloaded} ảnh", completed_tab_id or -1)
                            else:
                                self._log(f"❌ Lỗi: {image_task.error_message}", completed_tab_id or -1)
                    except Exception as e:
                        self._log(f"❌ Lỗi tác vụ: {e}")
                        if retry_count < max_retries and item_used:
                            retry_queue.append((item_used, retry_count + 1))
            else:
                await asyncio.sleep(0.5)

        success = len([r for r in results if r.status == 'completed' and r.output_paths])
        fail = len(results) - success
        self._log(f"🎉 Hoàn thành: {success}/{len(results)} thành công" + (f", {fail} lỗi" if fail else ""))
        return results
