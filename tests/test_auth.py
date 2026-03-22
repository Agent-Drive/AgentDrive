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
