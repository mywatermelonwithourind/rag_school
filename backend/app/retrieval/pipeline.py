"""
检索流水线 — retrieval 组

Milvus 子块召回 → MySQL 父块聚合 → 混合粗排 → qwen3-rerank 精排
当前为 mock 实现，返回固定父块数据。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.core.database import get_db_session
from app.core.models import ParentChunkRecord
from app.retrieval.embedding import embed_texts
from app.retrieval.hybrid_ranker import hybrid_rank
from app.retrieval.milvus_client import search_child_chunks
from app.retrieval.reranker import rerank
from app.workflow.state import FAQMatchResult, RetrievalPlan, SourceChunk

logger = logging.getLogger(__name__)

MIN_CHILD_CONFIDENCE = 0.2
PARENT_CHILD_BEST_WEIGHT = 0.78
PARENT_CHILD_AVERAGE_WEIGHT = 0.17
PARENT_CHILD_DENSITY_WEIGHT = 0.03
PARENT_CHILD_QUERY_COVERAGE_WEIGHT = 0.02
PARENT_CHILD_AVERAGE_GAP = 0.10

# Mock 父块库
_MOCK_PARENT_CHUNKS: dict[str, SourceChunk] = {
    "pc_office_hours": {
        "parent_chunk_id": "pc_office_hours",
        "child_chunk_id": "cc_001",
        "content": "计算机学院办公室工作时间为周一至周五 8:30-17:00，中午 12:00-13:30 休息。",
        "doc_id": "doc_admin_guide",
        "kb_id": "kb_cs_college",
        "score_vector": 0.92,
        "score_lexical": 0.88,
        "score_hybrid": 0.90,
        "score_rerank": None,
        "metadata": {"section": "办公时间"},
    },
    "pc_office_location": {
        "parent_chunk_id": "pc_office_location",
        "child_chunk_id": "cc_004",
        "content": "计算机学院办公室位于信息楼 3 层，学生可在工作时间前往咨询学籍、证明和日常事务。",
        "doc_id": "doc_admin_guide",
        "kb_id": "kb_cs_college",
        "score_vector": 0.0,
        "score_lexical": 0.0,
        "score_hybrid": 0.0,
        "score_rerank": None,
        "metadata": {"section": "办公室地点"},
    },
    "pc_counselor_contact": {
        "parent_chunk_id": "pc_counselor_contact",
        "child_chunk_id": "cc_002",
        "content": "本科生辅导员联系方式请参见学院官网「学生工作」栏目，或拨打学院办公室总机转接。",
        "doc_id": "doc_student_affairs",
        "kb_id": "kb_cs_college",
        "score_vector": 0.85,
        "score_lexical": 0.80,
        "score_hybrid": 0.83,
        "score_rerank": None,
        "metadata": {"section": "辅导员"},
    },
    "pc_graduation_req": {
        "parent_chunk_id": "pc_graduation_req",
        "child_chunk_id": "cc_003",
        "content": "计算机专业毕业学分要求为 160 学分，其中必修 98 学分，选修不少于 42 学分。",
        "doc_id": "doc_curriculum",
        "kb_id": "kb_cs_college",
        "score_vector": 0.78,
        "score_lexical": 0.75,
        "score_hybrid": 0.76,
        "score_rerank": None,
        "metadata": {"section": "毕业要求"},
    },
    "pc_graduation_process": {
        "parent_chunk_id": "pc_graduation_process",
        "child_chunk_id": "cc_005",
        "content": "毕业资格审核通常依据培养方案、课程成绩和学分完成情况进行，具体安排以学院通知为准。",
        "doc_id": "doc_curriculum",
        "kb_id": "kb_cs_college",
        "score_vector": 0.0,
        "score_lexical": 0.0,
        "score_hybrid": 0.0,
        "score_rerank": None,
        "metadata": {"section": "毕业审核"},
    },
}


def _clamp_score(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _fetch_by_parent_ids(parent_ids: list[str]) -> list[SourceChunk]:
    """从 MySQL 按 parent_chunk_id 取父块全文。"""
    ordered_ids = [str(parent_id).strip() for parent_id in parent_ids if str(parent_id).strip()]
    if not ordered_ids:
        return []

    try:
        with get_db_session() as db:
            records = db.scalars(
                select(ParentChunkRecord).where(ParentChunkRecord.parent_chunk_id.in_(ordered_ids))
            ).all()
    except Exception:
        logger.exception("Failed to load parent chunks from MySQL")
        return []

    records_by_id = {record.parent_chunk_id: record for record in records}
    chunks: list[SourceChunk] = []
    for parent_id in ordered_ids:
        record = records_by_id.get(parent_id)
        if record is None:
            continue
        chunks.append(
            {
                "parent_chunk_id": record.parent_chunk_id,
                "child_chunk_id": None,
                "content": record.content,
                "doc_id": record.doc_id,
                "kb_id": record.kb_id,
                "score_vector": 0.0,
                "score_lexical": 0.0,
                "score_hybrid": 0.0,
                "score_rerank": None,
                "metadata": {
                    **(record.meta or {}),
                    "title": record.title,
                    "chunk_index": record.chunk_index,
                },
            }
        )
    return chunks


def fetch_parent_chunks_by_ids(parent_ids: list[str]) -> list[SourceChunk]:
    """
    按 parent_chunk_id 批量取父块（FAQ 直出 / answer 节点用）。

    TODO(retrieval/B): 改查 MySQL parent_chunk 表
    """
    return _fetch_by_parent_ids(parent_ids)


def _child_hit_summary(
    hit: dict[str, Any],
    *,
    query: str,
    query_index: int,
    query_weight: float,
) -> dict[str, Any]:
    score = _clamp_score(float(hit.get("score", 0.0) or 0.0))
    return {
        "child_chunk_id": str(hit.get("child_chunk_id") or ""),
        "parent_chunk_id": str(hit.get("parent_chunk_id") or ""),
        "score": score,
        "weighted_score": _clamp_score(score * query_weight),
        "retrieval_query": query,
        "retrieval_query_index": query_index,
        "retrieval_query_weight": query_weight,
    }


def _apply_parent_child_weighting(candidate: dict[str, Any], query_count: int) -> dict[str, Any]:
    child_hits = [
        hit
        for hit in candidate.get("child_hits", [])
        if isinstance(hit, dict)
    ]
    weighted_scores = sorted(
        (_clamp_score(float(hit.get("weighted_score", hit.get("score", 0.0)) or 0.0)) for hit in child_hits),
        reverse=True,
    )
    if not weighted_scores:
        return candidate

    best_weighted_score = weighted_scores[0]
    near_top_scores = [
        score for score in weighted_scores[:3] if best_weighted_score - score < PARENT_CHILD_AVERAGE_GAP
    ]
    average_top_child_score = (
        sum(near_top_scores) / len(near_top_scores)
        if near_top_scores
        else best_weighted_score
    )
    child_density_score = min(1.0, len(child_hits) / 3)
    query_keys = {
        int(hit.get("retrieval_query_index", 0) or 0)
        for hit in child_hits
    }
    query_coverage_denominator = max(1, min(3, query_count))
    query_coverage_score = min(1.0, len(query_keys) / query_coverage_denominator)
    weighted_child_score = _clamp_score(
        best_weighted_score * PARENT_CHILD_BEST_WEIGHT
        + average_top_child_score * PARENT_CHILD_AVERAGE_WEIGHT
        + child_density_score * PARENT_CHILD_DENSITY_WEIGHT
        + query_coverage_score * PARENT_CHILD_QUERY_COVERAGE_WEIGHT
    )
    return {
        **candidate,
        "best_weighted_score": best_weighted_score,
        "average_top_child_score": average_top_child_score,
        "child_density_score": child_density_score,
        "query_coverage_score": query_coverage_score,
        "weighted_child_score": weighted_child_score,
    }


def build_parent_candidates_from_child_hits(
    child_hits: list[dict[str, Any]],
    *,
    min_confidence: float = MIN_CHILD_CONFIDENCE,
    query_count: int = 1,
) -> list[dict[str, Any]]:
    """把多个子块命中聚合成父块候选，并计算父块向量侧分数。"""
    candidates_by_parent_id: dict[str, dict[str, Any]] = {}
    for hit in child_hits:
        score = _clamp_score(float(hit.get("score", 0.0) or 0.0))
        if score < min_confidence:
            continue
        parent_chunk_id = str(hit.get("parent_chunk_id") or "").strip()
        if not parent_chunk_id:
            continue

        candidate = candidates_by_parent_id.setdefault(
            parent_chunk_id,
            {
                "parent_chunk_id": parent_chunk_id,
                "representative_child_chunk_id": str(hit.get("child_chunk_id") or ""),
                "child_hits": [],
                "best_score": score,
            },
        )
        candidate["child_hits"].append(hit)
        if score > float(candidate.get("best_score", 0.0) or 0.0):
            candidate["best_score"] = score
            candidate["representative_child_chunk_id"] = str(hit.get("child_chunk_id") or "")

    candidates = [
        _apply_parent_child_weighting(candidate, query_count=query_count)
        for candidate in candidates_by_parent_id.values()
    ]
    return sorted(
        candidates,
        key=lambda item: float(item.get("weighted_child_score", item.get("best_score", 0.0)) or 0.0),
        reverse=True,
    )


def _candidates_to_parent_chunks(candidates: list[dict[str, Any]]) -> list[SourceChunk]:
    parent_ids = [str(candidate.get("parent_chunk_id") or "") for candidate in candidates]
    records_by_id = {
        chunk["parent_chunk_id"]: chunk
        for chunk in _fetch_by_parent_ids(parent_ids)
    }
    chunks: list[SourceChunk] = []
    for candidate in candidates:
        parent_id = str(candidate.get("parent_chunk_id") or "")
        record = records_by_id.get(parent_id)
        if record is None:
            continue
        metadata = dict(record.get("metadata") or {})
        metadata["child_hits"] = list(candidate.get("child_hits") or [])
        metadata["score_breakdown"] = {
            **dict(metadata.get("score_breakdown") or {}),
            "best_child_score": float(candidate.get("best_score", 0.0) or 0.0),
            "best_weighted_score": float(candidate.get("best_weighted_score", 0.0) or 0.0),
            "average_top_child_score": float(candidate.get("average_top_child_score", 0.0) or 0.0),
            "child_density_score": float(candidate.get("child_density_score", 0.0) or 0.0),
            "query_coverage_score": float(candidate.get("query_coverage_score", 0.0) or 0.0),
            "weighted_child_score": float(candidate.get("weighted_child_score", 0.0) or 0.0),
        }
        chunks.append(
            {
                **record,
                "child_chunk_id": str(candidate.get("representative_child_chunk_id") or "") or record.get("child_chunk_id"),
                "score_vector": float(candidate.get("weighted_child_score", candidate.get("best_score", 0.0)) or 0.0),
                "score_lexical": 0.0,
                "score_hybrid": 0.0,
                "score_rerank": None,
                "metadata": metadata,
            }
        )
    return chunks


def is_retrieval_sufficient(sources: list[SourceChunk], plan: RetrievalPlan) -> bool:
    """
    判定检索材料是否充足 — 标准由成员 B 定义，成员 D 在 answer 兜底时只读结果。

    当前规则（桩）:
        - sources 非空
        - top-1 的 rerank 分（或 hybrid 分）≥ plan.min_score_threshold

    TODO(retrieval/B): 明确召回数下限、多 query 合并规则、rerank/hybrid 阈值取舍
    TODO(workflow/D): answer 节点仅消费 state.retrieval_sufficient，勿在此重复实现
    """
    if not sources:
        return False

    threshold = plan.get("min_score_threshold", 0.35)
    best_score = max(
        (s.get("score_rerank") or s.get("score_hybrid", 0.0) for s in sources),
        default=0.0,
    )
    return best_score >= threshold


def run_retrieval(
    queries: list[str],
    plan: RetrievalPlan,
    faq_match: FAQMatchResult | None = None,
) -> tuple[list[SourceChunk], bool]:
    """
    执行检索流水线。

    Args:
        queries: 检索 query 列表
        plan: 检索计划
        faq_match: FAQ 命中时可直取 target_parent_chunk_ids

    Returns:
        (sources, retrieval_sufficient)
    """
    if faq_match and faq_match.get("matched") and faq_match.get("target_parent_chunk_ids"):
        sources = _fetch_by_parent_ids(faq_match["target_parent_chunk_ids"])
        sufficient = is_retrieval_sufficient(sources, plan) if sources else False
        return sources, sufficient

    if not queries:
        return [], False

    all_hits: list[SourceChunk] = []
    all_child_hits: list[dict[str, Any]] = []

    query_count = max(1, len(queries))
    for query_index, query in enumerate(queries):
        # 1. Embedding
        _ = embed_texts([query])

        # 2. Milvus 子块召回（mock）
        child_hits = search_child_chunks(query, top_k=plan.get("top_k_vector", 20))
        query_weight = 1.0 if query_index == 0 else 0.85
        all_child_hits.extend(
            _child_hit_summary(
                hit,
                query=query,
                query_index=query_index,
                query_weight=query_weight,
            )
            for hit in child_hits
        )

    # 3. 父块聚合：多个子块命中归并到 parent，并计算父块向量侧分数
    parent_candidates = build_parent_candidates_from_child_hits(
        all_child_hits,
        min_confidence=MIN_CHILD_CONFIDENCE,
        query_count=query_count,
    )
    if not parent_candidates:
        return [], False

    parents = _candidates_to_parent_chunks(parent_candidates[: plan.get("top_k_parent", 8)])

    # 4. 混合粗排
    if plan.get("use_hybrid", True):
        parents = hybrid_rank(queries[0], parents)

    all_hits.extend(parents)

    # 去重按 parent_chunk_id
    seen: set[str] = set()
    unique: list[SourceChunk] = []
    for s in all_hits:
        pid = s["parent_chunk_id"]
        if pid not in seen:
            seen.add(pid)
            unique.append(s)
            continue
        for index, existing in enumerate(unique):
            if existing["parent_chunk_id"] == pid and s.get("score_hybrid", 0.0) > existing.get("score_hybrid", 0.0):
                unique[index] = s
                break

    threshold = plan.get("min_score_threshold", 0.35)
    unique = [
        source
        for source in unique
        if float(source.get("score_hybrid", 0.0) or 0.0) >= threshold
    ]

    # 5. Rerank 精排
    if plan.get("use_rerank", True) and unique:
        primary_query = queries[0]
        unique = rerank(primary_query, unique, top_k=plan.get("top_k_rerank", 5))
    else:
        unique = unique[: plan.get("top_k_rerank", 5)]

    sufficient = is_retrieval_sufficient(unique, plan)

    return unique, sufficient
