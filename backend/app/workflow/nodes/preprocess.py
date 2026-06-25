"""LangGraph 节点 — preprocess"""

from __future__ import annotations

from app.core.utils import normalize_text
from app.workflow.state import AgentState


def preprocess_node(state: AgentState) -> AgentState:
    """
    预处理节点：清洗问题、初始化 session_context 与 debug_trace。

    输入（读取）:
        - question: 用户原始问题
        - history: 对话历史
        - session_id: 会话 ID

    输出（写入）:
        - normalized_question: 清洗后问题
        - session_context: 会话上下文（占位）
        - debug_trace: 追加 "preprocess"

    负责成员: workflow 组（可与 api 组联调入口）
    TODO(workflow): 从 history 提取上一轮主题写入 session_context
    """
    question = state.get("question", "")
    normalized = normalize_text(question)

    session_context = state.get("session_context") or {
        "last_topic": None,
        "turn_count": len(state.get("history", [])),
    }

    trace = list(state.get("debug_trace", []))
    trace.append("preprocess")

    return {
        **state,
        "normalized_question": normalized,
        "session_context": session_context,
        "debug_trace": trace,
    }
