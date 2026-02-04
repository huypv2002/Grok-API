# Tài liệu Yêu cầu

## Giới thiệu

Phần mềm "X Grok Multi-Account Video Generator" là ứng dụng desktop cho phép người dùng quản lý nhiều tài khoản X.AI và tự động tạo video thông qua Grok API. Ứng dụng sử dụng antidetect-browser để bypass các cơ chế bảo vệ và hỗ trợ chạy đa luồng để tối ưu hiệu suất.

## Thuật ngữ

- **Account_Manager**: Module quản lý tài khoản người dùng X.AI
- **Browser_Controller**: Module điều khiển antidetect-browser với fingerprint riêng biệt
- **Video_Generator**: Module tạo video thông qua Grok API
- **Session_Manager**: Module quản lý phiên đăng nhập và cookies
- **Progress_Tracker**: Module theo dõi tiến trình tạo video
- **Fingerprint**: Dấu vân tay trình duyệt duy nhất cho mỗi tài khoản
- **Cloudflare_Turnstile**: Cơ chế bảo vệ chống bot của Cloudflare
- **Aspect_Ratio**: Tỷ lệ khung hình video (16:9, 9:16, 1:1)

## Yêu cầu

### Yêu cầu 1: Quản lý tài khoản

**User Story:** Là người dùng, tôi muốn quản lý nhiều tài khoản X.AI để có thể sử dụng chúng cho việc tạo video.

#### Tiêu chí chấp nhận

1. WHEN người dùng thêm tài khoản mới với email và password THEN Account_Manager SHALL lưu thông tin vào storage và hiển thị trong danh sách
2. WHEN người dùng chỉnh sửa thông tin tài khoản THEN Account_Manager SHALL cập nhật thông tin trong storage và làm mới hiển thị
3. WHEN người dùng xóa tài khoản THEN Account_Manager SHALL xóa tài khoản khỏi storage và danh sách hiển thị
4. WHEN tải danh sách tài khoản THEN Account_Manager SHALL hiển thị trạng thái của mỗi tài khoản (logged_in, logged_out, error)
5. WHEN lưu tài khoản THEN Account_Manager SHALL mã hóa password trước khi lưu vào file JSON hoặc SQLite

### Yêu cầu 2: Đăng nhập tự động

**User Story:** Là người dùng, tôi muốn hệ thống tự động đăng nhập vào các tài khoản X.AI để không phải thao tác thủ công.

#### Tiêu chí chấp nhận

1. WHEN bắt đầu đăng nhập THEN Browser_Controller SHALL mở antidetect-browser với fingerprint riêng biệt cho tài khoản đó
2. WHEN browser đã sẵn sàng THEN Browser_Controller SHALL điều hướng đến URL https://accounts.x.ai/sign-in?redirect=grok-com&email=true
3. WHEN form đăng nhập hiển thị THEN Browser_Controller SHALL tự động điền email và click nút "Next"
4. WHEN form password hiển thị THEN Browser_Controller SHALL tự động điền password và click nút "Login"
5. IF Cloudflare Turnstile challenge xuất hiện THEN Browser_Controller SHALL chờ người dùng giải quyết hoặc tự động xử lý
6. WHEN đăng nhập thành công THEN Session_Manager SHALL trích xuất và lưu cookies quan trọng (sso, sso-rw, x-userid, cf_clearance)
7. IF đăng nhập thất bại THEN Account_Manager SHALL cập nhật trạng thái tài khoản thành "error" với thông báo lỗi

### Yêu cầu 3: Tạo video

**User Story:** Là người dùng, tôi muốn tạo video từ prompt văn bản thông qua Grok API.

#### Tiêu chí chấp nhận

1. WHEN người dùng nhập prompt và chọn tài khoản THEN Video_Generator SHALL gọi API POST https://grok.com/rest/media/post/create với headers và body phù hợp
2. WHEN API trả về response thành công THEN Video_Generator SHALL lưu post ID và thumbnailImageUrl
3. WHEN có post ID THEN Video_Generator SHALL gọi API POST https://grok.com/rest/app-chat/conversations/new để bắt đầu quá trình tạo video
4. THE Video_Generator SHALL gửi request với các tham số: modelName="grok-3", toolOverrides={"videoGen": true}, và responseMetadata chứa cài đặt video
5. IF API trả về lỗi THEN Video_Generator SHALL thực hiện retry với exponential backoff tối đa 3 lần

