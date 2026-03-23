import bcrypt
import pytest
from agentdrive.services.auth import hash_api_key, verify_api_key


def test_hash_api_key():
    key = "sk-test-key-12345"
    hashed = hash_api_key(key)
    assert hashed != key
    assert bcrypt.checkpw(key.encode(), hashed.encode())


def test_verify_api_key_valid():
    key = "sk-test-key-12345"
    hashed = hash_api_key(key)
    assert verify_api_key(key, hashed) is True


def test_verify_api_key_invalid():
    hashed = hash_api_key("sk-real-key")
    assert verify_api_key("sk-wrong-key", hashed) is False


from agentdrive.services.auth import generate_api_key, parse_key_prefix, KEY_PREFIX


def test_generate_api_key_format():
    raw_key, prefix, hashed = generate_api_key()
    assert raw_key.startswith(KEY_PREFIX)
    assert len(prefix) == 8
    assert raw_key[len(KEY_PREFIX):len(KEY_PREFIX) + 8] == prefix
    assert hashed != raw_key


def test_generate_api_key_verifies():
    raw_key, prefix, hashed = generate_api_key()
    assert verify_api_key(raw_key, hashed) is True


def test_generate_api_key_unique():
    key1, _, _ = generate_api_key()
    key2, _, _ = generate_api_key()
    assert key1 != key2


def test_parse_key_prefix_valid():
    prefix = parse_key_prefix("sk-ad-abc12345restofthekey")
    assert prefix == "abc12345"


def test_parse_key_prefix_legacy():
    prefix = parse_key_prefix("some-old-key-format")
    assert prefix is None


def test_parse_key_prefix_too_short():
    prefix = parse_key_prefix("sk-ad-ab")
    assert prefix is None
