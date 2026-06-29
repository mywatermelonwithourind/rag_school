"""BGE Embedding 客户端 — retrieval 组"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def embed_texts(texts: list[str], *, allow_fallback: bool = True) -> list[list[float]]:
    """
    文本向量化。

    优先调用 OpenAI-compatible embeddings API。检索链路默认允许降级为
    确定性本地向量，避免用户请求打成 500；入库链路应传
    allow_fallback=False，防止 mock/fallback 向量污染 Milvus。
    """
    settings = get_settings()
    dim = embedding_dimension()

    if settings.embedding_mock:
        if not allow_fallback:
            raise RuntimeError("Real embedding is required for ingestion, but RAG_EMBEDDING_MOCK=true")
        return [_deterministic_embedding(text, dim) for text in texts]

    if settings.embedding_api_key and settings.embedding_base_url:
        try:
            return _embed_with_openai_compatible_api(
                texts=texts,
                model=settings.embedding_model,
                api_key=settings.embedding_api_key,
                base_url=settings.embedding_base_url,
                dim=dim,
                timeout_seconds=settings.embedding_timeout_seconds,
            )
        except Exception:
            if not allow_fallback:
                raise
            logger.exception("Embedding API failed; falling back to deterministic embeddings")

    if not allow_fallback:
        raise RuntimeError("Real embedding is required for ingestion, but API key or base URL is missing")

    return [_deterministic_embedding(text, dim) for text in texts]


def embedding_dimension() -> int:
    """返回检索链路实际使用的 embedding 维度。"""
    settings = get_settings()
    embedding_dim = int(settings.embedding_dim)
    milvus_dim = int(settings.milvus_dim)
    if embedding_dim != milvus_dim:
        logger.warning(
            "Embedding dim %s does not match Milvus dim %s; using Milvus dim",
            embedding_dim,
            milvus_dim,
        )
        return milvus_dim
    return embedding_dim


def _embed_with_openai_compatible_api(
    *,
    texts: list[str],
    model: str,
    api_key: str,
    base_url: str,
    dim: int,
    timeout_seconds: float,
) -> list[list[float]]:
    endpoint = f"{base_url.rstrip('/')}/embeddings"
    payload: dict[str, Any] = {
        "model": model,
        "input": texts,
        "dimensions": dim,
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
    embeddings = [_validate_dim(item.get("embedding", []), dim) for item in items]
    if len(embeddings) != len(texts):
        raise RuntimeError(f"Embedding API returned {len(embeddings)} vectors for {len(texts)} inputs")
    return embeddings


def _validate_dim(vector: list[Any], dim: int) -> list[float]:
    values = [float(item) for item in vector]
    if len(values) != dim:
        raise RuntimeError(f"Embedding API returned dim={len(values)}, expected dim={dim}")
    return values


def _deterministic_embedding(text: str, dim: int) -> list[float]:
    seed = text.encode("utf-8", errors="ignore") or b"empty"
    values: list[float] = []
    counter = 0

    while len(values) < dim:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) == dim:
                break
        counter += 1

    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]
