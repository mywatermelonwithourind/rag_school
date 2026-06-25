"""LangGraph 节点 — retrieval"""

from __future__ import annotations

from app.retrieval.pipeline import run_retrieval
from app.workflow.state import AgentState


def retrieval_node(state: AgentState) -> AgentState:
    """
    检索节点：Milvus 召回 → 父块聚合 → 混合粗排 → rerank 精排。

    仅 rewrite / decompose 路径到达（direct_* 已在 graph 层跳过）。

    输入（读取）:
        - retrieval_queries
        - retrieval_plan

    输出（写入）:
        - sources: list[SourceChunk]
        - retrieval_sufficient: bool（标准由 retrieval 组定义，answer 组只读）
        - debug_trace: 追加 "retrieval"

    负责成员: retrieval 组（B）
    TODO(retrieval/B): 替换 mock pipeline 为真实 Milvus + MySQL + rerank
    TODO(workflow/D): answer 兜底仅读取 retrieval_sufficient，勿重复实现阈值
    """
    plan = state.get("retrieval_plan") or {}
    queries = state.get("retrieval_queries") or []

    sources, sufficient = run_retrieval(queries=queries, plan=plan)

    trace = list(state.get("debug_trace", []))
    trace.append(f"retrieval:sources={len(sources)},sufficient={sufficient}")

    return {
        **state,
        "sources": sources,
        "retrieval_sufficient": sufficient,
        "debug_trace": trace,
    }
