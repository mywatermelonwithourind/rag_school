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


class IngestRequest(BaseModel):
    dir_path: str | None = Field(
        default=None,
        description="Relative path under backend/data, or null for backend/data/raw",
    )
    kb_id: str = Field(default="kb_cs_college", min_length=1, max_length=64)
    write_vectors: bool = True
    fail_on_vector_error: bool = False


class IngestResponse(BaseModel):
    docs: int
    skipped_docs: list[str] = Field(default_factory=list)
    parents: int
    children: int
    parent_upserts: int
    vector_upserts: int
    source_dir: str
    warnings: list[str] = Field(default_factory=list)


class KbDocumentSchema(BaseModel):
    doc_id: str
    kb_id: str
    title: str
    source_name: str
    file_ext: str
    source_type: str
    content_chars: int
    parent_count: int
    child_count: int
    vector_count: int
    status: str
    warnings: list[str] = Field(default_factory=list)
    updated_at: str


class KbDocumentListResponse(BaseModel):
    total: int
    items: list[KbDocumentSchema] = Field(default_factory=list)
