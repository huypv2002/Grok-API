"""Video Generator - Browser automation for Grok video generation"""
import time
import re
import ssl
import os

ssl._create_default_https_context = ssl._create_unverified_context

from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
import httpx
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from .models import Account, VideoSettings, VideoTask
from .browser_controller import BrowserController

IMAGINE_URL = "https://grok.com/imagine"
OUTPUT_DIR = Path("output")


class VideoGenerator:
    def __init__(self):
        self.browser: Optional[BrowserController] = None
        self.client = httpx.Client(timeout=120.0, verify=False)
    
    def generate_video(
        self,
        account: Account,
        prompt: str,
        settings: VideoSettings,
        on_status: Optional[Callable] = None,
        headless: bool = False  # Default NOT headless vì Cloudflare
    ) -> VideoTask:
        """Full video generation flow using browser automation"""
        task = VideoTask(
            account_email=account.email,
            prompt=prompt,
            settings=settings,
            status="creating"
        )
        
        self.browser = BrowserController(account.fingerprint_id)
        
        try:
            # Step 1: Open browser (NOT headless to bypass Cloudflare)
            if on_status:
                on_status("Opening browser...")
            self.browser.open_browser(headless=False)  # Always visible for Cloudflare
            
            # Minimize window if user wanted headless
            if headless and self.browser.driver:
                self.browser.driver.minimize_window()
                if on_status:
                    on_status("Browser minimized (background mode)")
            
            # Step 2: Navigate to grok.com first to set cookies
            if on_status:
                on_status("Setting up session...")
            self.browser.navigate_to("https://grok.com", wait_time=3)
            
            # Step 3: Inject cookies
            if account.cookies:
                if on_status:
                    on_status("Restoring session cookies...")
                self.browser.set_cookies(account.cookies, ".grok.com")
                time.sleep(1)
                self.browser.driver.refresh()
                time.sleep(3)
            
            # Step 4: Navigate to imagine page
            if on_status:
                on_status("Navigating to Grok Imagine...")
            self.browser.navigate_to(IMAGINE_URL, wait_time=5)
            
            # Handle Cloudflare challenge
            if on_status:
                on_status("Checking for Cloudflare...")
            
            cloudflare_passed = self._handle_cloudflare(on_status, timeout=120)
            if not cloudflare_passed:
                task.status = "failed"
                task.error_message = "Cloudflare challenge timeout"
                return task
            
            # Check if logged in
            current_url = self.browser.get_current_url()
            if 'sign-in' in current_url or 'accounts.x.ai' in current_url:
                if on_status:
                    on_status("Session expired. Please login again.")
                task.status = "failed"
                task.error_message = "Session expired. Please login again."
                return task
            
            time.sleep(3)
            
            # Step 5: Select Video mode
            if on_status:
                on_status("Selecting Video mode...")
            self._select_video_mode(on_status)
            time.sleep(2)
            
            # Step 6: Enter prompt
            if on_status:
                on_status("Entering prompt...")
            if not self._enter_prompt(prompt, on_status):
                task.status = "failed"
                task.error_message = "Failed to enter prompt"
                return task
            time.sleep(1)
            
            # Step 7: Submit
            if on_status:
                on_status("Submitting...")
            self._submit_prompt()
            time.sleep(3)
            
            # Step 8: Wait for video to be FULLY generated
            if on_status:
                on_status("Waiting for video generation (this may take 2-5 minutes)...")
            
            # Wait for download button to appear (means video is ready)
            video_ready = self._wait_for_download_button(on_status, timeout=600)
            
            if video_ready:
                if on_status:
                    on_status("Video ready! Clicking download...")
                
                # Click download button and get video URL
                video_url = self._click_download_and_get_url(on_status)
                
                if video_url:
                    task.media_url = video_url
                    
                    if on_status:
                        on_status("Downloading video...")
                    output_path = self._download_video(video_url, account.email, prompt)
                    
                    if output_path:
                        file_size = os.path.getsize(output_path)
                        if file_size < 100000:
                            if on_status:
                                on_status(f"Warning: File too small ({file_size} bytes)")
                            task.status = "failed"
                            task.error_message = "Downloaded file too small"
                            return task
                        
                        task.output_path = output_path
                        task.status = "completed"
                        task.completed_at = datetime.now()
                        if on_status:
                            on_status(f"Done! Saved: {output_path}")
                    else:
                        task.status = "failed"
                        task.error_message = "Download failed"
                else:
                    task.status = "failed"
                    task.error_message = "Could not get video URL"
            else:
                task.status = "failed"
                task.error_message = "Video generation timeout"
            
            return task
            
        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            if on_status:
                on_status(f"Error: {e}")
            return task
        finally:
            if self.browser:
                self.browser.close_browser()
    
    def _select_video_mode(self, on_status: Optional[Callable] = None) -> None:
        """Select Video mode from dropdown"""
        if not self.browser or not self.browser.driver:
            return
        
        try:
            # Click model selector
            model_btn = self.browser.find_element('#model-select-trigger')
            if model_btn:
                model_btn.click()
                time.sleep(1)
                
                # Find and click Video option
                video_opts = self.browser.find_elements('//span[contains(text(), "Video")]', By.XPATH)
                for opt in video_opts:
                    try:
                        opt.click()
                        if on_status:
                            on_status("Video mode selected")
                        time.sleep(0.5)
                        return
                    except:
                        continue
        except Exception as e:
            if on_status:
                on_status(f"Mode selection: {e}")
    
    def _handle_cloudflare(self, on_status: Optional[Callable], timeout: int = 120) -> bool:
        """Handle Cloudflare Turnstile challenge"""
        if not self.browser or not self.browser.driver:
            return False
        
        start = time.time()
        
        while time.time() - start < timeout:
            page_source = self.browser.get_page_source()
            current_url = self.browser.get_current_url()
            
            # Check if Cloudflare challenge is present
            if 'Just a moment' not in page_source and 'challenge' not in current_url:
                if on_status:
                    on_status("Cloudflare passed!")
                return True
            
            if on_status:
                elapsed = int(time.time() - start)
                on_status(f"Waiting for Cloudflare... ({elapsed}s) - Please solve if needed")
            
            # Try to click the checkbox
            try:
                # Find Cloudflare iframe
                iframes = self.browser.find_elements('iframe')
                for iframe in iframes:
                    src = iframe.get_attribute('src') or ''
                    if 'challenges.cloudflare.com' in src or 'turnstile' in src:
                        # Switch to iframe and click
                        self.browser.driver.switch_to.frame(iframe)
                        try:
                            checkbox = self.browser.find_element('input[type="checkbox"]')
                            if checkbox:
                                checkbox.click()
                        except:
                            pass
                        self.browser.driver.switch_to.default_content()
                        break
            except:
                pass
            
            time.sleep(3)
        
        return False
    
    def _enter_prompt(self, prompt: str, on_status: Optional[Callable] = None) -> bool:
        """Enter prompt in editor"""
        if not self.browser or not self.browser.driver:
            return False
        
        try:
            # Try multiple selectors for the editor
            selectors = [
                'div.tiptap.ProseMirror',
                'div[contenteditable="true"]',
                '.ProseMirror',
                'div[data-placeholder]'
            ]
            
            editor = None
            for sel in selectors:
                editor = self.browser.find_element(sel)
                if editor:
                    break
            
            if editor:
                # Click to focus
                editor.click()
                time.sleep(0.5)
                
                # Clear existing content
                self.browser.execute_script("arguments[0].innerHTML = ''", editor)
                time.sleep(0.3)
                
                # Type prompt
                editor.send_keys(prompt)
                time.sleep(0.5)
                
                if on_status:
                    on_status(f"Prompt entered: {prompt[:40]}...")
                return True
            else:
                if on_status:
                    on_status("Could not find editor element")
                return False
                
        except Exception as e:
            if on_status:
                on_status(f"Prompt error: {e}")
            return False
    
    def _submit_prompt(self) -> None:
        """Click submit button"""
        if not self.browser or not self.browser.driver:
            return
        
        try:
            # Wait for submit button to be enabled
            time.sleep(1)
            
            # Find submit button
            submit = self.browser.find_element('button[type="submit"]')
            if submit:
                # Check if button is enabled
                is_disabled = submit.get_attribute('disabled')
                if is_disabled:
                    time.sleep(2)  # Wait more
                submit.click()
            else:
                # Try pressing Enter
                self.browser.send_keys(Keys.ENTER)
        except Exception as e:
            print(f"Submit error: {e}")
    
    def _wait_for_video_complete(self, on_status: Optional[Callable], timeout: int = 600) -> Optional[str]:
        """Wait for video to be FULLY generated"""
        if not self.browser or not self.browser.driver:
            return None
        
        start = time.time()
        last_url = None
        stable_count = 0
        check_count = 0
        
        while time.time() - start < timeout:
            try:
                check_count += 1
                video_url = self._find_video_url()
                
                if video_url:
                    if on_status:
                        on_status(f"Found video URL, verifying...")
                    
                    # Verify video is ready (has content)
                    if self._verify_video_ready(video_url):
                        if on_status:
                            on_status("Video ready!")
                        return video_url
                    
                    # Track URL stability - if same URL appears 3 times, try download
                    if video_url == last_url:
                        stable_count += 1
                        if stable_count >= 3:
                            if on_status:
                                on_status("Video URL stable, downloading...")
                            return video_url
                    else:
                        stable_count = 0
                        last_url = video_url
                else:
                    # Check if still generating
                    loading = self._check_loading_state()
                    elapsed = int(time.time() - start)
                    
                    if on_status:
                        if loading:
                            on_status(f"Generating video... ({elapsed}s)")
                        elif check_count % 5 == 0:
                            on_status(f"Waiting for video... ({elapsed}s)")
                    
            except Exception as e:
                if on_status:
                    on_status(f"Check error: {str(e)[:30]}")
            
            time.sleep(3)  # Check every 3 seconds
        
        return None
    
    def _wait_for_download_button(self, on_status: Optional[Callable], timeout: int = 600) -> bool:
        """Wait for download button to appear (means video is ready)"""
        if not self.browser or not self.browser.driver:
            return False
        
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                # Look for download button with aria-label="Tải xuống" or "Download"
                download_selectors = [
                    'button[aria-label="Tải xuống"]',
                    'button[aria-label="Download"]',
                    'button[aria-label*="download" i]',
                    'button[aria-label*="tải" i]',
                    'button svg.lucide-download',
                    'button:has(svg[class*="download"])',
                ]
                
                for sel in download_selectors:
                    try:
                        btn = self.browser.find_element(sel)
                        if btn and btn.is_displayed():
                            if on_status:
                                on_status("Download button found!")
                            return True
                    except:
                        continue
                
                # Also check for video element
                videos = self.browser.find_elements('video')
                for v in videos:
                    try:
                        src = v.get_attribute('src')
                        if src and '.mp4' in src:
                            if on_status:
                                on_status("Video element found!")
                            return True
                    except:
                        continue
                
                elapsed = int(time.time() - start)
                if on_status and elapsed % 10 == 0:
                    on_status(f"Generating video... ({elapsed}s)")
                    
            except Exception as e:
                pass
            
            time.sleep(3)
        
        return False
    
    def _click_download_and_get_url(self, on_status: Optional[Callable] = None) -> Optional[str]:
        """Click download button and get video URL"""
        if not self.browser or not self.browser.driver:
            return None
        
        try:
            # First try to find video URL directly from video element
            video_url = self._find_video_url()
            if video_url:
                if on_status:
                    on_status(f"Found video URL directly")
                return video_url
            
            # Try to find and click download button using JavaScript
            # Based on HTML: <button aria-label="Tải xuống"> with svg.lucide-download
            js_click_download = """
            // Method 1: Find by aria-label (exact match)
            var btn = document.querySelector('button[aria-label="Tải xuống"]');
            if (btn && btn.offsetParent !== null) {
                btn.click();
                return 'clicked_aria';
            }
            
            // Method 2: Find by svg class lucide-download
            var svg = document.querySelector('svg.lucide-download');
            if (svg) {
                var btn = svg.closest('button');
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    return 'clicked_svg';
                }
            }
            
            // Method 3: Find button containing download icon
            var buttons = document.querySelectorAll('button');
            for (var b of buttons) {
                var hasSvg = b.querySelector('svg.lucide-download') || 
                             b.querySelector('svg[class*="download"]');
                if (hasSvg && b.offsetParent !== null) {
                    b.click();
                    return 'clicked_btn';
                }
            }
            
            return null;
            """
            
            clicked = self.browser.execute_script(js_click_download)
            
            if clicked:
                if on_status:
                    on_status(f"Clicked download button ({clicked}), waiting...")
                time.sleep(2)
                
                # After clicking, browser may trigger download or show video
                # Try to find video URL
                video_url = self._find_video_url()
                if video_url:
                    return video_url
                
                # Wait a bit more and try again
                time.sleep(3)
                video_url = self._find_video_url()
                if video_url:
                    return video_url
            
            # Try Selenium click as fallback
            download_selectors = [
                'button[aria-label="Tải xuống"]',
                'button[aria-label="Download"]',
            ]
            
            for sel in download_selectors:
                try:
                    btn = self.browser.find_element(sel)
                    if btn and btn.is_displayed():
                        if on_status:
                            on_status("Clicking download via Selenium...")
                        self.browser.execute_script("arguments[0].click();", btn)
                        time.sleep(3)
                        
                        video_url = self._find_video_url()
                        if video_url:
                            return video_url
                except:
                    continue
            
            # Final attempt - search page source
            video_url = self._find_video_url()
            return video_url
            
        except Exception as e:
            if on_status:
                on_status(f"Download error: {str(e)[:40]}")
            return None
    
    def _find_video_url(self) -> Optional[str]:
        """Find video URL in page using multiple methods"""
        if not self.browser:
            return None
        
        try:
            # Method 1: Use JavaScript to find video src (most reliable)
            js_find_video = """
            // Check video elements
            var videos = document.querySelectorAll('video');
            for (var v of videos) {
                if (v.src && v.src.includes('.mp4') && v.src.startsWith('http')) {
                    return v.src;
                }
                if (v.currentSrc && v.currentSrc.includes('.mp4') && v.currentSrc.startsWith('http')) {
                    return v.currentSrc;
                }
                var sources = v.querySelectorAll('source');
                for (var s of sources) {
                    if (s.src && s.src.includes('.mp4') && s.src.startsWith('http')) {
                        return s.src;
                    }
                }
            }
            
            // Check for blob URLs and convert
            for (var v of videos) {
                if (v.src && v.src.startsWith('blob:')) {
                    // Can't directly get blob URL content, but video exists
                    return 'blob:' + v.src;
                }
            }
            
            return null;
            """
            
            js_result = self.browser.execute_script(js_find_video)
            if js_result and js_result.startswith('http'):
                return js_result
            
            # Method 2: Check video elements via Selenium
            videos = self.browser.find_elements('video')
            for v in videos:
                try:
                    src = v.get_attribute('src')
                    if src and '.mp4' in src and src.startswith('http'):
                        return src
                    
                    current_src = v.get_attribute('currentSrc')
                    if current_src and '.mp4' in current_src and current_src.startswith('http'):
                        return current_src
                    
                    sources = v.find_elements(By.TAG_NAME, 'source')
                    for s in sources:
                        src = s.get_attribute('src')
                        if src and '.mp4' in src and src.startswith('http'):
                            return src
                except:
                    continue
            
            # Method 3: Search page source for video URLs
            html = self.browser.get_page_source()
            
            patterns = [
                r'https://imagine-public\.x\.ai/[^"\'<>\s\)]+\.mp4[^"\'<>\s\)]*',
                r'https://[^"\'<>\s]+\.mp4(?:\?[^"\'<>\s]*)?',
                r'"src"\s*:\s*"(https://[^"]+\.mp4[^"]*)"',
                r'"url"\s*:\s*"(https://[^"]+\.mp4[^"]*)"',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html)
                for url in matches:
                    if 'thumbnail' in url.lower() or 'preview' in url.lower():
                        continue
                    url = url.replace('\\u0026', '&').replace('\\/', '/').strip('"')
                    if url.startswith('http') and '.mp4' in url:
                        return url
            
        except Exception as e:
            print(f"Find video URL error: {e}")
        
        return None
    
    def _check_loading_state(self) -> Optional[str]:
        """Check if video is still generating"""
        if not self.browser:
            return None
        
        try:
            # Look for loading indicators
            loading_selectors = [
                '.animate-spin',
                '[class*="loading"]',
                '[class*="generating"]',
                '.spinner',
                'svg[class*="animate"]',
                '[class*="pulse"]'
            ]
            
            for sel in loading_selectors:
                elements = self.browser.find_elements(sel)
                if elements:
                    return "generating"
            
            # Check for progress text in page
            html = self.browser.get_page_source()
            loading_texts = ['generating', 'creating', 'processing', 'loading', 'please wait']
            for text in loading_texts:
                if text in html.lower():
                    return "in progress"
            
            # Check for video placeholder (means video is being generated)
            placeholders = self.browser.find_elements('[class*="placeholder"]')
            if placeholders:
                return "generating"
                
        except:
            pass
        
        return None
    
    def _verify_video_ready(self, url: str) -> bool:
        """Verify video URL is actually ready to download"""
        try:
            # Do a HEAD request to check content-length
            response = self.client.head(url, follow_redirects=True, timeout=10.0)
            if response.status_code == 200:
                content_length = response.headers.get('content-length', '0')
                content_type = response.headers.get('content-type', '')
                
                # Video should be at least 500KB and be video type
                size = int(content_length)
                if size > 500000:
                    return True
                elif size > 100000 and 'video' in content_type:
                    return True
        except Exception as e:
            pass
        return False
    
    def _download_video(self, url: str, email: str, prompt: str, retry: int = 3) -> Optional[str]:
        """Download video file using multiple methods"""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        email_short = email.split("@")[0][:10]
        prompt_short = re.sub(r'[^\w\s]', '', prompt)[:20].replace(' ', '_')
        filename = f"{ts}_{email_short}_{prompt_short}.mp4"
        path = OUTPUT_DIR / filename
        
        # Clean URL
        url = url.replace('\\u0026', '&').replace('\\/', '/')
        
        # Method 1: Try download using browser's fetch (has cookies/session)
        if self.browser and self.browser.driver:
            try:
                result = self._download_via_browser(url, str(path.absolute()))
                if result and path.exists():
                    file_size = os.path.getsize(path)
                    if file_size > 100000:
                        print(f"Downloaded via browser fetch: {path} ({file_size} bytes)")
                        return str(path)
            except Exception as e:
                print(f"Browser fetch failed: {e}")
            
            # Method 2: Use browser to create download link and click
            try:
                result = self._download_via_link_click(url, filename)
                if result:
                    # Check default download folder
                    import glob
                    download_paths = [
                        Path.home() / "Downloads" / filename,
                        Path.home() / "Downloads" / f"{filename.replace('.mp4', '')}*.mp4",
                    ]
                    
                    time.sleep(3)  # Wait for download
                    
                    for dp in download_paths:
                        if '*' in str(dp):
                            matches = glob.glob(str(dp))
                            if matches:
                                # Move to output folder
                                import shutil
                                shutil.move(matches[0], str(path))
                                if path.exists() and os.path.getsize(path) > 100000:
                                    print(f"Downloaded via link click: {path}")
                                    return str(path)
                        elif dp.exists():
                            import shutil
                            shutil.move(str(dp), str(path))
                            if path.exists() and os.path.getsize(path) > 100000:
                                print(f"Downloaded via link click: {path}")
                                return str(path)
            except Exception as e:
                print(f"Link click download failed: {e}")
        
        # Method 3: Fallback to httpx with browser cookies
        cookies_dict = {}
        if self.browser and self.browser.driver:
            try:
                cookies_dict = self.browser.get_cookies()
            except:
                pass
        
        for attempt in range(retry):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
                    'Referer': 'https://grok.com/',
                    'Origin': 'https://grok.com',
                }
                
                with self.client.stream("GET", url, follow_redirects=True, timeout=180.0, headers=headers, cookies=cookies_dict) as r:
                    if r.status_code != 200:
                        print(f"Download attempt {attempt + 1}: HTTP {r.status_code}")
                        time.sleep(2)
                        continue
                    
                    with open(path, "wb") as f:
                        for chunk in r.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                
                if path.exists():
                    file_size = os.path.getsize(path)
                    if file_size > 100000:
                        return str(path)
                        
            except Exception as e:
                print(f"Download attempt {attempt + 1} error: {e}")
                time.sleep(3)
        
        return None
    
    def _download_via_link_click(self, url: str, filename: str) -> bool:
        """Create a download link and click it"""
        if not self.browser or not self.browser.driver:
            return False
        
        try:
            js_code = """
            var a = document.createElement('a');
            a.href = arguments[0];
            a.download = arguments[1];
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            return true;
            """
            
            result = self.browser.execute_script(js_code, url, filename)
            return result == True
        except Exception as e:
            print(f"Link click error: {e}")
            return False
    
    def _download_via_browser(self, url: str, save_path: str) -> bool:
        """Download video using browser's JavaScript fetch"""
        if not self.browser or not self.browser.driver:
            return False
        
        try:
            # Use JavaScript to fetch and get blob data
            # This works because browser has the session cookies
            js_code = """
            async function downloadVideo(url) {
                try {
                    const response = await fetch(url, {
                        method: 'GET',
                        credentials: 'include',
                        mode: 'cors'
                    });
                    
                    if (!response.ok) {
                        // Try without credentials
                        const response2 = await fetch(url, {
                            method: 'GET',
                            mode: 'no-cors'
                        });
                        if (!response2.ok) {
                            return {error: 'HTTP ' + response.status};
                        }
                    }
                    
                    const blob = await response.blob();
                    
                    // Check if blob has content
                    if (blob.size < 10000) {
                        return {error: 'Blob too small: ' + blob.size};
                    }
                    
                    const reader = new FileReader();
                    
                    return new Promise((resolve, reject) => {
                        reader.onloadend = function() {
                            try {
                                const base64 = reader.result.split(',')[1];
                                resolve({data: base64, size: blob.size, type: blob.type});
                            } catch(e) {
                                reject({error: e.toString()});
                            }
                        };
                        reader.onerror = function() {
                            reject({error: 'FileReader error'});
                        };
                        reader.readAsDataURL(blob);
                    });
                } catch (e) {
                    return {error: e.toString()};
                }
            }
            return await downloadVideo(arguments[0]);
            """
            
            result = self.browser.driver.execute_script(js_code, url)
            
            if result and isinstance(result, dict):
                if 'data' in result and result['data']:
                    import base64
                    video_data = base64.b64decode(result['data'])
                    
                    if len(video_data) > 100000:  # At least 100KB
                        with open(save_path, 'wb') as f:
                            f.write(video_data)
                        return True
                    else:
                        print(f"Downloaded data too small: {len(video_data)} bytes")
                        
                elif 'error' in result:
                    print(f"JS download error: {result['error']}")
                
        except Exception as e:
            print(f"Browser download error: {e}")
        
        return False
    
    def close(self):
        self.client.close()
        if self.browser:
            self.browser.close_browser()
