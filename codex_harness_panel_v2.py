#!/usr/bin/env python3
"""
Standalone harness metrics panel V2.

This file is intentionally separate from codex_token_widget.py so the
existing monitor UI stays untouched.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional, Sequence

import tkinter as tk
from tkinter import messagebox
from tkinter import font as tkfont

from codex_context_inspector import ParsedSession, TranscriptItem, detect_codex_home, parse_session
from codex_harness_metrics_v2 import (
    HarnessMetricsAnalyzerV2,
    HarnessRequestMetricsV2,
    HarnessSessionMetricsV2,
    bucket_for_item,
    estimate_bucket_tokens,
)


WINDOW_BG = "#0d1423"
SURFACE_BG = "#11192b"
CARD_BG = "#121c30"
TITLE_BG = "#0a1220"
BORDER_COLOR = "#2a3a55"
TEXT_PRIMARY = "#f8fafc"
TEXT_MUTED = "#93a4bf"
TEXT_SOFT = "#6dd3ff"
METRIC_BLUE = "#8ab8ff"
METRIC_GREEN = "#34d399"
METRIC_ORANGE = "#fb923c"
METRIC_YELLOW = "#fde047"
METRIC_PINK = "#fb7185"
DETAIL_BG = "#0d1526"
DETAIL_BORDER = "#2b3a55"


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


def fmt_ratio(value: float) -> str:
    return f"{value:.1f}x"


def shorten_text(text: str, max_chars: int = 160) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


class HarnessPanelV2:
    def __init__(
        self,
        codex_home: Path,
        refresh_ms: int = 5000,
        session_path: Optional[str] = None,
        turn_id: Optional[str] = None,
        parent: Optional[tk.Misc] = None,
    ) -> None:
        self.codex_home = codex_home
        self.refresh_ms = refresh_ms
        self.session_path = session_path
        self.turn_id = turn_id
        self.analyzer = HarnessMetricsAnalyzerV2()
        self.parent = parent
        self.owns_mainloop = parent is None

        if parent is None:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(parent)
            self.root.transient(parent.winfo_toplevel())
        self.root.title("Codex Harness V2" if not turn_id else f"Codex Harness V2 · {turn_id[-8:]}")
        self.root.configure(bg=WINDOW_BG)
        self.root.geometry("1160x860+80+80")
        self.root.minsize(1080, 760)

        self.title_font = tkfont.Font(family="PingFang SC", size=15, weight="bold")
        self.metric_font = tkfont.Font(family="PingFang SC", size=24, weight="bold")
        self.section_font = tkfont.Font(family="PingFang SC", size=13, weight="bold")
        self.small_font = tkfont.Font(family="PingFang SC", size=11)
        self.tiny_font = tkfont.Font(family="PingFang SC", size=10)

        self.after_id: Optional[str] = None
        self.report: Optional[HarnessSessionMetricsV2] = None
        self.parsed_session: Optional[ParsedSession] = None
        self.turns_line_map: dict[int, object] = {}

        self._build_ui()
        self.root.after(100, self.refresh)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=SURFACE_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        outer.pack(fill="both", expand=True)

        title_bar = tk.Frame(outer, bg=TITLE_BG, height=44)
        title_bar.pack(fill="x")

        title_text = "Codex Harness V2" if not self.turn_id else f"Codex Harness V2 · 当前轮"
        tk.Label(title_bar, text=title_text, fg=TEXT_PRIMARY, bg=TITLE_BG, font=self.title_font).pack(
            side="left", padx=(18, 0), pady=10
        )
        self.status_label = tk.Label(title_bar, text="加载中...", fg=TEXT_SOFT, bg=TITLE_BG, font=self.tiny_font)
        self.status_label.pack(side="left", padx=(18, 0), pady=11)

        cards = tk.Frame(outer, bg=SURFACE_BG)
        cards.pack(fill="x", padx=12, pady=(12, 8))

        self.card_turn_cost = self._make_metric(cards, "平均轮次成本")
        self.card_turn_cost.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.card_rt = self._make_metric(cards, "平均轮内往返")
        self.card_rt.pack(side="left", fill="both", expand=True, padx=6)
        self.card_tool = self._make_metric(cards, "工具膨胀占比")
        self.card_tool.pack(side="left", fill="both", expand=True, padx=6)
        self.card_cache = self._make_metric(cards, "缓存命中占比")
        self.card_cache.pack(side="left", fill="both", expand=True, padx=6)
        self.card_latest = self._make_metric(cards, "最新轮成本")
        self.card_latest.pack(side="left", fill="both", expand=True, padx=(6, 0))

        middle = tk.Frame(outer, bg=SURFACE_BG)
        middle.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        middle.grid_columnconfigure(0, weight=1)
        middle.grid_columnconfigure(1, weight=2)
        middle.grid_rowconfigure(0, weight=1)

        left = tk.Frame(middle, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = tk.Frame(middle, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        tk.Label(
            left,
            text="Compact Summary" if self.turn_id else "Session Summary",
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
            font=self.section_font,
        ).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.summary_text = tk.Text(
            left,
            height=9,
            wrap="word",
            bg=CARD_BG,
            fg="#dbe4f0",
            relief="flat",
            font=("Menlo", 11),
        )
        self.summary_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        tk.Label(
            right,
            text="Requests In This Turn" if self.turn_id else "Top Turns By Cost",
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
            font=self.section_font,
        ).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.turns_text = tk.Text(
            right,
            height=11,
            wrap="none",
            bg=CARD_BG,
            fg="#dbe4f0",
            relief="flat",
            font=("Menlo", 11),
        )
        self.turns_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.turns_text.bind("<Button-1>", self._on_turns_click)

        bottom = tk.Frame(outer, bg=SURFACE_BG)
        bottom.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        bottom.grid_columnconfigure(0, weight=2)
        bottom.grid_columnconfigure(1, weight=1)
        bottom.grid_rowconfigure(0, weight=1)

        actions = tk.Frame(bottom, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        actions.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        findings = tk.Frame(bottom, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        findings.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        tk.Label(actions, text="Recommended Actions", fg=TEXT_PRIMARY, bg=CARD_BG, font=self.section_font).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.actions_text = tk.Text(
            actions,
            height=12,
            wrap="word",
            bg=CARD_BG,
            fg="#dbe4f0",
            relief="flat",
            font=("Menlo", 11),
        )
        self.actions_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        tk.Label(findings, text="Diagnosis", fg=TEXT_PRIMARY, bg=CARD_BG, font=self.section_font).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.findings_text = tk.Text(
            findings,
            height=10,
            wrap="word",
            bg=CARD_BG,
            fg="#dbe4f0",
            relief="flat",
            font=("Menlo", 11),
        )
        self.findings_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def _make_metric(self, parent: tk.Widget, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        label = tk.Label(frame, text=title, fg="#8fc7ff", bg=CARD_BG, font=self.small_font)
        label.pack(anchor="w", padx=12, pady=(10, 6))
        value = tk.Label(frame, text="-", fg=TEXT_PRIMARY, bg=CARD_BG, font=self.metric_font)
        value.pack(anchor="w", padx=12)
        detail = tk.Label(frame, text="", fg=TEXT_MUTED, bg=CARD_BG, font=self.tiny_font)
        detail.pack(anchor="w", padx=12, pady=(6, 8))
        frame.value_label = value  # type: ignore[attr-defined]
        frame.detail_label = detail  # type: ignore[attr-defined]
        return frame

    def _set_metric(self, frame: tk.Frame, value: str, detail: str, color: str) -> None:
        frame.value_label.config(text=value, fg=color)  # type: ignore[attr-defined]
        frame.detail_label.config(text=detail)  # type: ignore[attr-defined]

    def _set_text(self, widget: tk.Text, lines: List[str]) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", "\n".join(lines))
        widget.configure(state="disabled")

    def _create_detail_window(self, title: str, geometry: str) -> tk.Toplevel:
        detail = tk.Toplevel(self.root)
        detail.title(title)
        detail.configure(bg=DETAIL_BG)
        detail.geometry(geometry)
        detail.minsize(760, 560)
        return detail

    def _on_turns_click(self, event: tk.Event[tk.Text]) -> None:
        if self.report is None:
            return
        try:
            index = self.turns_text.index(f"@{event.x},{event.y}")
            line_no = int(index.split(".", 1)[0])
        except Exception:
            return
        target = self.turns_line_map.get(line_no)
        if target is None:
            return
        if isinstance(target, HarnessRequestMetricsV2):
            self._open_request_breakdown(target)
            return
        turn_id = getattr(target, "turn_id", None)
        if not turn_id:
            return
        HarnessPanelV2(
            codex_home=self.codex_home,
            refresh_ms=self.refresh_ms,
            session_path=self.session_path or (self.report.session_file if self.report else None),
            turn_id=turn_id,
            parent=self.root,
        )

    def _request_context_items(self, req: HarnessRequestMetricsV2) -> List[TranscriptItem]:
        if self.parsed_session is None:
            return []
        for call in self.parsed_session.calls:
            if call.index == req.call_index:
                return self.parsed_session.transcript_pool[: call.context_end_index]
        return []

    def _request_output_items(self, req: HarnessRequestMetricsV2) -> List[TranscriptItem]:
        if self.parsed_session is None:
            return []
        for call in self.parsed_session.calls:
            if call.index == req.call_index:
                return call.output_items
        return []

    def _build_upstream_rows(self, req: HarnessRequestMetricsV2) -> List[str]:
        items = self._request_context_items(req)
        bucket_tokens = estimate_bucket_tokens(items, req.input_tokens)
        grouped: dict[str, List[TranscriptItem]] = {}
        for item in items:
            grouped.setdefault(bucket_for_item(item), []).append(item)
        rows = ["上行分类", "-" * 48]
        for bucket, token_count in sorted(bucket_tokens.items(), key=lambda item: item[1], reverse=True):
            bucket_items = grouped.get(bucket, [])
            rows.append(f"- {bucket}: {fmt_eng(token_count)} / {len(bucket_items)} 项")
            for sample in bucket_items[:2]:
                rows.append(f"    · {sample.title}: {shorten_text(sample.text, 120)}")
        if len(rows) == 2:
            rows.append("- 无可用上行分类")
        return rows

    def _build_downstream_rows(self, req: HarnessRequestMetricsV2) -> List[str]:
        items = self._request_output_items(req)
        total_output = req.output_tokens + req.reasoning_output_tokens
        if not items or total_output <= 0:
            return ["下行分类", "-" * 48, "- 无可用下行分类"]
        weights: dict[str, int] = {}
        grouped: dict[str, List[TranscriptItem]] = {}
        for item in items:
            if item.kind == "reasoning":
                bucket = "reasoning"
            elif item.kind == "function_call":
                bucket = "tool_call"
            elif item.role == "assistant":
                bucket = "assistant_output"
            else:
                bucket = "other"
            grouped.setdefault(bucket, []).append(item)
            weights[bucket] = weights.get(bucket, 0) + max(len(item.text or ""), 1)
        total_weight = sum(weights.values())
        rows = ["下行分类", "-" * 48]
        for bucket, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True):
            token_count = int(round(total_output * weight / max(total_weight, 1)))
            bucket_items = grouped.get(bucket, [])
            rows.append(f"- {bucket}: {fmt_eng(token_count)} / {len(bucket_items)} 项")
            for sample in bucket_items[:2]:
                rows.append(f"    · {sample.title}: {shorten_text(sample.text, 120)}")
        return rows

    def _open_request_breakdown(self, req: HarnessRequestMetricsV2) -> None:
        try:
            detail = self._create_detail_window(
                title=f"Request {req.call_index} Breakdown",
                geometry="980x720+120+120",
            )
            header = tk.Label(
                detail,
                text=(
                    f"call {req.call_index}  |  input {fmt_eng(req.input_tokens)}  |  "
                    f"output {fmt_eng(req.output_tokens + req.reasoning_output_tokens)}  |  "
                    f"cache {fmt_pct(req.cache_ratio)}"
                ),
                fg=TEXT_PRIMARY,
                bg=DETAIL_BG,
                font=self.section_font,
            )
            header.pack(anchor="w", padx=16, pady=(14, 8))

            body = tk.Frame(detail, bg=DETAIL_BG)
            body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            body.grid_columnconfigure(0, weight=1)
            body.grid_columnconfigure(1, weight=1)
            body.grid_rowconfigure(0, weight=1)

            upstream = tk.Frame(body, bg=CARD_BG, highlightbackground=DETAIL_BORDER, highlightthickness=1)
            upstream.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            downstream = tk.Frame(body, bg=CARD_BG, highlightbackground=DETAIL_BORDER, highlightthickness=1)
            downstream.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

            for parent, title, rows in (
                (upstream, "Upstream Breakdown", self._build_upstream_rows(req)),
                (downstream, "Downstream Breakdown", self._build_downstream_rows(req)),
            ):
                tk.Label(parent, text=title, fg=TEXT_PRIMARY, bg=CARD_BG, font=self.section_font).pack(
                    anchor="w", padx=14, pady=(12, 8)
                )
                widget = tk.Text(
                    parent,
                    wrap="word",
                    bg=CARD_BG,
                    fg="#dbe4f0",
                    relief="flat",
                    font=("Menlo", 11),
                )
                widget.pack(fill="both", expand=True, padx=14, pady=(0, 14))
                self._set_text(widget, rows)
        except Exception as exc:
            messagebox.showerror("打开请求详情失败", str(exc))

    def _build_findings(self, report: HarnessSessionMetricsV2) -> List[str]:
        lines: List[str] = []
        scope = "这一轮" if report.focus_turn_id else "这个 session"
        if report.avg_tool_inflation_ratio >= 0.6:
            lines.append(
                f"1. {scope} 的上行主要被工具结果吃掉了，工具膨胀占比 {fmt_pct(report.avg_tool_inflation_ratio)}。"
            )
        if report.avg_round_trips_per_turn >= 6:
            lines.append(
                f"2. 平均每轮往返 {report.avg_round_trips_per_turn:.1f} 次，说明 planner / tool loop 偏长。"
            )
        if report.avg_up_down_ratio >= 20:
            lines.append(
                f"3. 上下行比 {fmt_ratio(report.avg_up_down_ratio)}，成本主要花在上下文上传，不在模型输出。"
            )
        if report.avg_cache_ratio >= 0.8:
            lines.append(
                f"4. 缓存占比 {fmt_pct(report.avg_cache_ratio)} 很高，说明大量上下文在重复上传。"
            )
        if report.hottest_turn_cost >= report.avg_turn_cost * 2:
            lines.append(
                f"5. 最热轮次成本 {fmt_eng(report.hottest_turn_cost)}，明显高于平均轮次成本 {fmt_eng(report.avg_turn_cost)}。"
            )
        if not lines:
            lines.append("当前没有特别突出的异常模式，结构相对平稳。")
        return lines

    def _build_actions(self, report: HarnessSessionMetricsV2) -> List[str]:
        lines: List[str] = []
        scope = "这一轮" if report.focus_turn_id else "这个 session"
        priority = 1

        def add_action(title: str, why: str, do: str, impact: str) -> None:
            nonlocal priority
            lines.append(f"P{priority}. {title}")
            lines.append(f"   Why: {why}")
            lines.append(f"   Do:  {do}")
            lines.append(f"   Impact: {impact}")
            lines.append("")
            priority += 1

        if report.avg_tool_inflation_ratio >= 0.6:
            add_action(
                "先治理 tool output",
                f"{scope} 有 {fmt_pct(report.avg_tool_inflation_ratio)} 的输入来自工具结果和工具调用。",
                "终端输出只保留结论+关键行；文件读取只保留命中片段；JSON 只保留关键字段；旧工具结果改成摘要+引用。",
                "通常能先把上行砍掉 30%-60%，这是最直接的收益点。",
            )
        if report.avg_round_trips_per_turn >= 6:
            add_action(
                "缩短单轮往返次数",
                f"平均每轮往返 {report.avg_round_trips_per_turn:.1f} 次，说明 planner 或 stop condition 偏松。",
                "给 planner 加最大工具步数；重试设上限；工具命中后优先收敛，不要继续扩搜。",
                "能同时降低整轮总成本和长轮次失控概率。",
            )
        if report.avg_up_down_ratio >= 20:
            add_action(
                "压缩历史上下文",
                f"上下行比 {fmt_ratio(report.avg_up_down_ratio)}，主要成本在上传，不在模型生成。",
                "只保留最近 1-2 轮原文；更早内容改成 working memory；archive 留本地，不默认重传。",
                "会降低每次请求的固定负担，让后续所有轮次都变轻。",
            )
        if report.avg_cache_ratio >= 0.8:
            add_action(
                "拆分 working memory 和 archive",
                f"缓存占比 {fmt_pct(report.avg_cache_ratio)}，说明很多旧内容在重复带入。",
                "把上下文拆成固定约束、当前目标、最近结论三层，其余历史按需回看。",
                "这样更适合做 turn 级 compact，也能减少重复上传。",
            )
        if report.total_turns > 1 and report.hottest_turn_cost >= report.avg_turn_cost * 2:
            add_action(
                "优先复盘最热轮次",
                f"最热轮次 {fmt_eng(report.hottest_turn_cost)}，显著高于平均轮次 {fmt_eng(report.avg_turn_cost)}。",
                f"先针对 hottest turn `{report.hottest_turn_id[-8:]}` 做单轮诊断，确认是否是某个工具链或提示词导致。",
                "比平均优化更快，因为先抓最大异常点往往最省时间。",
            )
        if not lines:
            add_action(
                "先建立基线",
                "当前没有特别突出的结构性异常。",
                "记录 avg turn cost / avg round trips / tool inflation 作为基线，后续每次改 harness 后做对比。",
                "你能判断优化是否真的有效，而不是只靠感觉。",
            )
        return lines

    def refresh(self) -> None:
        try:
            report = self.analyzer.analyze_latest(
                self.codex_home,
                path_arg=self.session_path,
                turn_filter=self.turn_id,
            )
            self.report = report
            self.parsed_session = parse_session(Path(report.session_file))
            self.status_label.config(text="已更新")
            self._render(report)
        except Exception as exc:
            self.status_label.config(text=f"错误: {exc}")
        finally:
            if self.after_id is not None:
                self.root.after_cancel(self.after_id)
            self.after_id = self.root.after(self.refresh_ms, self.refresh)

    def _render(self, report: HarnessSessionMetricsV2) -> None:
        self._set_metric(
            self.card_turn_cost,
            fmt_eng(report.avg_turn_cost),
            f"{report.total_turns} 轮 / hottest {fmt_eng(report.hottest_turn_cost)}",
            METRIC_BLUE,
        )
        self._set_metric(
            self.card_rt,
            f"{report.avg_round_trips_per_turn:.1f}",
            f"{report.total_round_trips} 次总往返",
            METRIC_GREEN,
        )
        self._set_metric(
            self.card_tool,
            fmt_pct(report.avg_tool_inflation_ratio),
            "tool output + tool call 占输入比例",
            METRIC_ORANGE,
        )
        self._set_metric(
            self.card_cache,
            fmt_pct(report.avg_cache_ratio),
            f"平均输入 {fmt_eng(report.avg_input_tokens_per_request)} / 请求",
            METRIC_YELLOW,
        )
        self._set_metric(
            self.card_latest,
            fmt_eng(report.latest_turn_cost),
            f"latest turn {report.latest_turn_id[-8:]}",
            METRIC_PINK,
        )

        if self.turn_id:
            summary_lines = [
                f"session_file: {Path(report.session_file).name}",
                f"thread_id:    {report.thread_id}",
                f"model:        {report.model}",
                f"focus_turn:   {report.focus_turn_id or '-'}",
                f"exact_total:  {fmt_eng(report.exact_total_tokens)}",
                f"round_trips:  {report.total_round_trips}",
                f"avg_turn:     {fmt_eng(report.avg_turn_cost)}",
                f"avg_up/down:  {fmt_ratio(report.avg_up_down_ratio)}",
                f"cache_ratio:  {fmt_pct(report.avg_cache_ratio)}",
                f"tool_ratio:   {fmt_pct(report.avg_tool_inflation_ratio)}",
            ]
        else:
            summary_lines = [
                f"session_file: {report.session_file}",
                f"thread_id:    {report.thread_id}",
                f"model:        {report.model}",
                f"focus_turn:   {report.focus_turn_id or '-'}",
                f"exact_total:  {fmt_eng(report.exact_total_tokens)}",
                f"turns:        {report.total_turns}",
                f"round_trips:  {report.total_round_trips}",
                f"avg_turn:     {fmt_eng(report.avg_turn_cost)}",
                f"avg_rt_turn:  {report.avg_round_trips_per_turn:.2f}",
                f"avg_up/down:  {fmt_ratio(report.avg_up_down_ratio)}",
                f"hottest_turn: {report.hottest_turn_id}",
                f"latest_turn:  {report.latest_turn_id}",
            ]
        self._set_text(self.summary_text, summary_lines)

        self.turns_line_map = {}
        if self.turn_id:
            turn_lines = [
                "call   input    output   cache    tool    up/down pressure",
                "-" * 68,
            ]
            for idx, req in enumerate(report.request_metrics[:20], start=3):
                downstream = req.output_tokens + req.reasoning_output_tokens
                turn_lines.append(
                    f"{req.call_index:>4} "
                    f"{fmt_eng(req.input_tokens):>8} "
                    f"{fmt_eng(downstream):>8} "
                    f"{fmt_pct(req.cache_ratio):>7} "
                    f"{fmt_pct(req.tool_inflation_ratio):>7} "
                    f"{fmt_ratio(req.up_down_ratio):>8} "
                    f"{req.pressure:>8}"
                )
                self.turns_line_map[idx] = req
        else:
            turn_lines = [
                "turn_id                              cost      rt   cache   tool    up/down pressure",
                "-" * 92,
            ]
            for idx, turn in enumerate(report.turn_metrics[:12], start=3):
                turn_lines.append(
                    f"{turn.turn_id[-12:]:<36} "
                    f"{fmt_eng(turn.total_tokens):>8} "
                    f"{turn.round_trips:>4} "
                    f"{fmt_pct(turn.cache_ratio):>7} "
                    f"{fmt_pct(turn.tool_inflation_ratio):>7} "
                    f"{fmt_ratio(turn.up_down_ratio):>8} "
                    f"{turn.pressure_peak:>8}"
                )
                self.turns_line_map[idx] = turn
        self._set_text(self.turns_text, turn_lines)
        self._set_text(self.findings_text, self._build_findings(report))
        self._set_text(self.actions_text, self._build_actions(report))

    def run(self) -> None:
        if self.owns_mainloop:
            self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone Codex harness metrics panel V2.")
    parser.add_argument("--codex-home", help="Path to Codex home. Defaults to $CODEX_HOME or ~/.codex")
    parser.add_argument("--refresh-ms", type=int, default=5000, help="Refresh interval in milliseconds")
    parser.add_argument("--path", help="Use a specific rollout jsonl file")
    parser.add_argument("--turn-id", help="Focus the panel on a specific turn id")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    codex_home = detect_codex_home(args.codex_home)
    panel = HarnessPanelV2(
        codex_home=codex_home,
        refresh_ms=args.refresh_ms,
        session_path=args.path,
        turn_id=args.turn_id,
    )
    panel.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
