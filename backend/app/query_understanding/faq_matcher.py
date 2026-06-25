"""FAQ 规则匹配 — query_understanding 组"""

from __future__ import annotations

from app.core.config import get_settings
from app.workflow.state import FAQMatchResult

# Mock FAQ 规则（联调用；正式数据在 MySQL faq_rule / faq_alias 表）
_MOCK_FAQ_RULES: list[dict] = [
    {
        "faq_id": "faq_001",
        "standard_question": "计算机学院办公时间是什么",
        "aliases": ["上班时间", "几点上班", "办公室几点开"],
        "target_parent_chunk_ids": ["pc_office_hours"],
        "answer_mode": "parent_chunk_direct",
    },
    {
        "faq_id": "faq_002",
        "standard_question": "如何联系辅导员",
        "aliases": ["辅导员电话", "辅导员联系方式"],
        "target_parent_chunk_ids": ["pc_counselor_contact"],
        "answer_mode": "template",
    },
]


def match_faq(question: str) -> FAQMatchResult:
    """
    FAQ 匹配：标准问 + 别名表（exact / contains）。

    TODO(query_understanding):
        - 从 MySQL 加载 faq_rule + faq_alias
        - 支持 match_type: exact | contains | regex
        - 可选 embedding 语义匹配作为 fallback

    Args:
        question: 用户问题（已清洗）

    Returns:
        FAQMatchResult
    """
    settings = get_settings()
    q = question.lower().strip()

    best: FAQMatchResult = {
        "matched": False,
        "faq_id": None,
        "standard_question": None,
        "target_parent_chunk_ids": [],
        "answer_mode": "llm_generate",
        "confidence": 0.0,
    }

    for rule in _MOCK_FAQ_RULES:
        std = rule["standard_question"].lower()
        if q == std or std in q or q in std:
            return {
                "matched": True,
                "faq_id": rule["faq_id"],
                "standard_question": rule["standard_question"],
                "target_parent_chunk_ids": rule["target_parent_chunk_ids"],
                "answer_mode": rule["answer_mode"],
                "confidence": 0.95,
            }
        for alias in rule.get("aliases", []):
            if alias.lower() in q:
                return {
                    "matched": True,
                    "faq_id": rule["faq_id"],
                    "standard_question": rule["standard_question"],
                    "target_parent_chunk_ids": rule["target_parent_chunk_ids"],
                    "answer_mode": rule["answer_mode"],
                    "confidence": 0.90,
                }

    return best
