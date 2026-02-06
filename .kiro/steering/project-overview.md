# X Grok Video Generator - Project Steering

## Tổng quan dự án

Ứng dụng desktop (PySide6) tự động tạo video từ Grok AI (grok.com/imagine) hỗ trợ đa tài khoản, đa tab đồng thời. Ứng dụng bypass Cloudflare challenge, quản lý session, và tải video tự động.

## Kiến trúc

```
main.py                    # Entry point - PySide6 QApplication
src/
  core/                    # Business logic layer
    models.py              # Dataclass: Account, VideoSettings, VideoTask
    account_manager.py     # CRUD tài khoản, lưu JSON (data/accounts.json)
    encryption.py          # Fernet encrypt/decrypt password (data/.key)
    session_manager.py     # Login flow qua undetected_chromedriver
    browser_controller.py  # Wrapper undetected_chromedriver (legacy, dùng cho login)
    cf_solver.py           # Cloudflare solver dùng zendriver + CDP
    video_generator.py     # VideoGenerator (single) + MultiTabVideoGenerator (multi-tab)
    video_generator_api.py # APIVideoGenerator - tạo video qua API trực tiếp
    grok_api.py            # GrokAPI - HTTP client gọi REST API grok.com
    history_manager.py     # SQLite lưu lịch sử video (data/history.db)
  gui/                     # PySide6 UI layer
    main_window.py         # MainWindow + AnimatedBg (galaxy/star particles)
    account_tab.py         # Tab quản lý tài khoản (add/edit/delete/login)
    video_gen_tab.py       # Tab tạo video (multi-account, multi-tab)
    history_tab.py         # Tab lịch sử (xem/download/export CSV)
giaima/
  deobfuscator.py          # CF-Clearance-Scraper gốc (reference implementation)
```

## Công nghệ & Dependencies

- Python 3.10+
- PySide6 (Qt6) - GUI framework
- zendriver - Browser automation chính (CDP-based, dùng cho video gen + CF solve)
- undetected_chromedriver + selenium - Browser automation phụ (dùng cho login flow)
- httpx - HTTP client cho API calls
- cryptography (Fernet) - Mã hóa password
- pydantic - Data validation (khai báo nhưng dùng dataclass)

## Flow chính

### 1. Login Flow (undetected_chromedriver)
```
SessionManager.login() → BrowserController.open_browser()
  → Navigate to accounts.x.ai → Fill email/password
  → Handle Turnstile → Extract cookies (sso, sso-rw, cf_clearance)
  → Save to Account.cookies
```

### 2. Video Generation Flow (zendriver - chính)
```
MultiTabVideoGenerator.start()
  → Inject cookies via CDP → Navigate to /imagine
  → Handle Cloudflare (detect challenge type → solve)
  → Per tab: Select Video mode → Enter prompt → Submit
  → Wait for post ID in URL (/imagine/post/{uuid})
  → Wait for video render → Click share → Download via CDP
```

### 3. API Video Generation Flow (httpx - nhanh hơn)
```
GrokAPI.generate_video()
  → POST /rest/media/post/create (get parentPostId)
  → POST /rest/app-chat/conversations/new (stream response, get final postId)
  → POST /rest/media/post/create-link (share link)
  → GET imagine-public.x.ai/.../share-videos/{postId}.mp4
```

### 4. Cloudflare Bypass Flow (zendriver)
```
CloudflareSolver → Navigate to grok.com
  → Detect challenge type (JavaScript/Managed/Interactive)
  → Set UserAgentMetadata via CDP
  → Find turnstile widget in shadow DOM → Click
  → Wait for cf_clearance cookie
```

## Quy tắc code

### Ngôn ngữ
- Code comments và log messages: mix tiếng Việt + tiếng Anh
- UI labels: tiếng Việt (Tỷ lệ, Thời lượng, Tải xuống...)
- Grok UI elements: tiếng Việt (Tạo một video, Tạo link chia sẻ, Tải xuống)

### Patterns quan trọng
- QThread workers cho tác vụ nặng (LoginWorker, AccountWorker, VideoWorker, DownloadWorker)
- Signal/Slot cho communication giữa threads và UI
- asyncio.run() bridge giữa sync Qt code và async zendriver code
- CDP (Chrome DevTools Protocol) cho cookie injection, download behavior, mouse events
- Retry logic với max_retries cho video generation

### Browser Profiles
- Mỗi account có fingerprint_id (UUID) → thư mục profile riêng tại `data/profiles/{uuid}/`
- undetected_chromedriver dùng user_data_dir cho persistent sessions
- zendriver dùng CDP set_cookie cho cookie injection (không dùng profile)

### Cookie Management
- Required cookies: `sso`, `sso-rw`, `x-userid`, `cf_clearance`
- cf_clearance hết hạn nhanh → cần refresh thường xuyên
- Cache cf_clearance tại `data/cf_clearance_cache.json`
- User-Agent phải match giữa lúc lấy cf_clearance và lúc gọi API

### Video Download
- URL pattern: `https://imagine-public.x.ai/imagine-public/share-videos/{post_id}.mp4?cache=1&dl=1`
- Cần `__cf_bm` cookie → phải navigate browser đến URL trước khi download
- Download qua CDP `set_download_behavior` hoặc requests library
- Output directory: `output/`

### Data Storage
- Accounts: `data/accounts.json` (JSON, password encrypted)
- History: `data/history.db` (SQLite)
- Settings: `data/settings.json` (JSON)
- Encryption key: `data/.key` (Fernet key)
- Browser profiles: `data/profiles/` (Chrome user data)

## Lưu ý khi phát triển

1. zendriver là thư viện async → luôn dùng `async/await`, bridge qua `asyncio.run()` khi gọi từ sync code
2. Cloudflare challenge có 3 loại: JavaScript (tự giải), Managed (cần click), Interactive (Turnstile widget trong shadow DOM)
3. Grok UI dùng Radix UI components → selector cần dùng `[data-radix-*]`, `[role="menuitem"]`
4. Video mode selection: click `#model-select-trigger` → menu opens → click menuitem có text "Video" hoặc SVG polygon icon
5. Prompt editor: TipTap ProseMirror → `div.tiptap.ProseMirror` hoặc `div[contenteditable="true"]`
6. MultiTabVideoGenerator: 1 browser per account, tối đa 3 tabs concurrent
7. `os._exit()` trong main.py để force kill tất cả threads/processes khi đóng app
8. Fixed User-Agent: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36`
