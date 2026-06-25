"""API 请求/响应模型 — api 组"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class CitationSchema(BaseModel):
    parent_chunk_id: str
    doc_id: str
    snippet: str
    relevance_score: float


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationSchema] = Field(default_factory=list)
    session_id: str
    debug_trace: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    mysql: bool
    milvus: bool = False
