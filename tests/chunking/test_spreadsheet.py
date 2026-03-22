from agentdrive.chunking.spreadsheet import SpreadsheetChunker


def test_supported_types():
    chunker = SpreadsheetChunker()
    assert "csv" in chunker.supported_types()


def test_csv_chunking():
    csv_content = "Name,Age,City\nAlice,30,NYC\nBob,25,SF\nCharlie,35,LA\n"
    chunker = SpreadsheetChunker()
    results = chunker.chunk(csv_content, "people.csv")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "Alice" in all_content
    assert "Name" in all_content


def test_headers_in_context():
    csv_content = "Name,Age\nAlice,30\n"
    chunker = SpreadsheetChunker()
    results = chunker.chunk(csv_content, "data.csv")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("Name" in p for p in prefixes)
