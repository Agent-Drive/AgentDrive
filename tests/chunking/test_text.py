from agentdrive.chunking.text import TextChunker

def test_supported_types():
    chunker = TextChunker()
    assert "text" in chunker.supported_types()

def test_short_text():
    chunker = TextChunker()
    results = chunker.chunk("Hello world.", "notes.txt")
    assert len(results) == 1
    assert results[0].children[0].content == "Hello world."

def test_paragraph_splitting():
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
    chunker = TextChunker()
    results = chunker.chunk(text, "notes.txt")
    assert len(results) >= 1
    all_content = " ".join(c.content for group in results for c in group.children)
    assert "First paragraph" in all_content
    assert "Third paragraph" in all_content

def test_context_prefix_applied():
    chunker = TextChunker()
    results = chunker.chunk("Some text.", "notes.txt")
    assert "notes.txt" in results[0].children[0].context_prefix
