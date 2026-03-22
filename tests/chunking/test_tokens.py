from agentdrive.chunking.tokens import count_tokens, truncate_to_tokens


def test_count_tokens_short():
    assert count_tokens("hello world") > 0
    assert count_tokens("hello world") == 2


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_count_tokens_code():
    code = "def hello():\n    return 'world'"
    tokens = count_tokens(code)
    assert tokens > 5


def test_truncate_to_tokens():
    text = "The quick brown fox jumps over the lazy dog. " * 100
    truncated = truncate_to_tokens(text, max_tokens=20)
    assert count_tokens(truncated) <= 20
    assert len(truncated) < len(text)


def test_truncate_short_text_unchanged():
    text = "short text"
    assert truncate_to_tokens(text, max_tokens=100) == text
