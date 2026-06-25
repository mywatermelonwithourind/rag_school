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
    TODO(query_understanding/C): 用 LLM 或规则分类替换 mock classify_intent；
        direct_answer 判定须保守，拿不准优先 rewrite（见 router.ROUTING_PROMPT_CONSTRAINTS）
    """
    settings = get_settings()
    question = state.get("normalized_question") or state.get("question", "")

    if state.get("faq_short_circuit"):
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
    trace.append(f"query_route:{intent}")

    return {
        **state,
        "query_intent": intent,
        "retrieval_plan": plan,
        "debug_trace": trace,
    }
