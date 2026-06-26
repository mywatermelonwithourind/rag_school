"""文档加载 — data 组"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SUPPORTED_DOCUMENT_SUFFIXES = {".md", ".txt", ".pdf", ".docx"}


def clean_document_text(text: str) -> str:
    """Clean raw document text while preserving paragraph boundaries."""
    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _read_text_file(path: Path) -> str:
    return _decode_text_bytes(path.read_bytes())


def _read_docx_bytes(data: bytes) -> str:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        texts = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        if texts:
            paragraphs.append("".join(texts))
    return "\n".join(paragraphs)


def _read_docx(path: Path) -> str:
    return _read_docx_bytes(path.read_bytes())


def _read_pdf_bytes(data: bytes) -> tuple[str, str | None]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return "", "PDF extraction skipped: install pypdf first"

    reader = PdfReader(BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages), None


def _read_pdf(path: Path) -> tuple[str, str | None]:
    return _read_pdf_bytes(path.read_bytes())


def _load_document_content(
    *,
    filename: str,
    data: bytes | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    warnings: list[str] = []
    raw_content = ""

    if suffix in (".md", ".txt"):
        raw_content = _decode_text_bytes(data) if data is not None else _read_text_file(path or Path(filename))
    elif suffix == ".docx":
        try:
            raw_content = _read_docx_bytes(data) if data is not None else _read_docx(path or Path(filename))
        except Exception as exc:
            warnings.append(f"DOCX extraction failed: {exc}")
    elif suffix == ".pdf":
        try:
            raw_content, warning = (
                _read_pdf_bytes(data) if data is not None else _read_pdf(path or Path(filename))
            )
            if warning:
                warnings.append(warning)
        except Exception as exc:
            warnings.append(f"PDF extraction failed: {exc}")
    else:
        warnings.append(f"Unsupported document format: {suffix}")

    content = clean_document_text(raw_content)
    if not content and not warnings:
        warnings.append("No text content extracted")

    return {
        "doc_id": Path(filename).stem,
        "title": Path(filename).stem,
        "content": content,
        "metadata": {"source_name": filename, "format": suffix},
        "warnings": warnings,
    }


def load_document(file_path: str | Path) -> dict[str, Any]:
    """
    加载单个文档（PDF/Markdown/Word 等）。

    Returns:
        {"doc_id", "title", "content", "metadata", "warnings"}
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "doc_id": path.stem,
            "title": path.stem,
            "content": "",
            "metadata": {"source_path": str(path), "format": path.suffix.lower()},
            "warnings": [f"File not found: {path}"],
        }

    doc = _load_document_content(filename=path.name, path=path)
    doc["metadata"]["source_path"] = str(path)
    return doc


def load_document_from_bytes(filename: str, data: bytes) -> dict[str, Any]:
    """Load one uploaded document from memory."""
    return _load_document_content(filename=filename, data=data)


def load_documents_from_dir(dir_path: str | Path) -> list[dict[str, Any]]:
    """批量加载目录下文档。"""
    directory = Path(dir_path)
    if not directory.exists():
        return []
    docs = []
    for f in sorted(directory.glob("**/*")):
        if f.is_file() and f.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES:
            docs.append(load_document(f))
    return docs
