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
from app.retrieval.pipeline import fetch_parent_chunks_by_ids
from app.workflow.graph import run_rag_pipeline
from app.workflow.llm_client import generate_answer_stream, stream_text
from app.workflow.nodes.answer import _build_direct_parent_citations, _format_faq_direct_answer
from app.workflow.nodes.preprocess import preprocess_node
from app.workflow.nodes.query_route import query_route_node
from app.workflow.nodes.rule_match import rule_match_node
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


def _is_faq_direct_state(state: AgentState) -> bool:
    return (
        state.get("query_intent") == "direct_parent_chunk"
        and bool((state.get("faq_match") or {}).get("matched"))
    )


def _stream_answer_tokens(state: AgentState) -> tuple[list[str], float]:
    answer = state.get("answer", "")
    return list(stream_text(answer)), STREAM_TOKEN_DELAY_SECONDS


def _build_faq_stream_state(initial_state: AgentState) -> AgentState | None:
    state = preprocess_node(initial_state)
    state = rule_match_node(state)
    state = query_route_node(state)
    if not _is_faq_direct_state(state):
        return None

    faq_match = state.get("faq_match") or {}
    sources = fetch_parent_chunks_by_ids(faq_match.get("target_parent_chunk_ids", []))
    if not sources:
        return {
            **state,
            "sources": [],
            "answer": "",
            "citations": [],
            "debug_trace": [*list(state.get("debug_trace", [])), "answer:insufficient"],
        }
    return {
        **state,
        "sources": sources,
        "citations": _build_direct_parent_citations(sources, limit=3),
        "debug_trace": [*list(state.get("debug_trace", [])), "answer:faq_direct_stream"],
    }


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
    initial_state = _build_initial_state(body)
    faq_stream_state = _build_faq_stream_state(initial_state)

    if faq_stream_state is not None:
        async def faq_event_generator() -> AsyncGenerator[str, None]:
            sources = list(faq_stream_state.get("sources") or [])
            full_answer = ""
            if sources:
                try:
                    for token in generate_answer_stream(
                        question=faq_stream_state.get("question", ""),
                        history=faq_stream_state.get("history", []),
                        sources=sources,
                    ):
                        full_answer += token
                        payload = json.dumps({"type": "token", "content": token}, ensure_ascii=False)
                        yield f"data: {payload}\n\n"
                        await asyncio.sleep(0)
                except Exception:
                    full_answer = _format_faq_direct_answer(
                        sources,
                        faq_stream_state.get("faq_match"),
                    )
                    for token in stream_text(full_answer):
                        payload = json.dumps({"type": "token", "content": token}, ensure_ascii=False)
                        yield f"data: {payload}\n\n"
                        await asyncio.sleep(STREAM_TOKEN_DELAY_SECONDS)

            final_state = {
                **faq_stream_state,
                "answer": full_answer,
            }
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
                    "answer": full_answer,
                },
                ensure_ascii=False,
            )
            yield f"data: {done_payload}\n\n"
            asyncio.create_task(asyncio.to_thread(_persist_completed_turn, final_state))

        return StreamingResponse(
            faq_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    final_state = run_rag_pipeline(initial_state)

    async def event_generator() -> AsyncGenerator[str, None]:
        answer = final_state.get("answer", "")
        tokens, delay_seconds = _stream_answer_tokens(final_state)
        for token in tokens:
            payload = json.dumps({"type": "token", "content": token}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

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
