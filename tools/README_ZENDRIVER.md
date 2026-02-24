# Grok Account Creator với Zendriver

Tool đa luồng tạo Grok account thực tế bằng zendriver, thực hiện toàn bộ quy trình đăng ký tự động.

## Tính năng

- **Đăng ký thực tế** bằng zendriver (không mô phỏng)
- **Đa luồng xử lý** (configurable workers)
- **Tự động click và điền form** trên trang `accounts.x.ai/sign-up`
- **Đọc hòm thư hotmail** qua API để lấy verification code
- **Tự động điền verification code** và xác thực
- **Xử lý Cloudflare challenge** (nếu có)
- **Xuất kết quả** ra JSON và CSV

## Quy trình đăng ký thực tế

1. **Truy cập** `https://accounts.x.ai/sign-up`
2. **Click nút** "Sign up with email"
3. **Điền email** vào input field
4. **Click nút** "Sign up"
5. **Chờ email verification** (10-30 giây)
6. **Đọc hòm thư** lấy verification code
7. **Điền verification code** vào form OTP
8. **Click nút** "Confirm email"
9. **Xác thực thành công** → Lưu cookies

## Cài đặt

```bash
# Cài đặt zendriver (nếu chưa có)
pip install zendriver

# Cài đặt dependencies khác
pip install httpx asyncio

# Hoặc từ project chính
pip install -r ../requirements.txt
```

## Cấu trúc file

### 1. File hotmail (bắt buộc)
Định dạng: `email|password|refresh_token|client_id`

Ví dụ:
```
ngocvuwsf96b3@outlook.com|bkR2kqB7RDhY|M.C546_BAY.0.U.-CgbRMVtzlw7Zv!MBsOktXLYQW71NIbqPHUshaVBN3dC6ikfBL*OF!jPTJ4BVfOUDtbY9Ws2yQpgv9zydccAW8xbZbt5KfiDQ5Wcdj1Hj9l25a8rfFWcAbyK2*FttzrXb10bBLol5!b2*PqD4eHbiUmR3pSnDEmRtPSE*KnWtNpqULELVwB6Zawnywu1ujEFro3pjTeezLK57QAxbC1Cz1s80J9mH3nYn7eT*8jz3uXszYCodR6*uMCAAh!9S34YFS2tPE3PLzTOu07o!FlGLwOKQ4KoIMjVYP6ozrxgjWzmUPPFPDNM8qVnQ9ihZCARq9NUDHowmEuj59WSKLh9EBh8$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
```

### 2. String thẻ compact (tùy chọn)
Định dạng: `6224792557857660|05|2029|3386224792557852612|12|2027|865...`

## Cách sử dụng

### 1. Test 1 account (hiển thị browser)
```bash
python test_zendriver_real.py
# Chọn option 1
```

### 2. Test nhiều account (headless)
```bash
python test_zendriver_real.py
# Chọn option 2
```

### 3. Chạy chính thức với file hotmail
```bash
# Tạo file hotmail trước
cat > hotmails_real.txt << 'EOF'
ngocvuwsf96b3@outlook.com|bkR2kqB7RDhY|M.C546_BAY.0.U.-CgbRMVtzlw7Zv!MBsOktXLYQW71NIbqPHUshaVBN3dC6ikfBL*OF!jPTJ4BVfOUDtbY9Ws2yQpgv9zydccAW8xbZbt5KfiDQ5Wcdj1Hj9l25a8rfFWcAbyK2*FttzrXb10bBLol5!b2*PqD4eHbiUmR3pSnDEmRtPSE*KnWtNpqULELVwB6Zawnywu1ujEFro3pjTeezLK57QAxbC1Cz1s80J9mH3nYn7eT*8jz3uXszYCodR6*uMCAAh!9S34YFS2tPE3PLzTOu07o!FlGLwOKQ4KoIMjVYP6ozrxgjWzmUPPFPDNM8qVnQ9ihZCARq9NUDHowmEuj59WSKLh9EBh8$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
huongphanmib67b1@outlook.com|Vq9SD6PkAFQM|M.C540_SN1.0.U.-Cpc1nCVKNgiYwfEkovU5FV*gh8B0Mn0QtW0dowS1ds4fW1FcZt9Nsjh3c2MDeoYTwUn*ulPJQgLsVBWgkdbM!q482zpLI6DFX4LNXbnkr8mp33EA73al53F9lwoBnkFn6UOtBwyomKg5AnVOwLZFNQ5hdmqF5hOjrGyqNhKeodJXXpPhn61b4Kcldz1guWfih2HUMcHnuqiJ4pMMPV9unu7cVK022K1ax8*EwtDyI96OyGTaW3KU6TAvfJozU5ZemvqXiNssr0IvFINzvQatN3rpER5Omt6FMI!efseiLKUz3rZTcDRwE9bSLFGIxzypptmslZGaBAjREN5xfbdNFPc$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
EOF

# Chạy tool
python grok_account_creator_zendriver.py \
  --hotmails hotmails_real.txt \
  --cards-compact "6224792557857660|05|2029|3386224792557852612|12|2027|8656224792557857546|12|2032|1406224792557859278|02|2029|2516224792557851416|05|2027|9386224792557851739|05|2031|2886224792557855300|01|2029|3146224792557858585|01|2027|3946224792557859153|02|2028|9836224792557859310|07|2030|972" \
  --workers 3 \
  --headless
```

