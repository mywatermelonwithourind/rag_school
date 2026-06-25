"""
LLM 客户端 — 百炼 deepseek 直连（可 mock）

TODO(workflow): 实现真实 HTTP 调用与流式 token 输出供 SSE 使用
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.workflow.state import HistoryMessage, SourceChunk


def generate_answer(
    question: str,
    history: list[HistoryMessage],
    sources: list[SourceChunk],
    insufficient: bool = False,
) -> str:
    """
    基于检索材料生成答案。

    Args:
        question: 用户问题
        history: 对话历史
        sources: 检索到的父块
        insufficient: 是否材料不足（由调用方处理兜底时可忽略）

    Returns:
        生成的回答文本
    """
    settings = get_settings()

    if settings.llm_mock:
        ctx = "\n".join(s["content"][:80] for s in sources[:3])
        return (
            f"[MOCK LLM 回答] 关于「{question}」：\n"
            f"根据知识库材料（{len(sources)} 条），"
            f"简要说明如下…\n"
            f"参考片段：{ctx or '无'}"
        )

    # TODO(workflow): 真实 API 调用
    # import httpx
    # messages = _build_messages(question, history, sources)
    # response = httpx.post(...)
    raise NotImplementedError("真实 LLM 调用待 workflow 组实现")


def generate_answer_stream(
    question: str,
    history: list[HistoryMessage],
    sources: list[SourceChunk],
):
    """
    流式生成（SSE 用）。

    Yields:
        token 字符串
    """
    full = generate_answer(question, history, sources)
    for i, char in enumerate(full):
        yield char
