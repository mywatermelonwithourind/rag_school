"""LangGraph 节点 — executor（rewrite / decompose 分支）"""

from __future__ import annotations

from collections.abc import Callable

from app.query_understanding.rewrite import decompose_query, rewrite_query
from app.workflow.state import AgentState, QueryIntent


def _handle_rewrite(state: AgentState) -> list[str]:
    """
    rewrite 分支：多轮指代消解改写。

    TODO(query_understanding): LLM 改写 + 指代消解
    """
    question = state.get("normalized_question") or state.get("question", "")
    rewritten = rewrite_query(
        question=question,
        history=state.get("history", []),
        session_context=state.get("session_context", {}),
    )
    return [rewritten]


def _handle_decompose(state: AgentState) -> list[str]:
    """
    decompose 分支：复杂问题拆分子查询。

    TODO(query_understanding): LLM 拆分
    """
    question = state.get("normalized_question") or state.get("question", "")
    return decompose_query(question)


_EXECUTOR_HANDLERS: dict[QueryIntent, Callable[[AgentState], list[str]]] = {
    "rewrite": _handle_rewrite,
    "decompose": _handle_decompose,
}


def executor_node(state: AgentState) -> AgentState:
    """
    执行器节点：为 rewrite / decompose 产出 retrieval_queries。

    仅在被 query_route 条件边路由到 executor 时执行；
    direct_parent_chunk / direct_answer 跳过本节点。

    输入（读取）:
        - query_intent（应为 rewrite 或 decompose）
        - normalized_question, history, session_context

    输出（写入）:
        - retrieval_queries: list[str]
        - debug_trace: 追加 "executor:{intent}"

    负责成员: query_understanding 组（改写/拆分）+ workflow 组（编排）
    """
    intent: QueryIntent = state.get("query_intent", "rewrite")
    handler = _EXECUTOR_HANDLERS.get(intent, _handle_rewrite)
    queries = handler(state)

    trace = list(state.get("debug_trace", []))
    trace.append(f"executor:{intent}")

    return {
        **state,
        "retrieval_queries": queries,
        "debug_trace": trace,
    }
