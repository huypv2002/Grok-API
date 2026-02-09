"""
Test: Upload ảnh lên Grok Imagine → Nhập prompt → Tạo video → Download

Flow:
1. Navigate to /imagine/favorites (hoặc /imagine)
2. Upload ảnh qua CDP DOM.setFileInputFiles (bypass file dialog)
3. Chờ redirect → /imagine/post/{uuid}
4. Nhập prompt + chọn settings (Video mode, 10s, 720p, 16:9)
5. Submit → chờ render → share → download
"""
import asyncio
import json
import os
import re
import sys
import time
import base64
import glob
import tempfile
import urllib.request
from pathlib import Path
from datetime import datetime

try:
    import zendriver
    from zendriver import cdp
except ImportError:
    print("❌ pip install zendriver")
    sys.exit(1)

# === Config ===
IMAGINE_URL = "https://grok.com/imagine"
FAVORITES_URL = "https://grok.com/imagine/favorites"
OUTPUT_DIR = Path("output")
FIXED_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"

# Load account cookies
ACCOUNTS_FILE = Path("data/accounts.json")


def load_first_logged_in_account():
    """Load first logged_in account from accounts.json"""
    if not ACCOUNTS_FILE.exists():
        print("❌ data/accounts.json not found")
        return None
    data = json.loads(ACCOUNTS_FILE.read_text())
    for acc in data.get("accounts", []):
        if acc.get("status") == "logged_in" and acc.get("cookies"):
            return acc
    print("❌ No logged_in account found")
    return None


async def inject_cookies(tab, cookies: dict):
    """Inject cookies via CDP"""
    for name, value in cookies.items():
        if name == "cf_clearance":
            continue
        try:
            await tab.send(cdp.network.set_cookie(
                name=name, value=value,
                domain=".grok.com", path="/",
                secure=True,
                http_only=name in ("sso", "sso-rw"),
            ))
        except Exception:
            pass


async def handle_cloudflare(browser, tab, timeout=60):
    """Handle Cloudflare challenge if present"""
    html = await tab.get_content()
    indicators = ["Just a moment", "Checking your browser", "challenge-platform", "cf-turnstile"]
    if not any(ind in html for ind in indicators):
        print("✅ No Cloudflare challenge")
        return True

    print("🔐 Cloudflare detected, solving...")
    try:
        import user_agents
        from zendriver.cdp.emulation import UserAgentBrandVersion, UserAgentMetadata
        device = user_agents.parse(FIXED_USER_AGENT)
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
            mobile=False, model="", platform="macOS",
            platform_version="15.0.0", full_version=device.browser.version_string, wow64=False,
        )
        tab.feed_cdp(cdp.network.set_user_agent_override(FIXED_USER_AGENT, user_agent_metadata=metadata))
    except Exception as e:
        print(f"⚠️ UA metadata: {e}")

    # Try click turnstile
    try:
        from zendriver.core.element import Element
        widget_input = await tab.find("input")
        if widget_input and widget_input.parent and widget_input.parent.shadow_roots:
            challenge = Element(widget_input.parent.shadow_roots[0], tab, widget_input.parent.tree)
            challenge = challenge.children[0]
            if isinstance(challenge, Element) and "display: none;" not in challenge.attrs.get("style", ""):
                await asyncio.sleep(1)
                await challenge.get_position()
                await challenge.mouse_click()
                print("   Clicked turnstile")
    except Exception as e:
        print(f"   Turnstile click: {e}")

    # Wait for cf_clearance
    for i in range(timeout):
        cookies = await browser.cookies.get_all()
        for c in cookies:
            if c.name == "cf_clearance":
                print(f"✅ Cloudflare passed! ({i}s)")
                return True
        await asyncio.sleep(1)
        if i % 10 == 0:
            print(f"   Waiting... ({i}s)")

    print("❌ Cloudflare timeout")
    return False


