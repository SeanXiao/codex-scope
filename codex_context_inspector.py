#!/usr/bin/env python3
"""
Inspect local Codex session logs to reconstruct context payloads and exact token usage.

This tool reads:
1. ~/.codex/sessions/**/*.jsonl
2. ~/.codex/state_*.sqlite

It is designed for the local Codex desktop / CLI session format that persists:
- the full session transcript,
- per-model-call token_count events,
- per-thread total tokens_used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TIMESTAMP_RE = re.compile(r"rollout-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})-")


@dataclass
class ThreadRecord:
    thread_id: str
    rollout_path: Optional[Path]
    updated_at: Optional[int]
    title: str
    model: Optional[str]
    tokens_used: int
    cwd: str
    source: str
    provider: str


@dataclass
class TranscriptItem:
    role: str
    kind: str
    title: str
    text: str
    raw: Dict[str, Any]
    transcriptable: bool = True


@dataclass
class ModelCall:
    index: int
    turn_id: Optional[str]
    started_at: Optional[str]
    context_end_index: int
    output_items: List[TranscriptItem] = field(default_factory=list)
    usage: Optional[Dict[str, Any]] = None
    total_after: Optional[Dict[str, Any]] = None
    model_context_window: Optional[int] = None


@dataclass
class ParsedSession:
    path: Path
    thread_id: Optional[str]
    session_timestamp: Optional[str]
    model: Optional[str]
    base_instructions: Optional[str]
    transcript_pool: List[TranscriptItem]
    calls: List[ModelCall]

    @property
    def exact_total_tokens(self) -> Optional[int]:
        for call in reversed(self.calls):
            if call.total_after and call.total_after.get("total_tokens") is not None:
                return int(call.total_after["total_tokens"])
        return None


def detect_codex_home(explicit_home: Optional[str]) -> Path:
    if explicit_home:
        return Path(explicit_home).expanduser().resolve()
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()


def detect_state_db(codex_home: Path) -> Path:
    candidates = sorted(codex_home.glob("state_*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    fallback = codex_home / "state.sqlite"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Could not find a Codex state sqlite db under {codex_home}")


def sqlite_query(db_path: Path, query: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()


def load_threads(codex_home: Path) -> Dict[str, ThreadRecord]:
    db_path = detect_state_db(codex_home)
    rows = sqlite_query(
        db_path,
        """
        SELECT id, rollout_path, updated_at, title, model, tokens_used, cwd, source, model_provider
        FROM threads
        ORDER BY updated_at DESC, id DESC
        """,
    )
    threads: Dict[str, ThreadRecord] = {}
    for row in rows:
        rollout_path = Path(row["rollout_path"]).expanduser() if row["rollout_path"] else None
        threads[row["id"]] = ThreadRecord(
            thread_id=row["id"],
            rollout_path=rollout_path,
            updated_at=row["updated_at"],
            title=normalize_text(row["title"]),
            model=normalize_text(row["model"]) or None,
            tokens_used=int(row["tokens_used"] or 0),
            cwd=normalize_text(row["cwd"]),
            source=normalize_text(row["source"]),
            provider=normalize_text(row["model_provider"]),
        )
    return threads


def extract_rollout_timestamp(path: Path) -> Optional[str]:
    match = TIMESTAMP_RE.search(path.name)
    if not match:
        return None
    raw = match.group(1)
    if len(raw) != 19:
        return raw
    date_part, time_part = raw.split("T", 1)
    return f"{date_part} {time_part.replace('-', ':')}"


def iter_session_paths(codex_home: Path) -> Iterable[Path]:
    return sorted((codex_home / "sessions").rglob("*.jsonl"), key=lambda p: str(p))


def extract_message_text(content: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for item in content:
        item_type = item.get("type")
        if item_type in {"input_text", "output_text"}:
            parts.append(item.get("text", ""))
        elif item_type == "image":
            parts.append(f"[image] {item.get('image_url', '')}".strip())
        elif item_type == "input_image":
            parts.append(f"[input_image] {item.get('file_id', '')}".strip())
        else:
            parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return "\n".join(part for part in parts if part)


def summarize_turn_context(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary")
    model_context_window = None
    if isinstance(summary, dict):
        model_context_window = summary.get("model_context_window")
    selected = {
        "turn_id": payload.get("turn_id"),
        "cwd": payload.get("cwd"),
        "current_date": payload.get("current_date"),
        "timezone": payload.get("timezone"),
        "model": payload.get("model"),
        "approval_policy": payload.get("approval_policy"),
        "sandbox_policy": payload.get("sandbox_policy"),
        "personality": payload.get("personality"),
        "effort": payload.get("effort"),
        "model_context_window": model_context_window,
    }
    return json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=True)


def shorten(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " / ".join(part for part in (normalize_text(item).strip() for item in value) if part)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def parse_session(path: Path) -> ParsedSession:
    transcript_pool: List[TranscriptItem] = []
    calls: List[ModelCall] = []
    current_call: Optional[ModelCall] = None
    current_turn_id: Optional[str] = None
    base_instructions: Optional[str] = None
    session_timestamp: Optional[str] = None
    thread_id: Optional[str] = None
    model: Optional[str] = None

    def ensure_call(timestamp: Optional[str]) -> ModelCall:
        nonlocal current_call
        if current_call is None:
            current_call = ModelCall(
                index=len(calls) + 1,
                turn_id=current_turn_id,
                started_at=timestamp,
                context_end_index=len(transcript_pool),
            )
        return current_call

    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            event = json.loads(raw_line)
            timestamp = event.get("timestamp")
            event_type = event.get("type")
            payload = event.get("payload", {})

            if event_type == "session_meta":
                thread_id = payload.get("id")
                session_timestamp = payload.get("timestamp")
                model = payload.get("model") or model
                base_instructions = payload.get("base_instructions", {}).get("text")
                if base_instructions:
                    transcript_pool.append(
                        TranscriptItem(
                            role="system",
                            kind="base_instructions",
                            title="base_instructions",
                            text=base_instructions,
                            raw=payload,
                        )
                    )
                continue

            if event_type == "turn_context":
                transcript_pool.append(
                    TranscriptItem(
                        role="system",
                        kind="turn_context",
                        title=f"turn_context:{payload.get('turn_id', 'unknown')}",
                        text=summarize_turn_context(payload),
                        raw=payload,
                    )
                )
                model = payload.get("model") or model
                continue

            if event_type == "event_msg":
                inner_type = payload.get("type")
                if inner_type == "task_started":
                    current_turn_id = payload.get("turn_id")
                elif inner_type == "token_count" and payload.get("info") and current_call is not None:
                    info = payload["info"]
                    current_call.usage = info.get("last_token_usage")
                    current_call.total_after = info.get("total_token_usage")
                    current_call.model_context_window = info.get("model_context_window")
                    calls.append(current_call)
                    for item in current_call.output_items:
                        if item.transcriptable:
                            transcript_pool.append(item)
                    current_call = None
                continue

            if event_type != "response_item":
                continue

            item_type = payload.get("type")
            if item_type == "message":
                role = payload.get("role", "unknown")
                text = extract_message_text(payload.get("content", []))
                item = TranscriptItem(
                    role=role,
                    kind="message",
                    title=f"{role}_message",
                    text=text,
                    raw=payload,
                )
                if role in {"developer", "user"}:
                    transcript_pool.append(item)
                else:
                    ensure_call(timestamp).output_items.append(item)
                continue

            if item_type == "function_call":
                arguments = payload.get("arguments", "")
                item = TranscriptItem(
                    role="assistant",
                    kind="function_call",
                    title=f"function_call:{payload.get('name', 'unknown')}",
                    text=arguments,
                    raw=payload,
                )
                ensure_call(timestamp).output_items.append(item)
                continue

            if item_type == "function_call_output":
                item = TranscriptItem(
                    role="tool",
                    kind="function_call_output",
                    title=f"function_call_output:{payload.get('call_id', 'unknown')}",
                    text=payload.get("output", ""),
                    raw=payload,
                )
                transcript_pool.append(item)
                continue

            if item_type == "reasoning":
                summary_parts = []
                for part in payload.get("summary", []):
                    if part.get("type") == "summary_text":
                        summary_parts.append(part.get("text", ""))
                    else:
                        summary_parts.append(json.dumps(part, ensure_ascii=False, sort_keys=True))
                text = "\n".join(summary_parts).strip() or json.dumps(payload, ensure_ascii=False, sort_keys=True)
                item = TranscriptItem(
                    role="assistant",
                    kind="reasoning",
                    title="reasoning",
                    text=text,
                    raw=payload,
                    transcriptable=False,
                )
                ensure_call(timestamp).output_items.append(item)
                continue

    if current_call is not None:
        calls.append(current_call)

    return ParsedSession(
        path=path,
        thread_id=thread_id,
        session_timestamp=session_timestamp,
        model=model,
        base_instructions=base_instructions,
        transcript_pool=transcript_pool,
        calls=calls,
    )


def resolve_session_path(
    codex_home: Path,
    threads: Dict[str, ThreadRecord],
    latest: bool,
    thread_id: Optional[str],
    path: Optional[str],
) -> Path:
    if path:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Session file not found: {resolved}")
        return resolved

    if thread_id:
        record = threads.get(thread_id)
        if not record or not record.rollout_path:
            raise KeyError(f"Could not find thread {thread_id} in the Codex state db")
        return record.rollout_path

    if latest:
        paths = list(iter_session_paths(codex_home))
        if not paths:
            raise FileNotFoundError(f"No session files found under {codex_home / 'sessions'}")
        return paths[-1]

    raise ValueError("Please specify one of --latest, --thread-id, or --path")


def exact_tokens_for_thread(record: ThreadRecord) -> int:
    exact = record.tokens_used
    if record.rollout_path and record.rollout_path.exists():
        parsed = parse_session(record.rollout_path)
        session_total = parsed.exact_total_tokens
        if session_total is not None:
            exact = max(exact, session_total)
    return exact


def command_sessions(args: argparse.Namespace) -> int:
    codex_home = detect_codex_home(args.codex_home)
    threads = load_threads(codex_home)
    ordered = list(threads.values())
    if args.limit:
        ordered = ordered[: args.limit]

    print(f"codex_home: {codex_home}")
    print(f"sessions: {len(threads)}")
    print()
    for record in ordered:
        exact_tokens = exact_tokens_for_thread(record) if args.exact else record.tokens_used
        stamp = extract_rollout_timestamp(record.rollout_path) if record.rollout_path else "unknown"
        print(f"thread_id: {record.thread_id}")
        print(f"  timestamp: {stamp}")
        print(f"  model: {record.model or 'unknown'}")
        print(f"  tokens: {exact_tokens}")
        print(f"  cwd: {record.cwd}")
        print(f"  title: {shorten(record.title.strip(), 120)}")
        print(f"  session_file: {record.rollout_path or 'missing'}")
        print()
    return 0


def command_totals(args: argparse.Namespace) -> int:
    codex_home = detect_codex_home(args.codex_home)
    threads = load_threads(codex_home)
    total = 0
    for record in threads.values():
        total += exact_tokens_for_thread(record) if args.exact else record.tokens_used
    print(f"codex_home: {codex_home}")
    print(f"session_count: {len(threads)}")
    print(f"total_tokens: {total}")
    print(f"mode: {'exact-from-session-jsonl' if args.exact else 'state-db'}")
    return 0


def command_summary(args: argparse.Namespace) -> int:
    codex_home = detect_codex_home(args.codex_home)
    threads = load_threads(codex_home)
    path = resolve_session_path(codex_home, threads, args.latest, args.thread_id, args.path)
    parsed = parse_session(path)
    db_record = threads.get(parsed.thread_id or "")
    exact_total = parsed.exact_total_tokens
    print(f"session_file: {path}")
    print(f"thread_id: {parsed.thread_id or 'unknown'}")
    print(f"timestamp: {parsed.session_timestamp or extract_rollout_timestamp(path) or 'unknown'}")
    print(f"model: {parsed.model or (db_record.model if db_record else 'unknown')}")
    print(f"calls: {len(parsed.calls)}")
    print(f"exact_total_tokens: {exact_total if exact_total is not None else 'unknown'}")
    if db_record:
        print(f"state_db_tokens_used: {db_record.tokens_used}")
        print(f"title: {db_record.title.strip()}")
        print(f"cwd: {db_record.cwd}")
    if parsed.calls:
        last = parsed.calls[-1]
        print(f"last_call_input_tokens: {value_or_unknown(last.usage, 'input_tokens')}")
        print(f"last_call_cached_input_tokens: {value_or_unknown(last.usage, 'cached_input_tokens')}")
        print(f"last_call_output_tokens: {value_or_unknown(last.usage, 'output_tokens')}")
        print(f"last_call_reasoning_output_tokens: {value_or_unknown(last.usage, 'reasoning_output_tokens')}")
    return 0


def value_or_unknown(mapping: Optional[Dict[str, Any]], key: str) -> Any:
    if not mapping:
        return "unknown"
    value = mapping.get(key)
    return value if value is not None else "unknown"


def command_calls(args: argparse.Namespace) -> int:
    codex_home = detect_codex_home(args.codex_home)
    threads = load_threads(codex_home)
    path = resolve_session_path(codex_home, threads, args.latest, args.thread_id, args.path)
    parsed = parse_session(path)
    print(f"session_file: {path}")
    print(f"thread_id: {parsed.thread_id or 'unknown'}")
    print(f"exact_total_tokens: {parsed.exact_total_tokens if parsed.exact_total_tokens is not None else 'unknown'}")
    print()
    for call in parsed.calls:
        context_items = parsed.transcript_pool[: call.context_end_index]
        context_chars = sum(len(item.text) for item in context_items)
        kinds = ", ".join(item.title for item in call.output_items if item.kind != "reasoning") or "(no output items yet)"
        print(f"call #{call.index}")
        print(f"  turn_id: {call.turn_id or 'unknown'}")
        print(f"  started_at: {call.started_at or 'unknown'}")
        print(f"  context_items: {len(context_items)}")
        print(f"  context_chars: {context_chars}")
        print(f"  input_tokens: {value_or_unknown(call.usage, 'input_tokens')}")
        print(f"  cached_input_tokens: {value_or_unknown(call.usage, 'cached_input_tokens')}")
        print(f"  output_tokens: {value_or_unknown(call.usage, 'output_tokens')}")
        print(f"  reasoning_output_tokens: {value_or_unknown(call.usage, 'reasoning_output_tokens')}")
        print(f"  total_tokens: {value_or_unknown(call.usage, 'total_tokens')}")
        print(f"  running_total_after_call: {value_or_unknown(call.total_after, 'total_tokens')}")
        print(f"  outputs: {shorten(kinds, 200)}")
        print()
    return 0


def format_context_items(items: Sequence[TranscriptItem], max_chars: int, include_reasoning: bool) -> str:
    blocks: List[str] = []
    for index, item in enumerate(items, start=1):
        if item.kind == "reasoning" and not include_reasoning:
            continue
        blocks.append(
            "\n".join(
                [
                    f"### item {index}",
                    f"role: {item.role}",
                    f"kind: {item.kind}",
                    f"title: {item.title}",
                    "content:",
                    shorten(item.text, max_chars),
                ]
            )
        )
    return "\n\n".join(blocks)


def command_dump_context(args: argparse.Namespace) -> int:
    codex_home = detect_codex_home(args.codex_home)
    threads = load_threads(codex_home)
    path = resolve_session_path(codex_home, threads, args.latest, args.thread_id, args.path)
    parsed = parse_session(path)
    if args.call < 1 or args.call > len(parsed.calls):
        raise IndexError(f"Call index out of range: {args.call}, session has {len(parsed.calls)} call(s)")
    call = parsed.calls[args.call - 1]
    items = parsed.transcript_pool[: call.context_end_index]
    if args.json:
        payload = {
            "session_file": str(path),
            "thread_id": parsed.thread_id,
            "call_index": call.index,
            "turn_id": call.turn_id,
            "started_at": call.started_at,
            "usage": call.usage,
            "running_total_after_call": call.total_after,
            "context_items": [
                {
                    "role": item.role,
                    "kind": item.kind,
                    "title": item.title,
                    "content": item.text if args.max_chars <= 0 else shorten(item.text, args.max_chars),
                }
                for item in items
                if args.include_reasoning or item.kind != "reasoning"
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"session_file: {path}")
    print(f"thread_id: {parsed.thread_id or 'unknown'}")
    print(f"call: {call.index}")
    print(f"turn_id: {call.turn_id or 'unknown'}")
    print(f"started_at: {call.started_at or 'unknown'}")
    print(f"input_tokens: {value_or_unknown(call.usage, 'input_tokens')}")
    print(f"cached_input_tokens: {value_or_unknown(call.usage, 'cached_input_tokens')}")
    print(f"output_tokens: {value_or_unknown(call.usage, 'output_tokens')}")
    print(f"reasoning_output_tokens: {value_or_unknown(call.usage, 'reasoning_output_tokens')}")
    print(f"total_tokens: {value_or_unknown(call.usage, 'total_tokens')}")
    print()
    print(format_context_items(items, args.max_chars, args.include_reasoning))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect local Codex session context payloads and exact token usage."
    )
    parser.add_argument("--codex-home", help="Path to the Codex home directory. Defaults to $CODEX_HOME or ~/.codex")
    sub = parser.add_subparsers(dest="command", required=True)

    sessions = sub.add_parser("sessions", help="List recent sessions")
    sessions.add_argument("--limit", type=int, default=10, help="Number of sessions to print")
    sessions.add_argument("--exact", action="store_true", help="Refresh exact totals from session JSONL")
    sessions.set_defaults(func=command_sessions)

    totals = sub.add_parser("totals", help="Print total token usage across sessions")
    totals.add_argument("--exact", action="store_true", help="Refresh exact totals from session JSONL")
    totals.set_defaults(func=command_totals)

    summary = sub.add_parser("summary", help="Show one session summary")
    add_session_selector(summary)
    summary.set_defaults(func=command_summary)

    calls = sub.add_parser("calls", help="List exact token usage for each model call in a session")
    add_session_selector(calls)
    calls.set_defaults(func=command_calls)

    dump_context = sub.add_parser("dump-context", help="Print the reconstructed input context for one model call")
    add_session_selector(dump_context)
    dump_context.add_argument("--call", type=int, required=True, help="1-based model call index")
    dump_context.add_argument("--max-chars", type=int, default=2000, help="Per-item content char limit; use 0 for full")
    dump_context.add_argument("--include-reasoning", action="store_true", help="Include reasoning summary items")
    dump_context.add_argument("--json", action="store_true", help="Print JSON instead of text")
    dump_context.set_defaults(func=command_dump_context)

    return parser


def add_session_selector(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--latest", action="store_true", help="Use the latest session file")
    parser.add_argument("--thread-id", help="Use a specific thread id from the state db")
    parser.add_argument("--path", help="Use a specific rollout jsonl file")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
