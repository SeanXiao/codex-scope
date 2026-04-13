#!/usr/bin/env python3
"""
Realtime MVP for turn-level compaction opportunity tracking.

This is intentionally separate from the existing monitor and V2 windows.
It focuses on one question:

"If I compact the most expensive turn right now, how much can I actually save?"
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import font as tkfont

from codex_context_budget import default_budget_policy
from codex_context_inspector import detect_codex_home
from codex_context_throttler import simulate_call
from codex_harness_metrics_v2 import HarnessMetricsAnalyzerV2, HarnessTurnMetricsV2


WINDOW_BG = "#0d1423"
SURFACE_BG = "#11192b"
CARD_BG = "#121c30"
TITLE_BG = "#0a1220"
BORDER_COLOR = "#2a3a55"
TEXT_PRIMARY = "#f8fafc"
TEXT_MUTED = "#93a4bf"
TEXT_SOFT = "#6dd3ff"
GREEN = "#34d399"
ORANGE = "#fb923c"
YELLOW = "#fde047"
PINK = "#fb7185"
BLUE = "#8ab8ff"


def fmt_eng(value: float | int) -> str:
    abs_value = abs(float(value))
    sign = "-" if value < 0 else ""
    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs_value >= threshold:
            return f"{sign}{abs_value / threshold:.1f}".rstrip("0").rstrip(".") + suffix
    if isinstance(value, float):
        return f"{sign}{abs_value:.1f}".rstrip("0").rstrip(".")
    return f"{sign}{int(abs_value)}"


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


@dataclass
class TurnOpportunity:
    label: str
    turn_id: str
    round_trips: int
    input_before: int
    input_after_est: int
    saved_tokens: int
    saved_ratio: float
    total_tokens: int
    tool_ratio: float
    cache_ratio: float


class CompactionMVP:
    def __init__(self, refresh_ms: int = 5000) -> None:
        self.refresh_ms = refresh_ms
        self.codex_home = detect_codex_home(None)
        self.analyzer = HarnessMetricsAnalyzerV2()
        self.policy = default_budget_policy()
        self.root = tk.Tk()
        self.root.title("Codex Compaction MVP")
        self.root.configure(bg=WINDOW_BG)
        self.root.geometry("1080x720+120+120")
        self.root.minsize(980, 660)

        self.title_font = tkfont.Font(family="PingFang SC", size=15, weight="bold")
        self.metric_font = tkfont.Font(family="PingFang SC", size=30, weight="bold")
        self.section_font = tkfont.Font(family="PingFang SC", size=13, weight="bold")
        self.small_font = tkfont.Font(family="PingFang SC", size=11)
        self.tiny_font = tkfont.Font(family="PingFang SC", size=10)

        self.after_id: Optional[str] = None
        self.last_key: Optional[Tuple[str, int, int]] = None
        self.latest_opportunities: List[TurnOpportunity] = []

        self._build_ui()
        self.root.after(100, self.refresh)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=SURFACE_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        outer.pack(fill="both", expand=True)

        title_bar = tk.Frame(outer, bg=TITLE_BG, height=44)
        title_bar.pack(fill="x")
        tk.Label(title_bar, text="Codex Compaction MVP", fg=TEXT_PRIMARY, bg=TITLE_BG, font=self.title_font).pack(
            side="left", padx=(18, 0), pady=10
        )
        self.status_label = tk.Label(title_bar, text="加载中...", fg=TEXT_SOFT, bg=TITLE_BG, font=self.tiny_font)
        self.status_label.pack(side="left", padx=(18, 0), pady=11)

        hero = tk.Frame(outer, bg=SURFACE_BG)
        hero.pack(fill="x", padx=12, pady=(12, 8))
        self.best_card = self._make_big_card(hero, "Best Opportunity")
        self.best_card.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.latest_card = self._make_big_card(hero, "Latest Turn")
        self.latest_card.pack(side="left", fill="both", expand=True, padx=(6, 0))

        middle = tk.Frame(outer, bg=SURFACE_BG)
        middle.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        middle.grid_columnconfigure(0, weight=1)
        middle.grid_columnconfigure(1, weight=1)
        middle.grid_rowconfigure(0, weight=1)

        ranking = tk.Frame(middle, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        ranking.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(ranking, text="Top Savings Opportunities", fg=TEXT_PRIMARY, bg=CARD_BG, font=self.section_font).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.table_text = tk.Text(
            ranking,
            wrap="none",
            bg=CARD_BG,
            fg="#dbe4f0",
            relief="flat",
            font=("Menlo", 11),
            height=16,
        )
        self.table_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        action = tk.Frame(middle, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        action.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Label(action, text="What To Do Next", fg=TEXT_PRIMARY, bg=CARD_BG, font=self.section_font).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.action_text = tk.Text(
            action,
            wrap="word",
            bg=CARD_BG,
            fg="#dbe4f0",
            relief="flat",
            font=("Menlo", 11),
            height=16,
        )
        self.action_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def _make_big_card(self, parent: tk.Widget, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        title_label = tk.Label(frame, text=title, fg="#8fc7ff", bg=CARD_BG, font=self.small_font)
        title_label.pack(anchor="w", padx=12, pady=(10, 6))
        name_label = tk.Label(frame, text="-", fg=TEXT_PRIMARY, bg=CARD_BG, font=self.section_font)
        name_label.pack(anchor="w", padx=12)
        value_label = tk.Label(frame, text="-", fg=GREEN, bg=CARD_BG, font=self.metric_font)
        value_label.pack(anchor="w", padx=12, pady=(4, 0))
        detail_label = tk.Label(frame, text="", fg=TEXT_MUTED, bg=CARD_BG, font=self.tiny_font, justify="left")
        detail_label.pack(anchor="w", padx=12, pady=(8, 10))
        frame.name_label = name_label  # type: ignore[attr-defined]
        frame.value_label = value_label  # type: ignore[attr-defined]
        frame.detail_label = detail_label  # type: ignore[attr-defined]
        return frame

    def _set_card(self, frame: tk.Frame, name: str, value: str, detail: str, color: str) -> None:
        frame.name_label.config(text=name)  # type: ignore[attr-defined]
        frame.value_label.config(text=value, fg=color)  # type: ignore[attr-defined]
        frame.detail_label.config(text=detail)  # type: ignore[attr-defined]

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _simulate_turn(self, session_file: Path, turn: HarnessTurnMetricsV2, request_rows) -> TurnOpportunity:
        input_before = 0
        input_after_est = 0
        for req in request_rows:
            sim = simulate_call(session_file, req.call_index, self.policy)
            input_before += sim.input_tokens
            input_after_est += sim.estimated_compacted_input_tokens
        saved_tokens = max(input_before - input_after_est, 0)
        saved_ratio = (saved_tokens / input_before) if input_before else 0.0
        return TurnOpportunity(
            label=turn.turn_id[-8:],
            turn_id=turn.turn_id,
            round_trips=turn.round_trips,
            input_before=input_before,
            input_after_est=input_after_est,
            saved_tokens=saved_tokens,
            saved_ratio=saved_ratio,
            total_tokens=turn.total_tokens,
            tool_ratio=turn.tool_inflation_ratio,
            cache_ratio=turn.cache_ratio,
        )

    def _build_actions(self, best: TurnOpportunity, latest: TurnOpportunity) -> str:
        lines = [
            f"1. 先做 hottest turn `{best.label}`。",
            f"   它当前真实输入 {fmt_eng(best.input_before)}，按现有节流规则预计可省 {fmt_eng(best.saved_tokens)} ({fmt_pct(best.saved_ratio)})。",
            "",
            "2. 第一优先级：治理 tool output。",
            f"   当前 best turn 的工具膨胀占比接近 {fmt_pct(best.tool_ratio)}，说明成本主要是工具正文反复进入上下文。",
            "   建议先把 shell/file/search/api 输出统一改成: 结论 + 关键行 + 引用。",
            "",
            "3. 第二优先级：turn compact。",
            "   每轮结束后只保留 user_intent / actions_taken / key_findings / next_step，旧工具原文转 archive。",
            "",
            "4. 第三优先级：working memory / archive 分层。",
            f"   latest turn `{latest.label}` 也还有 {fmt_eng(latest.saved_tokens)} 的潜在收益，说明不是单点异常，而是结构性问题。",
            "",
            "MVP success criteria:",
            f"- hottest turn input from {fmt_eng(best.input_before)} down toward {fmt_eng(best.input_after_est)}",
            f"- latest turn input from {fmt_eng(latest.input_before)} down toward {fmt_eng(latest.input_after_est)}",
            "- tool inflation ratio visibly drops in V2",
        ]
        return "\n".join(lines)

    def _render(self, opportunities: List[TurnOpportunity]) -> None:
        best = opportunities[0]
        latest = next((item for item in opportunities if item.label == "latest"), None) or opportunities[0]
        self._set_card(
            self.best_card,
            f"turn {best.label}",
            f"save {fmt_eng(best.saved_tokens)}",
            (
                f"before {fmt_eng(best.input_before)}  ->  after {fmt_eng(best.input_after_est)}\n"
                f"{best.round_trips} rt  |  tool {fmt_pct(best.tool_ratio)}  |  cache {fmt_pct(best.cache_ratio)}"
            ),
            GREEN,
        )
        self._set_card(
            self.latest_card,
            f"turn {latest.label}",
            f"save {fmt_eng(latest.saved_tokens)}",
            (
                f"before {fmt_eng(latest.input_before)}  ->  after {fmt_eng(latest.input_after_est)}\n"
                f"{latest.round_trips} rt  |  tool {fmt_pct(latest.tool_ratio)}  |  cache {fmt_pct(latest.cache_ratio)}"
            ),
            ORANGE,
        )

        rows = ["turn        before     after      save    ratio   rt   tool   cache", "-" * 72]
        for item in opportunities:
            rows.append(
                f"{item.label:<10} "
                f"{fmt_eng(item.input_before):>8} "
                f"{fmt_eng(item.input_after_est):>8} "
                f"{fmt_eng(item.saved_tokens):>8} "
                f"{fmt_pct(item.saved_ratio):>7} "
                f"{item.round_trips:>4} "
                f"{fmt_pct(item.tool_ratio):>6} "
                f"{fmt_pct(item.cache_ratio):>7}"
            )
        self._set_text(self.table_text, "\n".join(rows))
        self._set_text(self.action_text, self._build_actions(best, latest))

    def refresh(self) -> None:
        try:
            report = self.analyzer.analyze_latest(self.codex_home)
            key = (report.session_file, report.total_round_trips, report.exact_total_tokens)
            if key != self.last_key:
                session_file = Path(report.session_file)
                opportunities: List[TurnOpportunity] = []
                latest_turn = report.latest_turn_id
                candidate_turns = report.turn_metrics[:5]
                if latest_turn and latest_turn not in {turn.turn_id for turn in candidate_turns}:
                    latest_metric = next((turn for turn in report.turn_metrics if turn.turn_id == latest_turn), None)
                    if latest_metric:
                        candidate_turns = candidate_turns + [latest_metric]

                for turn in candidate_turns:
                    reqs = [req for req in report.request_metrics if req.turn_id == turn.turn_id]
                    opp = self._simulate_turn(session_file, turn, reqs)
                    if turn.turn_id == latest_turn:
                        opp.label = "latest"
                    opportunities.append(opp)
                opportunities.sort(key=lambda item: item.saved_tokens, reverse=True)
                self.latest_opportunities = opportunities
                self._render(opportunities)
                self.last_key = key
            self.status_label.config(text=f"已更新 {time.strftime('%H:%M:%S')}")
        except Exception as exc:
            self.status_label.config(text=f"错误: {exc}")
        finally:
            if self.after_id is not None:
                self.root.after_cancel(self.after_id)
            self.after_id = self.root.after(self.refresh_ms, self.refresh)

    def run(self) -> None:
        self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Realtime MVP for Codex compaction opportunity tracking.")
    parser.add_argument("--refresh-ms", type=int, default=5000, help="Refresh interval in milliseconds")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    CompactionMVP(refresh_ms=args.refresh_ms).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
