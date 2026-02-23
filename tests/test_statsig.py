"""
Test x-statsig-id algorithm — verify structure bằng real curl data.

Real x-statsig-id từ curl request (Chrome 145, macOS, Feb 23 2026):
  URL: POST /rest/app-chat/conversations/new
  Value: CrikC+49MCAdVZqABhxyd79VyOtrBc+HZVsGn4np0Spi+b7OgxlFzbwwvNt8WXQ1ujGQRg/4uJEG5RK318xiq8Sw8u8jCQ

Verified structure (70 bytes total):
  [1 byte XOR key] + XOR(key, [48 meta] + [4 ts LE] + [16 SHA256] + [0x03])
  - Timestamp: LITTLE-ENDIAN, int(time()) - 1682924400
  - SHA256: of "{METHOD}!{path}!{ts}" + fingerprint_info, first 16 bytes
  - Fixed byte: 0x03
"""
import base64
import hashlib
import os
import struct
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.statsig import (
    StatsigIdGenerator,
    EPOCH_OFFSET,
    HARDCODED_FINGERPRINT,
    STATIC_STATSIG_ID,
    generate_statsig_id,
)

# ============================================================
# Real data từ curl request
# ============================================================
REAL_STATSIG_ID = (
    "CrikC+49MCAdVZqABhxyd79VyOtrBc+HZVsGn4np0Spi"
    "+b7OgxlFzbwwvNt8WXQ1ujGQRg/4uJEG5RK318xiq8Sw8u8jCQ"
)
REAL_METHOD = "POST"
REAL_PATH = "/rest/app-chat/conversations/new"
REAL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)


def _pad_b64(s: str) -> str:
    """Add base64 padding nếu thiếu."""
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return s


def _decode_statsig(statsig_b64: str) -> dict:
    """Decode x-statsig-id → dict với các thành phần."""
    raw = base64.b64decode(_pad_b64(statsig_b64))
    xor_key = raw[0]
    encrypted = raw[1:]
    decrypted = bytes(b ^ xor_key for b in encrypted)

    return {
        "total_bytes": len(raw),
        "xor_key": xor_key,
        "payload_len": len(decrypted),
        "meta": decrypted[:48],
        "timestamp_bytes": decrypted[48:52],
        "timestamp": struct.unpack("<I", decrypted[48:52])[0],
        "sha256_16": decrypted[52:68],
        "fixed_byte": decrypted[68] if len(decrypted) > 68 else None,
    }


# ============================================================
# Test 1: Decode real statsig-id — verify structure
# ============================================================
def test_decode_real_statsig_structure():
    """Verify cấu trúc 70 bytes: key(1) + XOR(meta(48) + ts(4) + sha(16) + 0x03)."""
    d = _decode_statsig(REAL_STATSIG_ID)

    assert d["total_bytes"] == 70, f"Expected 70 bytes, got {d['total_bytes']}"
    assert d["payload_len"] == 69, f"Expected 69 byte payload, got {d['payload_len']}"
    assert len(d["meta"]) == 48, f"Meta should be 48 bytes"
    assert len(d["sha256_16"]) == 16, f"SHA256 should be 16 bytes"
    assert d["fixed_byte"] == 0x03, f"Fixed byte should be 0x03, got {d['fixed_byte']}"
    print("✅ test_decode_real_statsig_structure PASSED")
    print(f"   XOR key: 0x{d['xor_key']:02x}")
    print(f"   Meta (hex): {d['meta'].hex()[:40]}...")
    print(f"   SHA256[:16]: {d['sha256_16'].hex()}")
    print(f"   Fixed byte: 0x{d['fixed_byte']:02x}")


# ============================================================
# Test 2: Verify timestamp — little-endian, offset = 1682924400
# ============================================================
def test_timestamp_little_endian():
    """Timestamp phải là little-endian, decode ra thời gian hợp lý (Feb 2026)."""
    d = _decode_statsig(REAL_STATSIG_ID)

    ts_val = d["timestamp"]
    actual_unix = ts_val + EPOCH_OFFSET

    # Curl được lấy khoảng Feb 23, 2026
    # Cho phép sai số ±7 ngày
    import datetime
    dt = datetime.datetime.fromtimestamp(actual_unix)
    print(f"   Decoded time: {dt.strftime('%Y-%m-%d %H:%M:%S')}")

    assert 2026 == dt.year, f"Expected year 2026, got {dt.year}"
    assert dt.month == 2, f"Expected month 2, got {dt.month}"
    assert 16 <= dt.day <= 28, f"Expected day ~23, got {dt.day}"

    # Verify big-endian would give wrong result
    ts_be = struct.unpack(">I", d["timestamp_bytes"])[0]
    actual_be = ts_be + EPOCH_OFFSET
    dt_be = datetime.datetime.fromtimestamp(actual_be)
    assert dt_be.year != 2026, "Big-endian should NOT give 2026"
    print(f"   Big-endian would give: {dt_be.year} (wrong)")
    print("✅ test_timestamp_little_endian PASSED")


