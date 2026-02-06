#!/bin/bash
# Test monitoring gói - kiểm tra subscription flow
API="https://grok-auth-api.kh431248.workers.dev"
KEY="huyem"
USER="test_monitor_sh"
PWD="pass123"
PASSED=0
FAILED=0

check() {
    local name="$1" condition="$2" detail="$3"
    if [ "$condition" = "true" ]; then
        echo "  ✅ $name"
        PASSED=$((PASSED+1))
    else
        echo "  ❌ $name — $detail"
        FAILED=$((FAILED+1))
    fi
}

call() {
    curl -s -X "$1" "$2" -H "Content-Type: application/json" ${3:+-H "X-Admin-Key: $KEY"} ${4:+-d "$4"}
}

# Cleanup
call DELETE "$API/admin/users?username=$USER" admin > /dev/null 2>&1

# 1. Tạo account + Login
echo ""
echo "🔹 Test 1: Tạo account + Login"
call POST "$API/admin/users" admin "{\"username\":\"$USER\",\"password\":\"$PWD\",\"plan\":\"basic\",\"expires_at\":\"2026-03-01\"}" > /dev/null
R=$(call POST "$API/login" "" "{\"username\":\"$USER\",\"password\":\"$PWD\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
PLAN=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('plan',''))" 2>/dev/null)
check "Login OK" "$([ "$OK" = "True" ] && echo true || echo false)"
check "Plan = basic" "$([ "$PLAN" = "basic" ] && echo true || echo false)" "got: $PLAN"

# 2. Check subscription (còn hạn)
echo ""
echo "🔹 Test 2: Check subscription (còn hạn)"
R=$(call POST "$API/check" "" "{\"username\":\"$USER\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
EXP=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('expired',''))" 2>/dev/null)
check "Check OK" "$([ "$OK" = "True" ] && echo true || echo false)"
check "Not expired" "$([ "$EXP" = "False" ] && echo true || echo false)"

# 3. Sai password
echo ""
echo "🔹 Test 3: Login sai password"
R=$(call POST "$API/login" "" "{\"username\":\"$USER\",\"password\":\"wrong\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
check "Login fail" "$([ "$OK" = "False" ] && echo true || echo false)"

# 4. Hết hạn
echo ""
echo "🔹 Test 4: Set hết hạn → Check"
call PUT "$API/admin/users" admin "{\"username\":\"$USER\",\"expires_at\":\"2026-02-01\"}" > /dev/null
R=$(call POST "$API/check" "" "{\"username\":\"$USER\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
EXP=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('expired',''))" 2>/dev/null)
check "Check expired" "$([ "$OK" = "False" ] && echo true || echo false)"
check "expired=True" "$([ "$EXP" = "True" ] && echo true || echo false)"

# 5. Khóa account
echo ""
echo "🔹 Test 5: Khóa account → Login + Check"
call PUT "$API/admin/users" admin "{\"username\":\"$USER\",\"is_active\":false,\"expires_at\":\"2026-12-31\"}" > /dev/null
R=$(call POST "$API/login" "" "{\"username\":\"$USER\",\"password\":\"$PWD\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
check "Login bị khóa" "$([ "$OK" = "False" ] && echo true || echo false)"
R=$(call POST "$API/check" "" "{\"username\":\"$USER\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
check "Check bị khóa" "$([ "$OK" = "False" ] && echo true || echo false)"

# 6. Mở khóa + gia hạn
echo ""
echo "🔹 Test 6: Mở khóa + gia hạn → Check OK"
call PUT "$API/admin/users" admin "{\"username\":\"$USER\",\"is_active\":true,\"expires_at\":\"2026-06-01\",\"plan\":\"premium\"}" > /dev/null
R=$(call POST "$API/check" "" "{\"username\":\"$USER\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
PLAN=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('plan',''))" 2>/dev/null)
check "Check OK sau gia hạn" "$([ "$OK" = "True" ] && echo true || echo false)"
check "Plan = premium" "$([ "$PLAN" = "premium" ] && echo true || echo false)" "got: $PLAN"

# 7. User không tồn tại
echo ""
echo "🔹 Test 7: User không tồn tại"
R=$(call POST "$API/check" "" "{\"username\":\"nonexistent_xyz_999\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
check "Check 404" "$([ "$OK" = "False" ] && echo true || echo false)"

# 8. Simulate app monitoring logic
echo ""
echo "🔹 Test 8: Simulate SubscriptionChecker"
R=$(call POST "$API/check" "" "{\"username\":\"$USER\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
check "App tiếp tục (active)" "$([ "$OK" = "True" ] && echo true || echo false)"

call PUT "$API/admin/users" admin "{\"username\":\"$USER\",\"expires_at\":\"2026-01-01\"}" > /dev/null
R=$(call POST "$API/check" "" "{\"username\":\"$USER\"}")
OK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
check "App đóng (hết hạn)" "$([ "$OK" = "False" ] && echo true || echo false)"

# Cleanup
call DELETE "$API/admin/users?username=$USER" admin > /dev/null 2>&1

echo ""
echo "========================================"
echo "  Kết quả: $PASSED passed, $FAILED failed"
echo "========================================"
