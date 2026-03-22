from agentdrive.chunking.context import build_context_prefix


def test_pdf_context():
    prefix = build_context_prefix(
        content_type="pdf", filename="quarterly-report.pdf",
        heading_breadcrumb=["Financial Results", "Revenue"],
    )
    assert "quarterly-report.pdf" in prefix
    assert "Financial Results" in prefix
    assert "Revenue" in prefix


def test_markdown_context():
    prefix = build_context_prefix(
        content_type="markdown", filename="README.md",
        heading_breadcrumb=["API Reference", "Authentication", "OAuth2"],
    )
    assert "API Reference > Authentication > OAuth2" in prefix


def test_code_context():
    prefix = build_context_prefix(
        content_type="code", filename="src/auth/service.py",
        class_name="AuthService", function_name="authenticate",
    )
    assert "src/auth/service.py" in prefix
    assert "AuthService" in prefix
    assert "authenticate" in prefix


def test_structured_context():
    prefix = build_context_prefix(
        content_type="json", filename="config.json", key_path="api.endpoints[0]",
    )
    assert "config.json" in prefix
    assert "api.endpoints[0]" in prefix


def test_spreadsheet_context():
    prefix = build_context_prefix(
        content_type="csv", filename="data.csv",
        sheet_name="Revenue", columns=["Region", "Revenue", "Growth"],
    )
    assert "data.csv" in prefix
    assert "Revenue" in prefix
    assert "Region" in prefix


def test_minimal_context():
    prefix = build_context_prefix(content_type="text", filename="notes.txt")
    assert "notes.txt" in prefix
