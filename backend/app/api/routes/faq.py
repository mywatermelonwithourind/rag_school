"""FAQ endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.query_understanding.faq_matcher import (
    existing_parent_chunk_ids,
    load_enabled_faq_rules,
    normalize_target_parent_chunk_ids,
)

router = APIRouter(prefix="/faq", tags=["faq"])


@router.get("/suggestions")
async def faq_suggestions(limit: int = 6):
    """Return enabled FAQ questions whose target parent chunks are available."""
    safe_limit = max(1, min(int(limit or 6), 20))
    suggestions: list[dict[str, str]] = []

    for rule in load_enabled_faq_rules():
        answer_mode = str(rule.answer_mode or "").strip()
        parent_ids = normalize_target_parent_chunk_ids(rule.target_parent_chunk_ids)
        if answer_mode == "parent_chunk_direct" and not existing_parent_chunk_ids(parent_ids):
            continue
        question = str(rule.standard_question or "").strip()
        if not question:
            continue
        suggestions.append({"faq_id": str(rule.faq_id), "question": question})
        if len(suggestions) >= safe_limit:
            break

    return {"items": suggestions}
