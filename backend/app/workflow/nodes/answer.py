"""LangGraph 节点 — answer"""

from __future__ import annotations

from app.core.config import get_settings
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


def _build_citations(sources: list[SourceChunk], limit: int = 5) -> list[Citation]:
    settings = get_settings()
    threshold = settings.rerank_display_threshold
    citations: list[Citation] = []
    seen_parent_ids: set[str] = set()

    for source in sources:
        parent_id = source["parent_chunk_id"]
        if parent_id in seen_parent_ids:
            continue
        seen_parent_ids.add(parent_id)

        rerank_score = source.get("score_rerank")
        score = _score(source)
        if rerank_score is not None and float(rerank_score) < threshold:
            continue

        child_texts, child_offsets = _child_texts_and_offsets(source)
        citations.append(
            {
                "parent_chunk_id": parent_id,
                "doc_id": source["doc_id"],
                "file_id": source["doc_id"],
                "file_name": _display_name(source),
                "passage_text": source["content"],
                "child_text": child_texts[0] if child_texts else "",
                "child_texts": child_texts,
                "child_offsets": child_offsets,
                "snippet": source["content"][:120],
                "relevance_score": score,
                "rerank_score": float(rerank_score) if rerank_score is not None else None,
            }
        )
        if len(citations) >= limit:
            break

    return citations


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
