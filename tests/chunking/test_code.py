from pathlib import Path
from agentdrive.chunking.code import CodeChunker

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.py"

def test_supported_types():
    chunker = CodeChunker()
    assert "code" in chunker.supported_types()

def test_splits_at_functions():
    content = FIXTURE.read_text()
    chunker = CodeChunker()
    results = chunker.chunk(content, "auth/service.py")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "authenticate" in all_content
    assert "refresh_token" in all_content

def test_class_context_prepended():
    content = FIXTURE.read_text()
    chunker = CodeChunker()
    results = chunker.chunk(content, "auth/service.py")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("AuthService" in p for p in prefixes)

def test_file_path_in_context():
    content = FIXTURE.read_text()
    chunker = CodeChunker()
    results = chunker.chunk(content, "auth/service.py")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("auth/service.py" in p for p in prefixes)

def test_content_type_is_code():
    content = FIXTURE.read_text()
    chunker = CodeChunker()
    results = chunker.chunk(content, "auth/service.py")
    for group in results:
        for child in group.children:
            assert child.content_type == "code"

def test_standalone_function_chunked():
    content = "def hello():\n    return 'world'\n\ndef goodbye():\n    return 'farewell'\n"
    chunker = CodeChunker()
    results = chunker.chunk(content, "utils.py")
    all_content = [c.content for g in results for c in g.children]
    assert any("hello" in c for c in all_content)
    assert any("goodbye" in c for c in all_content)

def test_unsupported_language_fallback():
    content = "fn main() {\n    println!(\"hello\");\n}\n"
    chunker = CodeChunker()
    results = chunker.chunk(content, "main.rs")
    assert len(results) >= 1
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "main" in all_content
