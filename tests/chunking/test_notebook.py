import json
from agentdrive.chunking.notebook import NotebookChunker


def make_notebook(cells):
    return json.dumps({"nbformat": 4, "metadata": {}, "cells": cells})


def test_supported_types():
    chunker = NotebookChunker()
    assert "notebook" in chunker.supported_types()


def test_pairs_markdown_with_code():
    nb = make_notebook([
        {"cell_type": "markdown", "source": ["## Data Loading"], "metadata": {}},
        {"cell_type": "code", "source": ["import pandas as pd\ndf = pd.read_csv('data.csv')"], "metadata": {}, "outputs": []},
    ])
    chunker = NotebookChunker()
    results = chunker.chunk(nb, "analysis.ipynb")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "Data Loading" in all_content
    assert "import pandas" in all_content


def test_notebook_context():
    nb = make_notebook([
        {"cell_type": "markdown", "source": ["## Setup"], "metadata": {}},
        {"cell_type": "code", "source": ["x = 1"], "metadata": {}, "outputs": []},
    ])
    chunker = NotebookChunker()
    results = chunker.chunk(nb, "test.ipynb")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("test.ipynb" in p for p in prefixes)