async def upload_image_via_cdp(tab, image_path: str):
    """
    Upload ảnh bằng CDP: tìm <input type="file"> ẩn và set file vào đó.
    Grok dùng hidden file input, nút "Tải lên hình ảnh" trigger click vào input này.
    Hỗ trợ cả local path và URL (tự download về temp).
    """
    # Nếu là URL → download về temp file
    if image_path.startswith("http://") or image_path.startswith("https://"):
        print(f"🌐 Downloading image from URL...")
        try:
            # Đoán extension từ URL
            url_path = image_path.split("?")[0]
            ext = os.path.splitext(url_path)[1] or ".jpg"
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                ext = ".jpg"
            tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir="data")
            req = urllib.request.Request(image_path, headers={"User-Agent": FIXED_USER_AGENT})
            with urllib.request.urlopen(req) as resp:
                tmp.write(resp.read())
            tmp.close()
            abs_path = tmp.name
            print(f"   Saved to: {abs_path} ({os.path.getsize(abs_path)} bytes)")
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False
    else:
        abs_path = os.path.abspath(image_path)
    
    if not os.path.exists(abs_path):
        print(f"❌ Image not found: {abs_path}")
        return False

    print(f"📤 Uploading image: {abs_path}")

    # Bước 1: Tìm file input element
    # Grok có thể dùng <input type="file" hidden> hoặc trong shadow DOM
    file_input_info = await tab.evaluate("""
        (function() {
            // Tìm tất cả input[type="file"]
            var inputs = document.querySelectorAll('input[type="file"]');
            if (inputs.length > 0) {
                return {found: true, count: inputs.length, id: inputs[0].id || '', accept: inputs[0].accept || ''};
            }
            return {found: false};
        })()
    """)
    print(f"   File input search: {file_input_info}")

    if not file_input_info or not file_input_info.get("found"):
        # Thử click nút upload trước để trigger tạo file input
        print("   Clicking upload button to trigger file input...")
        await tab.evaluate("""
            (function() {
                // Tìm nút "Tải lên hình ảnh"
                var btns = document.querySelectorAll('button');
                for (var btn of btns) {
                    var label = btn.getAttribute('aria-label') || btn.textContent || '';
                    if (label.includes('Tải lên hình ảnh') || label.includes('Upload')) {
                        btn.click();
                        return 'clicked';
                    }
                }
                // Tìm bằng SVG upload icon
                var svgs = document.querySelectorAll('svg.lucide-upload');
                for (var svg of svgs) {
                    var btn = svg.closest('button');
                    if (btn) { btn.click(); return 'clicked svg'; }
                }
                return 'not found';
            })()
        """)
        await asyncio.sleep(1)

        # Tìm lại file input
        file_input_info = await tab.evaluate("""
            (function() {
                var inputs = document.querySelectorAll('input[type="file"]');
                if (inputs.length > 0) {
                    return {found: true, count: inputs.length};
                }
                return {found: false};
            })()
        """)
        print(f"   File input after click: {file_input_info}")

    if not file_input_info or not file_input_info.get("found"):
        print("❌ Cannot find file input element")
        return False

    # Bước 2: Lấy node ID của file input qua CDP
    # Get document root
    doc = await tab.send(cdp.dom.get_document())
    root_node_id = doc.node_id

    # Query selector cho input[type="file"]
    file_node_id = await tab.send(cdp.dom.query_selector(root_node_id, 'input[type="file"]'))

    if not file_node_id:
        print("❌ Cannot get file input node ID")
        return False

    print(f"   File input node ID: {file_node_id}")

    # Bước 3: Set file vào input element
    await tab.send(cdp.dom.set_file_input_files(
        files=[abs_path],
        node_id=file_node_id
    ))
    print("✅ File set via CDP!")

    # Bước 4: Chờ upload hoàn tất (page sẽ redirect hoặc hiện preview)
    await asyncio.sleep(3)
    return True


async def wait_for_post_redirect(tab, timeout=30):
    """Chờ redirect từ /imagine/favorites → /imagine/post/{uuid}"""
    pattern = r'/imagine/post/([a-f0-9-]{36})'
    for i in range(timeout):
        url = await tab.evaluate("window.location.href")
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        await asyncio.sleep(1)
        if i % 5 == 0:
            print(f"   Waiting for redirect... ({i}s) URL: {url[:60]}")
    return None


async def save_debug_screenshot(tab, label="debug"):
    """Save debug screenshot"""
    try:
        ss = await tab.send(cdp.page.capture_screenshot())
        if ss:
            debug_path = Path("data") / f"debug_{label}_{datetime.now().strftime('%H%M%S')}.png"
            debug_path.parent.mkdir(exist_ok=True)
            with open(debug_path, "wb") as f:
                f.write(base64.b64decode(ss))
            print(f"   📸 Screenshot: {debug_path}")
    except Exception as e:
        print(f"   Screenshot error: {e}")


