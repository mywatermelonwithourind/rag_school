"""入库脚本 — data 组

将父块写入 MySQL，子块 embedding 后写入 Milvus。
"""

from __future__ import annotations

from typing import Any

from app.data.chunking import chunk_document
from app.data.loader import load_documents_from_dir
from app.retrieval.embedding import embed_texts


def ingest_directory(dir_path: str, kb_id: str = "kb_cs_college") -> dict[str, int]:
    """
    目录批量入库。

    TODO(data):
        - INSERT INTO parent_chunk ...
        - Milvus insert child_chunks + vectors
        - 事务 / 幂等 / 增量更新

    Returns:
        {"docs", "parents", "children"} 计数
    """
    docs = load_documents_from_dir(dir_path)
    total_parents = 0
    total_children = 0

    for doc in docs:
        doc.setdefault("metadata", {})["kb_id"] = kb_id
        parents, children = chunk_document(doc)
        total_parents += len(parents)
        total_children += len(children)

        if children:
            texts = [c["content"] for c in children]
            _ = embed_texts(texts)
            # TODO(data): milvus insert + mysql insert

    return {"docs": len(docs), "parents": total_parents, "children": total_children}


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "./data/raw"
    result = ingest_directory(path)
    print(f"Ingest complete: {result}")
