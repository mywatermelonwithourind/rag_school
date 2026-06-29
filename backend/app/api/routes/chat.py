"""聊天接口 — SSE 流式 + 同步 — api 组"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ChatResponse, ChatSessionDetail, ChatSessionSummary, CitationSchema
from app.core.chat_history import (
    list_recent_sessions,
    load_recent_history,
    load_session_detail,
    save_chat_turn,
)
from app.core.utils import new_session_id
from app.workflow.graph import run_rag_pipeline
from app.workflow.llm_client import stream_text
from app.workflow.state import AgentState

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

HISTORY_TURN_LIMIT = 2
STREAM_TOKEN_DELAY_SECONDS = 0.012


def _build_initial_state(body: ChatRequest) -> AgentState:
    session_id = body.session_id or new_session_id()
    history = []
    trace = []
    if body.session_id:
        try:
            history = load_recent_history(session_id, limit=HISTORY_TURN_LIMIT)
            trace.append(f"history_loaded:messages={len(history)}")
        except Exception:
            logger.exception("Failed to load chat history")
            trace.append("history_load_failed")

    return {
        "question": body.question,
        "history": history,
        "session_id": session_id,
        "debug_trace": trace,
    }


def _persist_completed_turn(state: AgentState) -> None:
    """Best-effort archive; failures must not affect the user-facing answer."""
    try:
        save_chat_turn(
            session_id=state.get("session_id", ""),
            question=state.get("question", ""),
            answer=state.get("answer", ""),
            query_intent=state.get("query_intent"),
            citations=state.get("citations", []),
            debug_trace=state.get("debug_trace", []),
        )
    except Exception:
        logger.exception("Failed to persist chat turn")


@router.get("/sessions", response_model=list[ChatSessionSummary])
async def chat_sessions(limit: int = 30):
    """List recent persisted chat sessions for the sidebar."""
    safe_limit = max(1, min(limit, 100))
    return [ChatSessionSummary(**session) for session in list_recent_sessions(limit=safe_limit)]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def chat_session_detail(session_id: str):
    """Load one persisted chat session with expanded messages."""
    session = load_session_detail(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return ChatSessionDetail(**session)


@router.post("", response_model=ChatResponse)
async def chat_sync(body: ChatRequest):
    """同步问答（调试用）。"""
    state = run_rag_pipeline(_build_initial_state(body))
    _persist_completed_turn(state)
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
    final_state = run_rag_pipeline(_build_initial_state(body))

    async def event_generator() -> AsyncGenerator[str, None]:
        answer = final_state.get("answer", "")
        for token in stream_text(answer):
            payload = json.dumps({"type": "token", "content": token}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            await asyncio.sleep(STREAM_TOKEN_DELAY_SECONDS)

        citations_payload = json.dumps(
            {"type": "citations", "content": final_state.get("citations", [])},
            ensure_ascii=False,
        )
        yield f"data: {citations_payload}\n\n"

        done_payload = json.dumps(
            {
                "type": "done",
                "session_id": final_state.get("session_id", ""),
                "debug_trace": final_state.get("debug_trace", []),
                "answer": answer,
            },
            ensure_ascii=False,
        )
        yield f"data: {done_payload}\n\n"

        # Only archive after the complete SSE stream reaches done.
        # If the client disconnects earlier, the generator is cancelled and this turn is not stored.
        asyncio.create_task(asyncio.to_thread(_persist_completed_turn, final_state))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