async def disable_auto_video_generation(tab):
    """
    Tắt "Bật Tạo Video Tự Động" trong Settings → Hành vi.
    Chỉ cần chạy 1 lần per browser session.
    
    Flow:
    1. Click avatar button (bottom-left) → mở menu (CDP mouse click cho Radix UI)
    2. Click "Cài đặt" menuitem → mở dialog
    3. Click "Hành vi" / "Behavior" tab
    4. Tìm toggle "Bật Tạo Video Tự Động" / "Enable Auto Video" → tắt nếu đang bật
    5. Đóng dialog
    """
    print("⚙️ Disabling auto video generation...")
    
    # Step 1: Click avatar button via CDP mouse (JS click doesn't trigger Radix menu)
    avatar_pos = await tab.evaluate("""
        (function() {
            // Tìm avatar button ở bottom-left
            var container = document.querySelector('div.absolute.bottom-3');
            if (container) {
                var btn = container.querySelector('button[aria-haspopup="menu"]');
                if (btn) {
                    var rect = btn.getBoundingClientRect();
                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, method: 'bottom-3'};
                }
            }
            // Fallback: tìm tất cả button[aria-haspopup="menu"] có avatar
            var btns = document.querySelectorAll('button[aria-haspopup="menu"]');
            for (var b of btns) {
                var span = b.querySelector('span.rounded-full');
                if (span) {
                    var rect = b.getBoundingClientRect();
                    if (rect.width > 0) return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, method: 'fallback'};
                }
            }
            return {found: false};
        })()
    """)
    print(f"   Avatar button: {avatar_pos}")
    if not avatar_pos or not avatar_pos.get('found'):
        print("⚠️ Avatar button not found, skipping settings")
        return False
    
    # CDP mouse click (Radix UI cần real pointer events, không phải JS click)
    x, y = avatar_pos['x'], avatar_pos['y']
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mousePressed", x=x, y=y,
        button=cdp.input_.MouseButton.LEFT, click_count=1
    ))
    await asyncio.sleep(0.05)
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mouseReleased", x=x, y=y,
        button=cdp.input_.MouseButton.LEFT, click_count=1
    ))
    print("   Avatar: CDP clicked")
    
    # Wait for Radix menu to render
    await asyncio.sleep(1.5)
    
    # Step 2: Click "Cài đặt" / "Settings" menuitem
    for attempt in range(8):
        menu_info = await tab.evaluate("""
            (function() {
                // Radix menu content (portal)
                var menu = document.querySelector('[role="menu"]');
                if (!menu) return {status: 'no_menu'};
                var items = menu.querySelectorAll('[role="menuitem"]');
                if (items.length === 0) return {status: 'menu_empty', menuHTML: menu.innerHTML.substring(0, 200)};
                var texts = [];
                for (var item of items) texts.push(item.textContent.trim().substring(0, 30));
                // Tìm Cài đặt / Settings
                for (var item of items) {
                    var text = (item.textContent || '').trim();
                    if (text === 'Cài đặt' || text === 'Settings' || text.includes('Cài đặt') || text.includes('Settings')) {
                        var rect = item.getBoundingClientRect();
                        return {status: 'found', text: text, x: rect.x + rect.width/2, y: rect.y + rect.height/2, allItems: texts};
                    }
                }
                return {status: 'not_matched', allItems: texts};
            })()
        """)
        print(f"   Menu ({attempt+1}): {menu_info}")
        
        if menu_info and menu_info.get('status') == 'found':
            # CDP click on the menuitem
            mx, my = menu_info['x'], menu_info['y']
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mousePressed", x=mx, y=my,
                button=cdp.input_.MouseButton.LEFT, click_count=1
            ))
            await asyncio.sleep(0.05)
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mouseReleased", x=mx, y=my,
                button=cdp.input_.MouseButton.LEFT, click_count=1
            ))
            print(f"   Cài đặt: CDP clicked '{menu_info['text']}'")
            break
        elif menu_info and menu_info.get('status') == 'not_matched':
            # Menu has items but none match - click first item as fallback
            items_list = menu_info.get('allItems', [])
            print(f"   Menu items: {items_list}")
            # Try JS click on first item
            await tab.evaluate("""
                (function() {
                    var items = document.querySelectorAll('[role="menu"] [role="menuitem"]');
                    if (items.length > 0) items[0].click();
                })()
            """)
            break
        await asyncio.sleep(1)
    else:
        print("⚠️ Menu never appeared, trying Escape + retry")
        await tab.send(cdp.input_.dispatch_key_event(type_="keyDown", key="Escape"))
        await asyncio.sleep(0.5)
        # Dismiss any overlay and skip
        print("⚠️ Could not open settings menu")
        return False
    
    await asyncio.sleep(1.5)
    
    # Step 3: Click "Hành vi" / "Behavior" tab in settings dialog
    clicked = await tab.evaluate("""
        (function() {
            var dialog = document.querySelector('[role="dialog"]');
            if (!dialog) return 'no dialog';
            
            var buttons = dialog.querySelectorAll('button');
            for (var btn of buttons) {
                var text = (btn.textContent || '').trim();
                if (text.includes('Hành vi') || text.includes('Behavior')) {
                    btn.click();
                    return 'clicked: ' + text;
                }
            }
            // Debug: list all button texts in dialog
            var texts = [];
            for (var b of buttons) texts.push(b.textContent.trim().substring(0, 30));
            return 'not found, buttons: ' + JSON.stringify(texts);
        })()
    """)
    print(f"   Hành vi tab: {clicked}")
    if 'not found' in str(clicked) or 'no dialog' in str(clicked):
        print("⚠️ 'Hành vi' tab not found in dialog")
        await tab.evaluate("""
            (function() {
                var close = document.querySelector('[role="dialog"] button[aria-label="Close"]');
                if (!close) close = document.querySelector('[role="dialog"] button:has(svg.lucide-x)');
                if (close) close.click();
            })()
        """)
        return False
    
    await asyncio.sleep(1)
    
    # Step 4: Tìm và tắt toggle "Bật Tạo Video Tự Động" / "Enable Auto Video Generation"
    result = await tab.evaluate("""
        (function() {
            var dialog = document.querySelector('[role="dialog"]');
            if (!dialog) return {error: 'no dialog'};
            
            // Tìm tất cả toggle switches trong dialog
            var switches = dialog.querySelectorAll('button[role="switch"]');
            if (switches.length === 0) return {error: 'no switches found'};
            
            // Tìm bằng label text
            for (var sw of switches) {
                var labelId = sw.getAttribute('aria-labelledby');
                if (labelId) {
                    var label = document.getElementById(labelId);
                    if (label) {
                        var text = label.textContent || '';
                        if (text.includes('Video Tự Động') || text.includes('Auto Video') || 
                            text.includes('Tạo Video') || text.includes('Generate Video')) {
                            var state = sw.getAttribute('data-state');
                            if (state === 'checked') {
                                sw.click();
                                return {toggled: true, was: 'checked', label: text.trim()};
                            }
                            return {toggled: false, was: state, msg: 'already off', label: text.trim()};
                        }
                    }
                }
            }
            
            // Fallback: tìm bằng text gần switch
            for (var sw of switches) {
                var row = sw.closest('.flex') || sw.parentElement;
                if (row) {
                    var text = row.textContent || '';
                    if (text.includes('Video Tự Động') || text.includes('Auto Video') ||
                        text.includes('Tạo Video') || text.includes('Generate Video')) {
                        var state = sw.getAttribute('data-state');
                        if (state === 'checked') {
                            sw.click();
                            return {toggled: true, was: 'checked', label: text.trim().substring(0, 50)};
                        }
                        return {toggled: false, was: state, msg: 'already off', label: text.trim().substring(0, 50)};
                    }
                }
            }
            
            // Debug: list all switches and their labels
            var info = [];
            for (var sw of switches) {
                var labelId = sw.getAttribute('aria-labelledby');
                var label = labelId ? (document.getElementById(labelId) || {}).textContent : '';
                var row = sw.closest('.flex') || sw.parentElement;
                var rowText = row ? row.textContent.trim().substring(0, 60) : '';
                info.push({state: sw.getAttribute('data-state'), label: label, rowText: rowText});
            }
            return {error: 'target switch not found', switches: info};
        })()
    """)
    print(f"   Auto video toggle: {result}")
    
    await asyncio.sleep(0.5)
    
    # Step 5: Đóng dialog
    await tab.evaluate("""
        (function() {
            var dialog = document.querySelector('[role="dialog"]');
            if (!dialog) return;
            // Tìm nút đóng
            var close = dialog.querySelector('button[aria-label="Close"]') ||
                        dialog.querySelector('button[aria-label="Đóng"]');
            if (!close) {
                // Tìm nút X (thường ở top-right)
                var btns = dialog.querySelectorAll('button');
                for (var b of btns) {
                    var svg = b.querySelector('svg.lucide-x');
                    if (svg) { close = b; break; }
                    var sr = b.querySelector('.sr-only');
                    if (sr && (sr.textContent.trim() === 'Đóng' || sr.textContent.trim() === 'Close')) { close = b; break; }
                }
            }
            if (close) close.click();
        })()
    """)
    print("   ✅ Settings dialog closed")
    
    await asyncio.sleep(1)
    return True


