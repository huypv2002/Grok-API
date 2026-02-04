# Kế hoạch Implementation: X Grok Multi-Account Video Generator

## Tổng quan

Triển khai ứng dụng desktop Python với PySide6, antidetect-browser, và httpx để quản lý nhiều tài khoản X.AI và tạo video qua Grok API.

## Tasks

- [x] 1. Thiết lập cấu trúc project và dependencies
  - [x] 1.1 Tạo cấu trúc thư mục và file cấu hình
    - Tạo thư mục: src/, src/core/, src/gui/, src/utils/, output/, tests/
    - Tạo requirements.txt với: PySide6, httpx, cryptography, antidetect-browser
    - Tạo main.py entry point
    - _Requirements: 5.1_

  - [x] 1.2 Tạo data models và types
    - Định nghĩa Account dataclass với email, password, status, cookies, fingerprint_id
    - Định nghĩa VideoSettings dataclass với aspect_ratio, video_length, resolution
    - Định nghĩa VideoTask dataclass với id, account, prompt, settings, status, media_url
    - _Requirements: 1.1, 6.1, 6.2, 6.3_

- [x] 2. Implement AccountManager
  - [x] 2.1 Implement password encryption/decryption
    - Sử dụng cryptography.fernet cho mã hóa
    - Tạo hàm encrypt_password() và decrypt_password()
    - Lưu key vào file riêng hoặc derive từ master password
    - _Requirements: 1.5, 7.4_

  - [ ]* 2.2 Write property test cho password encryption
    - **Property 2: Password Encryption Round-trip**
    - **Validates: Requirements 1.5, 7.4**

  - [x] 2.3 Implement AccountManager class
    - Implement add_account(), update_account(), delete_account()
    - Implement save_to_storage() lưu vào JSON file
    - Implement load_from_storage() đọc từ JSON file
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 2.4 Write property test cho Account CRUD
    - **Property 1: Account CRUD Round-trip**
    - **Validates: Requirements 1.1, 1.2, 1.3**

- [x] 3. Checkpoint - Kiểm tra AccountManager
  - Chạy tests, đảm bảo CRUD và encryption hoạt động đúng

- [x] 4. Implement BrowserController và SessionManager
  - [x] 4.1 Implement BrowserController
    - Tích hợp antidetect-browser library
    - Implement open_browser() với fingerprint riêng
    - Implement navigate_to(), fill_input(), click_button()
    - Implement wait_for_element() với timeout
    - Implement get_cookies() để extract cookies
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 4.2 Implement SessionManager
    - Implement login() flow: navigate -> fill email -> click Next -> fill password -> click Login
    - Implement extract_cookies() lấy sso, sso-rw, x-userid, cf_clearance
    - Implement is_session_valid() kiểm tra cookies còn hạn
    - Implement get_headers() tạo headers cho API request
    - _Requirements: 2.5, 2.6, 2.7, 7.1, 7.2, 7.3_

  - [x] 4.3 Implement Cloudflare Turnstile handling
    - Detect Turnstile challenge element
    - Chờ user giải quyết hoặc timeout
    - Extract cf_clearance sau khi pass
    - _Requirements: 2.5, 7.3_