### 4. Chạy với hiển thị browser (debug)
```bash
python grok_account_creator_zendriver.py \
  --hotmails hotmails_real.txt \
  --workers 1 \
  # Bỏ --headless để xem browser
```

## Các tham số

- `--hotmails`: File chứa danh sách hotmail (bắt buộc)
- `--cards-compact`: String thẻ định dạng compact
- `--output`: File output kết quả (mặc định: grok_accounts_zendriver.json)
- `--workers`: Số lượng workers đồng thời (mặc định: 3)
- `--headless`: Chạy browser ở chế độ headless (không hiển thị)
- `--test`: Chế độ test (chỉ xử lý 1 account đầu tiên)

## Output

Tool tạo các file output:

1. `grok_accounts_zendriver.json` - Kết quả chi tiết JSON
2. `grok_accounts_zendriver.csv` - Kết quả CSV
3. `grok_account_creator_zendriver.log` - Log file

## Các trạng thái account

- `created`: Đang bắt đầu xử lý
- `email_sent`: Đã gửi email verification
- `verified`: Đã xác thực thành công
- `trial_activated`: Đã kích hoạt trial (chưa implement)
- `error`: Lỗi trong quá trình xử lý

## Xử lý lỗi thường gặp

### 1. Zendriver không khả dụng
```
Lỗi: Zendriver không khả dụng
Giải pháp: pip install zendriver hoặc chạy từ project chính
```

### 2. Không tìm thấy element
```
Lỗi: Không tìm thấy nút 'Sign up with email'
Giải pháp: UI có thể thay đổi, cần cập nhật selector
```

### 3. Cloudflare challenge
```
Lỗi: Bị chặn bởi Cloudflare
Giải pháp: Tool tự động xử lý challenge, nhưng có thể cần thời gian
```

### 4. Không nhận được email verification
```
Lỗi: Không tìm thấy verification code
Giải pháp: Chờ lâu hơn (2-5 phút), check spam folder
```

## Selector hiện tại

Tool sử dụng các selector sau:

1. **Nút Sign up with email**: 
   - `button:has-text("Sign up with email")`
   - `button[type="button"]:has(svg.lucide-mail)`

2. **Input email**:
   - `input[data-testid="email"]`
   - `input[type="email"]`

3. **Nút Sign up submit**:
   - `button[type="submit"]:has-text("Sign up")`

4. **Form verification**:
   - `h1:has-text("Verify your email")`

5. **Input OTP**:
   - `input[data-input-otp]`
   - `input[autocomplete="one-time-code"]`

6. **Nút Confirm email**:
   - `button[type="submit"]:has-text("Confirm email")`

## Lưu ý quan trọng

1. **Rate limiting**: Grok có thể giới hạn số lượng đăng ký từ cùng IP
2. **Email delay**: Verification code có thể mất 2-5 phút mới đến
3. **Cloudflare**: Có thể cần giải challenge, tool tự động xử lý
4. **UI changes**: Selector có thể thay đổi khi Grok update UI
5. **Headless mode**: Nên dùng `--headless` cho chạy production
6. **Workers**: Không nên đặt quá cao (3-5 là hợp lý)

## Debug

Để debug, chạy với `--headless` (bỏ) để xem browser:

```bash
python grok_account_creator_zendriver.py --hotmails test.txt --workers 1
```

Xem log file:
```bash
tail -f grok_account_creator_zendriver.log
```

## Integration với project chính

Sau khi tạo account thành công, có thể import vào project chính:

```python
from src.core.account_manager import AccountManager

manager = AccountManager()
for account in results:
    if account.status == "verified":
        manager.add_account(account.email, account.password)
```

## Ví dụ dữ liệu thực tế

Xem file `test_zendriver_real.py` để có ví dụ đầy đủ với dữ liệu thực tế bạn cung cấp.