async def select_video_mode_and_settings(tab):
    """Select Video mode + settings (10s, 720p, 16:9)
    
    Flow giống MultiTabVideoGenerator._select_video_mode_on_tab:
    1. Click #model-select-trigger → mở menu
    2. Apply settings (duration, resolution, aspect) TRONG menu
    3. Click Video menuitem → đóng menu
    """
    # Step 1: Click trigger to open menu
    print("🎬 Opening model select menu...")
    trigger_info = None
    for attempt in range(10):
        await asyncio.sleep(0.5)
        trigger_info = await tab.evaluate("""
            (function() {
                var trigger = document.querySelector('#model-select-trigger');
                if (trigger) {
                    var rect = trigger.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
                return {found: false};
            })()
        """)
        if trigger_info and trigger_info.get('found'):
            break
        print(f"   Waiting for trigger... ({attempt+1})")

    if not trigger_info or not trigger_info.get('found'):
        print("⚠️ Trigger not found")
        return

    await tab.evaluate("""
        (function() {
            var trigger = document.querySelector('#model-select-trigger');
            if (trigger) trigger.click();
        })()
    """)
    await asyncio.sleep(1)

    # Check menu opened
    menu_state = await tab.evaluate("""
        (function() {
            var menu = document.querySelector('[data-radix-menu-content][data-state="open"]') ||
                       document.querySelector('[role="menu"][data-state="open"]');
            return menu ? {open: true} : {open: false};
        })()
    """)
    print(f"   Menu state: {menu_state}")

    if not menu_state.get('open'):
        # Fallback: CDP click
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

    # Step 2: Apply settings INSIDE the menu
    for label in ["10s", "720p", "16:9"]:
        result = await tab.evaluate(f"""
            (function() {{
                var buttons = document.querySelectorAll('button[aria-label]');
                for (var btn of buttons) {{
                    if (btn.getAttribute('aria-label') === '{label}') {{
                        btn.click();
                        return 'clicked ' + '{label}';
                    }}
                }}
                return '{label} not found';
            }})()
        """)
        print(f"   Setting {label}: {result}")
        await asyncio.sleep(0.3)

    # Step 3: Click Video option (closes menu)
    result = await tab.evaluate("""
        (function() {
            var items = document.querySelectorAll('[role="menuitem"]');
            for (var item of items) {
                var text = item.textContent || '';
                if (text.includes('Video') && text.includes('Tạo một video')) {
                    item.click();
                    return 'clicked Video';
                }
                var svg = item.querySelector('svg');
                if (svg && svg.querySelector('polygon')) {
                    item.click();
                    return 'clicked Video (polygon)';
                }
            }
            return 'Video not found';
        })()
    """)
    print(f"   Video mode: {result}")
    await asyncio.sleep(1)

    # Verify
    verify = await tab.evaluate("""
        (function() {
            var trigger = document.querySelector('#model-select-trigger');
            if (!trigger) return 'NO_TRIGGER';
            var svg = trigger.querySelector('svg');
            if (svg && svg.querySelector('polygon')) return 'VIDEO_MODE_OK';
            var text = trigger.textContent || '';
            if (text.includes('Video')) return 'VIDEO_MODE_OK';
            return 'UNKNOWN: ' + text.substring(0, 20);
        })()
    """)
    print(f"   ✅ Final mode: {verify}")


