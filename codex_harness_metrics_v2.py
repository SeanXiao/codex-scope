#!/usr/bin/env python3
"""
Harness-oriented V2 metrics model for local Codex sessions.

This file intentionally does not touch the current widget UI.
It provides a more "harness engineering" view of a session:
- turn cost
- round trips per turn
- input/output ratio
- cache ratio
- tool inflation
- context pressure
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from codex_context_budget import default_budget_policy
from codex_context_inspector import (
    TranscriptItem,
    detect_codex_home,
    load_threads,
    parse_session,
    resolve_session_path,
    value_or_unknown,
)


def pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def chars_for_items(items: Sequence[TranscriptItem]) -> int:
    return sum(max(len(item.text or ""), 1) for item in items)


def estimate_bucket_tokens(
    items: Sequence[TranscriptItem],
    input_tokens: int,
) -> Dict[str, int]:
    if input_tokens <= 0 or not items:
        return {}

    weights: Dict[str, int] = {}
    for item in items:
        bucket = bucket_for_item(item)
        weights[bucket] = weights.get(bucket, 0) + max(len(item.text or ""), 1)

    total_weight = sum(weights.values())
    if total_weight <= 0:
        return {}

    raw = {bucket: input_tokens * weight / total_weight for bucket, weight in weights.items()}
    floored = {bucket: int(value) for bucket, value in raw.items()}
    remain = max(input_tokens - sum(floored.values()), 0)
    ranked = sorted(raw.items(), key=lambda item: item[1] - int(item[1]), reverse=True)
    for idx in range(remain):
        floored[ranked[idx % len(ranked)][0]] += 1
    return floored


def bucket_for_item(item: TranscriptItem) -> str:
    if item.kind == "base_instructions":
        return "system"
    if item.role == "developer":
        return "developer"
    if item.role == "user":
        return "user"
    if item.kind == "turn_context":
        return "planner"
    if item.role == "tool":
        return "tool_output"
    if item.role == "assistant" and item.kind == "function_call":
        return "tool_call"
    if item.role == "assistant":
        return "assistant_history"
    return "other"


@dataclass
class HarnessRequestMetricsV2:
    call_index: int
    turn_id: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    context_items: int
    context_chars: int
    cache_ratio: float
    up_down_ratio: float
    tool_inflation_ratio: float
    assistant_history_ratio: float
    planner_ratio: float
    pressure: str


@dataclass
class HarnessTurnMetricsV2:
    turn_id: str
    round_trips: int
    total_tokens: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    avg_input_tokens: float
    avg_output_tokens: float
    cache_ratio: float
    up_down_ratio: float
    tool_inflation_ratio: float
    assistant_history_ratio: float
    planner_ratio: float
    pressure_peak: str


@dataclass
class HarnessSessionMetricsV2:
    session_file: str
    thread_id: str
    model: str
    focus_turn_id: Optional[str]
    total_turns: int
    total_round_trips: int
    exact_total_tokens: int
    avg_turn_cost: float
    avg_round_trips_per_turn: float
    avg_input_tokens_per_request: float
    avg_cache_ratio: float
    avg_tool_inflation_ratio: float
    avg_up_down_ratio: float
    hottest_turn_id: str
    hottest_turn_cost: int
    latest_turn_id: str
    latest_turn_cost: int
    turn_metrics: List[HarnessTurnMetricsV2]
    request_metrics: List[HarnessRequestMetricsV2]


class HarnessMetricsAnalyzerV2:
    def __init__(self) -> None:
        self.policy = default_budget_policy()

    def analyze_session(self, session_file: Path, turn_filter: Optional[str] = None) -> HarnessSessionMetricsV2:
        parsed = parse_session(session_file)
        request_metrics: List[HarnessRequestMetricsV2] = []
        turn_index: Dict[str, List[HarnessRequestMetricsV2]] = {}

        for call in parsed.calls:
            input_tokens = int(value_or_unknown(call.usage, "input_tokens") or 0)
            cached_input_tokens = int(value_or_unknown(call.usage, "cached_input_tokens") or 0)
            output_tokens = int(value_or_unknown(call.usage, "output_tokens") or 0)
            reasoning_output_tokens = int(value_or_unknown(call.usage, "reasoning_output_tokens") or 0)
            total_tokens = int(value_or_unknown(call.usage, "total_tokens") or 0)
            context_items = parsed.transcript_pool[: call.context_end_index]
            bucket_tokens = estimate_bucket_tokens(context_items, input_tokens)
            tool_tokens = bucket_tokens.get("tool_output", 0) + bucket_tokens.get("tool_call", 0)
            assistant_history_tokens = bucket_tokens.get("assistant_history", 0)
            planner_tokens = bucket_tokens.get("planner", 0)
            downstream = output_tokens + reasoning_output_tokens
            turn_id = call.turn_id or "unknown"

            metrics = HarnessRequestMetricsV2(
                call_index=call.index,
                turn_id=turn_id,
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_output_tokens=reasoning_output_tokens,
                total_tokens=total_tokens,
                context_items=len(context_items),
                context_chars=chars_for_items(context_items),
                cache_ratio=pct(cached_input_tokens, input_tokens),
                up_down_ratio=pct(input_tokens, max(downstream, 1)),
                tool_inflation_ratio=pct(tool_tokens, input_tokens),
                assistant_history_ratio=pct(assistant_history_tokens, input_tokens),
                planner_ratio=pct(planner_tokens, input_tokens),
                pressure=self.policy.pressure_level(input_tokens),
            )
            if turn_filter and metrics.turn_id != turn_filter:
                continue
            request_metrics.append(metrics)
            turn_index.setdefault(turn_id, []).append(metrics)

        turn_metrics: List[HarnessTurnMetricsV2] = []
        for turn_id, requests in turn_index.items():
            total_input = sum(item.input_tokens for item in requests)
            total_output = sum(item.output_tokens + item.reasoning_output_tokens for item in requests)
            total_cached = sum(item.cached_input_tokens for item in requests)
            total_tokens = sum(item.total_tokens for item in requests)
            pressure_peak = self._pressure_peak(requests)
            turn_metrics.append(
                HarnessTurnMetricsV2(
                    turn_id=turn_id,
                    round_trips=len(requests),
                    total_tokens=total_tokens,
                    input_tokens=total_input,
                    cached_input_tokens=total_cached,
                    output_tokens=sum(item.output_tokens for item in requests),
                    reasoning_output_tokens=sum(item.reasoning_output_tokens for item in requests),
                    avg_input_tokens=(total_input / len(requests)) if requests else 0.0,
                    avg_output_tokens=(total_output / len(requests)) if requests else 0.0,
                    cache_ratio=pct(total_cached, total_input),
                    up_down_ratio=pct(total_input, max(total_output, 1)),
                    tool_inflation_ratio=self._weighted_ratio(requests, "tool_inflation_ratio", "input_tokens"),
                    assistant_history_ratio=self._weighted_ratio(requests, "assistant_history_ratio", "input_tokens"),
                    planner_ratio=self._weighted_ratio(requests, "planner_ratio", "input_tokens"),
                    pressure_peak=pressure_peak,
                )
            )

        turn_metrics.sort(key=lambda item: item.total_tokens, reverse=True)
        hottest_turn = turn_metrics[0] if turn_metrics else None
        latest_turn = None
        if request_metrics:
            latest_turn_id = request_metrics[-1].turn_id
            latest_turn = next((item for item in turn_metrics if item.turn_id == latest_turn_id), None)

        exact_total = (
            sum(item.total_tokens for item in request_metrics)
            if turn_filter
            else parsed.exact_total_tokens or sum(item.total_tokens for item in request_metrics)
        )
        return HarnessSessionMetricsV2(
            session_file=str(session_file),
            thread_id=parsed.thread_id or "unknown",
            model=parsed.model or "unknown",
            focus_turn_id=turn_filter,
            total_turns=len(turn_metrics),
            total_round_trips=len(request_metrics),
            exact_total_tokens=exact_total,
            avg_turn_cost=(exact_total / len(turn_metrics)) if turn_metrics else 0.0,
            avg_round_trips_per_turn=(len(request_metrics) / len(turn_metrics)) if turn_metrics else 0.0,
            avg_input_tokens_per_request=(
                sum(item.input_tokens for item in request_metrics) / len(request_metrics)
                if request_metrics
                else 0.0
            ),
            avg_cache_ratio=self._weighted_ratio(request_metrics, "cache_ratio", "input_tokens"),
            avg_tool_inflation_ratio=self._weighted_ratio(request_metrics, "tool_inflation_ratio", "input_tokens"),
            avg_up_down_ratio=self._weighted_ratio(request_metrics, "up_down_ratio", "input_tokens"),
            hottest_turn_id=hottest_turn.turn_id if hottest_turn else "unknown",
            hottest_turn_cost=hottest_turn.total_tokens if hottest_turn else 0,
            latest_turn_id=latest_turn.turn_id if latest_turn else "unknown",
            latest_turn_cost=latest_turn.total_tokens if latest_turn else 0,
            turn_metrics=turn_metrics,
            request_metrics=request_metrics,
        )

    def analyze_latest(
        self,
        codex_home: Path,
        thread_id: Optional[str] = None,
        path_arg: Optional[str] = None,
        turn_filter: Optional[str] = None,
    ) -> HarnessSessionMetricsV2:
        threads = load_threads(codex_home)
        session_file = resolve_session_path(codex_home, threads, True, thread_id, path_arg)
        return self.analyze_session(session_file, turn_filter=turn_filter)

    def _pressure_peak(self, requests: Sequence[HarnessRequestMetricsV2]) -> str:
        levels = [item.pressure for item in requests]
        for level in ("critical", "high", "medium", "low"):
            if level in levels:
                return level
        return "low"

    def _weighted_ratio(self, rows: Sequence[object], attr_name: str, weight_name: str) -> float:
        total_weight = sum(getattr(row, weight_name, 0) for row in rows)
        if total_weight <= 0:
            return 0.0
        weighted_sum = sum(getattr(row, attr_name, 0.0) * getattr(row, weight_name, 0) for row in rows)
        return weighted_sum / total_weight


def print_session_report(report: HarnessSessionMetricsV2) -> None:
    print(f"session_file: {report.session_file}")
    print(f"thread_id: {report.thread_id}")
    print(f"model: {report.model}")
    print(f"exact_total_tokens: {report.exact_total_tokens}")
    print(f"total_turns: {report.total_turns}")
    print(f"total_round_trips: {report.total_round_trips}")
    print(f"avg_turn_cost: {report.avg_turn_cost:.1f}")
    print(f"avg_round_trips_per_turn: {report.avg_round_trips_per_turn:.2f}")
    print(f"avg_input_tokens_per_request: {report.avg_input_tokens_per_request:.1f}")
    print(f"avg_cache_ratio: {report.avg_cache_ratio * 100:.1f}%")
    print(f"avg_tool_inflation_ratio: {report.avg_tool_inflation_ratio * 100:.1f}%")
    print(f"avg_up_down_ratio: {report.avg_up_down_ratio:.1f}")
    print(f"hottest_turn_id: {report.hottest_turn_id}")
    print(f"hottest_turn_cost: {report.hottest_turn_cost}")
    print(f"latest_turn_id: {report.latest_turn_id}")
    print(f"latest_turn_cost: {report.latest_turn_cost}")
    print()
    print("top_turns_by_cost:")
    for turn in report.turn_metrics[:8]:
        print(
            "  - "
            f"{turn.turn_id}: cost={turn.total_tokens} "
            f"rt={turn.round_trips} "
            f"cache={turn.cache_ratio * 100:.1f}% "
            f"tool={turn.tool_inflation_ratio * 100:.1f}% "
            f"up/down={turn.up_down_ratio:.1f} "
            f"pressure={turn.pressure_peak}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Harness-oriented V2 metrics for local Codex sessions.")
    parser.add_argument("--codex-home", help="Path to the Codex home directory. Defaults to $CODEX_HOME or ~/.codex")
    parser.add_argument("--latest", action="store_true", help="Analyze the latest session")
    parser.add_argument("--thread-id", help="Use a specific thread id from the state db")
    parser.add_argument("--path", help="Use a specific rollout jsonl file")
    parser.add_argument("--turn-id", help="Focus on a specific turn id")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    codex_home = detect_codex_home(args.codex_home)
    analyzer = HarnessMetricsAnalyzerV2()
    report = analyzer.analyze_latest(
        codex_home,
        thread_id=args.thread_id,
        path_arg=args.path,
        turn_filter=args.turn_id,
    )
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        return 0
    print_session_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
