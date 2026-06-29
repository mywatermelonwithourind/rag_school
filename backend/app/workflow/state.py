"""
AgentState — LangGraph 全局状态契约（五人协作总纲）

每个字段标注：
  - 类型
  - 含义
  - 写入节点（writer）
  - 读取节点（readers）

成员分工对应：
  - query_understanding: query_intent, retrieval_plan, retrieval_queries, session_context
  - retrieval: sources, retrieval_plan (read)
  - workflow/answer: answer, citations
  - api: question, history (入口注入)
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

# ---------------------------------------------------------------------------
# 子类型定义
# ---------------------------------------------------------------------------

QueryIntent = Literal[
    "rewrite",           # 多轮指代消解后检索
    "decompose",         # 复杂问题拆分子查询
    "direct_answer",     # 无需检索，直接回答（寒暄/超范围）
    "direct_parent_chunk",  # FAQ 命中，直接返回父块
]

AnswerMode = Literal["llm_generate", "template", "parent_chunk_direct"]

RetrievalPlan = TypedDict(
    "RetrievalPlan",
    {
        "top_k_vector": int,       # Milvus 子块召回数
        "top_k_parent": int,       # 父块聚合后保留数
        "top_k_rerank": int,       # 精排后保留数
        "use_hybrid": bool,        # 是否启用混合粗排
        "use_rerank": bool,        # 是否启用 qwen3-rerank
        "min_score_threshold": float,  # 材料不足阈值
    },
)

HistoryMessage = TypedDict(
    "HistoryMessage",
    {
        "role": Literal["user", "assistant"],
        "content": str,
    },
)

SourceChunk = TypedDict(
    "SourceChunk",
    {
        "parent_chunk_id": str,
        "child_chunk_id": str | None,
        "content": str,
        "doc_id": str,
        "kb_id": str,
        "score_vector": float,
        "score_lexical": float,
        "score_hybrid": float,
        "score_rerank": float | None,
        "metadata": dict[str, Any],
    },
)

Citation = TypedDict(
    "Citation",
    {
        "parent_chunk_id": str,
        "doc_id": str,
        "file_id": str,
        "file_name": str,
        "passage_text": str,
        "child_text": str,
        "child_texts": list[str],
        "child_offsets": list[list[int]],
        "snippet": str,
        "relevance_score": float,
        "rerank_score": float | None,
    },
)

FAQMatchResult = TypedDict(
    "FAQMatchResult",
    {
        "matched": bool,
        "faq_id": str | None,
        "standard_question": str | None,
        "target_parent_chunk_ids": list[str],
        "answer_mode": AnswerMode,
        "confidence": float,
    },
)


class AgentState(TypedDict, total=False):
    """
    LangGraph 主图共享状态。

    流转概览::
        preprocess → rule_match → query_route
            ├─ direct_parent_chunk / direct_answer → answer
            └─ rewrite / decompose → executor → retrieval → answer

    单域设计：不含 kb_id / user_id。未来多知识库扩展见 README，不在本阶段代码中预留字段。
    """

    # ----- 入口字段（api 层写入） -----
    question: str
    """用户当前轮原始问题。writer: api | readers: 全部节点"""

    raw_question: str
    """preprocess 锁定的用户原始问题。writer: preprocess | readers: audit/debug"""

    history: list[HistoryMessage]
    """多轮对话历史（不含当前 question）。writer: api | readers: preprocess, executor, answer"""

    session_id: str
    """会话 ID，用于日志与上下文隔离。writer: api | readers: 全部节点"""

    # ----- 预处理 -----
    session_context: dict[str, Any]
    """
    会话级上下文（如上一轮检索主题、用户身份占位等）。
    writer: preprocess
    readers: query_route, executor, answer
    """

    normalized_question: str
    """清洗后的问题（去空白、全半角等）。writer: preprocess | readers: rule_match, query_route"""

    # ----- FAQ 规则匹配（query_understanding） -----
    faq_match: FAQMatchResult
    """FAQ 规则匹配结果。writer: rule_match | readers: query_route, executor, answer"""

    faq_short_circuit: bool
    """True 表示 FAQ 命中且可跳过检索。writer: rule_match | readers: graph 条件边"""

    # ----- 查询理解与路由（query_understanding） -----
    query_intent: QueryIntent
    """
    路由分类结果，决定 executor 分支。
    writer: query_route
    readers: executor, retrieval, answer
    """

    retrieval_plan: RetrievalPlan
    """
    检索策略参数（top_k、阈值等）。
    writer: query_route
    readers: retrieval, answer
    """

    retrieval_queries: list[str]
    """
    实际送入检索的 query 列表（改写/拆分后可能多条）。
    writer: executor
    readers: retrieval
    """

    # ----- 检索结果（retrieval） -----
    sources: list[SourceChunk]
    """
    召回并排好序的父块/子块列表。
    writer: retrieval
    readers: answer
    """

    retrieval_sufficient: bool
    """
    检索材料是否充足（判定标准由 retrieval/B 在 is_retrieval_sufficient 定义）。
    writer: retrieval
    readers: answer（D 兜底时只读，勿重复实现阈值）
    """

    # ----- 生成结果（workflow/answer） -----
    answer: str
    """最终回答文本。writer: answer | readers: api(SSE 输出)"""

    citations: list[Citation]
    """出处引用列表。writer: answer | readers: api(SSE 输出)"""

    # ----- 控制流 / 调试 -----
    error: str | None
    """非致命错误信息。writer: 任意节点 | readers: answer, api"""

    debug_trace: list[str]
    """节点执行轨迹，便于联调。writer: 各节点 append | readers: api(可选返回)"""
