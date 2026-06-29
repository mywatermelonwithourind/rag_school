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


def list_recent_sessions(limit: int = 30, scan_limit: int = 500) -> list[dict[str, Any]]:
    """Return recent chat sessions summarized from stored turns."""
    if limit <= 0:
        return []

    with get_db_session() as db:
        records = list(
            db.scalars(
                select(ChatConversationRecord)
                .order_by(
                    ChatConversationRecord.created_at.desc(),
                    ChatConversationRecord.id.desc(),
                )
                .limit(scan_limit)
            )
        )

    grouped: dict[str, list[ChatConversationRecord]] = {}
    for record in records:
        grouped.setdefault(record.session_id, []).append(record)

    sessions = []
    for session_id, session_records in grouped.items():
        ordered = sorted(session_records, key=lambda item: (item.created_at, item.id))
        latest = max(session_records, key=lambda item: (item.created_at, item.id))
        title_source = ordered[0].question if ordered else session_id
        sessions.append(
            {
                "session_id": session_id,
                "title": _title_from_question(title_source),
                "updated_at": latest.created_at.isoformat(),
                "turn_count": len(session_records),
            }
        )

    sessions.sort(key=lambda item: item["updated_at"], reverse=True)
    return sessions[:limit]


def load_session_detail(session_id: str, limit: int = 100) -> dict[str, Any] | None:
    """Load a persisted session and expand turns into user/assistant messages."""
    if not session_id:
        return None

    with get_db_session() as db:
        records = list(
            db.scalars(
                select(ChatConversationRecord)
                .where(ChatConversationRecord.session_id == session_id)
                .order_by(
                    ChatConversationRecord.created_at.asc(),
                    ChatConversationRecord.id.asc(),
                )
                .limit(limit)
            )
        )

    if not records:
        return None

    messages: list[dict[str, Any]] = []
    for record in records:
        created_at = record.created_at.isoformat()
        messages.append(
            {
                "role": "user",
                "content": record.question,
                "citations": [],
                "created_at": created_at,
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": record.answer,
                "citations": _jsonable(record.citations or []),
                "created_at": created_at,
            }
        )

    latest = records[-1]
    return {
        "session_id": session_id,
        "title": _title_from_question(records[0].question),
        "updated_at": latest.created_at.isoformat(),
        "turn_count": len(records),
        "messages": messages,
    }


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


def _title_from_question(question: str) -> str:
    normalized = " ".join(question.strip().split())
    return f"{normalized[:22]}..." if len(normalized) > 22 else normalized
