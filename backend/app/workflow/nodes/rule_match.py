"""LangGraph 节点 — rule_match (FAQ)"""

from __future__ import annotations

from app.query_understanding.faq_matcher import match_faq
from app.workflow.state import AgentState, FAQMatchResult


def rule_match_node(state: AgentState) -> AgentState:
    """
    FAQ 规则匹配节点。

    输入（读取）:
        - normalized_question: 清洗后问题

    输出（写入）:
        - faq_match: FAQ 匹配结果
        - faq_short_circuit: 是否短路跳过检索
        - debug_trace: 追加 "rule_match"

    负责成员: query_understanding 组
    TODO(query_understanding): 替换 mock 为 MySQL FAQ 表 + 别名表联合匹配
    """
    question = state.get("normalized_question") or state.get("question", "")
    faq_result: FAQMatchResult = match_faq(question)

    short_circuit = faq_result["matched"] and faq_result["confidence"] >= 0.85

    trace = list(state.get("debug_trace", []))
    trace.append("rule_match")

    return {
        **state,
        "faq_match": faq_result,
        "faq_short_circuit": short_circuit,
        "debug_trace": trace,
    }
