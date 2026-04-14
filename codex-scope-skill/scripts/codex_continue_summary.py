#!/usr/bin/env python3
"""
Generate a continuation-ready summary card for the latest local Codex session.

This is intentionally simple:
- open a small window
- show a "continue chat" card
- copy it to the clipboard with one click
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Optional, Sequence

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

from codex_i18n import get_string, load_language, normalize_language, save_language
from codex_context_inspector import detect_codex_home, load_threads, parse_session, resolve_session_path


WINDOW_BG = "#0d1423"
SURFACE_BG = "#11192b"
CARD_BG = "#121c30"
TITLE_BG = "#0a1220"
BORDER_COLOR = "#2a3a55"
TEXT_PRIMARY = "#f8fafc"
TEXT_MUTED = "#93a4bf"
TEXT_SOFT = "#6dd3ff"
GREEN = "#34d399"
PATH_RE = re.compile(r"/(?:Users|tmp|var|mnt)[^ \n\t`\"'<>()\\【】†]+")
LINE_SUFFIX_RE = re.compile(r":\d+.*$")
FILE_ACTION_KEYWORDS = (
    "写入",
    "保存",
    "落盘",
    "更新",
    "修改",
    "创建",
    "新增",
    "删除",
    "改动",
    "output",
    "write",
    "saved",
    "updated",
    "created",
    "deleted",
    "add file",
    "update file",
    "delete file",
    "move to",
)
LOW_SIGNAL_MESSAGES = {
    "愿意",
    "开干",
    "可以",
    "行",
    "好",
    "好的",
    "嗯",
    "嗯嗯",
    "是",
    "对",
    "继续",
    "开始",
    "ok",
    "okay",
    "yes",
    "sure",
    "continue",
    "start",
}
OPERATIONAL_MESSAGES = {
    "重新打开",
    "打开",
    "重开",
    "刷新",
    "启动",
    "运行",
    "再打开",
    "再开",
    "reopen",
    "open",
    "refresh",
    "launch",
    "run",
}
SUMMARY_BLOB_MARKERS = (
    "【AI续聊卡】",
    "【续聊卡】",
    "请把下面内容当作新会话的机器输入",
    "请基于下面这张续聊卡继续",
    "一、Focus",
    "二、Current Task State",
    "三、Completed",
    "四、Pending / Next Action",
    "五、Key Files",
    "六、Current Turn Signals",
    "七、Recent Decisions",
    "八、Continue Instruction",
)
COMPLETED_HINTS = ("已", "已经", "改成", "加入", "增加", "去掉", "移除", "修复", "支持", "打开", "启动", "重启", "推上", "提交")
PENDING_HINTS = ("继续", "下一步", "接下来", "还需", "建议", "可以再", "验证", "检查", "确认", "完善", "优化")
LEADING_CHATTER = (
    "我已经",
    "已经",
    "现在",
    "我先",
    "我这边",
    "原因我已经定位到了",
    "我又看了一眼真实输出",
    "如果你下一步还想再收一刀",
    "我建议做成",
    "I already",
    "already",
    "now",
    "I will",
    "I suggest",
)
RELEVANT_FILE_SUFFIXES = {
    ".py",
    ".md",
    ".java",
    ".kt",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".xml",
    ".sh",
    ".zsh",
    ".command",
    ".txt",
    ".properties",
    ".gradle",
    ".vue",
    ".css",
    ".scss",
    ".html",
}
CITATION_RE = re.compile(r"【F:[^】]+】")
BROKEN_CITATION_RE = re.compile(r"【F:/[^\n]*")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
MULTISPACE_RE = re.compile(r"\s+")


@dataclass
class TurnDialogue:
    turn_id: str
    round_trips: int
    upstream_tokens: int
    downstream_tokens: int
    cached_tokens: int
    total_tokens: int
    file_hints: List[str]
    user_messages: List[str]
    assistant_messages: List[str]


def compact(text: str, max_chars: int = 220) -> str:
    merged = " ".join(line.strip() for line in sanitize_text(text).splitlines() if line.strip())
    if len(merged) <= max_chars:
        return merged
    return merged[: max_chars - 3] + "..."


def fmt_eng(value: float | int) -> str:
    abs_value = abs(float(value))
    sign = "-" if value < 0 else ""
    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs_value >= threshold:
            return f"{sign}{abs_value / threshold:.1f}".rstrip("0").rstrip(".") + suffix
    if isinstance(value, float):
        return f"{sign}{abs_value:.1f}".rstrip("0").rstrip(".")
    return f"{sign}{int(abs_value)}"


def sanitize_text(text: str) -> str:
    cleaned = text or ""
    cleaned = CITATION_RE.sub("", cleaned)
    cleaned = BROKEN_CITATION_RE.sub("", cleaned)
    cleaned = INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = cleaned.replace("[input_image]", "").replace("[image]", "")
    cleaned = cleaned.replace("```bash", "").replace("```text", "").replace("```", "")
    cleaned = MULTISPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def strip_summary_blob(text: str) -> str:
    cleaned = text or ""
    cut_positions = [cleaned.find(marker) for marker in SUMMARY_BLOB_MARKERS if marker in cleaned]
    if cut_positions:
        cleaned = cleaned[: min(cut_positions)]
    return cleaned.strip()


def sanitize_user_intent(text: str) -> str:
    cleaned = sanitize_text(strip_summary_blob(text))
    if "文件:" in cleaned:
        before, after = cleaned.split("文件:", 1)
        candidate = before.strip(" ，,;:")
        cleaned = candidate or f"文件: {after.strip()}"
    return cleaned


def split_sentences(text: str) -> List[str]:
    cleaned = sanitize_text(text)
    if not cleaned:
        return []
    for sep in ("。", "！", "？", "\n", ";"):
        cleaned = cleaned.replace(sep, "|")
    return [part.strip(" -|") for part in cleaned.split("|") if part.strip(" -|")]


def compress_fact(text: str, max_chars: int = 110) -> str:
    cleaned = sanitize_text(text)
    cleaned = re.sub(r"^[-–—\s]+", "", cleaned).strip()
    for prefix in LEADING_CHATTER:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].lstrip(" ：:，,")
    return compact(cleaned, max_chars)


def extract_status_facts(messages: Sequence[str], hints: Sequence[str], limit: int, fallback_prefix: Optional[str] = None) -> List[str]:
    facts: List[str] = []
    seen = set()
    for message in reversed(messages):
        for sentence in split_sentences(message):
            if hints and not any(hint in sentence for hint in hints):
                continue
            fact = compress_fact(sentence)
            if not fact or fact in seen:
                continue
            if fallback_prefix and not fact.startswith(fallback_prefix):
                fact = f"{fallback_prefix}{fact}"
            facts.append(fact)
            seen.add(fact)
            if len(facts) >= limit:
                return facts
    return facts


def normalize_status_fact(text: str, prefix: str, max_chars: int = 96) -> str:
    fact = compress_fact(text, max_chars=max_chars)
    fact = fact.strip(" ，,;:。")
    if fact.startswith(prefix):
        return fact
    return f"{prefix}{fact}"


def extract_file_hints(texts: Sequence[str], limit: int = 8) -> List[str]:
    hints: List[str] = []
    seen = set()
    for text in texts:
        if not text:
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            paths = PATH_RE.findall(line)
            if not paths:
                continue
            for path in paths:
                normalized = LINE_SUFFIX_RE.sub("", path.rstrip(".,;:"))
                path_obj = Path(normalized)
                if "/.codex/sessions/" in normalized or "/Library/Caches/" in normalized:
                    continue
                if path_obj.suffix.lower() not in RELEVANT_FILE_SUFFIXES:
                    continue
                if normalized not in seen:
                    hints.append(normalized)
                    seen.add(normalized)
            if len(hints) >= limit:
                return hints
    return hints


def is_low_signal_message(text: str) -> bool:
    merged = sanitize_user_intent(text)
    if not merged:
        return True
    if merged in LOW_SIGNAL_MESSAGES:
        return True
    return len(merged) <= 4


def is_operational_message(text: str) -> bool:
    merged = sanitize_user_intent(text)
    if not merged:
        return True
    if merged in OPERATIONAL_MESSAGES:
        return True
    if len(merged) <= 6 and any(keyword in merged for keyword in OPERATIONAL_MESSAGES):
        return True
    return False


def resolve_latest_user_request(focus_dialogue: Optional[TurnDialogue], prior_dialogues: Sequence[TurnDialogue]) -> Optional[str]:
    if focus_dialogue:
        sanitized_focus = [sanitize_user_intent(item) for item in focus_dialogue.user_messages if sanitize_user_intent(item)]
        for text in reversed(sanitized_focus):
            if not is_low_signal_message(text) and not is_operational_message(text):
                return compact(text, 220)
        for text in reversed(sanitized_focus):
            if not is_low_signal_message(text):
                return compact(text, 220)
    for dialogue in reversed(prior_dialogues):
        sanitized_users = [sanitize_user_intent(item) for item in dialogue.user_messages if sanitize_user_intent(item)]
        for text in reversed(sanitized_users):
            if not is_low_signal_message(text) and not is_operational_message(text):
                return compact(text, 220)
    return None


def resolve_current_goal(
    dialogues: Sequence[TurnDialogue],
    focus_index: Optional[int],
    focus_dialogue: Optional[TurnDialogue],
    lang: str,
) -> str:
    if focus_dialogue:
        for text in reversed(focus_dialogue.user_messages):
            if not is_low_signal_message(text) and not is_operational_message(text):
                return compact(sanitize_user_intent(text), 220)
        for text in reversed(focus_dialogue.user_messages):
            if not is_low_signal_message(text):
                return compact(sanitize_user_intent(text), 220)
    if focus_index is not None:
        for dialogue in reversed(dialogues[:focus_index]):
            for text in reversed(dialogue.user_messages):
                if not is_low_signal_message(text) and not is_operational_message(text):
                    return compact(sanitize_user_intent(text), 220)
        for dialogue in reversed(dialogues[:focus_index]):
            for text in reversed(dialogue.user_messages):
                if not is_low_signal_message(text):
                    return compact(sanitize_user_intent(text), 220)
    if focus_dialogue and focus_dialogue.assistant_messages:
        return compact(focus_dialogue.assistant_messages[-1], 220)
    return get_string("summary.empty", lang)


def resolve_project_context(parsed) -> tuple[Optional[str], Optional[str]]:
    if not parsed.thread_id:
        return None, None
    try:
        codex_home = detect_codex_home(None)
        threads = load_threads(codex_home)
        record = threads.get(parsed.thread_id)
    except Exception:
        record = None
    if not record or not record.cwd:
        return None, None
    cwd = record.cwd
    project_name = Path(cwd).name or cwd
    return project_name, cwd


def summarize_recent_assistant(dialogue: Optional[TurnDialogue], limit: int = 3) -> List[str]:
    if not dialogue:
        return []
    results: List[str] = []
    seen = set()
    for text in reversed(dialogue.assistant_messages):
        item = compact(text, 220)
        if not item or item in seen:
            continue
        results.append(item)
        seen.add(item)
        if len(results) >= limit:
            break
    return list(reversed(results))


def pick_key_files(
    dialogues: Sequence[TurnDialogue],
    focus_index: Optional[int],
    focus_dialogue: Optional[TurnDialogue],
    cwd: Optional[str],
    limit: int = 6,
) -> List[str]:
    seen = set()
    files: List[str] = []
    project_root = cwd or ""
    for source in ([focus_dialogue] if focus_dialogue else []) + list(reversed(dialogues[:focus_index] if focus_index is not None else [])):
        if not source:
            continue
        for path in source.file_hints:
            if project_root and not path.startswith(project_root):
                continue
            if path not in seen:
                files.append(path)
                seen.add(path)
            if len(files) >= limit:
                return files
    if not files:
        for source in ([focus_dialogue] if focus_dialogue else []) + list(reversed(dialogues[:focus_index] if focus_index is not None else [])):
            if not source:
                continue
            for path in source.file_hints:
                if path not in seen:
                    files.append(path)
                    seen.add(path)
                if len(files) >= limit:
                    return files
    return files


def build_completed_and_pending(
    focus_dialogue: Optional[TurnDialogue], prior_dialogues: Sequence[TurnDialogue], current_goal: str
) -> tuple[List[str], List[str]]:
    assistant_messages = focus_dialogue.assistant_messages if focus_dialogue else []
    completed_raw = extract_status_facts(assistant_messages, COMPLETED_HINTS, limit=3)
    completed = [normalize_status_fact(item, "已完成: ") for item in completed_raw]
    if not completed:
        completed = [normalize_status_fact(item, "已完成: ") for item in extract_status_facts(assistant_messages, (), limit=2)]

    pending: List[str] = []
    if current_goal and current_goal != "(未提取到)":
        pending.append(f"待做: {compact(current_goal, 120)}")
    for item in extract_status_facts(assistant_messages, PENDING_HINTS, limit=2):
        candidate = normalize_status_fact(item, "待做: ")
        if candidate not in pending:
            pending.append(candidate)
        if len(pending) >= 2:
            break
    if not pending and prior_dialogues:
        last_prior = summarize_recent_assistant(prior_dialogues[-1], limit=1)
        if last_prior:
            pending = [normalize_status_fact(last_prior[-1], "待做: ", max_chars=120)]
    return completed[:3], pending[:2]


def build_key_decisions(prior_dialogues: Sequence[TurnDialogue], max_items: int = 12) -> List[str]:
    if not prior_dialogues:
        return []
    weighted = sorted(
        enumerate(prior_dialogues, start=1),
        key=lambda item: (item[1].total_tokens, item[0]),
        reverse=True,
    )
    selected = sorted(weighted[:max_items], key=lambda item: item[0])
    decisions: List[str] = []
    for index, dialogue in selected:
        user_text = ""
        for text in reversed(dialogue.user_messages):
            if not is_low_signal_message(text):
                user_text = compact(text, 100)
                break
        if not user_text and dialogue.user_messages:
            user_text = compact(dialogue.user_messages[-1], 100)
        assistant_text = ""
        if dialogue.assistant_messages:
            assistant_text = compress_fact(dialogue.assistant_messages[-1], 88)
        line = (
            f"- T{index} | rt {dialogue.round_trips} | total {fmt_eng(dialogue.total_tokens)}"
            f" | req {compact(sanitize_user_intent(user_text or '(无)'), 64)}"
            f" | done {assistant_text or '(无)'}"
        )
        decisions.append(line)
    return decisions


def build_full_turn_history(
    dialogues: Sequence[TurnDialogue],
    lang: str,
    max_chars_user: int = 220,
    max_chars_assistant: int = 320,
) -> List[str]:
    lines: List[str] = []
    for index, dialogue in enumerate(dialogues, start=1):
        lines.append(
            get_string(
                "summary.history.turn",
                lang,
                index=index,
                round_trips=dialogue.round_trips,
                upstream=fmt_eng(dialogue.upstream_tokens),
                downstream=fmt_eng(dialogue.downstream_tokens),
                cached=fmt_eng(dialogue.cached_tokens),
                total=fmt_eng(dialogue.total_tokens),
            )
        )
        if dialogue.user_messages:
            for user_text in dialogue.user_messages[-3:]:
                lines.append(f"  {get_string('summary.user', lang)}: {compact(sanitize_user_intent(user_text), max_chars_user)}")
        if dialogue.assistant_messages:
            for assistant_text in dialogue.assistant_messages[-3:]:
                lines.append(f"  {get_string('summary.assistant', lang)}: {compact(assistant_text, max_chars_assistant)}")
        if dialogue.file_hints:
            lines.append(get_string("summary.history.files", lang, files=" | ".join(dialogue.file_hints[:6])))
    return lines


def build_turn_dialogues(parsed) -> List[TurnDialogue]:
    dialogues: List[TurnDialogue] = []
    current_turn_id: Optional[str] = None
    current_users: List[str] = []
    current_assistant: List[str] = []
    current_round_trips = 0
    current_upstream_tokens = 0
    current_downstream_tokens = 0
    current_cached_tokens = 0
    current_total_tokens = 0
    current_file_texts: List[str] = []
    cursor = 0

    for call in parsed.calls:
        turn_id = call.turn_id or "unknown"
        context_delta = parsed.transcript_pool[cursor:call.context_end_index]
        new_user_messages = [
            item.text
            for item in context_delta
            if item.role == "user" and item.kind == "message" and (item.text or "").strip()
        ]

        if current_turn_id is None:
            current_turn_id = turn_id

        if turn_id != current_turn_id:
            dialogues.append(
                TurnDialogue(
                    turn_id=current_turn_id,
                    round_trips=current_round_trips,
                    upstream_tokens=current_upstream_tokens,
                    downstream_tokens=current_downstream_tokens,
                    cached_tokens=current_cached_tokens,
                    total_tokens=current_total_tokens,
                    file_hints=extract_file_hints(current_file_texts),
                    user_messages=current_users,
                    assistant_messages=current_assistant,
                )
            )
            current_turn_id = turn_id
            current_users = []
            current_assistant = []
            current_round_trips = 0
            current_upstream_tokens = 0
            current_downstream_tokens = 0
            current_cached_tokens = 0
            current_total_tokens = 0
            current_file_texts = []

        current_users.extend(new_user_messages)
        current_round_trips += 1
        usage = call.usage or {}
        current_upstream_tokens += int(usage.get("input_tokens") or 0)
        current_cached_tokens += int(usage.get("cached_input_tokens") or 0)
        current_downstream_tokens += int(usage.get("output_tokens") or 0) + int(
            usage.get("reasoning_output_tokens") or 0
        )
        current_total_tokens += int(usage.get("total_tokens") or 0)
        for item in context_delta:
            if item.role in {"tool", "assistant"} and (item.text or "").strip():
                current_file_texts.append(item.text)
        for item in call.output_items:
            if item.role == "assistant" and item.kind == "message" and (item.text or "").strip():
                current_assistant.append(item.text)
                current_file_texts.append(item.text)

        cursor = call.context_end_index + sum(1 for item in call.output_items if item.transcriptable)

    if current_turn_id is not None:
        dialogues.append(
            TurnDialogue(
                turn_id=current_turn_id,
                round_trips=current_round_trips,
                upstream_tokens=current_upstream_tokens,
                downstream_tokens=current_downstream_tokens,
                cached_tokens=current_cached_tokens,
                total_tokens=current_total_tokens,
                file_hints=extract_file_hints(current_file_texts),
                user_messages=current_users,
                assistant_messages=current_assistant,
            )
        )
    return dialogues


def build_continue_summary(path: Path, turn_id: Optional[str] = None, lang: str = "en") -> str:
    lang = normalize_language(lang)
    parsed = parse_session(path)
    dialogues = build_turn_dialogues(parsed)
    focus_turn_id = turn_id or (dialogues[-1].turn_id if dialogues else None)
    focus_index = next((index for index, item in enumerate(dialogues) if item.turn_id == focus_turn_id), None)
    focus_dialogue = dialogues[focus_index] if focus_index is not None else None
    prior_dialogues = dialogues[:focus_index] if focus_index is not None else []
    latest_assistant = summarize_recent_assistant(focus_dialogue, limit=3)
    recent_users = [compact(sanitize_user_intent(item), 180) for item in (focus_dialogue.user_messages[-3:] if focus_dialogue else []) if sanitize_user_intent(item)]
    total_tokens = parsed.exact_total_tokens or sum(int((call.usage or {}).get("total_tokens") or 0) for call in parsed.calls)
    current_goal = resolve_current_goal(dialogues, focus_index, focus_dialogue, lang)
    latest_user_request = resolve_latest_user_request(focus_dialogue, prior_dialogues)
    project_name, cwd = resolve_project_context(parsed)
    key_files = pick_key_files(dialogues, focus_index, focus_dialogue, cwd, limit=6)
    full_history = build_full_turn_history(prior_dialogues, lang)
    none_short = get_string("summary.none_short", lang)

    parts: List[str] = []
    parts.append(get_string("summary.card_title", lang))
    parts.append(get_string("summary.intro", lang))
    parts.append("")
    parts.append(get_string("summary.section.focus", lang))
    if focus_turn_id:
        parts.append(f"- turn_id: {focus_turn_id}")
    parts.append(f"- model: {parsed.model or 'unknown'}")
    if project_name:
        parts.append(f"- project: {project_name}")
    if cwd:
        parts.append(f"- cwd: {cwd}")
    parts.append("")
    parts.append(get_string("summary.section.state", lang))
    parts.append(f"- {get_string('summary.field.current_goal', lang)}: {current_goal}")
    if latest_user_request:
        parts.append(f"- {get_string('summary.field.latest_user_request', lang)}: {latest_user_request}")
    elif recent_users:
        parts.append(f"- {get_string('summary.field.latest_user_request', lang)}: {recent_users[-1]}")
    parts.append(f"- {get_string('summary.field.session_total_tokens', lang)}: {fmt_eng(total_tokens)}")
    parts.append(f"- {get_string('summary.field.session_round_trips', lang)}: {len(parsed.calls)}")
    parts.append(f"- {get_string('summary.field.focus_round_trips', lang)}: {(focus_dialogue.round_trips if focus_dialogue else 0)}")
    if focus_dialogue:
        parts.append(
            f"- {get_string('summary.field.focus_tokens', lang)}: "
            f"upstream {fmt_eng(focus_dialogue.upstream_tokens)} / "
            f"downstream {fmt_eng(focus_dialogue.downstream_tokens)} / "
            f"cached {fmt_eng(focus_dialogue.cached_tokens)} / "
            f"total {fmt_eng(focus_dialogue.total_tokens)}"
        )
    parts.append("")
    parts.append(get_string("summary.section.dialogue", lang))
    if recent_users:
        for item in recent_users:
            parts.append(f"- {get_string('summary.user', lang)}: {item}")
    else:
        parts.append(f"- {get_string('summary.user', lang)}: {none_short}")
    if latest_assistant:
        for item in latest_assistant:
            parts.append(f"- {get_string('summary.assistant', lang)}: {item}")
    else:
        parts.append(f"- {get_string('summary.assistant', lang)}: {none_short}")
    parts.append("")
    parts.append(get_string("summary.section.files", lang))
    if key_files:
        for item in key_files:
            parts.append(f"- {item}")
    else:
        parts.append(f"- {none_short}")
    parts.append("")
    parts.append(get_string("summary.section.signals", lang))
    if focus_dialogue:
        parts.append(f"- round_trips: {focus_dialogue.round_trips}")
        parts.append(f"- upstream_tokens: {fmt_eng(focus_dialogue.upstream_tokens)}")
        parts.append(f"- downstream_tokens: {fmt_eng(focus_dialogue.downstream_tokens)}")
        parts.append(f"- cached_tokens: {fmt_eng(focus_dialogue.cached_tokens)}")
        parts.append(f"- total_tokens: {fmt_eng(focus_dialogue.total_tokens)}")
        if latest_assistant:
            parts.append(f"- latest_assistant_outcome: {latest_assistant[-1]}")
    else:
        parts.append(f"- {none_short}")
    parts.append("")
    parts.append(get_string("summary.section.history", lang))
    if full_history:
        parts.extend(full_history)
    else:
        parts.append(get_string("summary.history.empty", lang))
    parts.append("")
    parts.append(get_string("summary.section.instruction", lang))
    parts.append(get_string("summary.instruction", lang))
    return "\n".join(parts)


class ContinueSummaryWindow:
    def __init__(self, refresh_ms: int = 5000, session_path: Optional[str] = None, lang: Optional[str] = None) -> None:
        self.refresh_ms = refresh_ms
        self.codex_home = detect_codex_home(None)
        self.fixed_session_path = Path(session_path).expanduser().resolve() if session_path else None
        self.lang = normalize_language(lang) if lang else load_language()
        self.root = tk.Tk()
        self.root.title(self._t("continue.window_title"))
        self.root.configure(bg=WINDOW_BG)
        self.root.geometry("980x760+140+140")
        self.root.minsize(860, 640)

        self.title_font = tkfont.Font(family="PingFang SC", size=15, weight="bold")
        self.section_font = tkfont.Font(family="PingFang SC", size=12, weight="bold")
        self.small_font = tkfont.Font(family="PingFang SC", size=10)

        self.current_summary = ""
        self.current_session_path: Optional[Path] = None
        self.after_id: Optional[str] = None

        self._build_ui()
        self.root.after(100, self.refresh)

    def _t(self, key: str, **kwargs: object) -> str:
        return get_string(key, self.lang, **kwargs)

    def _toggle_language(self) -> None:
        next_lang = "zh" if self.lang == "en" else "en"
        self.lang = save_language(next_lang)
        self.root.title(self._t("continue.window_title"))
        self.title_label.config(text=self._t("continue.window_title"))
        self.status_label.config(text=self._t("continue.status.loading"))
        self.copy_button.config(text=self._t("continue.button.copy"))
        self.refresh_button.config(text=self._t("continue.button.refresh"))
        self.helper_label.config(text=self._t("continue.helper"))
        self.section_title.config(text=self._t("continue.section.title"))
        self.lang_button.config(text=self._t("language.toggle"))
        self.current_summary = ""
        self.refresh()

    def _make_mac_button(
        self,
        parent: tk.Misc,
        *,
        text: str,
        command,
        kind: str = "secondary",
    ) -> tk.Label:
        if kind == "primary":
            bg = CARD_BG
            fg = "#dbeafe"
            hover_bg = "#16233a"
            hover_fg = "#eff6ff"
            border = "#35507a"
        else:
            bg = CARD_BG
            fg = "#cbd5e1"
            hover_bg = "#18243c"
            hover_fg = "#f8fafc"
            border = "#31415f"
        button = tk.Label(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            relief="solid",
            bd=1,
            highlightthickness=0,
            padx=14,
            pady=7,
            font=self.small_font,
            cursor="hand2",
            borderwidth=1,
        )
        button.bind("<Button-1>", lambda _event: command())
        button.bind("<Enter>", lambda _event: button.configure(bg=hover_bg, fg=hover_fg))
        button.bind("<Leave>", lambda _event: button.configure(bg=bg, fg=fg))
        button.configure(highlightbackground=border)
        return button

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=SURFACE_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        outer.pack(fill="both", expand=True)

        title_bar = tk.Frame(outer, bg=TITLE_BG, height=44)
        title_bar.pack(fill="x")
        self.title_label = tk.Label(
            title_bar,
            text=self._t("continue.window_title"),
            fg=TEXT_PRIMARY,
            bg=TITLE_BG,
            font=self.title_font,
        )
        self.title_label.pack(side="left", padx=(18, 0), pady=10)
        self.status_label = tk.Label(title_bar, text=self._t("continue.status.loading"), fg=TEXT_SOFT, bg=TITLE_BG, font=self.small_font)
        self.status_label.pack(side="left", padx=(18, 0), pady=11)
        self.lang_button = self._make_mac_button(
            title_bar,
            text=self._t("language.toggle"),
            command=self._toggle_language,
            kind="secondary",
        )
        self.lang_button.pack(side="right", padx=(0, 12), pady=7)

        actions = tk.Frame(outer, bg=SURFACE_BG)
        actions.pack(fill="x", padx=12, pady=(12, 8))

        self.copy_button = self._make_mac_button(
            actions,
            text=self._t("continue.button.copy"),
            command=self.copy_summary,
            kind="primary",
        )
        self.copy_button.pack(side="left")
        self.refresh_button = self._make_mac_button(
            actions,
            text=self._t("continue.button.refresh"),
            command=self.refresh,
            kind="secondary",
        )
        self.refresh_button.pack(side="left", padx=(10, 0))

        self.helper_label = tk.Label(
            actions,
            text=self._t("continue.helper"),
            fg=TEXT_MUTED,
            bg=SURFACE_BG,
            font=self.small_font,
        )
        self.helper_label.pack(side="left", padx=(16, 0))

        card = tk.Frame(outer, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.section_title = tk.Label(card, text=self._t("continue.section.title"), fg=TEXT_PRIMARY, bg=CARD_BG, font=self.section_font)
        self.section_title.pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.text = tk.Text(
            card,
            wrap="word",
            bg=CARD_BG,
            fg="#dbe4f0",
            relief="flat",
            font=("Menlo", 11),
        )
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def copy_summary(self) -> None:
        if not self.current_summary:
            messagebox.showinfo(self._t("continue.none_title"), self._t("continue.none_body"))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_summary)
        self.root.update()
        self.status_label.config(text=self._t("continue.status.copied"))

    def refresh(self) -> None:
        try:
            if self.fixed_session_path is not None:
                path = self.fixed_session_path
            else:
                threads = load_threads(self.codex_home)
                path = resolve_session_path(self.codex_home, threads, True, None, None)
            if path != self.current_session_path or not self.current_summary:
                self.current_summary = build_continue_summary(path, lang=self.lang)
                self.current_session_path = path
                self.text.configure(state="normal")
                self.text.delete("1.0", "end")
                self.text.insert("1.0", self.current_summary)
                self.text.configure(state="disabled")
            self.status_label.config(text=self._t("continue.status.updated", name=path.name))
        except Exception as exc:
            self.status_label.config(text=self._t("continue.status.error", message=str(exc)))
        finally:
            if self.after_id is not None:
                self.root.after_cancel(self.after_id)
            self.after_id = self.root.after(self.refresh_ms, self.refresh)

    def run(self) -> None:
        self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a continuation-ready summary card for the latest session.")
    parser.add_argument("--refresh-ms", type=int, default=5000, help="Refresh interval in milliseconds")
    parser.add_argument("--latest", action="store_true", help="Print latest session continue summary and exit")
    parser.add_argument("--path", help="Open or print continue summary for a specific session file")
    parser.add_argument("--lang", choices=("en", "zh"), help="UI language. Defaults to saved setting or English.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.latest:
        if args.path:
            path = Path(args.path).expanduser().resolve()
        else:
            codex_home = detect_codex_home(None)
            threads = load_threads(codex_home)
            path = resolve_session_path(codex_home, threads, True, None, None)
        print(build_continue_summary(path, lang=args.lang or load_language()))
        return 0
    ContinueSummaryWindow(refresh_ms=args.refresh_ms, session_path=args.path, lang=args.lang).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