- [x] 5. Implement VideoGenerator
  - [x] 5.1 Implement VideoSettings validation
    - Validate aspect_ratio trong [16:9, 9:16, 1:1]
    - Validate video_length trong [6, 10]
    - Validate resolution trong [720p, 1080p]
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 5.2 Write property test cho VideoSettings validation
    - **Property 6: Video Settings Validation**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

  - [x] 5.3 Implement create_media_post()
    - Gọi POST https://grok.com/rest/media/post/create
    - Headers: content-type, user-agent, x-xai-request-id, cookies
    - Body: {"mediaType":"MEDIA_POST_TYPE_VIDEO","prompt":"<prompt>"}
    - Parse response lấy post_id và thumbnailImageUrl
    - _Requirements: 3.1, 3.2_

  - [ ]* 5.4 Write property test cho API response parsing
    - **Property 3: API Response Parsing**
    - **Validates: Requirements 3.2**

  - [x] 5.5 Implement start_video_generation()
    - Gọi POST https://grok.com/rest/app-chat/conversations/new
    - Params: modelName="grok-3", message="<prompt> --mode=custom"
    - toolOverrides: {"videoGen": true}
    - responseMetadata: parentPostId, aspectRatio, videoLength, resolutionName
    - _Requirements: 3.3, 3.4_

  - [x] 5.6 Implement retry mechanism
    - Exponential backoff: 1s, 2s, 4s
    - Max 3 retries
    - Log mỗi retry attempt
    - _Requirements: 3.5, 8.1, 8.2, 8.3_

  - [ ]* 5.7 Write property test cho retry mechanism
    - **Property 4: Retry Mechanism**
    - **Validates: Requirements 3.5, 8.1, 8.2**

- [x] 6. Checkpoint - Kiểm tra VideoGenerator
  - Chạy tests, đảm bảo API calls và retry hoạt động đúng

- [x] 7. Implement Progress Tracking và Download
  - [x] 7.1 Implement poll_status()
    - Poll API định kỳ (mỗi 5s) để kiểm tra trạng thái video
    - Parse response lấy status và mediaUrl
    - _Requirements: 4.1, 4.2_

  - [x] 7.2 Implement download_video()
    - Download video từ mediaUrl
    - Lưu vào thư mục output/
    - Đặt tên file: {timestamp}_{email}_{prompt_short}.mp4
    - _Requirements: 4.3, 4.4_

  - [ ]* 7.3 Write property test cho filename format
    - **Property 5: Video Filename Format**
    - **Validates: Requirements 4.4**

  - [x] 7.4 Implement HistoryManager
    - Lưu video history vào SQLite
    - Implement add_history(), get_all_history()
    - _Requirements: 5.3_

- [x] 8. Implement GUI với PySide6
  - [x] 8.1 Implement MainWindow và tab structure
    - Tạo QMainWindow với QTabWidget
    - 3 tabs: Quản lý Account, Tạo Video, Lịch sử
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 8.2 Implement AccountTab
    - QTableWidget hiển thị danh sách account
    - Buttons: Thêm, Sửa, Xóa, Đăng nhập
    - Dialog thêm/sửa account
    - Hiển thị status với màu sắc
    - _Requirements: 5.1, 1.1, 1.2, 1.3, 1.4_

  - [x] 8.3 Implement VideoGenTab
    - QTextEdit cho prompt input
    - QComboBox chọn account
    - QComboBox cho aspect_ratio, video_length, resolution
    - QPushButton "Tạo Video"
    - QProgressBar và QTextEdit log
    - _Requirements: 5.2, 5.4, 5.6_

  - [x] 8.4 Implement HistoryTab
    - QTableWidget hiển thị lịch sử video
    - Columns: Thời gian, Account, Prompt, Status, Actions
    - Button mở thư mục output
    - _Requirements: 5.3_

- [x] 9. Implement Multi-threading
  - [x] 9.1 Implement VideoWorker
    - Kế thừa QRunnable
    - Signals: progress, finished, error
    - Run video generation trong background
    - _Requirements: 5.5_

  - [x] 9.2 Implement ThreadPool management
    - QThreadPool để quản lý workers
    - Cho phép nhiều account gen cùng lúc
    - Update UI từ worker signals
    - _Requirements: 5.5_

- [x] 10. Final Checkpoint
  - Chạy tất cả tests
  - Test manual với account thật
  - Kiểm tra tất cả chức năng hoạt động đúng

## Notes

- Tasks đánh dấu `*` là optional (tests), có thể bỏ qua để MVP nhanh hơn
- Mỗi task reference requirements cụ thể để traceability
- Checkpoints đảm bảo validate từng phần trước khi tiếp tục
- Property tests validate các correctness properties từ design
