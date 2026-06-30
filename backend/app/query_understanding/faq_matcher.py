"""FAQ 规则匹配 — query_understanding 组."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.core.models import FaqRuleRecord, ParentChunkRecord
from app.workflow.state import FAQMatchResult

logger = logging.getLogger(__name__)

SUPPORTED_ANSWER_MODES = {"parent_chunk_direct", "template", "llm_generate"}
SUPPORTED_MATCH_TYPES = {"exact", "contains", "regex"}


def _empty_result() -> FAQMatchResult:
    return {
        "matched": False,
        "faq_id": None,
        "standard_question": None,
        "target_parent_chunk_ids": [],
        "answer_mode": "llm_generate",
        "confidence": 0.0,
    }


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    value = re.sub(r"[\s\?？。.!！]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def normalize_target_parent_chunk_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []

    result: list[str] = []
    for item in values:
        parent_id = str(item or "").strip()
        if parent_id and parent_id not in result:
            result.append(parent_id)
    return result


def load_enabled_faq_rules() -> list[FaqRuleRecord]:
    try:
        with get_db_session() as db:
            return list(
                db.scalars(
                    select(FaqRuleRecord)
                    .options(selectinload(FaqRuleRecord.aliases))
                    .where(FaqRuleRecord.enabled == 1)
                    .order_by(FaqRuleRecord.priority.desc(), FaqRuleRecord.faq_id.asc())
                ).all()
            )
    except Exception as exc:
        logger.debug("FAQ rule lookup skipped: %s", exc)
        return []


def existing_parent_chunk_ids(parent_ids: list[str]) -> list[str]:
    if not parent_ids:
        return []
    try:
        with get_db_session() as db:
            existing = set(
                db.scalars(
                    select(ParentChunkRecord.parent_chunk_id).where(
                        ParentChunkRecord.parent_chunk_id.in_(parent_ids)
                    )
                ).all()
            )
    except Exception as exc:
        logger.debug("FAQ parent chunk validation skipped: %s", exc)
        return []
    return [parent_id for parent_id in parent_ids if parent_id in existing]


def match_rule(question: str, rule: FaqRuleRecord) -> tuple[bool, float]:
    normalized_question = normalize_text(question)
    standard_question = normalize_text(rule.standard_question)
    if normalized_question and standard_question:
        if normalized_question == standard_question or standard_question in normalized_question:
            return True, 0.95

    for alias in sorted(rule.aliases or [], key=lambda item: (int(item.alias_id or 0))):
        if not int(alias.enabled or 0):
            continue
        match_type = str(alias.match_type or "contains").strip().lower()
        if match_type not in SUPPORTED_MATCH_TYPES:
            continue
        alias_text = str(alias.alias_text or "").strip()
        normalized_alias = normalize_text(alias_text)
        if not normalized_alias and match_type != "regex":
            continue

        if match_type == "exact" and normalized_question == normalized_alias:
            return True, 0.93
        if match_type == "contains" and normalized_alias in normalized_question:
            return True, 0.90
        if match_type == "regex":
            try:
                if re.search(alias_text, question):
                    return True, 0.88
            except re.error:
                continue

    return False, 0.0


def match_faq(question: str) -> FAQMatchResult:
    """
    FAQ 匹配：从 MySQL faq_rule + faq_alias 读取标准问和别名。

    Args:
        question: 用户问题（已清洗）

    Returns:
        FAQMatchResult
    """
    for rule in load_enabled_faq_rules():
        answer_mode = str(rule.answer_mode or "").strip()
        if answer_mode not in SUPPORTED_ANSWER_MODES:
            continue

        matched, confidence = match_rule(question, rule)
        if not matched:
            continue

        target_parent_chunk_ids = existing_parent_chunk_ids(
            normalize_target_parent_chunk_ids(rule.target_parent_chunk_ids)
        )
        if answer_mode == "parent_chunk_direct" and not target_parent_chunk_ids:
            continue

        return {
            "matched": True,
            "faq_id": rule.faq_id,
            "standard_question": rule.standard_question,
            "target_parent_chunk_ids": target_parent_chunk_ids,
            "answer_mode": answer_mode,
            "confidence": confidence,
        }

    return _empty_result()
