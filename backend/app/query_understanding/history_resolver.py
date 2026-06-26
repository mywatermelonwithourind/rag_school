"""轻量历史指代消解能力。

本模块只提供纯函数，不接入当前 LangGraph 主链路。后续是否在 preprocess
或 executor 中启用，由项目范围再决定。
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from app.core.utils import normalize_text
from app.workflow.state import HistoryMessage

HistoryStrategy = Literal["pass_through", "reference_resolution", "history_compose"]


class FollowupResolution(TypedDict):
    standalone_question: str
    history_used: bool
    history_anchor: str
    history_strategy: HistoryStrategy


WEAK_HISTORY_MESSAGES = {
    "你好",
    "您好",
    "hello",
    "hi",
    "好的",
    "好",
    "收到",
    "知道了",
    "明白了",
    "谢谢",
    "谢谢你",
    "多谢",
    "嗯",
    "嗯嗯",
    "ok",
}

NON_COLLEGE_TERMS = (
    "天气",
    "股价",
    "股票",
    "新闻",
    "旅游",
    "去哪玩",
    "写代码",
    "代码",
    "python",
    "java",
    "翻译",
    "作文",
    "笑话",
)

COLLEGE_TERMS = (
    "学院",
    "计算机",
    "学籍",
    "课程",
    "学分",
    "选课",
    "毕业",
    "转专业",
    "培养方案",
    "考试",
    "补考",
    "重修",
    "辅导员",
    "办公室",
    "办公时间",
    "奖学金",
    "助学金",
    "实习",
    "实验室",
    "证明",
    "材料",
    "流程",
)

FOLLOWUP_MARKERS = (
    "这个呢",
    "那个呢",
    "它呢",
    "刚才那个",
    "上面那个",
    "这件事",
    "这种情况",
    "需要哪些材料",
    "需要什么材料",
    "要哪些材料",
    "要什么材料",
    "流程呢",
    "什么流程",
    "办理流程",
    "申请条件",
    "什么条件",
    "哪些条件",
    "可以吗",
    "能不能",
    "可不可以",
    "行吗",
    "行不行",
)

SLOT_MARKERS = (
    "材料",
    "证明",
    "流程",
    "条件",
    "标准",
    "时间",
    "多久",
    "怎么申请",
    "如何办理",
    "怎么办",
)

QUESTION_MARKERS = (
    "怎么",
    "如何",
    "什么",
    "哪些",
    "是否",
    "能否",
    "可以",
    "需要",
    "申请",
    "办理",
    "流程",
    "材料",
    "条件",
    "要求",
    "规定",
    "？",
    "?",
)


def resolve_followup(
    question: str,
    history: list[HistoryMessage],
) -> FollowupResolution:
    """把短追问/指代追问消解成独立检索问句。

    当前规则保持保守：
    - 完整新问题不拼历史；
    - 明显非学院主题不继承历史；
    - 只有短追问或补槽型问句才继承最近可用 user anchor。
    """
    current = normalize_text(question)
    anchor = find_usable_history_anchor(history)
    if not current or not anchor:
        return _pass_through(current)

    if is_obvious_non_college_topic(current) or is_self_contained_question(current):
        return _pass_through(current)

    if is_referential_followup(current):
        standalone = build_resolved_followup_query(anchor, current)
        return _resolved(
            standalone,
            anchor=anchor,
            strategy="reference_resolution",
        )

    if is_slot_followup(current):
        standalone = compose_with_history_anchor(anchor, current)
        return _resolved(
            standalone,
            anchor=anchor,
            strategy="history_compose",
        )

    return _pass_through(current)


def find_usable_history_anchor(history: list[HistoryMessage]) -> str:
    """从最近历史中找一条可继承的用户问题。"""
    for item in reversed(history[-12:]):
        if item.get("role") != "user":
            continue
        content = normalize_text(item.get("content", ""))
        if is_usable_history_anchor(content):
            return content
    return ""


def is_usable_history_anchor(text: str) -> bool:
    compact = compact_text(text)
    if not compact or compact.lower() in {item.lower() for item in WEAK_HISTORY_MESSAGES}:
        return False
    if is_obvious_non_college_topic(text):
        return False
    if len(compact) < 4 and "?" not in text and "？" not in text:
        return False
    return bool(re.search(r"[\w\u4e00-\u9fff]", compact))


def is_obvious_non_college_topic(text: str) -> bool:
    normalized = normalize_text(text).lower()
    if not normalized:
        return False
    if any(term.lower() in normalized for term in COLLEGE_TERMS):
        return False
    return any(term.lower() in normalized for term in NON_COLLEGE_TERMS)


def is_self_contained_question(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    if is_referential_followup(normalized):
        return False
    has_subject = any(term in normalized for term in COLLEGE_TERMS)
    has_question_intent = any(marker in normalized for marker in QUESTION_MARKERS)
    return has_subject and has_question_intent


def is_referential_followup(text: str) -> bool:
    normalized = normalize_text(text)
    compact = compact_text(normalized)
    if any(marker in normalized for marker in ("刚才", "上面", "这个", "那个", "它", "这种情况")):
        return True
    return compact in {compact_text(marker) for marker in FOLLOWUP_MARKERS}


def is_slot_followup(text: str) -> bool:
    normalized = normalize_text(text)
    if is_self_contained_question(normalized):
        return False
    return any(marker in normalized for marker in SLOT_MARKERS)


def build_resolved_followup_query(anchor: str, followup: str) -> str:
    topic = anchor_topic_phrase(anchor)
    current = normalize_text(followup)
    if "材料" in current or "证明" in current:
        return f"{topic}需要哪些材料？"
    if "流程" in current or "办理" in current:
        return f"{topic}的办理流程是什么？"
    if "条件" in current:
        return f"{topic}需要满足什么条件？"
    if any(marker in current for marker in ("可以吗", "能不能", "可不可以", "行吗", "行不行")):
        suffix = current if current.endswith(("？", "?")) else f"{current}？"
        return normalize_text(f"{topic}，{suffix}")
    if any(marker in current for marker in ("这个", "那个", "它", "刚才", "上面", "这种情况")):
        return f"{topic}的具体规定是什么？"
    return compose_with_history_anchor(anchor, current)


def compose_with_history_anchor(anchor: str, followup: str) -> str:
    topic = anchor_topic_phrase(anchor)
    current = normalize_text(followup)
    if current in {"多久", "多长时间", "需要多久"} or "时间" in current:
        return f"{topic}需要多久？"
    return normalize_text(f"{topic} {current}")


def anchor_topic_phrase(anchor: str, max_len: int = 48) -> str:
    topic = normalize_text(anchor).rstrip("？?").strip()
    for prefix in ("我想知道", "我想了解", "请问", "咨询一下", "关于"):
        if topic.startswith(prefix):
            topic = topic[len(prefix) :].strip()
    for suffix in (
        "是什么",
        "有哪些",
        "需要哪些材料",
        "需要什么材料",
        "怎么弄",
        "怎么办",
        "怎么申请",
        "如何申请",
        "如何办理",
    ):
        if topic.endswith(suffix):
            topic = topic[: -len(suffix)].strip()
            break
    return topic[:max_len].strip() or normalize_text(anchor)[:max_len]


def compact_text(text: str) -> str:
    return re.sub(r"[\s。！？!?,，~～.；;：:、…]+", "", normalize_text(text))


def _pass_through(question: str) -> FollowupResolution:
    return {
        "standalone_question": question,
        "history_used": False,
        "history_anchor": "",
        "history_strategy": "pass_through",
    }


def _resolved(
    standalone_question: str,
    *,
    anchor: str,
    strategy: HistoryStrategy,
) -> FollowupResolution:
    return {
        "standalone_question": normalize_text(standalone_question),
        "history_used": True,
        "history_anchor": anchor,
        "history_strategy": strategy,
    }
