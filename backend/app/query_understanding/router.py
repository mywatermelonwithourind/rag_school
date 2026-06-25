"""查询路由分类 — query_understanding 组"""

from __future__ import annotations

from typing import Any

from app.workflow.state import HistoryMessage, QueryIntent

# LLM 路由 prompt 约束（成员 C 实现 classify_intent 时必须遵守）
ROUTING_PROMPT_CONSTRAINTS = """
路由分类约束（成员 C — query_understanding）:

1. direct_answer 判定必须保守：仅当明确为寒暄、致谢、告别、与学院事务完全无关的闲聊时方可使用。
2. 拿不准时一律归为 rewrite（走检索），禁止将可能需查文档的业务问题误判为 direct_answer，避免 LLM 无材料编造。
3. 含学籍、课程、学分、办公时间、手续等学院相关关键词或隐含咨询意图的，必须 rewrite 或 decompose。
4. direct_parent_chunk 仅由 FAQ 规则命中（rule_match）触发，不由本分类器直接输出。
5. decompose 仅用于同一轮内明确包含多个独立子问题的复杂问句。
"""


def classify_intent(
    question: str,
    history: list[HistoryMessage],
    session_context: dict[str, Any],
) -> QueryIntent:
    """
    路由分类：决定 query_route 后的条件分流（executor 路径 or 直答 answer）。

    TODO(query_understanding/C):
        - 用 LLM few-shot 分类，system prompt 必须包含 ROUTING_PROMPT_CONSTRAINTS
        - direct_answer 保守：拿不准优先 rewrite，防止该查文档的问题误走 direct_answer 导致 LLM 编造
        - 或规则 + 关键词（寒暄 → direct_answer，含"和""以及" → decompose）

    Args:
        question: 清洗后问题
        history: 对话历史
        session_context: 会话上下文

    Returns:
        QueryIntent（不含 direct_parent_chunk，该意图由 FAQ 短路设定）
    """
    q = question.strip()

    # 寒暄 / 致谢 / 告别 → direct_answer（严格短句）
    greetings = ("你好", "您好", "hi", "hello", "谢谢", "再见")
    if any(g in q.lower() for g in greetings) and len(q) < 10:
        return "direct_answer"

    # 复杂多问 → decompose（简单规则占位）
    if "？" in q and "以及" in q:
        return "decompose"
    if q.count("?") + q.count("？") > 1:
        return "decompose"

    # 默认 rewrite（保守：宁可检索也不 direct_answer）
    return "rewrite"
