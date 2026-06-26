"""混合粗排 — retrieval 组

score = vector×0.6 + lexical×0.4 + sibling_boost
"""

from __future__ import annotations

from app.core.config import get_settings
from app.workflow.state import SourceChunk


def _clamp_score(value: float) -> float:
    return max(0.0, min(value, 1.0))


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
    doc_counts: dict[str, int] = {}
    for chunk in chunks:
        doc_id = chunk.get("doc_id", "")
        if doc_id:
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

    ranked: list[SourceChunk] = []
    for chunk in chunks:
        vec = chunk.get("score_vector", 0.5)
        lex = _lexical_score(query, chunk["content"])
        sibling_boost = lex * boost if doc_counts.get(chunk.get("doc_id", ""), 0) > 1 else 0.0
        hybrid = _clamp_score(vec * vw + lex * lw + sibling_boost)
        metadata = dict(chunk.get("metadata") or {})
        score_breakdown = dict(metadata.get("score_breakdown") or {})
        score_breakdown.update(
            {
                "hybrid_vector_weight": vw,
                "hybrid_lexical_weight": lw,
                "sibling_boost": sibling_boost,
            }
        )
        metadata["score_breakdown"] = score_breakdown
        updated = {
            **chunk,
            "score_lexical": lex,
            "score_hybrid": hybrid,
            "metadata": metadata,
        }
        ranked.append(updated)

    ranked.sort(key=lambda x: x["score_hybrid"], reverse=True)
    return ranked
