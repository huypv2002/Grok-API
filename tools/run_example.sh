#!/bin/bash
# Script chạy ví dụ Grok Account Creator

echo "=== Grok Account Creator Example ==="
echo ""

# Kiểm tra Python
if ! command -v python3 &> /dev/null; then
    echo "Python3 không được tìm thấy. Vui lòng cài đặt Python 3.10+"
    exit 1
fi

# Kiểm tra dependencies
echo "1. Kiểm tra dependencies..."
pip install httpx asyncio

# Tạo file hotmail từ dữ liệu bạn cung cấp
echo "2. Tạo file hotmail từ dữ liệu..."
cat > hotmails_real.txt << 'EOF'
lebuihgq55b2@outlook.com|NrepmubLwi5E|M.C507_BAY.0.U.-CsINeZsMZjaR3q5K3Sp*NmlAnqQjjIXRiE9VtVqhzlDHFODFSfwZ2FEr1G2x7y0e9blx6VF0x76N59ohFecBItO!Z3GwWupe3m8jJWpL!ZyUD3CjCHNVmj6298NxtLrxhlnwmKt*ezRnaju*VUBB4Sd3qu06YI85Sqd5FuP80jSr5ItYx3X0MYNwWYvZwsUl4d04ZdhMQL8!TW41Kt3WMxdJVN1RhBCeGTcjj8KcoIJH8iItj5AmUeURlg9a*VwUqBscqMUto1fHWXjZ7j1xR1WhRc0OvcAgklkVLzOJshQ3MMQnB0GXcdjg*J*8kF7IMdcHN!4OFXHJORthHSRD7uY$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
linhvujmg57b3@outlook.com|I661AKyKjrTu|M.C538_BL2.0.U.-Cs7KRHEIhek2TCyNMw4QOpIksh7TFKsISo15y!wy5Pd6xnVG3I8jYAi!YIuB9Kg5JUlaSKoeEn00I4AGecr*W7XYdaQzPvmFwAI3hbrxv7xS!SM!9xuTyRuTM7JnFD4QH8gU212oz6FTw0SA5XKXSY7ff34gJ7HlPxYCPnTvvXfy!ZWwYqe2g2ifj5Co3gPv6tqOkFfPUBF3phgUVFoOYAQPKjVbJfE2j0teAlA8hv4oCMK9Vs6QQuVmEe!z4lNhE!6XTfkOjvGK7nA81EWdpR1soR2AWLvuWL9t9*8H306o83!wkC948A4Ff7NMISkBGvX9xuKCHlcRuvfy1BuVPxs$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
quyenvuxdb92a2@outlook.com|8udvKRFRy190|M.C559_BL2.0.U.-CqHP2t4KcYJV3hfxSldaRESlG2F3cSc43zwPNzwK!EMdN47oMwqOONSdpAJDs7XLbDjyIOrG3yLllYoF*55GAO6a!WuON!F4eMHQTAfWjkoXv6bg2NyQW4rDo*re5wkZwEOtco*kMu*x7zoBjp4VHJmIhqVpNm0YgxMmVbtxoQHT6SrnQlmPCmxu2MGPE0LBnA0phkeMjxPLV5IjHPWVyC2Jl4lldaoVc4g41YxQOdEtlDs4aoaGnw86x0tCpD4S98cgQrMr3Fp05OFi*DW2oohKc76sQayYh2en2aij9NtokPMOSgA1vhDdNVKKZpJZFjwy821LgASh8yio9GTWbDs$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
ngocvuwsf96b3@outlook.com|bkR2kqB7RDhY|M.C546_BAY.0.U.-CgbRMVtzlw7Zv!MBsOktXLYQW71NIbqPHUshaVBN3dC6ikfBL*OF!jPTJ4BVfOUDtbY9Ws2yQpgv9zydccAW8xbZbt5KfiDQ5Wcdj1Hj9l25a8rfFWcAbyK2*FttzrXb10bBLol5!b2*PqD4eHbiUmR3pSnDEmRtPSE*KnWtNpqULELVwB6Zawnywu1ujEFro3pjTeezLK57QAxbC1Cz1s80J9mH3nYn7eT*8jz3uXszYCodR6*uMCAAh!9S34YFS2tPE3PLzTOu07o!FlGLwOKQ4KoIMjVYP6ozrxgjWzmUPPFPDNM8qVnQ9ihZCARq9NUDHowmEuj59WSKLh9EBh8$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
huongphanmib67b1@outlook.com|Vq9SD6PkAFQM|M.C540_SN1.0.U.-Cpc1nCVKNgiYwfEkovU5FV*gh8B0Mn0QtW0dowS1ds4fW1FcZt9Nsjh3c2MDeoYTwUn*ulPJQgLsVBWgkdbM!q482zpLI6DFX4LNXbnkr8mp33EA73al53F9lwoBnkFn6UOtBwyomKg5AnVOwLZFNQ5hdmqF5hOjrGyqNhKeodJXXpPhn61b4Kcldz1guWfih2HUMcHnuqiJ4pMMPV9unu7cVK022K1ax8*EwtDyI96OyGTaW3KU6TAvfJozU5ZemvqXiNssr0IvFINzvQatN3rpER5Omt6FMI!efseiLKUz3rZTcDRwE9bSLFGIxzypptmslZGaBAjREN5xfbdNFPc$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
EOF

echo "Đã tạo file hotmails_real.txt với 5 hotmail"

# Tạo file thẻ từ string bạn cung cấp
echo "3. Tạo file thẻ từ string compact..."
COMPACT_CARDS="6224792557857660|05|2029|3386224792557852612|12|2027|8656224792557857546|12|2032|1406224792557859278|02|2029|2516224792557851416|05|2027|9386224792557851739|05|2031|2886224792557855300|01|2029|3146224792557858585|01|2027|3946224792557859153|02|2028|9836224792557859310|07|2030|972"

# Chạy tool với string compact
echo "4. Chạy Grok Account Creator..."
echo "Command: python grok_account_creator.py --hotmails hotmails_real.txt --cards-compact \"$COMPACT_CARDS\" --workers 3 --test"

# Chạy ở chế độ test trước
python3 grok_account_creator.py --hotmails hotmails_real.txt --cards-compact "$COMPACT_CARDS" --workers 3 --test

echo ""
echo "=== Hoàn thành ==="
echo ""
echo "Để chạy thực tế (không test):"
echo "python grok_account_creator.py --hotmails hotmails_real.txt --cards-compact \"\$COMPACT_CARDS\" --workers 3"
echo ""
echo "Để xuất kết quả và import vào project chính:"
echo "python grok_account_creator.py --hotmails hotmails_real.txt --cards-compact \"\$COMPACT_CARDS\" --export-accounts accounts_created.txt --import-to-project"