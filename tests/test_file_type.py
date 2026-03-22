from agentdrive.services.file_type import detect_content_type


def test_detect_pdf():
    assert detect_content_type("report.pdf", "application/pdf") == "pdf"


def test_detect_markdown():
    assert detect_content_type("README.md", "text/markdown") == "markdown"


def test_detect_python():
    assert detect_content_type("main.py", "text/x-python") == "code"


def test_detect_typescript():
    assert detect_content_type("index.ts", "application/typescript") == "code"


def test_detect_json():
    assert detect_content_type("config.json", "application/json") == "json"


def test_detect_yaml():
    assert detect_content_type("config.yaml", "text/yaml") == "yaml"


def test_detect_csv():
    assert detect_content_type("data.csv", "text/csv") == "csv"


def test_detect_xlsx():
    assert detect_content_type("data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") == "xlsx"


def test_detect_notebook():
    assert detect_content_type("analysis.ipynb", "application/json") == "notebook"


def test_detect_image_png():
    assert detect_content_type("diagram.png", "image/png") == "image"


def test_detect_plain_text_fallback():
    assert detect_content_type("notes.txt", "text/plain") == "text"


def test_detect_unknown_falls_back_to_text():
    assert detect_content_type("mystery.xyz", "application/octet-stream") == "text"
