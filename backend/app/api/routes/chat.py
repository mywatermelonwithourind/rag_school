"""聊天接口 — SSE 流式 + 同步 — api 组"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ChatResponse, CitationSchema
from app.core.utils import new_session_id
from app.workflow.graph import run_rag_pipeline
from app.workflow.llm_client import stream_text
from app.workflow.state import AgentState, HistoryMessage

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_initial_state(body: ChatRequest) -> AgentState:
    history: list[HistoryMessage] = [
        {"role": m.role, "content": m.content} for m in body.history
    ]
    return {
        "question": body.question,
        "history": history,
        "session_id": body.session_id or new_session_id(),
        "debug_trace": [],
    }


@router.post("", response_model=ChatResponse)
async def chat_sync(body: ChatRequest):
    """同步问答（调试用）。"""
    state = run_rag_pipeline(_build_initial_state(body))
    return ChatResponse(
        answer=state.get("answer", ""),
        citations=[
            CitationSchema(**c) for c in state.get("citations", [])
        ],
        session_id=state.get("session_id", ""),
        debug_trace=state.get("debug_trace", []),
    )


@router.post("/stream")
async def chat_stream(body: ChatRequest):
    """
    SSE 流式问答。

    事件格式::
        data: {"type":"token","content":"..."}
        data: {"type":"citations","content":[...]}
        data: {"type":"done","session_id":"..."}
    """
    initial = _build_initial_state(body)
    state = run_rag_pipeline(initial)

    async def event_generator() -> AsyncGenerator[str, None]:
        answer = state.get("answer", "")
        # 展示层流式：唯一答案来源是 answer 节点写入的 state["answer"]。
        # TODO(workflow/D + api/E): answer 节点接真 LLM 流式后，可从图执行层透传 token，
        # 但 done.answer 仍应以最终 state["answer"] 为权威值。
        for token in stream_text(answer):
            payload = json.dumps({"type": "token", "content": token}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

        citations = state.get("citations", [])
        if citations:
            cit_payload = json.dumps(
                {"type": "citations", "content": citations},
                ensure_ascii=False,
            )
            yield f"data: {cit_payload}\n\n"

        done_payload = json.dumps(
            {
                "type": "done",
                "session_id": state.get("session_id", ""),
                "debug_trace": state.get("debug_trace", []),
                "answer": answer,
            },
            ensure_ascii=False,
        )
        yield f"data: {done_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
