"""LangGraph 节点 — preprocess"""

from __future__ import annotations

from app.core.utils import normalize_text
from app.query_understanding.history_resolver import resolve_followup
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
    history = state.get("history", [])

    resolution = resolve_followup(question, history)
    standalone_question = normalize_text(resolution["standalone_question"])
    working_question = resolution["standalone_question"] if resolution["history_used"] else question
    normalized = normalize_text(working_question)

    session_context = dict(state.get("session_context") or {})
    session_context.setdefault("last_topic", None)
    session_context["turn_count"] = len(history)
    session_context.update(
        {
            "standalone_question": standalone_question,
            "history_used": resolution["history_used"],
            "history_anchor": resolution["history_anchor"],
            "history_strategy": resolution["history_strategy"],
        }
    )

    trace = list(state.get("debug_trace", []))
    trace.append(f"preprocess:history_strategy={resolution['history_strategy']}")

    return {
        **state,
        "raw_question": question,
        "normalized_question": normalized,
        "session_context": session_context,
        "debug_trace": trace,
    }
