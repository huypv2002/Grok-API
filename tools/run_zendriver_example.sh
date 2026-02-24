#!/bin/bash
# Script chạy ví dụ Grok Account Creator với Zendriver

echo "=== Grok Account Creator với Zendriver ==="
echo ""

# Kiểm tra Python
if ! command -v python &> /dev/null; then
    echo "Python không được tìm thấy. Vui lòng cài đặt Python 3.10+"
    exit 1
fi

# Kiểm tra zendriver
echo "1. Kiểm tra zendriver..."
python -c "import zendriver" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Zendriver chưa được cài đặt. Cài đặt..."
    pip install zendriver
    if [ $? -ne 0 ]; then
        echo "Không thể cài đặt zendriver. Cần cài đặt thủ công: pip install zendriver"
        exit 1
    fi
    echo "✓ Đã cài đặt zendriver"
else
    echo "✓ Zendriver đã được cài đặt"
fi

# Kiểm tra dependencies
echo "2. Kiểm tra dependencies..."
pip install httpx

# Tạo file hotmail từ dữ liệu bạn cung cấp
echo "3. Tạo file hotmail từ dữ liệu thực tế..."
cat > hotmails_real_zendriver.txt << 'EOF'
ngocvuwsf96b3@outlook.com|bkR2kqB7RDhY|M.C546_BAY.0.U.-CgbRMVtzlw7Zv!MBsOktXLYQW71NIbqPHUshaVBN3dC6ikfBL*OF!jPTJ4BVfOUDtbY9Ws2yQpgv9zydccAW8xbZbt5KfiDQ5Wcdj1Hj9l25a8rfFWcAbyK2*FttzrXb10bBLol5!b2*PqD4eHbiUmR3pSnDEmRtPSE*KnWtNpqULELVwB6Zawnywu1ujEFro3pjTeezLK57QAxbC1Cz1s80J9mH3nYn7eT*8jz3uXszYCodR6*uMCAAh!9S34YFS2tPE3PLzTOu07o!FlGLwOKQ4KoIMjVYP6ozrxgjWzmUPPFPDNM8qVnQ9ihZCARq9NUDHowmEuj59WSKLh9EBh8$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
huongphanmib67b1@outlook.com|Vq9SD6PkAFQM|M.C540_SN1.0.U.-Cpc1nCVKNgiYwfEkovU5FV*gh8B0Mn0QtW0dowS1ds4fW1FcZt9Nsjh3c2MDeoYTwUn*ulPJQgLsVBWgkdbM!q482zpLI6DFX4LNXbnkr8mp33EA73al53F9lwoBnkFn6UOtBwyomKg5AnVOwLZFNQ5hdmqF5hOjrGyqNhKeodJXXpPhn61b4Kcldz1guWfih2HUMcHnuqiJ4pMMPV9unu7cVK022K1ax8*EwtDyI96OyGTaW3KU6TAvfJozU5ZemvqXiNssr0IvFINzvQatN3rpER5Omt6FMI!efseiLKUz3rZTcDRwE9bSLFGIxzypptmslZGaBAjREN5xfbdNFPc$|9e5f94bc-e8a4-4e73-b8be-63364c29d753
EOF

echo "Đã tạo file hotmails_real_zendriver.txt với 2 hotmail"

# String thẻ từ bạn cung cấp
COMPACT_CARDS="6224792557857660|05|2029|3386224792557852612|12|2027|8656224792557857546|12|2032|1406224792557859278|02|2029|2516224792557851416|05|2027|9386224792557851739|05|2031|2886224792557855300|01|2029|3146224792557858585|01|2027|3946224792557859153|02|2028|9836224792557859310|07|2030|972"

echo "4. String thẻ compact:"
echo "   ${COMPACT_CARDS:0:50}..."
echo "   Tổng cộng: $(echo $COMPACT_CARDS | tr '|' '\n' | wc -l) phần tử"

echo ""
echo "5. Chọn chế độ chạy:"
echo "   a) Test 1 account (hiển thị browser - debug)"
echo "   b) Test 2 accounts (headless - production)"
echo "   c) Chạy test script"
echo "   d) Thoát"

read -p "Lựa chọn (a/b/c/d): " choice

case $choice in
    a)
        echo "Chạy test 1 account (hiển thị browser)..."
        python grok_account_creator_zendriver.py \
            --hotmails hotmails_real_zendriver.txt \
            --cards-compact "$COMPACT_CARDS" \
            --workers 1 \
            --test
        ;;
    b)
        echo "Chạy test 2 accounts (headless)..."
        python grok_account_creator_zendriver.py \
            --hotmails hotmails_real_zendriver.txt \
            --cards-compact "$COMPACT_CARDS" \
            --workers 2 \
            --headless \
            --test
        ;;
    c)
        echo "Chạy test script interactive..."
        python test_zendriver_real.py
        ;;
    d)
        echo "Thoát."
        exit 0
        ;;
    *)
        echo "Lựa chọn không hợp lệ"
        exit 1
        ;;
esac

echo ""
echo "=== Hoàn thành ==="
echo ""
echo "Kết quả được lưu vào:"
echo "  - grok_accounts_zendriver.json"
echo "  - grok_accounts_zendriver.csv"
echo "  - grok_account_creator_zendriver.log"
echo ""
echo "Để chạy production (không test):"
echo "python grok_account_creator_zendriver.py --hotmails hotmails_real_zendriver.txt --cards-compact \"\$COMPACT_CARDS\" --workers 3 --headless"
echo ""
echo "Để debug (xem browser):"
echo "python grok_account_creator_zendriver.py --hotmails hotmails_real_zendriver.txt --workers 1"