async def enter_prompt_and_submit(tab, prompt: str):
    """Enter prompt and submit - handles both ProseMirror editor and TEXTAREA"""
    escaped = prompt.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
    result = await tab.evaluate(f"""
        (function() {{
            // Try ProseMirror editor first (main /imagine page)
            var editor = document.querySelector('div.tiptap.ProseMirror') ||
                         document.querySelector('div[contenteditable="true"]');
            if (editor) {{
                editor.focus();
                editor.innerHTML = '<p>{escaped}</p>';
                editor.dispatchEvent(new Event('input', {{bubbles: true}}));
                return 'filled_prosemirror';
            }}
            // Try TEXTAREA (post page after image upload)
            var textarea = document.querySelector('textarea');
            if (textarea) {{
                textarea.focus();
                // React controlled input: need to use native setter
                var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSet.call(textarea, '{escaped}');
                textarea.dispatchEvent(new Event('input', {{bubbles: true}}));
                textarea.dispatchEvent(new Event('change', {{bubbles: true}}));
                return 'filled_textarea';
            }}
            return 'no_editor';
        }})()
    """)
    print(f"   Prompt: {result}")
    await asyncio.sleep(1)

    # Submit — tìm nút "Tạo video" và CDP click
    btn_pos = await tab.evaluate("""
        (function() {
            var btns = document.querySelectorAll('button');
            // Priority 1: aria-label "Tạo video" / "Create video"
            for (var b of btns) {
                var label = b.getAttribute('aria-label') || '';
                if (label === 'Tạo video' || label === 'Create video' || label === 'Generate video') {
                    var rect = b.getBoundingClientRect();
                    return {found: true, method: 'aria-label', label: label, disabled: b.disabled,
                            x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                }
            }
            // Priority 2: button[type="submit"]
            var submit = document.querySelector('button[type="submit"]');
            if (submit) {
                var rect = submit.getBoundingClientRect();
                return {found: true, method: 'type-submit', disabled: submit.disabled,
                        x: rect.x + rect.width/2, y: rect.y + rect.height/2};
            }
            // Priority 3: button text "Tạo video"
            for (var b of btns) {
                var text = (b.textContent || '').trim();
                if (text === 'Tạo video' || text === 'Create video') {
                    var rect = b.getBoundingClientRect();
                    return {found: true, method: 'text', text: text, disabled: b.disabled,
                            x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                }
            }
            // Priority 4: aria-label Send/Gửi
            for (var b of btns) {
                var label = (b.getAttribute('aria-label') || '').toLowerCase();
                if (label.includes('send') || label.includes('gửi')) {
                    var rect = b.getBoundingClientRect();
                    return {found: true, method: 'send', label: label, disabled: b.disabled,
                            x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                }
            }
            return {found: false};
        })()
    """)
    print(f"   Submit button: {btn_pos}")
    
    if btn_pos and btn_pos.get('found'):
        if btn_pos.get('disabled'):
            print(f"   ⚠️ Button disabled, waiting...")
            # Chờ button enable (React state update sau khi nhập prompt)
            for wait in range(10):
                await asyncio.sleep(1)
                is_disabled = await tab.evaluate("""
                    (function() {
                        var btns = document.querySelectorAll('button');
                        for (var b of btns) {
                            var label = b.getAttribute('aria-label') || '';
                            if (label === 'Tạo video' || label === 'Create video') return b.disabled;
                        }
                        var submit = document.querySelector('button[type="submit"]');
                        if (submit) return submit.disabled;
                        return true;
                    })()
                """)
                if not is_disabled:
                    # Re-get position
                    btn_pos = await tab.evaluate("""
                        (function() {
                            var btns = document.querySelectorAll('button');
                            for (var b of btns) {
                                var label = b.getAttribute('aria-label') || '';
                                if ((label === 'Tạo video' || label === 'Create video') && !b.disabled) {
                                    var rect = b.getBoundingClientRect();
                                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                                }
                            }
                            return {found: false};
                        })()
                    """)
                    break
            else:
                print("   ⚠️ Button still disabled after 10s")
        
        if btn_pos and btn_pos.get('found'):
            sx, sy = btn_pos['x'], btn_pos['y']
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mousePressed", x=sx, y=sy,
                button=cdp.input_.MouseButton.LEFT, click_count=1
            ))
            await asyncio.sleep(0.05)
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mouseReleased", x=sx, y=sy,
                button=cdp.input_.MouseButton.LEFT, click_count=1
            ))
            print(f"   ✅ Submit: CDP clicked ({btn_pos.get('method', '')}: {btn_pos.get('label', btn_pos.get('text', ''))})")
    else:
        print("   ❌ No submit button found")


