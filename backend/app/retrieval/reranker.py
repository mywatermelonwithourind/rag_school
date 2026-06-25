"""qwen3-rerank 精排 — retrieval 组"""

from __future__ import annotations

from app.core.config import get_settings
from app.workflow.state import SourceChunk


def rerank(query: str, chunks: list[SourceChunk], top_k: int = 5) -> list[SourceChunk]:
    """
    精排并重排。

    TODO(retrieval):
        - 调用百炼 qwen3-rerank API
        - 写入 score_rerank

    当前 mock：按 score_hybrid 微调后排序。
    """
    settings = get_settings()

    if settings.rerank_mock:
        reranked: list[SourceChunk] = []
        for i, chunk in enumerate(chunks):
            base = chunk.get("score_hybrid", 0.5)
            mock_rerank = base + 0.02 * (len(chunks) - i)
            reranked.append({**chunk, "score_rerank": mock_rerank})
        reranked.sort(key=lambda x: x.get("score_rerank", 0.0), reverse=True)
        return reranked[:top_k]

    raise NotImplementedError("真实 rerank 待 retrieval 组实现")
