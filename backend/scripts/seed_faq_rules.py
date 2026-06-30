"""Seed FAQ rules from known ingested parent chunks."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import get_db_session
from app.core.models import FaqAliasRecord, FaqRuleRecord, ParentChunkRecord


FAQ_RULES = [
    {
        "faq_id": "faq_college_profile",
        "standard_question": "计算机工程学院简介",
        "target_parent_chunk_ids": ["pc_计算机工程学院简介_fab9f6a6_0"],
        "aliases": ["学院简介", "学院基本信息", "计算机工程学院基本情况", "介绍一下计算机工程学院"],
    },
    {
        "faq_id": "faq_cs_major",
        "standard_question": "计算机科学与技术专业设置",
        "target_parent_chunk_ids": ["pc_计算机科学与技术专业设置_ea4f50d8_0"],
        "aliases": ["计算机科学与技术专业", "计科专业", "计算机专业设置"],
    },
    {
        "faq_id": "faq_software_major",
        "standard_question": "软件工程专业设置",
        "target_parent_chunk_ids": ["pc_软件工程专业设置_241d94ae_0"],
        "aliases": ["软件工程专业", "软件工程", "软件专业设置"],
    },
    {
        "faq_id": "faq_intelligent_major",
        "standard_question": "智能科学与技术专业设置",
        "target_parent_chunk_ids": ["pc_智能科学与技术专业设置_1d20d674_0"],
        "aliases": ["智能科学与技术专业", "智能科学与技术", "智能专业设置"],
    },
    {
        "faq_id": "faq_cybersecurity_major",
        "standard_question": "网络空间安全专业设置",
        "target_parent_chunk_ids": ["pc_网络空间安全专业设置_96be924d_0"],
        "aliases": ["网络空间安全专业", "网络空间安全", "网安专业"],
    },
]


def main() -> None:
    with get_db_session() as db:
        parent_ids = {
            str(item)
            for item in db.scalars(select(ParentChunkRecord.parent_chunk_id)).all()
        }
        valid_rules = [
            rule
            for rule in FAQ_RULES
            if all(parent_id in parent_ids for parent_id in rule["target_parent_chunk_ids"])
        ]

        if not valid_rules:
            print("No FAQ rules inserted: target parent chunks are missing.")
            return

        rule_rows = [
            {
                "faq_id": rule["faq_id"],
                "standard_question": rule["standard_question"],
                "target_parent_chunk_ids": rule["target_parent_chunk_ids"],
                "answer_mode": "parent_chunk_direct",
                "template_answer": None,
                "priority": 100 - index,
                "enabled": 1,
            }
            for index, rule in enumerate(valid_rules)
        ]
        stmt = insert(FaqRuleRecord.__table__).values(rule_rows)
        db.execute(
            stmt.on_duplicate_key_update(
                standard_question=stmt.inserted.standard_question,
                target_parent_chunk_ids=stmt.inserted.target_parent_chunk_ids,
                answer_mode=stmt.inserted.answer_mode,
                template_answer=stmt.inserted.template_answer,
                priority=stmt.inserted.priority,
                enabled=stmt.inserted.enabled,
            )
        )

        faq_ids = [rule["faq_id"] for rule in valid_rules]
        db.execute(delete(FaqAliasRecord).where(FaqAliasRecord.faq_id.in_(faq_ids)))
        alias_rows = [
            {
                "faq_id": rule["faq_id"],
                "alias_text": alias,
                "match_type": "contains",
                "enabled": 1,
            }
            for rule in valid_rules
            for alias in rule["aliases"]
        ]
        if alias_rows:
            db.execute(insert(FaqAliasRecord.__table__).values(alias_rows))

    print(f"Inserted/updated {len(valid_rules)} FAQ rules.")


if __name__ == "__main__":
    main()
