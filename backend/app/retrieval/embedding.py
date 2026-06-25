"""BGE Embedding 客户端 — retrieval 组"""

from __future__ import annotations

from app.core.config import get_settings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    文本向量化。

    TODO(retrieval):
        - 调用 BGE API 或本地 sentence-transformers
        - 批量 embedding + cache

    当前返回固定维度 mock 向量。
    """
    settings = get_settings()
    dim = settings.milvus_dim

    if settings.embedding_mock:
        return [[0.01 * (i + 1)] * dim for i, _ in enumerate(texts)]

    raise NotImplementedError("真实 embedding 待 retrieval 组实现")
