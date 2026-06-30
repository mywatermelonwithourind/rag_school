"""LLM 客户端 — 百炼 deepseek 直连（可 mock）"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
from app.core.config import get_settings
from app.workflow.state import HistoryMessage, SourceChunk


def _format_history(history: list[HistoryMessage]) -> list[dict[str, str]]:
    return [
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]


def _format_sources(sources: list[SourceChunk]) -> str:
    if not sources:
        return "无检索材料。"

    blocks: list[str] = []
    for idx, source in enumerate(sources, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[材料 {idx}]",
                    f"parent_chunk_id: {source['parent_chunk_id']}",
                    f"doc_id: {source['doc_id']}",
                    f"content: {source['content']}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _build_messages(
    question: str,
    history: list[HistoryMessage],
    sources: list[SourceChunk],
) -> list[dict[str, str]]:
    if sources:
        system_prompt = (
            "你是集美大学计算机学院的智能问答助手,负责回答学院相关的专业问题"
            "(学籍、课程、学分、转专业、办事流程、规章制度等)。\n"
            "回答这类问题时,你必须严格遵守:\n\n"
            "只依据下方提供的知识库材料作答,不得使用材料之外的信息,不得用通用常识补充或脑补"
            "集美大学的具体规定。学院的真实规定只能来自材料,你的通用知识在这里不可靠。\n"
            "材料中有答案时:准确、完整地依据材料回答,涉及具体数字、条款、流程、时间、联系方式时"
            "原样引用不得改动,并指明出处(如\"根据《集美大学章程》第三十四条\")。回答要有条理,"
            "把材料里相关的点组织清楚,不要只丢一句。\n"
            "回答格式必须使用 Markdown: 先给一句简短结论,再用 `##` 小标题和 `-` 无序列表组织要点。"
            "不要把彼此独立的段落都写成 `1.`; 除非是同一个连续列表,否则不要使用有序编号。"
            "不要输出“材料开头”“材料一”等内部检索标记。\n"
            "材料中没有或不足以回答时:如实说明知识库中暂无相关规定,不要编造、不要用"
            "\"一般来说/通常\"等通用知识硬凑一个集美大学的答案。然后给出可行的下一步建议"
            "(查阅培养方案/学生手册、登录教务系统、联系学院教务办公室或辅导员)。\n"
            "不确定材料是否真的回答了问题时,宁可说\"材料中未明确\",也不要给一个看似合理但无依据的答案。"
        )
        user_prompt = (
            f"用户问题:{question}\n"
            "知识库材料:\n\n"
            f"{_format_sources(sources)}\n"
            "请依据上述材料回答。若材料中没有相关内容,如实说明并给出查询建议。"
            "输出时使用 Markdown 小标题和无序列表,不要重复使用 `1.` 开头。"
        )
    else:
        system_prompt = (
            "你是集美大学计算机学院的智能问答助手。当前用户的问题是日常对话、通用知识或与学院具体规定"
            "无关的问题(如闲聊、问候、通用编程/学习问题、常识等)。\n"
            "回答这类问题时:\n\n"
            "自由、灵活地运用你的知识正常回答,不需要依据知识库材料,把问题答好答透,自然友好。\n"
            "如果是通用知识/学习/编程类问题,可以给出有深度、有条理、对学生有帮助的回答"
            "(必要时举例、分点说明)。\n"
            "如果问题其实涉及集美大学的具体规定或事实(比如学分、流程、联系方式),不要凭通用知识编造"
            "集美大学的答案,而是说明这类信息需要查学院官方渠道,引导用户用学院相关的方式提问。\n"
            "保持简洁友好,符合面向学生的语气。"
        )
        user_prompt = f"用户问题:{question}\n请直接回答。"
    return [
        {"role": "system", "content": system_prompt},
        *_format_history(history),
        {"role": "user", "content": user_prompt},
    ]


def _mock_answer(question: str, sources: list[SourceChunk]) -> str:
    ctx = "\n".join(source["content"][:80] for source in sources[:3])
    return (
        f"[MOCK LLM 回答] 关于「{question}」：\n"
        f"根据知识库材料（{len(sources)} 条），简要说明如下。\n"
        f"参考片段：{ctx or '无'}"
    )


def _chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _request_payload(
    question: str,
    history: list[HistoryMessage],
    sources: list[SourceChunk],
    *,
    stream: bool,
) -> dict[str, Any]:
    settings = get_settings()
    return {
        "model": settings.llm_model,
        "messages": _build_messages(question, history, sources),
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "stream": stream,
    }


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.llm_api_key:
        raise RuntimeError("RAG_LLM_API_KEY 为空，无法调用真实 LLM；请设置 RAG_LLM_MOCK=true 或填入 API Key")

    return {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }


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
        return _mock_answer(question, sources)

    payload = _request_payload(question, history, sources, stream=False)
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            _chat_completions_url(settings.llm_base_url),
            headers=_auth_headers(),
            json=payload,
        )
        response.raise_for_status()

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM 响应缺少 choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("LLM 响应缺少 message.content")
    return content


def generate_answer_stream(
    question: str,
    history: list[HistoryMessage],
    sources: list[SourceChunk],
) -> Iterator[str]:
    """
    LLM 真流式生成接口。

    当前 API 层仍先执行图得到 state["answer"]，再展示层逐字推送。
    后续若 answer 节点改为端到端真流式，可复用本函数并将 token 从图执行层透传到 SSE。

    Yields:
        token 字符串
    """
    settings = get_settings()

    if settings.llm_mock:
        yield from stream_text(_mock_answer(question, sources))
        return

    payload = _request_payload(question, history, sources, stream=True)
    with httpx.Client(timeout=None) as client:
        with client.stream(
            "POST",
            _chat_completions_url(settings.llm_base_url),
            headers=_auth_headers(),
            json=payload,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue

                raw = line.removeprefix("data: ").strip()
                if raw == "[DONE]":
                    break

                payload = json.loads(raw)
                delta = (payload.get("choices") or [{}])[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content


def stream_text(text: str) -> Iterator[str]:
    """展示层流式：把已生成的最终答案按字符切成 SSE token。"""
    for char in text:
        yield char
