"""LangGraph 节点 — answer"""

from __future__ import annotations

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


def _build_citations(sources: list[SourceChunk], limit: int = 5) -> list[Citation]:
    return [
        {
            "parent_chunk_id": source["parent_chunk_id"],
            "doc_id": source["doc_id"],
            "snippet": source["content"][:120],
            "relevance_score": _score(source),
        }
        for source in sources[:limit]
    ]


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
