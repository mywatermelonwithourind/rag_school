"""LangGraph 节点 — answer"""

from __future__ import annotations

from app.retrieval.pipeline import fetch_parent_chunks_by_ids
from app.workflow.llm_client import generate_answer
from app.workflow.state import AgentState, Citation


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
    TODO(workflow/D): 完善 prompt、FAQ template 模式、出处格式化
    TODO(workflow/D): 材料不足兜底仅依据 retrieval_sufficient，勿重复实现 B 的阈值逻辑
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
            content = sources[0]["content"]
            citations: list[Citation] = [
                {
                    "parent_chunk_id": s["parent_chunk_id"],
                    "doc_id": s["doc_id"],
                    "snippet": s["content"][:120],
                    "relevance_score": s.get("score_rerank") or s.get("score_hybrid", 0.0),
                }
                for s in sources[:3]
            ]
            trace = list(state.get("debug_trace", []))
            trace.append("answer:faq_direct")
            return {
                **state,
                "answer": content,
                "citations": citations,
                "debug_trace": trace,
            }

    # 无需检索的直接回答
    if intent == "direct_answer":
        answer = generate_answer(
            question=state.get("question", ""),
            history=state.get("history", []),
            sources=[],
            insufficient=False,
        )
        trace = list(state.get("debug_trace", []))
        trace.append("answer:direct")
        return {
            **state,
            "answer": answer,
            "citations": [],
            "debug_trace": trace,
        }

    # 材料不足兜底（trust retrieval_sufficient from B）
    if not sufficient or not sources:
        fallback = (
            "抱歉，我在知识库中没有找到与您问题足够相关的材料。"
            "建议您换个说法或联系学院教务办公室获取准确信息。"
        )
        trace = list(state.get("debug_trace", []))
        trace.append("answer:insufficient")
        return {
            **state,
            "answer": fallback,
            "citations": [],
            "debug_trace": trace,
        }

    answer = generate_answer(
        question=state.get("question", ""),
        history=state.get("history", []),
        sources=sources,
        insufficient=False,
    )

    citations = [
        {
            "parent_chunk_id": s["parent_chunk_id"],
            "doc_id": s["doc_id"],
            "snippet": s["content"][:120],
            "relevance_score": s.get("score_rerank") or s.get("score_hybrid", 0.0),
        }
        for s in sources[:5]
    ]

    trace = list(state.get("debug_trace", []))
    trace.append("answer:generated")

    return {
        **state,
        "answer": answer,
        "citations": citations,
        "debug_trace": trace,
    }
