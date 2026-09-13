def build_context_prefix(
    content_type: str,
    filename: str,
    heading_breadcrumb: list[str] | None = None,
    class_name: str | None = None,
    function_name: str | None = None,
    key_path: str | None = None,
    sheet_name: str | None = None,
    columns: list[str] | None = None,
    notebook_section: str | None = None,
    cell_number: int | None = None,
) -> str:
    parts = []

    if content_type == "code":
        parts.append(f"File: {filename}")
        if class_name:
            parts.append(f"Class: {class_name}")
        if function_name:
            parts.append(f"Function: {function_name}")
    elif content_type in ("json", "yaml"):
        parts.append(f"File: {filename}")
        if key_path:
            parts.append(f"Path: {key_path}")
    elif content_type in ("csv", "xlsx"):
        parts.append(f"File: {filename}")
        if sheet_name:
            parts.append(f"Sheet: {sheet_name}")
        if columns:
            parts.append(f"Columns: {', '.join(columns)}")
    elif content_type == "notebook":
        parts.append(f"Notebook: {filename}")
        if notebook_section:
            parts.append(f"Section: {notebook_section}")
        if cell_number is not None:
            parts.append(f"Cell: {cell_number}")
    elif content_type in ("pdf", "markdown"):
        parts.append(f"File: {filename}")
        if heading_breadcrumb:
            parts.append(" > ".join(heading_breadcrumb))
    else:
        parts.append(f"File: {filename}")

    return " | ".join(parts)
