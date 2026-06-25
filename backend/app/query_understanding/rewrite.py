"""多轮改写与 query 拆分 — query_understanding 组"""

from __future__ import annotations

from typing import Any

from app.workflow.state import HistoryMessage


def rewrite_query(
    question: str,
    history: list[HistoryMessage],
    session_context: dict[str, Any],
) -> str:
    """
    多轮指代消解改写。

    TODO(query_understanding):
        - LLM 结合 history + session_context 改写
        - 处理"它/这个/上面说的"等指代

    当前桩：若 history 非空，拼接上一轮用户问题前缀。
    """
    if not history:
        return question

    last_user = ""
    for msg in reversed(history):
        if msg["role"] == "user":
            last_user = msg["content"]
            break

    if last_user and len(question) < 20:
        return f"{last_user}；补充问：{question}"
    return question


def decompose_query(question: str) -> list[str]:
    """
    复杂问题拆分为多个子查询。

    TODO(query_understanding): LLM 拆分

    当前桩：按中文问号分割。
    """
    parts = question.replace("?", "？").split("？")
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [question]
