#!/usr/bin/env python3
"""
Phase-1 context throttling simulator for local Codex sessions.

This does not modify Codex's real request assembly.
It simulates how much input-token pressure could be reduced by:
- summarizing historical tool outputs,
- trimming older assistant history,
- retaining only compact working memory for stale items.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from codex_context_budget import ContextBudgetPolicy, default_budget_policy
from codex_context_inspector import (
    TranscriptItem,
    detect_codex_home,
    load_threads,
    parse_session,
    resolve_session_path,
    value_or_unknown,
)
from codex_context_memory import WorkingMemory, build_working_memory


ERROR_KEYWORDS = ("error", "failed", "failure", "exception", "traceback", "warning", "warn")


@dataclass
class NormalizedItem:
    index: int
    role: str
    kind: str
    title: str
    category: str
    retention_mode: str
    original_chars: int
    compacted_chars: int
    original_text: str
    compacted_text: str


@dataclass
class SimulationResult:
    session_file: Path
    thread_id: str
    call_index: int
    input_tokens: int
    estimated_compacted_input_tokens: int
    estimated_saved_tokens: int
    estimated_saved_ratio: float
    pressure_before: str
    pressure_after: str
    before_category_tokens: List[Tuple[str, int]]
    after_category_tokens: List[Tuple[str, int]]
    top_tool_outputs: List[Tuple[str, int]]
    retention_summary: List[Tuple[str, int, int]]
    working_memory: WorkingMemory
    normalized_items: List[NormalizedItem]


def shorten(text: str, max_chars: int) -> str:
    merged = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(merged) <= max_chars:
        return merged
    return merged[: max_chars - 3] + "..."


def category_for_item(item: TranscriptItem) -> str:
    if item.kind == "base_instructions":
        return "system_prompt"
    if item.role == "developer":
        return "developer_prompt"
    if item.role == "user":
        return "user_message"
    if item.kind == "turn_context":
        return "runtime_context"
    if item.role == "tool":
        return "tool_output"
    if item.role == "assistant" and item.kind == "function_call":
        return "tool_call"
    if item.role == "assistant":
        return "assistant_history"
    return "other"


def summarize_tool_output(text: str, title: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return f"[Tool Result Summary] {title}: (empty)"

    picked: List[str] = []
    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in ERROR_KEYWORDS):
            picked.append(line)
    picked.extend(lines[:6])

    deduped: List[str] = []
    seen = set()
    for line in picked:
        if line in seen:
            continue
        seen.add(line)
        deduped.append(line)
        if len(deduped) >= 8:
            break

    bullets = "\n".join(f"- {shorten(line, 160)}" for line in deduped)
    return f"[Tool Result Summary]\ntool_result: {title}\nkey_points:\n{bullets}"


def summarize_assistant_message(text: str) -> str:
    return f"[Assistant Summary]\n{shorten(text, 280)}"


def summarize_tool_call(item: TranscriptItem) -> str:
    return f"[Tool Call] {item.title}\nargs: {shorten(item.text, 200)}"


def summarize_user_message(text: str) -> str:
    return f"[User Summary]\n{shorten(text, 220)}"


def retain_item(item: TranscriptItem, latest_user_index: Optional[int], index: int) -> Tuple[str, str]:
    category = category_for_item(item)

    if item.kind == "base_instructions" or item.role == "developer":
        return "keep_raw", item.text
    if item.role == "user":
        if latest_user_index is not None and index == latest_user_index:
            return "keep_raw", item.text
        return "keep_excerpt", summarize_user_message(item.text)
    if item.kind == "turn_context":
        return "keep_excerpt", shorten(item.text, 320)
    if item.role == "tool":
        compact = summarize_tool_output(item.text, item.title)
        if len(item.text) > 2000:
            return "archive_only", compact
        return "summary_only", compact
    if item.role == "assistant" and item.kind == "function_call":
        return "keep_excerpt", summarize_tool_call(item)
    if item.role == "assistant":
        return "summary_only", summarize_assistant_message(item.text)
    return "keep_excerpt", shorten(item.text, 220)


def estimate_category_tokens(
    items: Sequence[NormalizedItem],
    total_tokens: int,
    attr_name: str,
) -> List[Tuple[str, int]]:
    weights: Dict[str, int] = defaultdict(int)
    for item in items:
        value = getattr(item, attr_name)
        if value <= 0:
            continue
        weights[item.category] += max(value, 1)

    total_weight = sum(weights.values())
    if total_weight <= 0:
        return []

    raw = [(category, total_tokens * weight / total_weight) for category, weight in weights.items()]
    floored = {category: int(value) for category, value in raw}
    remain = max(total_tokens - sum(floored.values()), 0)
    ranked = sorted(raw, key=lambda item: item[1] - int(item[1]), reverse=True)
    for idx in range(remain):
        floored[ranked[idx % len(ranked)][0]] += 1

    rows = sorted(floored.items(), key=lambda item: item[1], reverse=True)
    return rows


def simulate_call(
    session_file: Path,
    call_index: int,
    policy: ContextBudgetPolicy,
) -> SimulationResult:
    parsed = parse_session(session_file)
    if call_index < 1 or call_index > len(parsed.calls):
        raise IndexError(f"Call index out of range: {call_index}, session has {len(parsed.calls)} call(s)")

    call = parsed.calls[call_index - 1]
    context_items = parsed.transcript_pool[: call.context_end_index]
    input_tokens = int(value_or_unknown(call.usage, "input_tokens") or 0)

    latest_user_index = None
    for idx, item in enumerate(context_items):
        if item.role == "user" and item.kind == "message":
            latest_user_index = idx

    normalized_items: List[NormalizedItem] = []
    tool_outputs: List[Tuple[str, int]] = []
    retention_counts: Dict[str, int] = defaultdict(int)
    retention_chars: Dict[str, int] = defaultdict(int)

    for idx, item in enumerate(context_items):
        mode, compacted_text = retain_item(item, latest_user_index, idx)
        original_chars = max(len(item.text), 1)
        compacted_chars = max(len(compacted_text), 1) if mode != "archive_only" else max(len(compacted_text), 1)
        if mode == "archive_only":
            compacted_chars = min(compacted_chars, 240)

        normalized = NormalizedItem(
            index=idx + 1,
            role=item.role,
            kind=item.kind,
            title=item.title,
            category=category_for_item(item),
            retention_mode=mode,
            original_chars=original_chars,
            compacted_chars=compacted_chars,
            original_text=item.text,
            compacted_text=compacted_text,
        )
        normalized_items.append(normalized)
        retention_counts[mode] += 1
        retention_chars[mode] += original_chars
        if normalized.category == "tool_output":
            tool_outputs.append((item.title, original_chars))

    total_original_chars = sum(item.original_chars for item in normalized_items) or 1
    total_compacted_chars = sum(item.compacted_chars for item in normalized_items)
    estimated_compacted_input_tokens = int(round(input_tokens * total_compacted_chars / total_original_chars)) if input_tokens > 0 else 0
    estimated_compacted_input_tokens = min(estimated_compacted_input_tokens, input_tokens)
    estimated_saved_tokens = max(input_tokens - estimated_compacted_input_tokens, 0)
    estimated_saved_ratio = (estimated_saved_tokens / input_tokens) if input_tokens > 0 else 0.0

    before_category_tokens = estimate_category_tokens(normalized_items, input_tokens, "original_chars")
    after_category_tokens = estimate_category_tokens(normalized_items, estimated_compacted_input_tokens, "compacted_chars")

    retention_summary = sorted(
        ((mode, retention_counts[mode], retention_chars[mode]) for mode in retention_counts),
        key=lambda item: (-item[2], item[0]),
    )
    top_tool_outputs = sorted(tool_outputs, key=lambda item: (-item[1], item[0]))[:12]

    return SimulationResult(
        session_file=session_file,
        thread_id=parsed.thread_id or "unknown",
        call_index=call_index,
        input_tokens=input_tokens,
        estimated_compacted_input_tokens=estimated_compacted_input_tokens,
        estimated_saved_tokens=estimated_saved_tokens,
        estimated_saved_ratio=estimated_saved_ratio,
        pressure_before=policy.pressure_level(input_tokens),
        pressure_after=policy.pressure_level(estimated_compacted_input_tokens),
        before_category_tokens=before_category_tokens,
        after_category_tokens=after_category_tokens,
        top_tool_outputs=top_tool_outputs,
        retention_summary=retention_summary,
        working_memory=build_working_memory(context_items),
        normalized_items=normalized_items,
    )


def print_simulation(result: SimulationResult) -> None:
    print(f"session_file: {result.session_file}")
    print(f"thread_id: {result.thread_id}")
    print(f"call: {result.call_index}")
    print(f"input_tokens_before: {result.input_tokens}")
    print(f"input_tokens_after_est: {result.estimated_compacted_input_tokens}")
    print(f"estimated_saved_tokens: {result.estimated_saved_tokens}")
    print(f"estimated_saved_ratio: {result.estimated_saved_ratio * 100:.1f}%")
    print(f"pressure_before: {result.pressure_before}")
    print(f"pressure_after: {result.pressure_after}")
    print()

    print("before_category_tokens:")
    for category, tokens in result.before_category_tokens:
        print(f"  - {category}: {tokens}")
    print()

    print("after_category_tokens:")
    for category, tokens in result.after_category_tokens:
        print(f"  - {category}: {tokens}")
    print()

    print("retention_summary:")
    for mode, count, chars in result.retention_summary:
        print(f"  - {mode}: {count} items / {chars} chars")
    print()

    print("top_tool_outputs_by_chars:")
    for title, chars in result.top_tool_outputs:
        print(f"  - {title}: {chars} chars")
    print()

    memory = result.working_memory
    print("working_memory_preview:")
    print(f"  current_goal: {memory.current_goal or '-'}")
    print(f"  key_files: {', '.join(memory.key_files) if memory.key_files else '-'}")
    print(f"  key_findings: {' | '.join(memory.key_findings) if memory.key_findings else '-'}")
    print(f"  next_step: {memory.next_step or '-'}")


def resolve_target_call(
    codex_home: Path,
    latest: bool,
    thread_id: Optional[str],
    path_arg: Optional[str],
    call_index: Optional[int],
) -> Tuple[Path, int]:
    threads = load_threads(codex_home)
    path = resolve_session_path(codex_home, threads, latest, thread_id, path_arg)
    parsed = parse_session(path)
    resolved_call = call_index or len(parsed.calls)
    if resolved_call < 1 or resolved_call > len(parsed.calls):
        raise IndexError(f"Call index out of range: {resolved_call}, session has {len(parsed.calls)} call(s)")
    return path, resolved_call


def should_run_for_threshold(result: SimulationResult, threshold_k: Optional[float]) -> bool:
    if threshold_k is None:
        return True
    threshold_tokens = int(threshold_k * 1000)
    return result.input_tokens >= threshold_tokens


def print_threshold_skip(result: SimulationResult, threshold_k: float) -> None:
    print(
        f"skip: latest input {result.input_tokens} < threshold {int(threshold_k * 1000)} "
        f"({threshold_k:.1f}K)"
    )


def command_simulate(args: argparse.Namespace) -> int:
    codex_home = detect_codex_home(args.codex_home)
    path, call_index = resolve_target_call(codex_home, args.latest, args.thread_id, args.path, args.call)
    result = simulate_call(path, call_index, default_budget_policy())

    if not should_run_for_threshold(result, args.threshold_k):
        print_threshold_skip(result, args.threshold_k)
        return 0

    if args.json:
        payload = {
            "session_file": str(result.session_file),
            "thread_id": result.thread_id,
            "call_index": result.call_index,
            "input_tokens_before": result.input_tokens,
            "input_tokens_after_est": result.estimated_compacted_input_tokens,
            "estimated_saved_tokens": result.estimated_saved_tokens,
            "estimated_saved_ratio": result.estimated_saved_ratio,
            "pressure_before": result.pressure_before,
            "pressure_after": result.pressure_after,
            "before_category_tokens": result.before_category_tokens,
            "after_category_tokens": result.after_category_tokens,
            "top_tool_outputs": result.top_tool_outputs,
            "retention_summary": result.retention_summary,
            "working_memory": result.working_memory.__dict__,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print_simulation(result)
    return 0


def command_watch(args: argparse.Namespace) -> int:
    codex_home = detect_codex_home(args.codex_home)
    seen_key: Optional[Tuple[str, int]] = None

    while True:
        try:
            path, call_index = resolve_target_call(codex_home, True, args.thread_id, args.path, None)
            key = (str(path), call_index)
            if key != seen_key:
                result = simulate_call(path, call_index, default_budget_policy())
                stamp = time.strftime("%H:%M:%S")
                print(f"\n[{stamp}] session={path.name} call={call_index}")
                if should_run_for_threshold(result, args.threshold_k):
                    if args.json:
                        payload = {
                            "session_file": str(result.session_file),
                            "thread_id": result.thread_id,
                            "call_index": result.call_index,
                            "input_tokens_before": result.input_tokens,
                            "input_tokens_after_est": result.estimated_compacted_input_tokens,
                            "estimated_saved_tokens": result.estimated_saved_tokens,
                            "estimated_saved_ratio": result.estimated_saved_ratio,
                            "pressure_before": result.pressure_before,
                            "pressure_after": result.pressure_after,
                            "before_category_tokens": result.before_category_tokens,
                            "after_category_tokens": result.after_category_tokens,
                            "top_tool_outputs": result.top_tool_outputs,
                            "retention_summary": result.retention_summary,
                            "working_memory": result.working_memory.__dict__,
                        }
                        print(json.dumps(payload, ensure_ascii=False, indent=2))
                    else:
                        print_simulation(result)
                else:
                    print_threshold_skip(result, args.threshold_k)
                seen_key = key
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            stamp = time.strftime("%H:%M:%S")
            print(f"[{stamp}] watch_error: {exc}")

        time.sleep(args.interval_sec)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate Phase-1 Codex context throttling.")
    parser.add_argument("--codex-home", help="Path to the Codex home directory. Defaults to $CODEX_HOME or ~/.codex")
    sub = parser.add_subparsers(dest="command")

    simulate = sub.add_parser("simulate", help="Simulate throttling for one request")
    simulate.add_argument("--latest", action="store_true", help="Use the latest session file")
    simulate.add_argument("--thread-id", help="Use a specific thread id from the state db")
    simulate.add_argument("--path", help="Use a specific rollout jsonl file")
    simulate.add_argument("--call", type=int, help="1-based model call index; defaults to the latest call in the session")
    simulate.add_argument("--threshold-k", type=float, help="Only print simulation when input reaches this threshold in K")
    simulate.add_argument("--json", action="store_true", help="Print JSON instead of text")
    simulate.set_defaults(func=command_simulate)

    watch = sub.add_parser("watch", help="Watch latest requests and auto-run when threshold is reached")
    watch.add_argument("--thread-id", help="Optional thread id; default watches latest session")
    watch.add_argument("--path", help="Optional rollout jsonl path; default watches latest session")
    watch.add_argument("--threshold-k", type=float, required=True, help="Auto-run when input reaches this threshold in K")
    watch.add_argument("--interval-sec", type=float, default=5.0, help="Polling interval in seconds")
    watch.add_argument("--json", action="store_true", help="Print JSON instead of text")
    watch.set_defaults(func=command_watch)

    parser.set_defaults(
        command="simulate",
        func=command_simulate,
        latest=True,
        thread_id=None,
        path=None,
        call=None,
        threshold_k=None,
        json=False,
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
