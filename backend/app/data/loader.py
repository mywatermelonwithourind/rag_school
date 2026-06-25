"""文档加载 — data 组"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_document(file_path: str | Path) -> dict[str, Any]:
    """
    加载单个文档（PDF/Markdown/Word 等）。

    TODO(data):
        - PDF: pymupdf / pdfplumber
        - Word: python-docx
        - Markdown: 直接读取

    Returns:
        {"doc_id", "title", "content", "metadata"}
    """
    path = Path(file_path)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        "doc_id": path.stem,
        "title": path.stem,
        "content": content or f"[MOCK] 文档 {path.name} 内容占位",
        "metadata": {"source_path": str(path), "format": path.suffix},
    }


def load_documents_from_dir(dir_path: str | Path) -> list[dict[str, Any]]:
    """批量加载目录下文档。"""
    directory = Path(dir_path)
    if not directory.exists():
        return []
    docs = []
    for f in directory.glob("**/*"):
        if f.suffix.lower() in (".md", ".txt", ".pdf", ".docx"):
            docs.append(load_document(f))
    return docs
