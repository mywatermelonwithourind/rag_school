"""LangGraph 节点 — answer"""

from __future__ import annotations

from app.core.config import get_settings
from app.file_management.service import get_kb_file
from app.retrieval.pipeline import fetch_parent_chunks_by_ids
from app.workflow.llm_client import generate_answer
from app.workflow.state import AgentState, Citation, SourceChunk


_INSUFFICIENT_ANSWER = (
    "抱歉，我在知识库中没有找到与您问题足够相关的材料。"
    "建议您换个说法或联系学院教务办公室获取准确信息。"
)


def _append_trace(state: AgentState, marker: str) -> list[str]:
    trace = list(state.get("debug_trace", []))
    trace.append(marker)
    return trace


def _score(source: SourceChunk) -> float:
    return float(source.get("score_rerank") or source.get("score_hybrid", 0.0))


def _display_name(source: SourceChunk) -> str:
    metadata = source.get("metadata") or {}
    return str(
        metadata.get("title")
        or metadata.get("source_name")
        or metadata.get("source_path")
        or source["doc_id"]
    )


def _compact_with_offsets(text: str) -> tuple[str, list[int]]:
    compact_chars: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            continue
        compact_chars.append(char)
        offsets.append(index)
    return "".join(compact_chars), offsets


def _locate_child_text(passage_text: str, child_text: str) -> list[int] | None:
    if not passage_text or not child_text:
        return None

    exact_start = passage_text.find(child_text)
    if exact_start >= 0:
        return [exact_start, exact_start + len(child_text)]

    compact_passage, passage_offsets = _compact_with_offsets(passage_text)
    compact_child, _ = _compact_with_offsets(child_text)
    if not compact_passage or not compact_child:
        return None

    compact_start = compact_passage.find(compact_child)
    if compact_start < 0:
        return None

    compact_end = compact_start + len(compact_child) - 1
    return [passage_offsets[compact_start], passage_offsets[compact_end] + 1]


def _child_texts_and_offsets(source: SourceChunk) -> tuple[list[str], list[list[int]]]:
    passage_text = source["content"]
    child_hits = [
        hit
        for hit in (source.get("metadata") or {}).get("child_hits", [])
        if isinstance(hit, dict)
    ]
    child_texts: list[str] = []
    offsets: list[list[int]] = []
    seen_offsets: set[tuple[int, int]] = set()

    for hit in sorted(child_hits, key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True):
        child_text = str(hit.get("content") or "").strip()
        if not child_text:
            continue
        child_texts.append(child_text)
        located = _locate_child_text(passage_text, child_text)
        if located is None:
            continue
        offset_key = (located[0], located[1])
        if offset_key in seen_offsets:
            continue
        seen_offsets.add(offset_key)
        offsets.append(located)

    offsets.sort(key=lambda item: (item[0], item[1]))
    return child_texts, offsets


def _source_file_id(source: SourceChunk) -> str:
    return str(source.get("doc_id") or "")


def _source_score(source: SourceChunk) -> float:
    rerank_score = source.get("score_rerank")
    if rerank_score is not None:
        return float(rerank_score)
    return _score(source)


def _parent_offsets_from_file_detail(file_detail: dict) -> dict[str, int]:
    offsets: dict[str, int] = {}
    cursor = 0
    parents = file_detail.get("parents") or []
    for index, parent in enumerate(parents):
        if index > 0:
            cursor += 2  # get_kb_file 使用 "\n\n" 拼接父块。
        parent_id = str(parent.get("parent_chunk_id") or "")
        offsets[parent_id] = cursor
        cursor += len(str(parent.get("content") or ""))
    return offsets


