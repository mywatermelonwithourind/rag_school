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
    rewrite 分支的轻量查询改写。

    TODO(query_understanding):
        - LLM 结合当前工作问题与 session_context 改写检索 query

    历史指代消解统一由 preprocess.resolve_followup 负责，本函数不再读取 history
    拼接上一轮问题，避免二次消解污染检索 query。
    """
    del history, session_context
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