async def wait_for_video_ready(tab, timeout=300):
    """Wait for video render"""
    start = time.time()
    while time.time() - start < timeout:
        status = await tab.evaluate("""
            (function() {
                var eyeOff = document.querySelector('svg.lucide-eye-off');
                if (eyeOff) return {ready: false, rejected: true};
                
                var downloadBtn = document.querySelector('button[aria-label="Tải xuống"]');
                if (!downloadBtn) {
                    var icons = document.querySelectorAll('svg.lucide-download');
                    for (var icon of icons) {
                        var btn = icon.closest('button');
                        if (btn) { downloadBtn = btn; break; }
                    }
                }
                if (!downloadBtn) return {ready: false, type: 'no_btn'};
                
                var container = downloadBtn.closest('div.flex.flex-row.border');
                if (!container) container = downloadBtn.parentElement;
                if (container) {
                    var cls = container.className || '';
                    if (cls.includes('opacity-50') || cls.includes('pointer-events-none'))
                        return {ready: false, type: 'generating'};
                }
                return {ready: true};
            })()
        """)
        if status and status.get("rejected"):
            print("⚠️ Video rejected!")
            return False
        if status and status.get("ready"):
            print("✅ Video ready!")
            return True
        elapsed = int(time.time() - start)
        if elapsed % 30 == 0 and elapsed > 0:
            print(f"   Rendering... ({elapsed}s)")
        await asyncio.sleep(3)
    print("❌ Render timeout")
    return False


async def click_share_and_download(browser, tab, post_id: str):
    """Click share → download video"""
    # Share
    await tab.evaluate("""
        (function() {
            var btn = document.querySelector('button[aria-label="Tạo link chia sẻ"]');
            if (!btn) {
                var icons = document.querySelectorAll('svg.lucide-share');
                for (var icon of icons) { var b = icon.closest('button'); if (b) { btn = b; break; } }
            }
            if (btn) btn.click();
        })()
    """)
    await asyncio.sleep(3)

    # Download
    video_url = f"https://imagine-public.x.ai/imagine-public/share-videos/{post_id}.mp4?cache=1"
    download_url = f"{video_url}&dl=1"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"📥 Downloading: {video_url}")
    download_tab = await browser.get(video_url, new_tab=True)
    await asyncio.sleep(3)

    try:
        await download_tab.send(cdp.browser.set_download_behavior(
            behavior="allow", download_path=str(OUTPUT_DIR.absolute())
        ))
    except Exception as e:
        print(f"   set_download_behavior: {e}")

    await download_tab.get(download_url)

    # Wait for file
    expected = OUTPUT_DIR / f"{post_id}.mp4"
    for i in range(30):
        await asyncio.sleep(5)
        if expected.exists() and os.path.getsize(expected) > 10000:
            await asyncio.sleep(2)
            size = os.path.getsize(expected)
            if os.path.getsize(expected) == size:
                print(f"✅ Downloaded: {expected} ({size / 1024 / 1024:.1f} MB)")
                try:
                    await download_tab.close()
                except:
                    pass
                return str(expected)
        if i % 3 == 0:
            print(f"   Waiting for download... ({i * 5}s)")

    try:
        await download_tab.close()
    except:
        pass
    print("⚠️ Download timeout")
    return None


async def _click_create_video_button(tab):
    """Click nút 'Tạo video' / 'Create video' bằng CDP mouse click.
    Đây là nút submit chính — KHÔNG cần bước submit riêng."""
    create_pos = await tab.evaluate("""
        (function() {
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                var label = b.getAttribute('aria-label') || '';
                var text = (b.textContent || '').trim();
                if (label === 'Tạo video' || label === 'Create video' || label === 'Generate video' ||
                    text === 'Tạo video' || text === 'Create video') {
                    var rect = b.getBoundingClientRect();
                    return {found: true, label: label || text, disabled: b.disabled,
                            x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                }
            }
            return {found: false};
        })()
    """)
    print(f"   Tạo video btn: {create_pos}")
    
    if not create_pos or not create_pos.get('found'):
        print("   ❌ 'Tạo video' button not found")
        return False
    
    # Wait for button to be enabled
    if create_pos.get('disabled'):
        print("   ⚠️ Tạo video disabled, waiting...")
        for w in range(15):
            await asyncio.sleep(1)
            create_pos = await tab.evaluate("""
                (function() {
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var label = b.getAttribute('aria-label') || '';
                        if (label === 'Tạo video' || label === 'Create video') {
                            var rect = b.getBoundingClientRect();
                            return {found: true, disabled: b.disabled,
                                    x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                        }
                    }
                    return {found: false};
                })()
            """)
            if create_pos and not create_pos.get('disabled'):
                break
    
    if create_pos and create_pos.get('found') and not create_pos.get('disabled'):
        cx, cy = create_pos['x'], create_pos['y']
        await tab.send(cdp.input_.dispatch_mouse_event(
            type_="mousePressed", x=cx, y=cy,
            button=cdp.input_.MouseButton.LEFT, click_count=1
        ))
        await asyncio.sleep(0.05)
        await tab.send(cdp.input_.dispatch_mouse_event(
            type_="mouseReleased", x=cx, y=cy,
            button=cdp.input_.MouseButton.LEFT, click_count=1
        ))
        print(f"   ✅ Tạo video: CDP clicked!")
        return True
    else:
        print("   ❌ Tạo video button still disabled or not found")
        return False


