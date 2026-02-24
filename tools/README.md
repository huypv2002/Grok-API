# Grok Account Creator CLI Tool

Tool đa luồng tự động tạo và trial Grok account từ list hotmail và thẻ tín dụng.

## Tính năng

- Đa luồng xử lý (configurable workers)
- Đọc hòm thư hotmail qua API để lấy verification code
- Tự động đăng ký Grok account
- Tự động xác thực email với verification code
- Tự động kích hoạt trial với thẻ tín dụng
- Xuất kết quả ra JSON và CSV
- Import account vào project chính X Grok Video Generator

## Cài đặt

```bash
# Cài đặt dependencies
pip install httpx asyncio

# Hoặc từ requirements.txt của project chính
pip install -r requirements.txt
```

## Cấu trúc file

### 1. File hotmail (bắt buộc)
Định dạng: `email|password|refresh_token|client_id`

Ví dụ:
```
lebuihgq55b2@outlook.com|NrepmubLwi5E|M.C507_BAY.0.U.-CsINeZsMZjaR3q5K3Sp*NmlAnqQjjIXRiE9VtVqhzlDHFODFSfwZ2FEr1G2x7y0e9blx6VF0x76N59ohFecBItO!Z3GwWupe3m8jJWpL!ZyUD3CjCHNVmj6298NxtLrxhlnwmKt*ezRnaju*VUBB4Sd3qu06YI85Sqd5FuP80jSr5ItYx3X0MYNwWYvZwsUl4d04ZdhMQL8!TW41Kt3WMxdJVN1RhBCeGTcjj8KcoIJH8iItj5AmUeURlg9a*VwUqBscqMUto1fHWXjZ7j1xR1WhRc0OvcAgklkVLzOJshQ3MMQnB0GXcdjg*J*8kF7IMdcHN!4OFXHJORthHSRD7uY$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
```

### 2. File thẻ tín dụng (tùy chọn)
Có 2 định dạng:

**Định dạng đầy đủ:**
```
number|expiry_month|expiry_year|cvv|name|address|city|state|zip_code|country
```

Ví dụ:
```
4111111111111111|12|2026|123|John Doe|123 Main St|New York|NY|10001|US
```

**Định dạng compact (từ string bạn cung cấp):**
```
6224792557857660|05|2029|3386224792557852612|12|2027|865...
```

## Cách sử dụng

### 1. Chạy cơ bản
```bash
cd tools
python grok_account_creator.py --hotmails hotmails_example.txt --cards credit_cards_parsed.txt
```

### 2. Sử dụng string thẻ compact
```bash
python grok_account_creator.py --hotmails hotmails_example.txt --cards-compact "6224792557857660|05|2029|3386224792557852612|12|2027|865..."
```

### 3. Xuất kết quả và import vào project chính
```bash
python grok_account_creator.py --hotmails hotmails_example.txt --cards credit_cards_parsed.txt --export-accounts accounts_output.txt --import-to-project
```

### 4. Tùy chọn workers
```bash
python grok_account_creator.py --hotmails hotmails_example.txt --cards credit_cards_parsed.txt --workers 5
```

### 5. Chế độ test
```bash
python grok_account_creator.py --hotmails hotmails_example.txt --test
```

## Các tham số

- `--hotmails`: File chứa danh sách hotmail (bắt buộc)
- `--cards`: File thẻ định dạng đầy đủ
- `--cards-compact`: String thẻ định dạng compact
- `--output`: File output kết quả JSON (mặc định: grok_accounts_output.json)
- `--export-accounts`: Xuất account sang định dạng email|password
- `--import-to-project`: Import account vào project chính sau khi tạo
- `--workers`: Số lượng workers đồng thời (mặc định: 3)
- `--test`: Chế độ test (không thực sự đăng ký)

## Output

Tool tạo các file output:

1. `grok_accounts_output.json` - Kết quả chi tiết JSON
2. `grok_accounts_output.csv` - Kết quả CSV
3. `accounts_output.txt` - Định dạng email|password cho import
4. `accounts_output.json` - Định dạng JSON cho import vào project chính
5. `grok_account_creator.log` - Log file

## Flow xử lý

1. **Đọc hòm thư**: Gọi API đọc hòm thư hotmail để tìm verification code
2. **Đăng ký account**: Tạo Grok account nếu chưa có
3. **Xác thực**: Dùng verification code để xác thực email
4. **Kích hoạt trial**: Dùng thẻ tín dụng để kích hoạt trial
5. **Xuất kết quả**: Lưu thông tin account đã tạo

## Lưu ý

- Tool sử dụng API `https://vinamax.com.vn/api/tools/hotmail` để đọc hòm thư
- Cần có kết nối internet
- Mỗi hotmail cần có refresh_token và client_id hợp lệ
- Thẻ tín dụng cần hợp lệ để kích hoạt trial
- Tool chạy độc lập với project chính, có thể import kết quả vào sau

## Troubleshooting

1. **Lỗi đọc hòm thư**: Kiểm tra refresh_token và client_id
2. **Không tìm thấy verification code**: Chờ email xác thực từ x.ai
3. **Lỗi đăng ký**: Email có thể đã được sử dụng
4. **Lỗi trial**: Thẻ tín dụng không hợp lệ hoặc đã hết hạn

## Ví dụ file hotmails_example.txt

Xem file `hotmails_example.txt` trong thư mục tools.

## Ví dụ file credit_cards_parsed.txt

Xem file `credit_cards_parsed.txt` trong thư mục tools.