from pathlib import Path

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".rb", ".c", ".cpp", ".h", ".hpp", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".r", ".m", ".cs", ".php", ".lua",
    ".zig", ".nim", ".ex", ".exs", ".clj", ".hs", ".ml", ".vue",
    ".svelte",
}

EXTENSION_MAP = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".mdx": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "json",
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".ipynb": "notebook",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".svg": "image",
    ".webp": "image",
    ".txt": "text",
    ".log": "text",
    ".rst": "text",
}


def detect_content_type(filename: str, mime_type: str | None = None) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".ipynb":
        return "notebook"
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]
    if mime_type:
        if "pdf" in mime_type:
            return "pdf"
        if "image" in mime_type:
            return "image"
        if "json" in mime_type:
            return "json"
        if "yaml" in mime_type or "yml" in mime_type:
            return "yaml"
    return "text"
