"""轻量历史指代消解能力。

本模块只提供纯函数；当前由 preprocess 节点调用，负责在 rule_match / route
之前生成本轮工作问题。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, TypedDict

import httpx
from app.core.config import get_settings
from app.core.utils import normalize_text
from app.workflow.state import HistoryMessage

HistoryStrategy = Literal["pass_through", "reference_resolution", "history_compose"]


class FollowupResolution(TypedDict):
    standalone_question: str
    history_used: bool
    history_anchor: str
    history_strategy: HistoryStrategy


logger = logging.getLogger(__name__)


LLM_TIMEOUT_SECONDS = 8.0
LLM_MAX_HISTORY_MESSAGES = 4


FOLLOWUP_SYSTEM_PROMPT = """
你是对话追问改写器。你的任务是判断当前问题是否依赖最近对话历史，并在需要时把它改写成一个完整、可独立理解的问题。

只输出 JSON，不要输出解释文字。JSON 格式:
{"is_followup": boolean, "standalone_question": string, "anchor": string, "reason": string}

铁律:
1. 第一轮/无历史时，is_followup=false，standalone_question 原样返回。
2. 当前问题本身已经完整、可独立理解的新问题时，is_followup=false，standalone_question 原样返回。例如“集美大学学分要求多少”“什么是递归”。
3. 当前问题与上文无关、属于话题切换时，is_followup=false，standalone_question 原样返回。例如上文讲笑话，当前问“今天天气怎么样”。
4. 只有当前问题短、含指代/省略、脱离上文无法理解时，才 is_followup=true。
5. 改写只补全被省略的对象或语境，不要扩写，不要加入历史里没有的信息。
6. 学院事务追问和日常闲聊追问都要处理。例:
   - 历史用户问“毕业学分要求是什么”，当前“那转专业呢” -> “转专业的流程和要求是什么？”
   - 历史用户问“讲个笑话”，当前“再讲一个” -> “再讲一个笑话”
   - 历史用户问“办公室几点开”，当前“那地址呢” -> “办公室地址是什么？”
7. anchor 填被继承的最近历史问题或主题；非追问时 anchor 为空字符串。
"""


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
    "地址",
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
    """把短追问/指代追问消解成独立问句。

    对外字段契约保持不变；内部使用一次轻量 LLM 判断+改写。
    LLM 不可用、返回异常或无历史时，严格降级为 pass_through。
    """
    current = normalize_text(question)
    if not current or not history:
        return _pass_through(current)

    payload = call_followup_llm(current, history)
    if not payload:
        return _pass_through(current)

    if bool(payload.get("is_followup")):
        standalone = normalize_text(str(payload.get("standalone_question") or current))
        anchor = normalize_text(str(payload.get("anchor") or ""))
        if standalone and standalone != current:
            return _resolved(
                standalone,
                anchor=anchor,
                strategy="reference_resolution",
            )

    return _pass_through(current)


def call_followup_llm(question: str, history: list[HistoryMessage]) -> dict[str, Any] | None:
    settings = get_settings()
    if settings.llm_mock:
        return None

    messages = [
        {"role": "system", "content": FOLLOWUP_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "history": recent_history_for_llm(history),
                    "current_question": question,
                },
                ensure_ascii=False,
            ),
        },
    ]
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
        "response_format": {"type": "json_object"},
    }

    try:
        with httpx.Client(timeout=LLM_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=_llm_headers(settings.llm_api_key),
                json=payload,
            )
            response.raise_for_status()
        content = (
            ((response.json().get("choices") or [{}])[0].get("message") or {})
            .get("content")
        )
        if not isinstance(content, str):
            return None
        return parse_llm_json(content)
    except Exception:
        logger.exception("History followup LLM rewrite failed; falling back to pass_through")
        return None


def recent_history_for_llm(history: list[HistoryMessage]) -> list[dict[str, str]]:
    recent = history[-LLM_MAX_HISTORY_MESSAGES:]
    return [
        {"role": item["role"], "content": normalize_text(item["content"])}
        for item in recent
        if item.get("role") in {"user", "assistant"} and normalize_text(item.get("content", ""))
    ]


def _llm_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        raise RuntimeError("RAG_LLM_API_KEY 为空，无法调用历史追问 LLM 改写")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def parse_llm_json(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


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
    if extract_contrastive_followup_subject(normalized):
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
    contrastive_subject = extract_contrastive_followup_subject(current)
    if contrastive_subject:
        if contrastive_subject == "地址":
            return f"{topic}地址是什么？"
        if "地址" in contrastive_subject:
            return f"{contrastive_subject}是什么？"
        if "转专业" in contrastive_subject:
            return f"{contrastive_subject}的流程和要求是什么？"
        return f"{contrastive_subject}的具体规定是什么？"
    if "材料" in current or "证明" in current:
        return f"{topic}需要哪些材料？"
    if "地址" in current:
        return f"{topic}地址是什么？"
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
        "几点开",
        "几点开放",
        "什么时候开",
        "开放时间是什么",
        "办公时间是什么",
    ):
        if topic.endswith(suffix):
            topic = topic[: -len(suffix)].strip()
            break
    return topic[:max_len].strip() or normalize_text(anchor)[:max_len]


def extract_contrastive_followup_subject(text: str) -> str:
    """提取“那转专业呢 / 那地址呢”一类口语追问里的新槽位。"""
    normalized = normalize_text(text).rstrip("？?")
    match = re.fullmatch(r"(?:那|那么|还有|另外)(?P<subject>[\w\u4e00-\u9fff]{1,16})呢?", normalized)
    if not match:
        return ""
    subject = match.group("subject").strip().rstrip("呢吗呀啊")
    if is_obvious_non_college_topic(subject):
        return ""
    if subject in {"这个", "那个", "它", "这件事", "这种情况"}:
        return ""
    return subject


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
