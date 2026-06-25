"""Conversation history persistence.

The workflow still receives plain AgentState.history messages. Storage details
stay at the API/core boundary so LangGraph nodes remain database-agnostic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.database import get_db_session
from app.core.models import ChatConversationRecord
from app.workflow.state import Citation, HistoryMessage


def load_recent_history(session_id: str, limit: int) -> list[HistoryMessage]:
    """
    Load the latest N completed chat turns and expand them into user/assistant messages.

    Only question/answer are used as LLM context. query_intent/citations/debug_trace
    are stored for analysis and deliberately excluded from AgentState.history.
    """
    if limit <= 0:
        return []

    with get_db_session() as db:
        records = list(
            db.scalars(
                select(ChatConversationRecord)
                .where(ChatConversationRecord.session_id == session_id)
                .order_by(
                    ChatConversationRecord.created_at.desc(),
                    ChatConversationRecord.id.desc(),
                )
                .limit(limit)
            )
        )

    history: list[HistoryMessage] = []
    for record in reversed(records):
        history.append({"role": "user", "content": record.question})
        history.append({"role": "assistant", "content": record.answer})
    return history


def save_chat_turn(
    *,
    session_id: str,
    question: str,
    answer: str,
    query_intent: str | None,
    citations: list[Citation],
    debug_trace: list[str],
) -> None:
    """Persist one completed Q&A turn in a single row."""
    record = ChatConversationRecord(
        session_id=session_id,
        question=question,
        answer=answer,
        query_intent=query_intent,
        citations=_jsonable(citations),
        debug_trace=list(debug_trace),
    )
    with get_db_session() as db:
        db.add(record)


def _jsonable(value: Any) -> Any:
    """Return JSON-column friendly plain containers."""
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
