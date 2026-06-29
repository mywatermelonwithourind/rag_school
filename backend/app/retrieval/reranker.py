"""qwen3-rerank 精排 — retrieval 组"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.workflow.state import SourceChunk

logger = logging.getLogger(__name__)


def rerank(query: str, chunks: list[SourceChunk], top_k: int = 5) -> list[SourceChunk]:
    """
    精排并重排。

    优先调用百炼 rerank API；未配置或调用失败时，按 hybrid 分确定性排序，
    避免检索链路因为精排服务不可用返回 500。
    """
    settings = get_settings()

    if not chunks:
        return []

    if not settings.rerank_mock and settings.rerank_api_key and settings.rerank_base_url:
        try:
            return _rerank_with_dashscope(
                query=query,
                chunks=chunks,
                top_k=top_k,
                model=settings.rerank_model,
                api_key=settings.rerank_api_key,
                base_url=settings.rerank_base_url,
            )
        except Exception:
            logger.exception("Rerank API failed; falling back to hybrid-score ranking")

    return _fallback_rerank(chunks, top_k=top_k)


def _fallback_rerank(chunks: list[SourceChunk], top_k: int) -> list[SourceChunk]:
    logger.info("Using fallback rerank for %s chunks", len(chunks))
    reranked: list[SourceChunk] = []
    for index, chunk in enumerate(chunks):
        base = float(chunk.get("score_hybrid", 0.5) or 0.0)
        fallback_score = base + 0.0001 * (len(chunks) - index)
        reranked.append({**chunk, "score_rerank": fallback_score})
    reranked.sort(key=lambda item: item.get("score_rerank", 0.0), reverse=True)
    return reranked[:top_k]


def _rerank_with_dashscope(
    *,
    query: str,
    chunks: list[SourceChunk],
    top_k: int,
    model: str,
    api_key: str,
    base_url: str,
) -> list[SourceChunk]:
    logger.info("Calling DashScope rerank model=%s chunks=%s top_k=%s", model, len(chunks), top_k)
    documents = [chunk["content"] for chunk in chunks]
    payload = {
        "model": model,
        "input": {
            "query": query,
            "documents": documents,
        },
        "parameters": {
            "top_n": top_k,
            "return_documents": False,
        },
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(
            base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    results = _extract_rerank_results(data)
    if not results:
        raise RuntimeError("Rerank API returned no results")

    reranked: list[SourceChunk] = []
    for result in results:
        index = int(result.get("index", -1))
        if index < 0 or index >= len(chunks):
            continue
        score = float(result.get("relevance_score", result.get("score", 0.0)) or 0.0)
        metadata = dict(chunks[index].get("metadata") or {})
        metadata["rerank_provider"] = "dashscope"
        metadata["rerank_raw_score"] = score
        reranked.append({**chunks[index], "score_rerank": score, "metadata": metadata})

    if not reranked:
        raise RuntimeError("Rerank API results did not match input documents")

    reranked.sort(key=lambda item: item.get("score_rerank", 0.0), reverse=True)
    return reranked[:top_k]


def _extract_rerank_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    output = data.get("output")
    if isinstance(output, dict) and isinstance(output.get("results"), list):
        return output["results"]
    if isinstance(data.get("results"), list):
        return data["results"]
    if isinstance(data.get("data"), list):
        return data["data"]
    return []
