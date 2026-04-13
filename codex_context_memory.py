#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from codex_context_inspector import TranscriptItem


FILE_PATH_RE = re.compile(r"(\/[A-Za-z0-9._\-/]+)")


@dataclass
class WorkingMemory:
    current_goal: str = ""
    hard_constraints: List[str] = field(default_factory=list)
    completed_items: List[str] = field(default_factory=list)
    pending_items: List[str] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    latest_failures: List[str] = field(default_factory=list)
    next_step: str = ""


@dataclass
class TurnSummary:
    user_intent: str = ""
    actions_taken: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    files_touched: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    next_step: str = ""


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _extract_files(text: str) -> List[str]:
    return _dedupe_keep_order(match.group(1) for match in FILE_PATH_RE.finditer(text))


def _compact_text(text: str, max_chars: int = 180) -> str:
    merged = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(merged) <= max_chars:
        return merged
    return merged[: max_chars - 3] + "..."


def build_working_memory(context_items: Sequence[TranscriptItem]) -> WorkingMemory:
    latest_user = ""
    assistant_snippets: List[str] = []
    tool_snippets: List[str] = []
    files: List[str] = []

    for item in context_items:
        files.extend(_extract_files(item.text))
        if item.role == "user" and item.kind == "message":
            latest_user = item.text
        elif item.role == "assistant" and item.kind == "message":
            assistant_snippets.append(_compact_text(item.text, 140))
        elif item.role == "tool":
            tool_snippets.append(_compact_text(item.text, 140))

    memory = WorkingMemory()
    memory.current_goal = _compact_text(latest_user, 220)
    memory.key_files = _dedupe_keep_order(files)[:8]
    memory.key_findings = _dedupe_keep_order(tool_snippets[-4:] + assistant_snippets[-2:])[:6]
    if assistant_snippets:
        memory.completed_items = [_dedupe_keep_order(assistant_snippets[-2:])[0]]
    if tool_snippets:
        memory.pending_items = [_dedupe_keep_order(tool_snippets[-1:])[0]]
    memory.next_step = assistant_snippets[-1] if assistant_snippets else ""
    return memory
