"""
LangGraph 主图装配

节点顺序::
    preprocess → rule_match → query_route
        ├─ [direct_parent_chunk | direct_answer] → answer → END
        └─ [rewrite | decompose] → executor → retrieval → answer → END

负责成员: workflow 组（D）
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.workflow.nodes.answer import answer_node
from app.workflow.nodes.executor import executor_node
from app.workflow.nodes.preprocess import preprocess_node
from app.workflow.nodes.query_route import query_route_node
from app.workflow.nodes.retrieval import retrieval_node
from app.workflow.nodes.rule_match import rule_match_node
from app.workflow.state import AgentState, QueryIntent

# 跳过 retrieval 的意图
_SKIP_RETRIEVAL_INTENTS: frozenset[QueryIntent] = frozenset({"direct_parent_chunk", "direct_answer"})


def route_after_query_route(state: AgentState) -> str:
    """
    query_route 后条件分流。

    - direct_parent_chunk / direct_answer → answer（跳过 executor + retrieval）
    - rewrite / decompose → executor → retrieval → answer
    """
    intent: QueryIntent = state.get("query_intent", "rewrite")
    if intent in _SKIP_RETRIEVAL_INTENTS:
        return "answer"
    return "executor"


def build_rag_graph():
    """构建并编译 RAG 主图。"""
    graph = StateGraph(AgentState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("rule_match", rule_match_node)
    graph.add_node("query_route", query_route_node)
    graph.add_node("executor", executor_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("answer", answer_node)

    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "rule_match")
    graph.add_edge("rule_match", "query_route")
    graph.add_conditional_edges(
        "query_route",
        route_after_query_route,
        {
            "executor": "executor",
            "answer": "answer",
        },
    )
    graph.add_edge("executor", "retrieval")
    graph.add_edge("retrieval", "answer")
    graph.add_edge("answer", END)

    return graph.compile()


# 单例，供 api 层调用
rag_graph = build_rag_graph()


def run_rag_pipeline(initial_state: AgentState) -> AgentState:
    """同步执行完整 RAG 流水线。"""
    result = rag_graph.invoke(initial_state)
    return result
