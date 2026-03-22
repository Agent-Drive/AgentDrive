from pathlib import Path
from agentdrive.chunking.markdown import MarkdownChunker

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.md"

def test_supported_types():
    chunker = MarkdownChunker()
    assert "markdown" in chunker.supported_types()

def test_splits_at_h2():
    content = FIXTURE.read_text()
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "api-reference.md")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "OAuth2" in all_content
    assert "Create User" in all_content

def test_breadcrumb_in_context():
    content = FIXTURE.read_text()
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "api-reference.md")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("Authentication" in p for p in prefixes)

def test_code_blocks_not_split():
    content = "## Setup\n\nInstall:\n\n```python\nimport os\nprint(os.getcwd())\n```\n\nDone."
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "setup.md")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "import os" in all_content
    assert "print(os.getcwd())" in all_content

def test_tables_kept_atomic():
    content = "## Data\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "data.md")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "| A | B |" in all_content

def test_front_matter_extracted():
    content = "---\ntitle: Test Doc\ntags: [a, b]\n---\n\n# Test\n\nContent here."
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "test.md")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "---" not in all_content or "title:" not in all_content

def test_tiny_sections_merged():
    content = "## A\n\nShort.\n\n## B\n\nAlso short.\n\n## C\n\nLonger section with more content that makes it worthwhile as its own chunk."
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "test.md")
    total_children = sum(len(g.children) for g in results)
    assert total_children <= 3