async def main():
    # === Parse args ===
    image_path = sys.argv[1] if len(sys.argv) > 1 else None
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Tạo video anime từ ảnh này, phong cách Ghibli, chuyển động nhẹ nhàng"

    if not image_path:
        # Tìm ảnh test trong project
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            files = glob.glob(f"assets/{ext}") + glob.glob(f"data/{ext}")
            if files:
                image_path = files[0]
                break
        if not image_path:
            print("Usage: python test_image_upload.py <image_path> [prompt]")
            print("   VD: python test_image_upload.py photo.jpg 'Tạo video từ ảnh'")
            sys.exit(1)

    print(f"🖼️  Image: {image_path}")
    print(f"📝 Prompt: {prompt}")
    print()

    # Load account
    acc = load_first_logged_in_account()
    if not acc:
        sys.exit(1)
    print(f"👤 Account: {acc['email']}")

    # Start browser
    config = zendriver.Config(headless=False)  # headed để debug
    config.add_argument(f"--user-agent={FIXED_USER_AGENT}")
    config.add_argument("--mute-audio")

    browser = zendriver.Browser(config)
    await browser.start()
    tab = browser.main_tab

    try:
        # Inject cookies
        print("\n🍪 Injecting cookies...")
        await tab.get("https://grok.com/favicon.ico")
        await asyncio.sleep(1)
        await inject_cookies(tab, acc["cookies"])

        # Navigate to /imagine
        print("\n🌐 Going to /imagine...")
        await tab.get(IMAGINE_URL)
        await asyncio.sleep(3)

        # Handle Cloudflare
        if not await handle_cloudflare(browser, tab):
            return

        await asyncio.sleep(2)

        # Tắt "Bật Tạo Video Tự Động" trong Settings → Hành vi (chỉ 1 lần)
        await disable_auto_video_generation(tab)

        # Upload image
        print("\n📤 Uploading image...")
        if not await upload_image_via_cdp(tab, image_path):
            print("❌ Upload failed")
            # Screenshot debug
            await save_debug_screenshot(tab, "upload_failed")
            return

        # Wait for redirect to /imagine/post/{uuid}
        print("\n⏳ Waiting for post page (image upload redirect)...")
        upload_post_id = await wait_for_post_redirect(tab, timeout=30)

        if not upload_post_id:
            url = await tab.evaluate("window.location.href")
            print(f"   Current URL: {url}")

            if "/imagine/post/" not in url:
                print("⚠️ No redirect to post page after upload.")
                await save_debug_screenshot(tab, "no_redirect")
                
                # Thử navigate trực tiếp nếu có post ID trong page
                post_from_page = await tab.evaluate("""
                    (function() {
                        // Tìm post ID từ các link trên page
                        var links = document.querySelectorAll('a[href*="/imagine/post/"]');
                        for (var a of links) {
                            var m = a.href.match(/\\/imagine\\/post\\/([a-f0-9-]{36})/);
                            if (m) return m[1];
                        }
                        return null;
                    })()
                """)
                if post_from_page:
                    upload_post_id = post_from_page
                    print(f"   Found post ID from page: {upload_post_id}")
                    await tab.get(f"https://grok.com/imagine/post/{upload_post_id}")
                    await asyncio.sleep(3)
                else:
                    print("❌ Cannot find post page after upload")
                    return
        
        print(f"✅ Upload Post ID: {upload_post_id}")
        await asyncio.sleep(2)

        # Post page sau upload ảnh (auto-video đã tắt):
        # Flow: prompt → Tùy chọn Video → settings (10s, 720p) → Tạo video
        # Post page KHÔNG có #model-select-trigger, KHÔNG có 16:9
        # Editor là TEXTAREA, không phải ProseMirror
        
        await save_debug_screenshot(tab, "post_page")
        
        # Chờ editor xuất hiện
        print("\n🎬 Configuring post page...")
        editor_found = False
        for wait in range(15):
            has_editor = await tab.evaluate("""
                (function() {
                    var textarea = document.querySelector('textarea');
                    var editor = document.querySelector('div.tiptap.ProseMirror') ||
                                 document.querySelector('div[contenteditable="true"]');
                    return !!(textarea || editor);
                })()
            """)
            if has_editor:
                editor_found = True
                break
            await asyncio.sleep(1)
            if wait % 3 == 0:
                print(f"   Waiting for editor... ({wait}s)")
        
        if not editor_found:
            print("❌ Editor never appeared on post page")
            await save_debug_screenshot(tab, "no_editor")
            return
        
        # === Step 1: Nhập prompt vào textarea ===
        escaped = prompt.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
        fill_result = await tab.evaluate(f"""
            (function() {{
                // Try TEXTAREA first (post page after image upload)
                var textarea = document.querySelector('textarea');
                if (textarea) {{
                    textarea.focus();
                    var nativeSet = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    nativeSet.call(textarea, '{escaped}');
                    textarea.dispatchEvent(new Event('input', {{bubbles: true}}));
                    textarea.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled_textarea';
                }}
                // Fallback: ProseMirror editor
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
        print(f"   ✏️ Prompt: {fill_result}")
        await asyncio.sleep(1)
        
        # === Step 2: Click "Tùy chọn Video" → mở settings panel ===
        btn_pos = await tab.evaluate("""
            (function() {
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var label = b.getAttribute('aria-label') || '';
                    if (label === 'Tùy chọn Video' || label === 'Video options' || label === 'Video Options') {
                        var rect = b.getBoundingClientRect();
                        return {found: true, label: label, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
                // Fallback: tìm bằng text
                for (var b of btns) {
                    var text = (b.textContent || '').trim();
                    if (text === 'Tùy chọn Video' || text === 'Video options') {
                        var rect = b.getBoundingClientRect();
                        return {found: true, label: text, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
                return {found: false};
            })()
        """)
        print(f"   Tùy chọn Video btn: {btn_pos}")
        
        if not btn_pos or not btn_pos.get('found'):
            print("   ⚠️ 'Tùy chọn Video' button not found, trying direct submit...")
            # Fallback: click "Tạo video" directly without settings
            await _click_create_video_button(tab)
        else:
            # CDP click to open panel (Radix UI needs real mouse events)
            bx, by = btn_pos['x'], btn_pos['y']
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mousePressed", x=bx, y=by,
                button=cdp.input_.MouseButton.LEFT, click_count=1
            ))
            await asyncio.sleep(0.05)
            await tab.send(cdp.input_.dispatch_mouse_event(
                type_="mouseReleased", x=bx, y=by,
                button=cdp.input_.MouseButton.LEFT, click_count=1
            ))
            print(f"   Tùy chọn Video: CDP clicked")
            await asyncio.sleep(1.5)
            
            # Debug: dump panel buttons
            panel_info = await tab.evaluate("""
                (function() {
                    // Tìm popover panel (Radix)
                    var popover = document.querySelector('[data-radix-popper-content-wrapper]');
                    if (!popover) {
                        var panels = document.querySelectorAll('[data-state="open"]');
                        for (var p of panels) {
                            if (p.querySelectorAll('button').length > 2) { popover = p; break; }
                        }
                    }
                    if (!popover) return {found: false};
                    var buttons = popover.querySelectorAll('button');
                    var labels = [];
                    for (var b of buttons) {
                        var text = b.textContent.trim().substring(0, 30);
                        var ariaLabel = b.getAttribute('aria-label') || '';
                        var pressed = b.getAttribute('aria-pressed') || b.getAttribute('data-state') || '';
                        labels.push({text: text, label: ariaLabel, state: pressed});
                    }
                    return {found: true, count: buttons.length, buttons: labels};
                })()
            """)
            print(f"   Panel: {json.dumps(panel_info, ensure_ascii=False)[:600]}")
            
            # === Step 3: Chọn settings trong panel (chỉ 10s, 720p — KHÔNG có 16:9 trên post page) ===
            for label in ["10s", "720p"]:
                result = await tab.evaluate(f"""
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
                if result and result.get('found'):
                    sx, sy = result['x'], result['y']
                    await tab.send(cdp.input_.dispatch_mouse_event(
                        type_="mousePressed", x=sx, y=sy,
                        button=cdp.input_.MouseButton.LEFT, click_count=1
                    ))
                    await asyncio.sleep(0.05)
                    await tab.send(cdp.input_.dispatch_mouse_event(
                        type_="mouseReleased", x=sx, y=sy,
                        button=cdp.input_.MouseButton.LEFT, click_count=1
                    ))
                    print(f"   Setting {label}: CDP clicked ✅")
                else:
                    print(f"   Setting {label}: not found")
                await asyncio.sleep(0.3)
            
            # === Step 4: Click "Tạo video" button (CDP click) ===
            # Đây là nút submit — KHÔNG cần bước submit riêng
            await asyncio.sleep(0.5)
            await _click_create_video_button(tab)
        
        await asyncio.sleep(2)
        await save_debug_screenshot(tab, "after_submit")
        
        await asyncio.sleep(3)

        # Wait for new post ID (video generation creates new post)
        print("\n⏳ Waiting for video post ID...")
        new_post_id = None
        for i in range(60):
            try:
                url = await tab.evaluate("window.location.href")
            except Exception as e:
                print(f"   ⚠️ Tab connection lost: {e}")
                # Browser có thể đã navigate đi hoặc crash
                # Thử lấy tab mới
                try:
                    tabs = await browser.get_targets()
                    for t in tabs:
                        if hasattr(t, 'url') and '/imagine/post/' in str(getattr(t, 'url', '')):
                            tab = t
                            url = await tab.evaluate("window.location.href")
                            break
                    else:
                        break
                except:
                    break
            
            match = re.search(r'/imagine/post/([a-f0-9-]{36})', url)
            if match:
                pid = match.group(1)
                if pid != upload_post_id:  # New post ID (video, not the upload)
                    new_post_id = pid
                    break
            await asyncio.sleep(1)
            if i % 10 == 0 and i > 0:
                print(f"   Waiting... ({i}s)")

        if new_post_id:
            print(f"✅ Video Post ID: {new_post_id}")
        else:
            new_post_id = upload_post_id
            print(f"   Using same post ID: {new_post_id}")

        # Wait for video render
        print("\n⏳ Waiting for video render...")
        if await wait_for_video_ready(tab):
            # Share + Download
            print("\n📥 Downloading...")
            result = await click_share_and_download(browser, tab, new_post_id)
            if result:
                print(f"\n🎉 Done! Video saved: {result}")
            else:
                print("\n⚠️ Download failed but video was generated")
        else:
            print("\n❌ Video render failed")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🔄 Closing browser...")
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