# ============================================================
# Test 3: Generate statsig-id — verify output format
# ============================================================
def test_generate_output_format():
    """generate_statsig_id() phải trả về base64 string decode được 70 bytes."""
    gen = StatsigIdGenerator()

    # Inject fake meta content (48 bytes) để không cần fetch grok.com
    gen._meta_content = os.urandom(48)
    gen._last_fetch_time = time.time()

    result = gen.generate(method="POST", path="/rest/app-chat/conversations/new")

    # Phải là valid base64
    raw = base64.b64decode(_pad_b64(result))
    assert len(raw) == 70, f"Expected 70 bytes, got {len(raw)}"

    # Decode và verify structure
    d = _decode_statsig(result)
    assert d["payload_len"] == 69
    assert d["fixed_byte"] == 0x03
    assert d["meta"] == gen._meta_content, "Meta mismatch after XOR roundtrip"

    # Timestamp hợp lý (within 5 seconds of now)
    expected_ts = int(time.time()) - EPOCH_OFFSET
    assert abs(d["timestamp"] - expected_ts) < 5, f"Timestamp drift too large"

    print("✅ test_generate_output_format PASSED")
    print(f"   Generated: {result[:40]}...")
    print(f"   Timestamp: {d['timestamp']} (expected ~{expected_ts})")


# ============================================================
# Test 4: XOR encryption/decryption roundtrip
# ============================================================
def test_xor_roundtrip():
    """XOR encrypt rồi decrypt phải ra payload gốc."""
    gen = StatsigIdGenerator()
    gen._meta_content = b'\xab' * 48
    gen._last_fetch_time = time.time()

    result = gen.generate(method="GET", path="/rest/media/post/create")
    d = _decode_statsig(result)

    # Meta phải match sau khi decrypt
    assert d["meta"] == gen._meta_content, "Meta mismatch after XOR roundtrip"
    assert d["fixed_byte"] == 0x03
    print("✅ test_xor_roundtrip PASSED")


# ============================================================
# Test 5: SHA256 calculation
# ============================================================
def test_sha256_calculation():
    """Verify SHA256 được tính đúng: SHA256("{METHOD}!{path}!{ts}" + fingerprint)[:16]."""
    gen = StatsigIdGenerator()
    gen._meta_content = os.urandom(48)
    gen._last_fetch_time = time.time()

    result = gen.generate(method="POST", path="/test/path")
    d = _decode_statsig(result)

    # Reconstruct SHA256
    ts = d["timestamp"]
    sha_input = f"POST!/test/path!{ts}{HARDCODED_FINGERPRINT}"
    expected_sha = hashlib.sha256(sha_input.encode("utf-8")).digest()[:16]

    assert d["sha256_16"] == expected_sha, (
        f"SHA256 mismatch:\n  got:      {d['sha256_16'].hex()}\n  expected: {expected_sha.hex()}"
    )
    print("✅ test_sha256_calculation PASSED")


# ============================================================
# Test 6: Fallback khi không có meta content
# ============================================================
def test_fallback_static():
    """Khi meta content = None, phải trả về STATIC_STATSIG_ID."""
    gen = StatsigIdGenerator()
    gen._meta_content = None

    result = gen.generate()
    assert result == STATIC_STATSIG_ID, "Should fallback to static value"
    print("✅ test_fallback_static PASSED")


# ============================================================
# Test 7: Different methods/paths produce different statsig-ids
# ============================================================
def test_different_requests_different_ids():
    """Mỗi request khác method/path phải cho SHA256 khác nhau."""
    gen = StatsigIdGenerator()
    gen._meta_content = os.urandom(48)
    gen._last_fetch_time = time.time()

    id1 = gen.generate(method="POST", path="/rest/app-chat/conversations/new")
    id2 = gen.generate(method="POST", path="/rest/media/post/create")
    id3 = gen.generate(method="GET", path="/rest/app-chat/conversations/new")

    # Tất cả phải khác nhau (XOR key random + SHA256 khác)
    assert id1 != id2, "Different paths should produce different IDs"
    assert id1 != id3, "Different methods should produce different IDs"
    print("✅ test_different_requests_different_ids PASSED")


# ============================================================
# Test 8: Convenience function generate_statsig_id()
# ============================================================
def test_convenience_function():
    """Module-level generate_statsig_id() phải hoạt động."""
    result = generate_statsig_id(method="POST", path="/test")
    assert isinstance(result, str), "Should return string"
    assert len(result) > 10, "Should not be empty"
    print(f"✅ test_convenience_function PASSED (len={len(result)})")


# ============================================================
# Run all tests
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Testing x-statsig-id algorithm")
    print("=" * 60)

    tests = [
        test_decode_real_statsig_structure,
        test_timestamp_little_endian,
        test_generate_output_format,
        test_xor_roundtrip,
        test_sha256_calculation,
        test_fallback_static,
        test_different_requests_different_ids,
        test_convenience_function,
    ]

    passed = 0
    failed = 0
    for test in tests:
        print(f"\n--- {test.__name__} ---")
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 60}")
