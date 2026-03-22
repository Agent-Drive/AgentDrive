from agentdrive.chunking.hierarchy import build_parent_child_chunks
from agentdrive.chunking.tokens import count_tokens

def test_short_section_single_parent_single_child():
    text = "This is a short section."
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="File: test.txt",
        parent_max_tokens=1500, child_max_tokens=300,
    )
    assert len(results) == 1
    assert results[0].parent.content == text
    assert len(results[0].children) == 1
    assert results[0].children[0].content == text

def test_long_section_splits_into_children():
    sentences = ["This is sentence number %d. " % i for i in range(50)]
    text = "".join(sentences)
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="File: test.txt",
        parent_max_tokens=1500, child_max_tokens=100,
    )
    assert len(results) >= 1
    for group in results:
        for child in group.children:
            assert count_tokens(child.content) <= 120

def test_children_have_context_prefix():
    text = "A meaningful paragraph about authentication flows."
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="File: auth.md | Section: Auth",
        parent_max_tokens=1500, child_max_tokens=300,
    )
    assert results[0].children[0].context_prefix == "File: auth.md | Section: Auth"

def test_tiny_text_not_discarded():
    text = "Short."
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="",
        parent_max_tokens=1500, child_max_tokens=300, min_child_tokens=0,
    )
    assert len(results) == 1
    assert results[0].children[0].content == "Short."

def test_empty_text():
    results = build_parent_child_chunks(text="", content_type="text", context_prefix="")
    assert results == []
