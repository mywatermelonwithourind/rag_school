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


COLLEGE_GUARD_TERMS = (
    "学院",
    "计算机",
    "学分",
    "课程",
    "课",
    "学籍",
    "选课",
    "转专业",
    "毕业",
    "办公",
    "办公室",
    "辅导员",
    "教务",
    "集美",
    "院长",
    "老师",
    "导师",
    "手续",
    "报名",
    "考试",
    "成绩",
    "奖学金",
    "助学金",
    "宿舍",
    "地址",
    "电话",
    "时间",
    "材料",
    "证明",
    "流程",
    "要求",
    "规定",
    "实习",
    "实验室",
)


DIRECT_ANSWER_PHRASES = {
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
    "你叫什么名字",
    "你是谁",
    "你是什么",
    "你能做什么",
    "你会什么",
    "讲个笑话",
    "讲一个笑话",
    "再讲一个笑话",
    "再讲个笑话",
    "再来一个笑话",
    "再来个笑话",
    "继续讲笑话",
    "讲个故事",
    "讲一个故事",
    "再讲一个故事",
    "再讲个故事",
    "再来一个故事",
    "再来个故事",
    "继续讲故事",
    "好无聊",
    "陪我聊天",
    "聊聊天",
    "今天天气不错",
    "今天天气真好",
    "今天天气很好",
    "天气真好",
    "天气不错",
    "今天好热",
    "今天好冷",
    "今天真热",
    "今天真冷",
}

DIRECT_ANSWER_PREFIXES = (
    "今天天气",
)


CHAT_FOLLOWUP_PREFIXES = (
    "再讲",
    "再来",
    "继续讲",
)

CHAT_FOLLOWUP_TOPICS = (
    "笑话",
    "故事",
)


GENERAL_TECH_TERMS = (
    "mysql",
    "数据库",
    "sql",
    "python",
    "java",
    "javascript",
    "js",
    "typescript",
    "ts",
    "递归",
    "算法",
    "数据结构",
    "链表",
    "二叉树",
    "树",
    "栈",
    "队列",
    "哈希",
    "哈希表",
    "操作系统",
    "网络",
    "计算机网络",
    "编译",
    "编译原理",
    "ai",
    "人工智能",
    "机器学习",
    "深度学习",
    "神经网络",
    "大模型",
    "llm",
    "rag",
    "向量数据库",
    "向量检索",
    "embedding",
    "api",
    "接口",
    "前端",
    "后端",
    "linux",
    "git",
    "docker",
    "redis",
    "http",
    "tcp",
    "ip",
)

GENERAL_EXPLANATION_TERMS = (
    "递归",
    "二叉树",
    "算法",
    "数据库",
    "人工智能",
    "机器学习",
    "操作系统",
    "计算机网络",
)


def _has_college_guard_term(text: str) -> bool:
    return any(term in text for term in COLLEGE_GUARD_TERMS)


def _is_direct_answer_chat(text: str) -> bool:
    if text in DIRECT_ANSWER_PHRASES:
        return True
    if any(text.startswith(prefix) for prefix in CHAT_FOLLOWUP_PREFIXES) and any(topic in text for topic in CHAT_FOLLOWUP_TOPICS):
        return True
    return any(text.startswith(prefix) and len(text) <= len(prefix) + 6 for prefix in DIRECT_ANSWER_PREFIXES)


def _contains_general_tech_term(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in GENERAL_TECH_TERMS)


def _is_general_knowledge_question(text: str) -> bool:
    lowered = text.lower()
    if not _contains_general_tech_term(lowered):
        return False

    if lowered in {term.lower() for term in GENERAL_EXPLANATION_TERMS}:
        return True
    if lowered.endswith("是什么") and _contains_general_tech_term(lowered.removesuffix("是什么")):
        return True
    if lowered.startswith("什么是") and _contains_general_tech_term(lowered.removeprefix("什么是")):
        return True
    if lowered.startswith("怎么学") and _contains_general_tech_term(lowered.removeprefix("怎么学")):
        return True
    if lowered.startswith("如何学") and _contains_general_tech_term(lowered.removeprefix("如何学")):
        return True
    if lowered.endswith("怎么学") and _contains_general_tech_term(lowered.removesuffix("怎么学")):
        return True
    if lowered.endswith("怎么用") and _contains_general_tech_term(lowered.removesuffix("怎么用")):
        return True
    if lowered.endswith("如何使用") and _contains_general_tech_term(lowered.removesuffix("如何使用")):
        return True
    return False


def _is_decompose_question(question: str) -> bool:
    question_mark_count = question.count("?") + question.count("？")
    if question_mark_count > 1:
        return True
    if question_mark_count >= 1 and any(
        marker in question for marker in ("以及", "并且", "分别", "同时", "另外")
    ):
        return True
    return any(marker in question for marker in ("分别介绍", "分别说明", "对比", "区别"))


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

    # 学院关键词否决前置：只要像学院事务，禁止走闲聊直答。
    if _has_college_guard_term(q):
        if _is_decompose_question(q):
            return "decompose"
        return "rewrite"

    # 寒暄 / 致谢 / 告别 / 窄匹配闲聊 → direct_answer。
    if _is_direct_answer_chat(lowered):
        return "direct_answer"

    # 通用知识 / 技术概念窄匹配 → direct_answer。学院词已在上方否决。
    if _is_general_knowledge_question(lowered):
        return "direct_answer"

    # 同轮多个独立问题 → decompose。仅对明确多问触发，普通“和/以及”不贸然拆。
    if _is_decompose_question(q):
        return "decompose"

    # 默认 rewrite（保守：宁可检索也不 direct_answer）
    return "rewrite"
