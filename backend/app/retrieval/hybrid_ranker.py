"""混合粗排 — retrieval 组

score = vector×0.6 + lexical×0.4 + sibling_boost
"""

from __future__ import annotations

from app.core.config import get_settings
from app.workflow.state import SourceChunk


def _lexical_score(query: str, content: str) -> float:
    """简单词重叠 lexical 分数（桩）。"""
    q_chars = set(query)
    c_chars = set(content)
    if not q_chars:
        return 0.0
    overlap = len(q_chars & c_chars) / len(q_chars)
    return min(overlap, 1.0)


def hybrid_rank(query: str, chunks: list[SourceChunk]) -> list[SourceChunk]:
    """
    混合粗排并降序排列。

    TODO(retrieval):
        - BM25 / MySQL FULLTEXT 作为 lexical 分量
        - sibling_boost: 同一 parent 下多子块命中加分

    Args:
        query: 检索 query
        chunks: 待排序父块

    Returns:
        按 score_hybrid 降序的 chunks（score_hybrid 已写入）
    """
    settings = get_settings()
    vw = settings.hybrid_vector_weight
    lw = settings.hybrid_lexical_weight
    boost = settings.sibling_boost

    ranked: list[SourceChunk] = []
    for chunk in chunks:
        vec = chunk.get("score_vector", 0.5)
        lex = _lexical_score(query, chunk["content"])
        hybrid = vec * vw + lex * lw + boost
        updated = {**chunk, "score_lexical": lex, "score_hybrid": hybrid}
        ranked.append(updated)

    ranked.sort(key=lambda x: x["score_hybrid"], reverse=True)
    return ranked
