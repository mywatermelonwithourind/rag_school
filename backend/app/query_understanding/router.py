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

    当前实现：规则优先，LLM 路由后续作为可选增强接入。
    direct_answer 必须保守，拿不准一律 rewrite，避免业务问题无材料直答。

    Args:
        question: 清洗后问题
        history: 对话历史
        session_context: 会话上下文

    Returns:
        QueryIntent（不含 direct_parent_chunk，该意图由 FAQ 短路设定）
    """
    del history, session_context  # 预留给后续 LLM 路由增强。

    q = question.strip()
    compact = "".join(ch for ch in q if not ch.isspace())
    lowered = compact.lower().strip("。！？!?,，~～.；;：:")

    # 寒暄 / 致谢 / 告别 → direct_answer（严格短句，避免业务问题误直答）
    direct_answer_phrases = {
        "你好",
        "您好",
        "hi",
        "hello",
        "谢谢",
        "谢谢你",
        "多谢",
        "再见",
        "拜拜",
        "好的",
        "好",
        "收到",
    }
    if lowered in direct_answer_phrases:
        return "direct_answer"

    # 同轮多个独立问题 → decompose。仅对明确多问触发，普通“和/以及”不贸然拆。
    question_mark_count = q.count("?") + q.count("？")
    if question_mark_count > 1:
        return "decompose"
    if question_mark_count >= 1 and any(
        marker in q for marker in ("以及", "并且", "分别", "同时", "另外")
    ):
        return "decompose"
    if any(marker in q for marker in ("分别介绍", "分别说明", "对比", "区别")):
        return "decompose"

    # 默认 rewrite（保守：宁可检索也不 direct_answer）
    return "rewrite"
