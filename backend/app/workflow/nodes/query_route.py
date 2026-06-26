"""LangGraph 节点 — query_route"""

from __future__ import annotations

from app.core.config import get_settings
from app.query_understanding.router import classify_intent
from app.workflow.state import AgentState, RetrievalPlan


def query_route_node(state: AgentState) -> AgentState:
    """
    查询路由节点：分类 intent 并生成 retrieval_plan。

    输入（读取）:
        - normalized_question, history, session_context
        - faq_match, faq_short_circuit

    输出（写入）:
        - query_intent: rewrite | decompose | direct_answer | direct_parent_chunk
        - retrieval_plan: 检索超参
        - debug_trace: 追加 "query_route"

    负责成员: query_understanding 组
    规则优先：FAQ 短路 → direct_parent_chunk；寒暄/多问/业务问题由 classify_intent 保守判定。
    """
    settings = get_settings()
    question = state.get("normalized_question") or state.get("question", "")
    faq_match = state.get("faq_match") or {}

    if state.get("faq_short_circuit") and faq_match.get("matched"):
        intent = "direct_parent_chunk"
    else:
        intent = classify_intent(
            question=question,
            history=state.get("history", []),
            session_context=state.get("session_context", {}),
        )

    plan: RetrievalPlan = {
        "top_k_vector": settings.top_k_vector,
        "top_k_parent": settings.top_k_parent,
        "top_k_rerank": settings.top_k_rerank,
        "use_hybrid": True,
        "use_rerank": True,
        "min_score_threshold": settings.min_score_threshold,
    }

    trace = list(state.get("debug_trace", []))
    route_source = "faq" if intent == "direct_parent_chunk" else "rule"
    trace.append(f"query_route:{intent},source={route_source}")

    return {
        **state,
        "query_intent": intent,
        "retrieval_plan": plan,
        "debug_trace": trace,
    }
