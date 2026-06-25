"""
检索流水线 — retrieval 组

Milvus 子块召回 → MySQL 父块聚合 → 混合粗排 → qwen3-rerank 精排
当前为 mock 实现，返回固定父块数据。
"""

from __future__ import annotations

from typing import Any

from app.retrieval.embedding import embed_texts
from app.retrieval.hybrid_ranker import hybrid_rank
from app.retrieval.milvus_client import search_child_chunks
from app.retrieval.reranker import rerank
from app.workflow.state import FAQMatchResult, RetrievalPlan, SourceChunk

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
}


def _fetch_by_parent_ids(parent_ids: list[str]) -> list[SourceChunk]:
    """从 mock / MySQL 按 parent_chunk_id 取父块全文。"""
    # TODO(retrieval): SELECT content FROM parent_chunk WHERE parent_chunk_id IN (...)
    return [_MOCK_PARENT_CHUNKS[pid] for pid in parent_ids if pid in _MOCK_PARENT_CHUNKS]


def fetch_parent_chunks_by_ids(parent_ids: list[str]) -> list[SourceChunk]:
    """
    按 parent_chunk_id 批量取父块（FAQ 直出 / answer 节点用）。

    TODO(retrieval/B): 改查 MySQL parent_chunk 表
    """
    return _fetch_by_parent_ids(parent_ids)


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

    for query in queries:
        # 1. Embedding
        _ = embed_texts([query])

        # 2. Milvus 子块召回（mock）
        child_hits = search_child_chunks(query, top_k=plan.get("top_k_vector", 20))

        # 3. 父块聚合（mock：映射到 mock 父块）
        parent_ids = list({h.get("parent_chunk_id", "") for h in child_hits if h.get("parent_chunk_id")})
        if not parent_ids:
            parent_ids = list(_MOCK_PARENT_CHUNKS.keys())[: plan.get("top_k_parent", 8)]

        parents = _fetch_by_parent_ids(parent_ids[: plan.get("top_k_parent", 8)])

        # 4. 混合粗排
        if plan.get("use_hybrid", True):
            parents = hybrid_rank(query, parents)

        all_hits.extend(parents)

    # 去重按 parent_chunk_id
    seen: set[str] = set()
    unique: list[SourceChunk] = []
    for s in all_hits:
        pid = s["parent_chunk_id"]
        if pid not in seen:
            seen.add(pid)
            unique.append(s)

    # 5. Rerank 精排
    if plan.get("use_rerank", True) and unique:
        primary_query = queries[0]
        unique = rerank(primary_query, unique, top_k=plan.get("top_k_rerank", 5))
    else:
        unique = unique[: plan.get("top_k_rerank", 5)]

    sufficient = is_retrieval_sufficient(unique, plan)

    return unique, sufficient
