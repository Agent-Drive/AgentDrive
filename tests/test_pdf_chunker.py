from unittest.mock import MagicMock, patch

import pytest


def _make_text_block(text: str, type_: str = "paragraph"):
    """Make a mock text_block with type and text."""
    block = MagicMock()
    block.text_block.text = text
    block.text_block.type_ = type_
    block.text_block.blocks = []
    block.table_block = None
    return block


def _make_table_block(headers: list[str], rows: list[list[str]]):
    """Make a mock table_block."""
    block = MagicMock()
    block.text_block = None

    header_row = MagicMock()
    header_row.cells = []
    for h in headers:
        cell = MagicMock()
        cell.blocks = [_make_text_block(h)]
        header_row.cells.append(cell)

    body_rows = []
    for row in rows:
        body_row = MagicMock()
        body_row.cells = []
        for val in row:
            cell = MagicMock()
            cell.blocks = [_make_text_block(val)]
            body_row.cells.append(cell)
        body_rows.append(body_row)

    table = MagicMock()
    table.header_rows = [header_row]
    table.body_rows = body_rows

    block.table_block = table
    return block


def _make_document(blocks):
    """Make a mock Document with document_layout.blocks."""
    doc = MagicMock()
    doc.document_layout.blocks = blocks
    return doc


class TestDocAiToMarkdown:
    def test_paragraph(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("This is a paragraph.", "paragraph"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "This is a paragraph." in result
        assert not result.startswith("#")

    def test_heading_levels(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("Main Title", "title"),
            _make_text_block("Section One", "heading-1"),
            _make_text_block("Subsection", "heading-2"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "# Main Title" in result
        assert "## Section One" in result
        assert "### Subsection" in result

    def test_list_items(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("First item", "list-item"),
            _make_text_block("Second item", "list-item"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "- First item" in result
        assert "- Second item" in result

    def test_table(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_table_block(
                headers=["Name", "Age"],
                rows=[["Alice", "30"], ["Bob", "25"]],
            ),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "| Name | Age |" in result
        assert "| --- | --- |" in result
        assert "| Alice | 30 |" in result
        assert "| Bob | 25 |" in result

    def test_empty_document(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([])
        result = _doc_ai_to_markdown(doc)
        assert result == ""

    def test_mixed_content(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("Report Title", "title"),
            _make_text_block("This is the introduction.", "paragraph"),
            _make_table_block(
                headers=["Col1", "Col2"],
                rows=[["Val1", "Val2"]],
            ),
            _make_text_block("Summary", "heading-1"),
            _make_text_block("Final thoughts.", "paragraph"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "# Report Title" in result
        assert "This is the introduction." in result
        assert "| Col1 | Col2 |" in result
        assert "## Summary" in result
        assert "Final thoughts." in result

    def test_skips_header_footer(self):
        from agentdrive.chunking.pdf import _doc_ai_to_markdown

        doc = _make_document([
            _make_text_block("Page 1 of 10", "header"),
            _make_text_block("Actual content.", "paragraph"),
            _make_text_block("Copyright 2025", "footer"),
        ])
        result = _doc_ai_to_markdown(doc)
        assert "Actual content." in result
        assert "Page 1 of 10" not in result
        assert "Copyright 2025" not in result
