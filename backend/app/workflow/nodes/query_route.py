"""LangGraph 节点 — query_route"""

from __future__ import annotations

from app.core.config import get_settings
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
    TODO(query_understanding/C): 恢复真实路由时，再接回 FAQ 短路与 classify_intent；
        当前最小闭环阶段强制 direct_answer，用于验证前后端 + LLM + 存库。
    """
    settings = get_settings()
    # TODO(query_understanding/C): 最小闭环临时短路，之后恢复为真实 intent 分类。
    intent = "direct_answer"

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