def _build_citations(sources: list[SourceChunk], limit: int = 5) -> list[Citation]:
    settings = get_settings()
    threshold = settings.rerank_display_threshold
    sources_by_file: dict[str, list[SourceChunk]] = {}

    for source in sources:
        file_id = _source_file_id(source)
        if not file_id:
            continue
        sources_by_file.setdefault(file_id, []).append(source)

    citations: list[Citation] = []
    for file_id, file_sources in sources_by_file.items():
        file_score = max((_source_score(source) for source in file_sources), default=0.0)
        if file_score < threshold:
            continue

        try:
            file_detail = get_kb_file(file_id)
        except Exception:
            continue

        full_text = str(file_detail.get("full_text") or "")
        parent_starts = _parent_offsets_from_file_detail(file_detail)
        highlight_offsets: list[list[int]] = []
        child_texts: list[str] = []
        seen_offsets: set[tuple[int, int]] = set()

        for source in file_sources:
            if _source_score(source) < threshold:
                continue
            parent_start = parent_starts.get(source["parent_chunk_id"])
            if parent_start is None:
                continue
            source_child_texts, source_child_offsets = _child_texts_and_offsets(source)
            child_texts.extend(source_child_texts)
            for start, end in source_child_offsets:
                full_start = parent_start + start
                full_end = parent_start + end
                if full_start < 0 or full_end > len(full_text) or full_start >= full_end:
                    continue
                offset_key = (full_start, full_end)
                if offset_key in seen_offsets:
                    continue
                seen_offsets.add(offset_key)
                highlight_offsets.append([full_start, full_end])

        highlight_offsets.sort(key=lambda item: (item[0], item[1]))
        first_source = max(file_sources, key=_source_score)
        first_parent_id = first_source["parent_chunk_id"]
        citations.append(
            {
                "parent_chunk_id": first_parent_id,
                "doc_id": file_id,
                "file_id": file_id,
                "file_name": _display_name(first_source),
                "full_text": full_text,
                "highlight_offsets": highlight_offsets,
                "reconstruction_notice": str(file_detail.get("reconstruction_notice") or ""),
                "passage_text": full_text,
                "child_text": child_texts[0] if child_texts else "",
                "child_texts": child_texts,
                "child_offsets": highlight_offsets,
                "snippet": full_text[:120],
                "relevance_score": file_score,
                "rerank_score": file_score,
            }
        )

    citations.sort(key=lambda item: float(item.get("rerank_score") or 0.0), reverse=True)
    return citations[:limit]


def answer_node(state: AgentState) -> AgentState:
    """
    答案生成节点：基于 sources 生成回答 + citations；材料不足时兜底。

    输入（读取）:
        - question, history
        - sources, retrieval_sufficient（sufficient 由 retrieval/B 写入，本节点只读）
        - query_intent, faq_match

    输出（写入）:
        - answer: str
        - citations: list[Citation]
        - debug_trace: 追加 "answer"

    负责成员: workflow 组（D）
    TODO(workflow/D): 后续真流式时，将 LLM token 事件从本节点/图执行层透传给 API。
    TODO(workflow/D): 材料不足兜底仅依据 retrieval_sufficient，勿重复实现 B 的阈值逻辑。
    """
    intent = state.get("query_intent", "rewrite")
    sources = list(state.get("sources") or [])
    sufficient = state.get("retrieval_sufficient", False)
    faq_match = state.get("faq_match")

    # FAQ 直出父块（跳过 retrieval 路径，此处按 faq_match 拉父块）
    if intent == "direct_parent_chunk" and faq_match and faq_match.get("matched"):
        if not sources:
            sources = fetch_parent_chunks_by_ids(
                faq_match.get("target_parent_chunk_ids", [])
            )
        if sources:
            return {
                **state,
                "sources": sources,
                "answer": sources[0]["content"],
                "citations": _build_citations(sources, limit=3),
                "debug_trace": _append_trace(state, "answer:faq_direct"),
            }

        return {
            **state,
            "answer": _INSUFFICIENT_ANSWER,
            "citations": [],
            "debug_trace": _append_trace(state, "answer:insufficient"),
        }

    # 无需检索的直接回答
    if intent == "direct_answer":
        answer = generate_answer(
            question=state.get("question", ""),
            history=state.get("history", []),
            sources=[],
            insufficient=False,
        )
        return {
            **state,
            "answer": answer,
            "citations": [],
            "debug_trace": _append_trace(state, "answer:direct"),
        }

    # 材料不足兜底（trust retrieval_sufficient from B）
    if not sufficient or not sources:
        return {
            **state,
            "answer": _INSUFFICIENT_ANSWER,
            "citations": [],
            "debug_trace": _append_trace(state, "answer:insufficient"),
        }

    answer = generate_answer(
        question=state.get("question", ""),
        history=state.get("history", []),
        sources=sources,
        insufficient=False,
    )

    return {
        **state,
        "answer": answer,
        "citations": _build_citations(sources, limit=5),
        "debug_trace": _append_trace(state, "answer:rag"),
    }
