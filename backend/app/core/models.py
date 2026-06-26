"""ORM models for application-owned MySQL tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ParentChunkRecord(Base):
    """Knowledge-base parent chunk stored in MySQL for display and FAQ direct answers."""

    __tablename__ = "parent_chunk"

    parent_chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kb_id: Mapped[str] = mapped_column(String(64), nullable=False, default="kb_cs_college")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


class ChatConversationRecord(Base):
    """One stored chat turn: user question and assistant answer in the same row."""

    __tablename__ = "chat_conversation"
    __table_args__ = (
        Index("idx_chat_conversation_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    query_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    debug_trace: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