### Yêu cầu 4: Theo dõi tiến trình video

**User Story:** Là người dùng, tôi muốn theo dõi tiến trình tạo video và tải về khi hoàn thành.

#### Tiêu chí chấp nhận

1. WHEN video đang được tạo THEN Progress_Tracker SHALL poll API định kỳ để kiểm tra trạng thái
2. WHEN trạng thái video thay đổi THEN Progress_Tracker SHALL cập nhật progress bar và log trong giao diện
3. WHEN video hoàn thành và có mediaUrl THEN Video_Generator SHALL tự động tải video về thư mục output
4. WHEN lưu video THEN Video_Generator SHALL đặt tên file theo format: {timestamp}_{account_email}_{prompt_short}.mp4
5. IF quá trình tạo video thất bại THEN Progress_Tracker SHALL hiển thị thông báo lỗi và cho phép retry

### Yêu cầu 5: Giao diện người dùng

**User Story:** Là người dùng, tôi muốn có giao diện trực quan để quản lý tài khoản và tạo video dễ dàng.

#### Tiêu chí chấp nhận

1. THE GUI SHALL hiển thị tab "Quản lý Account" với danh sách tài khoản và các nút thêm/sửa/xóa
2. THE GUI SHALL hiển thị tab "Tạo Video" với input prompt, dropdown chọn account, và các cài đặt video
3. THE GUI SHALL hiển thị tab "Lịch sử" với danh sách video đã tạo và thông tin chi tiết
4. WHEN có tác vụ đang chạy THEN GUI SHALL hiển thị progress bar và log realtime
5. THE GUI SHALL hỗ trợ chạy đa luồng cho phép nhiều tài khoản tạo video cùng lúc
6. WHEN người dùng thay đổi cài đặt video THEN GUI SHALL lưu cài đặt và áp dụng cho các request tiếp theo

### Yêu cầu 6: Cài đặt video

**User Story:** Là người dùng, tôi muốn tùy chỉnh các thông số video theo nhu cầu.

#### Tiêu chí chấp nhận

1. THE Video_Generator SHALL hỗ trợ aspect ratio: 16:9, 9:16, 1:1
2. THE Video_Generator SHALL hỗ trợ video length: 6 giây, 10 giây
3. THE Video_Generator SHALL hỗ trợ resolution: 720p, 1080p
4. WHEN người dùng chọn cài đặt THEN Video_Generator SHALL bao gồm các tham số trong responseMetadata của API request

### Yêu cầu 7: Quản lý phiên và bảo mật

**User Story:** Là người dùng, tôi muốn hệ thống tự động duy trì phiên đăng nhập và xử lý các vấn đề bảo mật.

#### Tiêu chí chấp nhận

1. THE Session_Manager SHALL refresh cookies định kỳ trước khi hết hạn
2. WHEN cookies hết hạn THEN Session_Manager SHALL tự động đăng nhập lại
3. IF gặp Cloudflare protection THEN Browser_Controller SHALL xử lý challenge và cập nhật cf_clearance cookie
4. THE Account_Manager SHALL mã hóa thông tin nhạy cảm khi lưu trữ
5. WHEN API request thất bại do authentication THEN Session_Manager SHALL trigger đăng nhập lại và retry request

### Yêu cầu 8: Xử lý lỗi và retry

**User Story:** Là người dùng, tôi muốn hệ thống tự động xử lý lỗi và retry để đảm bảo tác vụ hoàn thành.

#### Tiêu chí chấp nhận

1. WHEN API request thất bại THEN Video_Generator SHALL retry với exponential backoff (1s, 2s, 4s)
2. THE Video_Generator SHALL giới hạn tối đa 3 lần retry cho mỗi request
3. IF tất cả retry thất bại THEN Video_Generator SHALL log lỗi chi tiết và thông báo người dùng
4. WHEN network error xảy ra THEN Session_Manager SHALL kiểm tra kết nối và thông báo trạng thái
5. THE Progress_Tracker SHALL lưu trạng thái tác vụ để có thể resume sau khi khởi động lại ứng dụng
