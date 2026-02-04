# Tài liệu Thiết kế

## Tổng quan

X Grok Multi-Account Video Generator là ứng dụng desktop Python sử dụng PySide6 cho GUI, antidetect-browser để bypass Cloudflare, và httpx để gọi API. Ứng dụng hỗ trợ đa luồng với QThreadPool.

## Kiến trúc

```
┌─────────────────────────────────────────────────────────────┐
│                      MainWindow (PySide6)                    │
├─────────────┬─────────────────┬─────────────────────────────┤
│ AccountTab  │   VideoGenTab   │        HistoryTab           │
└──────┬──────┴────────┬────────┴──────────────┬──────────────┘
       │               │                       │
       ▼               ▼                       ▼
┌──────────────┐ ┌──────────────┐ ┌────────────────────────────┐
│AccountManager│ │VideoGenerator│ │      HistoryManager        │
└──────┬───────┘ └──────┬───────┘ └────────────────────────────┘
       │               │
       ▼               ▼
┌──────────────┐ ┌──────────────┐
│BrowserControl│ │SessionManager│
└──────────────┘ └──────────────┘
```

## Components và Interfaces

### 1. AccountManager

```python
class Account:
    email: str
    password: str  # encrypted
    status: Literal["logged_in", "logged_out", "error"]
    cookies: dict | None
    fingerprint_id: str
    last_login: datetime | None

class AccountManager:
    def add_account(email: str, password: str) -> Account
    def update_account(email: str, **kwargs) -> Account
    def delete_account(email: str) -> bool
    def get_all_accounts() -> list[Account]
    def save_to_storage() -> None
    def load_from_storage() -> None
```

### 2. BrowserController

```python
class BrowserController:
    def __init__(fingerprint_id: str)
    def open_browser() -> Browser
    def navigate_to(url: str) -> None
    def fill_input(selector: str, value: str) -> None
    def click_button(selector: str) -> None
    def wait_for_element(selector: str, timeout: int) -> bool
    def get_cookies() -> dict
    def close_browser() -> None
    def handle_turnstile() -> bool
```

### 3. SessionManager

```python
class SessionManager:
    def login(account: Account) -> bool
    def extract_cookies(browser: Browser) -> dict
    def refresh_cookies(account: Account) -> bool
    def is_session_valid(account: Account) -> bool
    def get_headers(account: Account) -> dict
```

### 4. VideoGenerator

```python
class VideoSettings:
    aspect_ratio: Literal["16:9", "9:16", "1:1"]
    video_length: Literal[6, 10]
    resolution: Literal["720p", "1080p"]

class VideoTask:
    id: str
    account: Account
    prompt: str
    settings: VideoSettings
    status: Literal["pending", "creating", "completed", "failed"]
    post_id: str | None
    media_url: str | None
    output_path: str | None

class VideoGenerator:
    def create_media_post(account: Account, prompt: str) -> str  # returns post_id
    def start_video_generation(account: Account, post_id: str, settings: VideoSettings) -> str
    def poll_status(conversation_id: str) -> dict
    def download_video(media_url: str, output_path: str) -> bool
```

### 5. WorkerThread

```python
class VideoWorker(QRunnable):
    def __init__(task: VideoTask, generator: VideoGenerator)
    signals: WorkerSignals  # progress, finished, error
    def run() -> None
```

## Data Models

### Account Storage (JSON)

```json
{
  "accounts": [
    {
      "email": "user@example.com",
      "password_encrypted": "base64...",
      "fingerprint_id": "uuid",
      "status": "logged_out",
      "cookies": null,
      "last_login": null
    }
  ]
}
```

### Video History (SQLite)

```sql
CREATE TABLE video_history (
    id TEXT PRIMARY KEY,
    account_email TEXT,
    prompt TEXT,
    aspect_ratio TEXT,
    video_length INTEGER,
    resolution TEXT,
    status TEXT,
    media_url TEXT,
    output_path TEXT,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

## Correctness Properties

*Một property là đặc tính hoặc hành vi phải đúng trong mọi trường hợp thực thi hợp lệ của hệ thống.*



Property 1: Account CRUD Round-trip
*For any* account với email và password hợp lệ, sau khi thêm vào storage rồi load lại, account phải tồn tại với thông tin đúng. Sau khi update, thông tin mới phải được phản ánh. Sau khi delete, account không còn trong danh sách.
**Validates: Requirements 1.1, 1.2, 1.3**

Property 2: Password Encryption Round-trip
*For any* password, sau khi encrypt và decrypt, phải trả về giá trị gốc. Password trong storage phải khác password gốc.
**Validates: Requirements 1.5, 7.4**

Property 3: API Response Parsing
*For any* API response hợp lệ từ /rest/media/post/create, Video_Generator phải extract được post_id và thumbnailImageUrl.
**Validates: Requirements 3.2**

Property 4: Retry Mechanism
*For any* API request thất bại, hệ thống phải retry với exponential backoff (1s, 2s, 4s) và dừng sau tối đa 3 lần.
**Validates: Requirements 3.5, 8.1, 8.2**

Property 5: Video Filename Format
*For any* video task hoàn thành, filename phải theo format: {timestamp}_{account_email}_{prompt_short}.mp4
**Validates: Requirements 4.4**

Property 6: Video Settings Validation
*For any* VideoSettings, chỉ chấp nhận aspect_ratio trong [16:9, 9:16, 1:1], video_length trong [6, 10], resolution trong [720p, 1080p].
**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

## Error Handling

1. **Network Errors**: Retry với exponential backoff, thông báo user sau 3 lần thất bại
2. **Authentication Errors**: Trigger re-login tự động
3. **Cloudflare Challenge**: Chờ user giải quyết hoặc timeout sau 60s
4. **API Rate Limit**: Delay và retry
5. **Invalid Input**: Validate trước khi gửi request, hiển thị lỗi cụ thể

## Testing Strategy

### Unit Tests
- Test AccountManager CRUD operations với mock storage
- Test password encryption/decryption
- Test VideoSettings validation
- Test filename generation

### Property-Based Tests
- Sử dụng thư viện `hypothesis` cho Python
- Minimum 100 iterations per property
- Tag format: **Feature: x-grok-video-generator, Property {number}: {property_text}**

### Integration Tests
- Test login flow với mock browser
- Test video generation flow với mock API
- Test end-to-end với test account (manual)
