"""Test download video from History"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, '.')


async def test_download():
    """Test download video using saved cookies"""
    import zendriver
    from zendriver import cdp
    from src.core.cf_solver import get_chrome_user_agent
    from src.core.video_generator import OUTPUT_DIR, VIDEO_DOWNLOAD_URL
    import re
    import requests
    from datetime import datetime
    
    # Test with a known post_id (replace with actual one)
    post_id = "674f312b-7223-4699-b963-9d553f43926b"  # From earlier test - should be ready
    
    # Load cookies from accounts.json
    accounts_file = Path("data/accounts.json")
    data = json.loads(accounts_file.read_text())
    cookies = data["accounts"][0]["cookies"]
    email = data["accounts"][0]["email"]
    
    print("=" * 60)
    print("Download Test")
    print("=" * 60)
    print(f"Post ID: {post_id}")
    print(f"Account: {email}")
    print(f"Cookies: {list(cookies.keys())}")
    
    # Create browser
    user_agent = get_chrome_user_agent()
    config = zendriver.Config(headless=True)
    config.add_argument(f"--user-agent={user_agent}")
    
    browser = zendriver.Browser(config)
    await browser.start()
    
    try:
        # Step 1: Inject cookies
        print("\n🍪 Injecting cookies...")
        await browser.main_tab.get("https://grok.com/favicon.ico")
        await asyncio.sleep(1)
        
        for name, value in cookies.items():
            try:
                await browser.main_tab.send(
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
        
        # Step 2: Go to post page
        post_url = f"https://grok.com/imagine/post/{post_id}"
        print(f"🌐 Going to {post_url}...")
        await browser.main_tab.get(post_url)
        await asyncio.sleep(3)
        
        # Step 3: Handle Cloudflare
        html = await browser.main_tab.get_content()
        if 'Just a moment' in html or 'challenge-platform' in html:
            print("🔐 Solving Cloudflare...")
            for i in range(30):
                browser_cookies = await browser.cookies.get_all()
                for c in browser_cookies:
                    if c.name == "cf_clearance":
                        print("✅ Cloudflare passed!")
                        break
                else:
                    await asyncio.sleep(1)
                    if i % 5 == 0:
                        print(f"⏳ Waiting... ({i}s)")
                    continue
                break
            await asyncio.sleep(2)
        
        # Take screenshot to debug
        import base64
        screenshot = await browser.main_tab.send(cdp.page.capture_screenshot())
        if screenshot:
            with open("data/debug_download.png", "wb") as f:
                f.write(base64.b64decode(screenshot))
            print("📸 Screenshot saved to data/debug_download.png")
        
        # Get page content for debugging
        html = await browser.main_tab.get_content()
        print(f"   Page title: {await browser.main_tab.evaluate('document.title')}")
        print(f"   Page URL: {await browser.main_tab.evaluate('window.location.href')}")
        
        # Step 4: Check video status
        print("⏳ Checking video status...")
        video_ready = False
        for attempt in range(40):  # Wait up to 2 minutes
            # Check multiple indicators
            status = await browser.main_tab.evaluate("""
                (function() {
                    // Check for video element
                    var video = document.querySelector('video');
                    if (video && video.src) return {ready: true, type: 'video'};
                    
                    // Check for share button enabled
                    var shareBtn = document.querySelector('button[aria-label*="share" i]') ||
                                   document.querySelector('button[aria-label*="chia sẻ"]');
                    if (shareBtn && !shareBtn.disabled) return {ready: true, type: 'share_btn'};
                    
                    // Check for border container
                    var c = document.querySelector('div.flex.flex-row.border');
                    if (c && !c.classList.contains('pointer-events-none')) return {ready: true, type: 'border'};
                    
                    // Check for loading indicator
                    var loading = document.querySelector('[class*="animate-spin"]') ||
                                  document.querySelector('[class*="loading"]');
                    if (loading) return {ready: false, type: 'loading'};
                    
                    return {ready: false, type: 'unknown'};
                })()
            """)
            print(f"   Status: {status}")
            if status and status.get('ready'):
                video_ready = True
                print("✅ Video is ready!")
                break
            await asyncio.sleep(3)
        
        if not video_ready:
            print("⚠️ Video may not be ready, trying anyway...")
        
        # Step 5: Click share
        print("🔗 Clicking share...")
        share_result = await browser.main_tab.evaluate("""
            (function() {
                var btn = document.querySelector('button[aria-label*="share" i]') ||
                          document.querySelector('button[aria-label*="chia sẻ"]');
                if (!btn) {
                    // Try finding by SVG icon
                    var svgs = document.querySelectorAll('svg');
                    for (var svg of svgs) {
                        if (svg.classList.contains('lucide-share') || 
                            svg.innerHTML.includes('path') && svg.closest('button')) {
                            btn = svg.closest('button');
                            break;
                        }
                    }
                }
                if (btn) {
                    btn.click();
                    return {clicked: true, text: btn.textContent || btn.getAttribute('aria-label')};
                }
                return {clicked: false};
            })()
        """)
        print(f"   Share result: {share_result}")
        await asyncio.sleep(3)
        
        # Try clicking share again if needed
        if not share_result.get('clicked'):
            print("   Trying alternative share method...")
            await browser.main_tab.evaluate("""
                (function() {
                    var btns = document.querySelectorAll('button');
                    for (var btn of btns) {
                        var label = btn.getAttribute('aria-label') || btn.textContent || '';
                        if (label.toLowerCase().includes('share') || label.includes('chia sẻ')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                })()
            """)
            await asyncio.sleep(2)
        
        # Step 6: Download
        print("📥 Downloading video...")
        video_url = VIDEO_DOWNLOAD_URL.format(post_id=post_id)
        
        # Get cookies from browser
        browser_cookies = await browser.cookies.get_all()
        cookies_dict = {}
        for c in browser_cookies:
            cookies_dict[c.name] = c.value
        
        print(f"   Browser cookies: {list(cookies_dict.keys())}")
        
        # Download
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_test_download.mp4"
        path = OUTPUT_DIR / filename
        
        headers = {
            'User-Agent': user_agent,
            'Referer': 'https://grok.com/',
        }
        
        response = requests.get(video_url, cookies=cookies_dict, headers=headers, timeout=120, stream=True)
        
        print(f"   HTTP Status: {response.status_code}")
        
        if response.status_code == 200:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            import os
            if path.exists() and os.path.getsize(path) > 10000:
                size_mb = os.path.getsize(path) / (1024 * 1024)
                print(f"✅ Downloaded: {filename} ({size_mb:.1f} MB)")
            else:
                print(f"❌ File too small: {os.path.getsize(path)} bytes")
        else:
            print(f"❌ Download failed: HTTP {response.status_code}")
            
    finally:
        await browser.stop()
        print("\n🛑 Browser closed")


if __name__ == "__main__":
    asyncio.run(test_download())
