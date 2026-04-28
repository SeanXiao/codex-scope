#!/usr/bin/env python3
"""
Floating Codex token monitor widget.

Features:
- draggable always-on-top widget
- latest 20 request cells
- per-request upstream / downstream bars
- current turn highlighted
- Chinese UI labels
"""

from __future__ import annotations

import argparse
import json
import platform
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import scrolledtext
from tkinter import font as tkfont
from tkinter import messagebox
from tkinter import ttk

from codex_i18n import get_label, get_string, load_language, normalize_language, save_language
from codex_context_inspector import detect_codex_home, iter_session_paths, load_threads, parse_session


WIDGET_STATE_PATH = Path("~/.codex/codex_token_widget.json").expanduser()
REFRESH_MS = 5000
BAR_LIMIT = 100
VISIBLE_BAR_SLOTS = 20
UPSTREAM_DISPLAY_CAP = 258_000
DOWNSTREAM_DISPLAY_CAP = 5_000
WINDOW_BG = "#0d1423"
SURFACE_BG = "#11192b"
CARD_BG = "#121c30"
TITLE_BG = "#0a1220"
BORDER_COLOR = "#2a3a55"
GRID_COLOR = "#27364d"
TEXT_PRIMARY = "#f8fafc"
TEXT_MUTED = "#93a4bf"
TEXT_SOFT = "#6dd3ff"
METRIC_PINK = "#ff6b86"
METRIC_BLUE = "#8ab8ff"
METRIC_YELLOW = "#ffe14d"
DETAIL_BG = "#0f172a"
DETAIL_TEXT_BG = "#111827"
DETAIL_TEXT_FG = "#e5e7eb"
DETAIL_ACCENT_BLUE = "#bfdbfe"
DETAIL_ACCENT_PINK = "#fda4af"
DETAIL_MUTED = "#e2e8f0"
TURN_PALETTE: List[Tuple[str, str]] = [
    ("#ef4444", "#fca5a5"),  # red
    ("#f97316", "#fdba74"),  # orange
    ("#eab308", "#fde68a"),  # yellow
    ("#22c55e", "#86efac"),  # green
    ("#06b6d4", "#67e8f9"),  # cyan
    ("#3b82f6", "#93c5fd"),  # blue
    ("#8b5cf6", "#c4b5fd"),  # violet
]
UPSTREAM_ATTR_SPECS: List[Tuple[str, str, str]] = [
    ("prompt", "prompt", "#38bdf8"),
    ("memory", "memory", "#8b5cf6"),
    ("planner", "planner", "#f97316"),
    ("tool", "tool", "#22c55e"),
    ("truncation", "truncation", "#f43f5e"),
    ("cache", "cache", "#fde047"),
]
BREAKDOWN_COLORS: Dict[str, str] = {
    "tool_output": "#22c55e",
    "tool_call_history": "#16a34a",
    "developer_prompt": "#38bdf8",
    "assistant_history": "#8b5cf6",
    "reasoning_output": "#f59e0b",
    "system_prompt": "#eab308",
    "runtime_context": "#f97316",
    "user_message": "#f43f5e",
    "other": "#94a3b8",
}
PIE_FALLBACK_COLORS: List[str] = [
    "#22c55e",
    "#16a34a",
    "#38bdf8",
    "#8b5cf6",
    "#f59e0b",
    "#eab308",
    "#f97316",
    "#f43f5e",
    "#94a3b8",
]


def parse_iso_utc(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def fmt_int(value: Optional[int]) -> str:
    if value is None:
        return "-"
    return f"{int(value):,}"


def fmt_k(value: Optional[int]) -> str:
    if value is None:
        return "-"
    return fmt_eng_unit(value, decimals=1)


def fmt_total_metric(value: Optional[int]) -> str:
    if value is None:
        return "-"
    abs_value = abs(int(value))
    if abs_value >= 1_000_000_000:
        return fmt_eng_unit(value, decimals=2)
    if abs_value >= 1_000_000:
        return fmt_eng_unit(value, decimals=1)
    return fmt_eng_unit(value, decimals=0)


def fmt_k_compact(value: Optional[int]) -> str:
    if value is None:
        return "-"
    return fmt_eng_unit(value, decimals=1)


def fmt_eng_unit_no_suffix(value: Optional[int], decimals: int = 1) -> str:
    if value is None:
        return "-"
    abs_value = abs(float(value))
    sign = "-" if value < 0 else ""
    units = (
        1_000_000_000,
        1_000_000,
        1_000,
    )
    for threshold in units:
        if abs_value >= threshold:
            scaled = abs_value / threshold
            quant = Decimal("1") if decimals <= 0 else Decimal(f"1.{'0' * decimals}")
            rounded = Decimal(str(scaled)).quantize(quant, rounding=ROUND_HALF_UP)
            if decimals <= 0:
                text = str(int(rounded))
            else:
                text = f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")
            return f"{sign}{text}"
    return f"{sign}{int(abs_value):,}"


def fmt_eng_unit(value: Optional[int], decimals: int = 1) -> str:
    if value is None:
        return "-"
    abs_value = abs(float(value))
    sign = "-" if value < 0 else ""
    units = (
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    )
    for threshold, suffix in units:
        if abs_value >= threshold:
            scaled = abs_value / threshold
            text = f"{scaled:.{decimals}f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    return f"{sign}{int(abs_value):,}"


def fmt_eng_unit_compact(value: Optional[int]) -> str:
    if value is None:
        return "-"
    return fmt_eng_unit(value, decimals=0)


def fmt_duration(seconds: Optional[float], lang: str) -> str:
    if seconds is None:
        return "-"
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if lang == "zh":
        if hours > 0:
            return f"{hours}小时{minutes:02d}分"
        if minutes > 0:
            return f"{minutes}分{secs:02d}秒"
        return f"{secs}秒"
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def clamp(value: int, cap: int) -> int:
    return max(0, min(value, cap))


def fmt_cn_compact(value: Optional[int]) -> str:
    if value is None:
        return "-"
    abs_value = abs(int(value))
    sign = "-" if value < 0 else ""
    if abs_value < 10000:
        return f"{sign}{abs_value:,}"
    if abs_value < 100000000:
        scaled = abs_value / 10000
        text = f"{scaled:.1f}".rstrip("0").rstrip(".")
        return f"{sign}{text}万"
    scaled = abs_value / 100000000
    text = f"{scaled:.1f}".rstrip("0").rstrip(".")
    return f"{sign}{text}亿"


def shorten(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def ensure_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " / ".join(part for part in (ensure_text(item).strip() for item in value) if part)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


@dataclass
class RequestPoint:
    thread_id: str
    turn_id: str
    session_file: Path
    call_index: int
    timestamp: Optional[datetime]
    total_tokens: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    user_text: str = ""
    upstream_breakdown: Tuple[Tuple[str, int, int], ...] = ()
    downstream_breakdown: Tuple[Tuple[str, int, int], ...] = ()

    @property
    def upstream_tokens(self) -> int:
        return self.input_tokens

    @property
    def downstream_tokens(self) -> int:
        return self.output_tokens + self.reasoning_output_tokens


@dataclass
class SessionSnapshot:
    thread_id: str
    session_file: Path
    title: str
    updated_at: int
    total_tokens: int
    requests: List[RequestPoint]


@dataclass
class DashboardSnapshot:
    generated_at: datetime
    latest_session: Optional[SessionSnapshot]
    latest_request: Optional[RequestPoint]
    previous_request: Optional[RequestPoint]
    current_turn_id: Optional[str]
    current_turn_requests: List[RequestPoint]
    current_turn_total: int
    daily_totals: List[Tuple[date, int]]
    today_requests: List[RequestPoint]
    yesterday_requests: List[RequestPoint]
    all_requests: List[RequestPoint]
    today_total: int
    yesterday_total: int
    all_total: int
    today_total_duration_seconds: float
    yesterday_total_duration_seconds: float
    all_total_duration_seconds: float
    today_new_session_count: int
    today_turn_count: int
    yesterday_new_session_count: int
    yesterday_turn_count: int
    yesterday_round_trip_count: int
    all_session_count: int
    all_turn_count: int


class SessionCache:
    def __init__(self, codex_home: Path) -> None:
        self.codex_home = codex_home
        self._cache: Dict[Path, Tuple[int, int, SessionSnapshot]] = {}

    def refresh(self) -> DashboardSnapshot:
        thread_map = load_threads(self.codex_home)
        snapshots: List[SessionSnapshot] = []
        seen_paths = set()

        for path in iter_session_paths(self.codex_home):
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            key = (int(stat.st_mtime_ns), int(stat.st_size))
            cached = self._cache.get(path)
            if cached and cached[0] == key[0] and cached[1] == key[1]:
                snapshot = cached[2]
            else:
                snapshot = self._parse_one(path, thread_map)
                self._cache[path] = (key[0], key[1], snapshot)
            snapshots.append(snapshot)
            seen_paths.add(path)

        stale = [path for path in self._cache if path not in seen_paths]
        for path in stale:
            del self._cache[path]

        snapshots.sort(key=lambda item: item.updated_at)
        all_requests: List[RequestPoint] = []
        for snapshot in snapshots:
            all_requests.extend(snapshot.requests)
        fallback = datetime.min.replace(tzinfo=timezone.utc).astimezone()
        all_requests.sort(key=lambda item: (item.timestamp or fallback, item.thread_id, item.call_index))

        now = datetime.now().astimezone()
        today = now.date()
        yesterday = today - timedelta(days=1)
        today_requests = [item for item in all_requests if item.timestamp and item.timestamp.date() == today]
        yesterday_requests = [item for item in all_requests if item.timestamp and item.timestamp.date() == yesterday]

        latest_session = snapshots[-1] if snapshots else None
        latest_request = all_requests[-1] if all_requests else None
        previous_request = all_requests[-2] if len(all_requests) >= 2 else None
        current_turn_id = latest_request.turn_id if latest_request else None
        current_turn_requests = [item for item in all_requests if current_turn_id and item.turn_id == current_turn_id]
        current_turn_total = sum(item.total_tokens for item in current_turn_requests)
        today_turn_count = len({(item.thread_id, item.turn_id) for item in today_requests})
        yesterday_turn_count = len({(item.thread_id, item.turn_id) for item in yesterday_requests})
        all_turn_count = len({(item.thread_id, item.turn_id) for item in all_requests})
        turn_requests_map: Dict[Tuple[str, str], List[RequestPoint]] = defaultdict(list)
        for item in all_requests:
            turn_requests_map[(item.thread_id, item.turn_id)].append(item)
        today_total_duration_seconds = 0.0
        yesterday_total_duration_seconds = 0.0
        all_total_duration_seconds = 0.0
        for requests in turn_requests_map.values():
            timestamps = [item.timestamp for item in requests if item.timestamp]
            if not timestamps:
                continue
            first_ts = min(timestamps)
            last_ts = max(timestamps)
            duration_seconds = max(0.0, (last_ts - first_ts).total_seconds())
            all_total_duration_seconds += duration_seconds
            if first_ts.date() == today:
                today_total_duration_seconds += duration_seconds
            elif first_ts.date() == yesterday:
                yesterday_total_duration_seconds += duration_seconds
        today_new_session_count = 0
        yesterday_new_session_count = 0
        for snapshot in snapshots:
            if not snapshot.requests:
                continue
            first_ts = snapshot.requests[0].timestamp
            if not first_ts:
                continue
            if first_ts.date() == today:
                today_new_session_count += 1
            elif first_ts.date() == yesterday:
                yesterday_new_session_count += 1
        daily_map: Dict[date, int] = {}
        for item in all_requests:
            if item.timestamp:
                day = item.timestamp.date()
                daily_map[day] = daily_map.get(day, 0) + item.total_tokens
        daily_totals = []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            daily_totals.append((day, daily_map.get(day, 0)))
        today_total = sum(item.total_tokens for item in today_requests)
        yesterday_total = sum(item.total_tokens for item in yesterday_requests)
        all_total = sum(item.total_tokens for item in all_requests)

        return DashboardSnapshot(
            generated_at=now,
            latest_session=latest_session,
            latest_request=latest_request,
            previous_request=previous_request,
            current_turn_id=current_turn_id,
            current_turn_requests=current_turn_requests,
            current_turn_total=current_turn_total,
            daily_totals=daily_totals,
            today_requests=today_requests,
            yesterday_requests=yesterday_requests,
            all_requests=all_requests,
            today_total=today_total,
            yesterday_total=yesterday_total,
            all_total=all_total,
            today_total_duration_seconds=today_total_duration_seconds,
            yesterday_total_duration_seconds=yesterday_total_duration_seconds,
            all_total_duration_seconds=all_total_duration_seconds,
            today_new_session_count=today_new_session_count,
            today_turn_count=today_turn_count,
            yesterday_new_session_count=yesterday_new_session_count,
            yesterday_turn_count=yesterday_turn_count,
            yesterday_round_trip_count=len(yesterday_requests),
            all_session_count=len(snapshots),
            all_turn_count=all_turn_count,
        )

    def _parse_one(self, path: Path, thread_map: Dict[str, object]) -> SessionSnapshot:
        parsed = parse_session(path)
        record = thread_map.get(parsed.thread_id or "")
        requests: List[RequestPoint] = []
        for call in parsed.calls:
            usage = call.usage or {}
            total_tokens = int(usage.get("total_tokens") or 0)
            if total_tokens <= 0:
                continue
            context_items = parsed.transcript_pool[: call.context_end_index]
            requests.append(
                RequestPoint(
                    thread_id=parsed.thread_id or "unknown",
                    turn_id=call.turn_id or "unknown",
                    session_file=path,
                    call_index=call.index,
                    timestamp=parse_iso_utc(call.started_at),
                    total_tokens=total_tokens,
                    input_tokens=int(usage.get("input_tokens") or 0),
                    cached_input_tokens=int(usage.get("cached_input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    reasoning_output_tokens=int(usage.get("reasoning_output_tokens") or 0),
                    user_text=self._latest_user_text(context_items),
                    upstream_breakdown=tuple(
                        self._estimate_upstream_breakdown_static(
                            context_items,
                            int(usage.get("input_tokens") or 0),
                        )
                    ),
                    downstream_breakdown=tuple(
                        self._estimate_downstream_breakdown_static(
                            call.output_items,
                            int(usage.get("output_tokens") or 0),
                            int(usage.get("reasoning_output_tokens") or 0),
                        )
                    ),
                )
            )

        if parsed.exact_total_tokens is not None:
            total_tokens = parsed.exact_total_tokens
        elif record is not None:
            total_tokens = int(getattr(record, "tokens_used", 0) or 0)
        else:
            total_tokens = sum(item.total_tokens for item in requests)

        title = ensure_text(getattr(record, "title", "")) if record is not None else ""
        updated_at = getattr(record, "updated_at", 0) if record is not None else 0
        if not updated_at:
            try:
                updated_at = int(path.stat().st_mtime * 1000)
            except FileNotFoundError:
                updated_at = 0

        return SessionSnapshot(
            thread_id=parsed.thread_id or "unknown",
            session_file=path,
            title=ensure_text(title).strip() or path.stem,
            updated_at=updated_at,
            total_tokens=total_tokens,
            requests=requests,
        )

    def _latest_user_text(self, context_items: Sequence[object]) -> str:
        for item in reversed(context_items):
            if getattr(item, "role", "") == "user" and getattr(item, "kind", "") == "message":
                return getattr(item, "text", "") or ""
        return ""

    def _category_label_static(self, ctx: object) -> str:
        role = getattr(ctx, "role", "")
        kind = getattr(ctx, "kind", "")
        title = getattr(ctx, "title", "")
        if kind == "base_instructions":
            return "system_prompt"
        if role == "developer":
            return "developer_prompt"
        if role == "user":
            return "user_message"
        if kind == "turn_context":
            return "runtime_context"
        if role == "tool":
            return "tool_output"
        if role == "assistant" and kind == "function_call":
            return "tool_call_history"
        if role == "assistant":
            return "assistant_history"
        return title or kind or role or "other"

    def _estimate_upstream_breakdown_static(
        self,
        context_items: Sequence[object],
        input_tokens: int,
    ) -> List[Tuple[str, int, int]]:
        category_weights: Dict[str, int] = defaultdict(int)
        category_counts: Dict[str, int] = defaultdict(int)
        for ctx in context_items:
            label = self._category_label_static(ctx)
            text = getattr(ctx, "text", "") or ""
            weight = max(len(text), 1)
            category_weights[label] += weight
            category_counts[label] += 1

        total_weight = sum(category_weights.values())
        if total_weight <= 0:
            return []

        raw_allocations = [(label, input_tokens * weight / total_weight) for label, weight in category_weights.items()]
        floored: Dict[str, int] = {label: int(value) for label, value in raw_allocations}
        remain = input_tokens - sum(floored.values())
        ranked = sorted(raw_allocations, key=lambda item: item[1] - int(item[1]), reverse=True)
        for idx in range(remain):
            floored[ranked[idx % len(ranked)][0]] += 1

        rows = [(label, floored[label], category_counts[label]) for label in floored]
        rows.sort(key=lambda item: item[1], reverse=True)
        return rows

    def _downstream_label_static(self, out: object) -> str:
        role = getattr(out, "role", "")
        kind = getattr(out, "kind", "")
        if kind == "reasoning":
            return "reasoning_output"
        if role == "assistant" and kind == "function_call":
            return "tool_call_history"
        if role == "assistant":
            return "assistant_history"
        return "other"

    def _estimate_downstream_breakdown_static(
        self,
        output_items: Sequence[object],
        output_tokens: int,
        reasoning_output_tokens: int,
    ) -> List[Tuple[str, int, int]]:
        allocations: Dict[str, int] = defaultdict(int)
        counts: Dict[str, int] = defaultdict(int)

        if reasoning_output_tokens > 0:
            allocations["reasoning_output"] += reasoning_output_tokens
            counts["reasoning_output"] += sum(1 for out in output_items if getattr(out, "kind", "") == "reasoning")

        weighted_items: List[Tuple[str, int]] = []
        for out in output_items:
            if getattr(out, "kind", "") == "reasoning":
                continue
            label = self._downstream_label_static(out)
            text = getattr(out, "text", "") or ""
            weight = max(len(text), 1)
            weighted_items.append((label, weight))
            counts[label] += 1

        if output_tokens > 0:
            total_weight = sum(weight for _label, weight in weighted_items)
            if total_weight <= 0:
                allocations["assistant_history"] += output_tokens
                counts["assistant_history"] += 1
            else:
                raw_allocations = [(label, output_tokens * weight / total_weight) for label, weight in weighted_items]
                floored: Dict[str, int] = defaultdict(int)
                for label, value in raw_allocations:
                    floored[label] += int(value)
                remain = output_tokens - sum(floored.values())
                ranked = sorted(raw_allocations, key=lambda item: item[1] - int(item[1]), reverse=True)
                for idx in range(remain):
                    floored[ranked[idx % len(ranked)][0]] += 1
                for label, value in floored.items():
                    allocations[label] += value

        rows = [(label, allocations[label], counts[label]) for label in allocations]
        rows.sort(key=lambda item: item[1], reverse=True)
        return rows


class TokenMonitorWidget:
    def __init__(self, codex_home: Path, refresh_ms: int = REFRESH_MS, lang: Optional[str] = None) -> None:
        self.codex_home = codex_home
        self.refresh_ms = refresh_ms
        self.cache = SessionCache(codex_home)
        self.lang = normalize_language(lang) if lang else load_language()
        self.is_macos = platform.system() == "Darwin"
        self.use_borderless = not self.is_macos
        self.root = tk.Tk()
        self.root.withdraw()
        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(self.use_borderless)
        self.window.title(self._t("monitor.window_title"))
        self.window.configure(bg=WINDOW_BG)

        self.state = self._load_state()
        geometry = self.state.get("geometry", "920x534+60+80")
        self.window.geometry(geometry)
        self.window.minsize(900, 520)

        self.drag_origin: Optional[Tuple[int, int]] = None
        self.refresh_inflight = False
        self.latest_snapshot: Optional[DashboardSnapshot] = None
        self.after_id: Optional[str] = None
        self.chart_regions: List[Tuple[Tuple[float, float, float, float], RequestPoint, str]] = []
        self.turn_label_regions: List[Tuple[Tuple[float, float, float, float], str]] = []
        self.chart_animation_after: Optional[str] = None
        self.last_chart_keys: Tuple[str, ...] = ()

        self.title_font = tkfont.Font(family="PingFang SC", size=15, weight="bold")
        self.metric_font = tkfont.Font(family="PingFang SC", size=22, weight="bold")
        self.small_font = tkfont.Font(family="PingFang SC", size=11)
        self.tiny_font = tkfont.Font(family="PingFang SC", size=10)
        self._init_detail_styles()

        self._build_ui()
        self.window.deiconify()
        self.window.after(100, self.refresh_async)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def _t(self, key: str, **kwargs: object) -> str:
        return get_string(key, self.lang, **kwargs)

    def _label(self, key: str) -> str:
        return ensure_text(get_label(key, self.lang))

    def _load_state(self) -> Dict[str, object]:
        if WIDGET_STATE_PATH.exists():
            try:
                return json.loads(WIDGET_STATE_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_state(self) -> None:
        WIDGET_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "geometry": self.window.geometry(),
        }
        WIDGET_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _toggle_language(self) -> None:
        next_lang = "zh" if self.lang == "en" else "en"
        self.lang = save_language(next_lang)
        self._apply_language()
        if self.latest_snapshot is not None:
            self._apply_snapshot(self.latest_snapshot)
        else:
            self.status_label.config(text=self._t("monitor.status.loading"))

    def _apply_language(self) -> None:
        self.window.title(self._t("monitor.window_title"))
        self.title_label.config(text=self._t("monitor.window_title"))
        self.lang_button.config(text=self._t("language.toggle"))
        if self.latest_snapshot is None:
            self._set_metric_title(self.today_metric, self._t("monitor.metric.today_title", duration="-"))
            self._set_metric_title(self.yesterday_metric, self._t("monitor.metric.yesterday_title", duration="-"))
            self._set_metric_title(self.all_metric, self._t("monitor.metric.total_title", duration="-"))

    def _build_ui(self) -> None:
        outer = tk.Frame(self.window, bg=SURFACE_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        outer.pack(fill="both", expand=True)

        title_bar = tk.Frame(outer, bg=TITLE_BG, height=44)
        title_bar.pack(fill="x")
        if self.use_borderless:
            title_bar.bind("<ButtonPress-1>", self._on_drag_start)
            title_bar.bind("<B1-Motion>", self._on_drag_move)
            title_bar.bind("<ButtonRelease-1>", self._on_drag_end)

            controls = tk.Frame(title_bar, bg=TITLE_BG)
            controls.pack(side="left", padx=(12, 8), pady=8)
            self._make_title_dot(controls, "#ff5f57", self.close).pack(side="left", padx=(0, 8))
            self._make_title_dot(controls, "#febc2e", self.refresh_async).pack(side="left", padx=(0, 8))
            self._make_title_dot(controls, "#28c840", self._focus_window).pack(side="left")

        self.title_label = tk.Label(
            title_bar,
            text=self._t("monitor.window_title"),
            fg=TEXT_PRIMARY,
            bg=TITLE_BG,
            font=self.title_font,
        )
        self.title_label.pack(side="left", padx=(14 if self.use_borderless else 18, 0), pady=10)
        if self.use_borderless:
            self.title_label.bind("<ButtonPress-1>", self._on_drag_start)
            self.title_label.bind("<B1-Motion>", self._on_drag_move)
            self.title_label.bind("<ButtonRelease-1>", self._on_drag_end)

        self.status_label = tk.Label(
            title_bar,
            text=self._t("monitor.status.loading"),
            fg=TEXT_SOFT,
            bg=TITLE_BG,
            font=self.tiny_font,
        )
        self.lang_button = self._make_detail_action_button(
            title_bar,
            text=self._t("language.toggle"),
            command=self._toggle_language,
            kind="secondary",
        )
        self.lang_button.pack(side="right", padx=(0, 8), pady=7)
        self.header_daily_label = tk.Label(
            title_bar,
            text="",
            fg=TEXT_MUTED,
            bg=TITLE_BG,
            font=self.tiny_font,
        )
        self.header_daily_label.pack(side="right", padx=(0, 8), pady=11)

        chart_card = tk.Frame(outer, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        chart_card.pack(fill="both", expand=True, padx=12, pady=(12, 8))

        self.canvas = tk.Canvas(chart_card, height=320, bg=CARD_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        footer = tk.Frame(outer, bg=SURFACE_BG)
        footer.pack(fill="x", padx=12, pady=(0, 12))

        self.legend_frame = tk.Frame(footer, bg=SURFACE_BG)
        self.legend_frame.pack(fill="x")

        stats = tk.Frame(outer, bg=SURFACE_BG)
        stats.pack(fill="x", padx=12, pady=(0, 12))

        self.today_metric = self._make_metric(stats, self._t("monitor.metric.today_title", duration="-"))
        self.today_metric.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.yesterday_metric = self._make_metric(stats, self._t("monitor.metric.yesterday_title", duration="-"))
        self.yesterday_metric.pack(side="left", fill="both", expand=True, padx=4)
        self.all_metric = self._make_metric(stats, self._t("monitor.metric.total_title", duration="-"))
        self.all_metric.pack(side="left", fill="both", expand=True, padx=(4, 0))

    def _make_metric(self, parent: tk.Widget, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
        label = tk.Label(frame, text=title, fg="#78a2cf", bg=CARD_BG, font=self.small_font)
        label.pack(anchor="w", padx=12, pady=(10, 6))
        value = tk.Label(frame, text="-", fg=TEXT_PRIMARY, bg=CARD_BG, font=self.metric_font)
        value.pack(anchor="w", padx=12)
        detail = tk.Label(frame, text="", fg=TEXT_MUTED, bg=CARD_BG, font=self.tiny_font, justify="left", anchor="w")
        detail.pack(anchor="w", padx=12, pady=(6, 8))
        frame.title_label = label  # type: ignore[attr-defined]
        frame.value_label = value  # type: ignore[attr-defined]
        frame.detail_label = detail  # type: ignore[attr-defined]
        return frame

    def _make_title_dot(self, parent: tk.Widget, color: str, command) -> tk.Label:
        dot = tk.Label(parent, text="●", fg=color, bg=TITLE_BG, cursor="hand2", font=self.small_font)
        dot.bind("<Button-1>", lambda _event: command())
        return dot

    def _make_detail_action_button(
        self,
        parent: tk.Widget,
        *,
        text: str,
        command,
        kind: str = "secondary",
        text_color: Optional[str] = None,
    ) -> tk.Label:
        if kind == "primary":
            bg = DETAIL_TEXT_BG
            fg = "#dbeafe"
            hover_bg = "#16233a"
            hover_fg = "#eff6ff"
            border = "#35507a"
        else:
            bg = DETAIL_TEXT_BG
            fg = "#cbd5e1"
            hover_bg = "#18243c"
            hover_fg = "#f8fafc"
            border = "#31415f"
        fg = text_color or fg
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
            font=self.tiny_font,
            cursor="hand2",
            borderwidth=1,
        )
        button.bind("<Button-1>", lambda _event: command())
        button.bind("<Enter>", lambda _event: button.configure(bg=hover_bg, fg=hover_fg))
        button.bind("<Leave>", lambda _event: button.configure(bg=bg, fg=fg))
        button.configure(highlightbackground=border)
        return button

    def _init_detail_styles(self) -> None:
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("CodexScope.TNotebook", background=DETAIL_BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "CodexScope.TNotebook.Tab",
            background=DETAIL_TEXT_BG,
            foreground=TEXT_MUTED,
            padding=(14, 8),
            borderwidth=0,
        )
        style.map(
            "CodexScope.TNotebook.Tab",
            background=[("selected", "#18243c"), ("active", "#16233a")],
            foreground=[("selected", "#f8fafc"), ("active", "#eff6ff")],
        )

    def _detail_color(self, label: str, index: int = 0) -> str:
        return BREAKDOWN_COLORS.get(label, PIE_FALLBACK_COLORS[index % len(PIE_FALLBACK_COLORS)])

    def _create_detail_notebook(self, parent: tk.Widget) -> ttk.Notebook:
        notebook = ttk.Notebook(parent, style="CodexScope.TNotebook")
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        return notebook

    def _create_scrollable_detail_frame(self, parent: tk.Widget) -> tk.Frame:
        shell = tk.Frame(parent, bg=DETAIL_BG)
        shell.pack(fill="both", expand=True)

        canvas = tk.Canvas(shell, bg=DETAIL_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        content = tk.Frame(canvas, bg=DETAIL_BG)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def sync_scrollregion(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_width(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def on_mousewheel(event) -> str | None:
            delta = event.delta
            if delta == 0:
                return None
            canvas.yview_scroll(int(-delta / 120), "units")
            return "break"

        content.bind("<Configure>", sync_scrollregion)
        canvas.bind("<Configure>", sync_width)
        canvas.bind("<MouseWheel>", on_mousewheel)
        content.bind("<MouseWheel>", on_mousewheel)
        return content

    def _create_tagged_detail_text(self, parent: tk.Widget) -> scrolledtext.ScrolledText:
        text = self._create_detail_text(parent)
        text.tag_configure("section", foreground="#dbeafe", font=("Menlo", 12, "bold"))
        text.tag_configure("meta_key", foreground="#93c5fd", font=("Menlo", 11, "bold"))
        text.tag_configure("meta_value", foreground=DETAIL_TEXT_FG, font=("Menlo", 11))
        text.tag_configure("body", foreground=DETAIL_TEXT_FG, font=("Menlo", 11))
        return text

    def _append_meta_line(self, text: scrolledtext.ScrolledText, key: str, value: str, value_tag: str = "meta_value") -> None:
        text.insert("end", f"{ensure_text(key)}: ", ("meta_key",))
        text.insert("end", f"{ensure_text(value)}\n", (value_tag,))

    def _append_content_block(self, text: scrolledtext.ScrolledText, header: str, body: str, color_tag: str) -> None:
        text.insert("end", f"{ensure_text(header)}\n", ("section", color_tag))
        text.insert("end", ensure_text(body).rstrip() + "\n\n", ("body",))

    def _build_breakdown_summary_panel(
        self,
        parent: tk.Widget,
        rows: Sequence[Tuple[str, int, int]],
        *,
        title: str,
        total_tokens: int,
    ) -> None:
        shell = tk.Frame(parent, bg=DETAIL_BG)
        shell.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        title_label = tk.Label(shell, text=title, fg="#dbeafe", bg=DETAIL_BG, anchor="w", font=self.small_font)
        title_label.pack(fill="x", pady=(0, 8))

        grid = tk.Frame(shell, bg=DETAIL_BG)
        grid.pack(fill="both", expand=True)
        for idx, (label, tokens, count) in enumerate(rows):
            color = self._detail_color(label, idx)
            card = tk.Frame(grid, bg=DETAIL_TEXT_BG, highlightbackground=BORDER_COLOR, highlightthickness=1)
            row = idx // 2
            col = idx % 2
            card.grid(row=row, column=col, sticky="nsew", padx=(0, 8) if col == 0 else (8, 0), pady=(0, 8))
            grid.grid_columnconfigure(col, weight=1)

            pct = (tokens / total_tokens * 100.0) if total_tokens > 0 else 0.0
            tk.Label(card, text=self._label(label), fg=color, bg=DETAIL_TEXT_BG, anchor="w", font=self.small_font).pack(fill="x", padx=12, pady=(10, 4))
            tk.Label(card, text=fmt_k(tokens), fg="#f8fafc", bg=DETAIL_TEXT_BG, anchor="w", font=self.metric_font).pack(fill="x", padx=12)
            detail_text = (
                f"{pct:.1f}% / {count} items"
                if self.lang == "en"
                else f"{pct:.1f}% / {count} 项"
            )
            tk.Label(card, text=detail_text, fg=TEXT_MUTED, bg=DETAIL_TEXT_BG, anchor="w", font=self.tiny_font).pack(fill="x", padx=12, pady=(4, 10))

    def _build_category_browser(
        self,
        parent: tk.Widget,
        grouped: Dict[str, List[object]],
        render_item,
    ) -> None:
        pane = tk.PanedWindow(parent, orient="horizontal", bg=DETAIL_BG, sashwidth=8, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        nav = tk.Frame(pane, bg=DETAIL_BG)
        body = tk.Frame(pane, bg=DETAIL_BG)
        pane.add(nav, minsize=220)
        pane.add(body, minsize=520)

        text = self._create_tagged_detail_text(body)
        categories = list(grouped.keys())
        if not categories:
            text.insert("1.0", self._t("detail.output.none"))
            text.configure(state="disabled")
            return

        def show_category(category: str) -> None:
            text.configure(state="normal")
            text.delete("1.0", "end")
            color = self._detail_color(category, categories.index(category))
            tag_name = f"category_{category}"
            text.tag_configure(tag_name, foreground=color, font=("Menlo", 12, "bold"))
            items = grouped.get(category, [])
            self._append_content_block(
                text,
                f"{self._label(category)} ({len(items)})",
                (
                    "Use the items below to inspect this category."
                    if self.lang == "en"
                    else "下面按该分类展示明细，方便快速定位。"
                ),
                tag_name,
            )
            for idx, entry in enumerate(items, start=1):
                render_item(text, entry, idx, tag_name)
            text.configure(state="disabled")

        for index, category in enumerate(categories):
            color = self._detail_color(category, index)
            button = self._make_detail_action_button(
                nav,
                text=f"{self._label(category)} ({len(grouped[category])})",
                command=lambda category=category: show_category(category),
                kind="secondary",
            )
            button.configure(fg=color)
            button.pack(fill="x", pady=(0, 8))

        show_category(categories[0])

    def _set_metric(self, frame: tk.Frame, value: str, detail: str, color: str = "#f8fafc") -> None:
        frame.value_label.config(text=value, fg=color)  # type: ignore[attr-defined]
        frame.detail_label.config(text=detail)  # type: ignore[attr-defined]

    def _set_metric_title(self, frame: tk.Frame, title: str) -> None:
        frame.title_label.config(text=title)  # type: ignore[attr-defined]

    def _create_detail_window(
        self,
        title: str,
        geometry: str,
        header_text: str,
        subheader_text: str,
        subheader_fg: str,
    ) -> tk.Toplevel:
        detail_window = tk.Toplevel(self.window)
        detail_window.title(title)
        detail_window.geometry(geometry)
        detail_window.configure(bg=DETAIL_BG)

        header = tk.Label(
            detail_window,
            text=header_text,
            fg=DETAIL_MUTED,
            bg=DETAIL_BG,
            anchor="w",
            justify="left",
            font=self.small_font,
        )
        header.pack(fill="x", padx=12, pady=(12, 8))

        subheader = tk.Label(
            detail_window,
            text=subheader_text,
            fg=subheader_fg,
            bg=DETAIL_BG,
            anchor="w",
            justify="left",
            font=self.tiny_font,
        )
        subheader.pack(fill="x", padx=12, pady=(0, 8))
        return detail_window

    def _create_detail_text(self, parent: tk.Widget) -> scrolledtext.ScrolledText:
        text = scrolledtext.ScrolledText(
            parent,
            wrap="word",
            bg=DETAIL_TEXT_BG,
            fg=DETAIL_TEXT_FG,
            insertbackground=DETAIL_TEXT_FG,
            relief="flat",
            font=("Menlo", 11),
        )
        text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        return text

    def _update_footer_labels(self, snapshot: DashboardSnapshot) -> None:
        latest = snapshot.latest_request
        latest_time = latest.timestamp.strftime("%H:%M:%S") if latest and latest.timestamp else "-"
        self.header_daily_label.config(text=self._t("monitor.header.latest", time=latest_time) if latest else "")

    def _focus_window(self) -> None:
        self.window.lift()
        self.window.focus_force()

    def _on_drag_start(self, event: tk.Event) -> None:
        self.drag_origin = (event.x_root, event.y_root)

    def _on_drag_move(self, event: tk.Event) -> None:
        if self.drag_origin is None:
            return
        dx = event.x_root - self.drag_origin[0]
        dy = event.y_root - self.drag_origin[1]
        x = self.window.winfo_x() + dx
        y = self.window.winfo_y() + dy
        self.window.geometry(f"+{x}+{y}")
        self.drag_origin = (event.x_root, event.y_root)

    def _on_drag_end(self, event: tk.Event) -> None:
        self.drag_origin = None
        self._save_state()

    def refresh_async(self) -> None:
        if self.refresh_inflight:
            return
        self.refresh_inflight = True
        self.status_label.config(text=self._t("monitor.status.refreshing"))
        worker = threading.Thread(target=self._refresh_worker, daemon=True)
        worker.start()

    def _refresh_worker(self) -> None:
        try:
            snapshot = self.cache.refresh()
            self.window.after(0, lambda: self._apply_snapshot(snapshot))
        except Exception as exc:
            self.window.after(0, lambda: self._apply_error(str(exc)))

    def _apply_error(self, message: str) -> None:
        self.refresh_inflight = False
        self.status_label.config(text=self._t("monitor.status.error", message=message))
        self._schedule_refresh()

    def _apply_snapshot(self, snapshot: DashboardSnapshot) -> None:
        self.refresh_inflight = False
        self.latest_snapshot = snapshot
        self.status_label.config(text=self._t("monitor.status.updated", time=snapshot.generated_at.strftime("%H:%M:%S")))

        latest = snapshot.latest_request

        self._set_metric_title(
            self.today_metric,
            self._t("monitor.metric.today_title", duration=fmt_duration(snapshot.today_total_duration_seconds, self.lang)),
        )
        self._set_metric(
            self.today_metric,
            fmt_k(snapshot.today_total),
            self._t(
                "monitor.metric.today_detail",
                sessions=snapshot.today_new_session_count,
                turns=snapshot.today_turn_count,
                round_trips=len(snapshot.today_requests),
            ),
            color=METRIC_BLUE,
        )

        self._set_metric_title(
            self.yesterday_metric,
            self._t(
                "monitor.metric.yesterday_title",
                duration=fmt_duration(snapshot.yesterday_total_duration_seconds, self.lang),
            ),
        )
        self._set_metric(
            self.yesterday_metric,
            fmt_k(snapshot.yesterday_total),
            self._t(
                "monitor.metric.yesterday_detail",
                sessions=snapshot.yesterday_new_session_count,
                turns=snapshot.yesterday_turn_count,
                round_trips=snapshot.yesterday_round_trip_count,
            ),
            color="#8fc7ff",
        )

        self._set_metric_title(
            self.all_metric,
            self._t("monitor.metric.total_title", duration=fmt_duration(snapshot.all_total_duration_seconds, self.lang)),
        )
        self._set_metric(
            self.all_metric,
            fmt_total_metric(snapshot.all_total),
            "\n".join(
                [
                    self._t("monitor.metric.total_exact", tokens=fmt_int(snapshot.all_total)),
                    self._t(
                        "monitor.metric.total_detail",
                        sessions=snapshot.all_session_count,
                        turns=snapshot.all_turn_count,
                        round_trips=len(snapshot.all_requests),
                    ),
                ]
            ),
            color=METRIC_BLUE,
        )

        self._render_color_legend(snapshot)
        self._update_footer_labels(snapshot)

        self._render_chart(snapshot)
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self.after_id is not None:
            self.window.after_cancel(self.after_id)
        self.after_id = self.window.after(self.refresh_ms, self.refresh_async)

    def _chart_key(self, item: RequestPoint) -> str:
        return f"{item.thread_id}:{item.turn_id}:{item.call_index}"

    def _chart_items(self, snapshot: DashboardSnapshot) -> List[RequestPoint]:
        source = snapshot.all_requests or snapshot.today_requests
        if not source:
            return []
        if len(snapshot.current_turn_requests) >= BAR_LIMIT:
            return snapshot.current_turn_requests[-BAR_LIMIT:]
        return source[-BAR_LIMIT:]

    def _visible_chart_items(self, snapshot: DashboardSnapshot) -> List[RequestPoint]:
        items = self._chart_items(snapshot)
        if len(items) <= VISIBLE_BAR_SLOTS:
            return items
        return items[-VISIBLE_BAR_SLOTS:]

    def _turn_color_map(self, snapshot: DashboardSnapshot) -> Dict[str, Tuple[str, str]]:
        source = snapshot.all_requests or snapshot.today_requests
        turn_colors: Dict[str, Tuple[str, str]] = {}
        if not source:
            return turn_colors
        for item in source:
            if item.turn_id in turn_colors:
                continue
            turn_colors[item.turn_id] = TURN_PALETTE[len(turn_colors) % len(TURN_PALETTE)]
        return turn_colors

    def _turn_total_map(self, snapshot: DashboardSnapshot) -> Dict[str, int]:
        source = snapshot.all_requests or snapshot.today_requests
        totals: Dict[str, int] = defaultdict(int)
        for item in source:
            totals[item.turn_id] += item.total_tokens
        if snapshot.current_turn_id:
            totals[snapshot.current_turn_id] = snapshot.current_turn_total
        return totals

    def _render_chart(self, snapshot: DashboardSnapshot) -> None:
        items = self._visible_chart_items(snapshot)
        keys = tuple(self._chart_key(item) for item in items)
        if self.chart_animation_after is not None:
            self.window.after_cancel(self.chart_animation_after)
            self.chart_animation_after = None

        if self.last_chart_keys and keys != self.last_chart_keys:
            self._animate_chart(snapshot, start_offset=26.0, frames=7)
        else:
            self._draw_chart(snapshot, row_offset=0.0)

        self.last_chart_keys = keys

    def _animate_chart(self, snapshot: DashboardSnapshot, start_offset: float, frames: int = 7) -> None:
        state = {"frame": 0}

        def step() -> None:
            progress = state["frame"] / max(frames - 1, 1)
            eased = (1.0 - progress) ** 2
            self._draw_chart(snapshot, row_offset=start_offset * eased)
            if state["frame"] >= frames - 1:
                self.chart_animation_after = None
                return
            state["frame"] += 1
            self.chart_animation_after = self.window.after(28, step)

        step()

    def _on_canvas_click(self, event: tk.Event) -> None:
        for (x1, y1, x2, y2), turn_id in reversed(self.turn_label_regions):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self._open_turn_detail(turn_id)
                return
        for (x1, y1, x2, y2), item, direction in reversed(self.chart_regions):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if direction == "up":
                    self._open_upstream_detail(item)
                else:
                    self._open_downstream_detail(item)
                return

    def _estimate_upstream_breakdown(self, context_items: Sequence[object], input_tokens: int) -> List[Tuple[str, int, int]]:
        category_weights: Dict[str, int] = defaultdict(int)
        category_counts: Dict[str, int] = defaultdict(int)
        for ctx in context_items:
            label = self._category_label(ctx)
            text = getattr(ctx, "text", "") or ""
            weight = max(len(text), 1)
            category_weights[label] += weight
            category_counts[label] += 1

        total_weight = sum(category_weights.values())
        if total_weight <= 0:
            return []

        raw_allocations: List[Tuple[str, float]] = []
        for label, weight in category_weights.items():
            raw_allocations.append((label, input_tokens * weight / total_weight))

        floored: Dict[str, int] = {label: int(value) for label, value in raw_allocations}
        remain = input_tokens - sum(floored.values())
        ranked = sorted(raw_allocations, key=lambda item: item[1] - int(item[1]), reverse=True)
        for idx in range(remain):
            floored[ranked[idx % len(ranked)][0]] += 1

        rows = [(label, floored[label], category_counts[label]) for label in floored]
        rows.sort(key=lambda item: item[1], reverse=True)
        return rows

    def _load_upstream_breakdown(self, item: RequestPoint) -> List[Tuple[str, int, int]]:
        if item.upstream_breakdown:
            return list(item.upstream_breakdown)
        parsed = parse_session(item.session_file)
        if item.call_index < 1 or item.call_index > len(parsed.calls):
            return []
        call = parsed.calls[item.call_index - 1]
        context_items = parsed.transcript_pool[: call.context_end_index]
        return self._estimate_upstream_breakdown(context_items, item.upstream_tokens)

    def _downstream_label(self, out: object) -> str:
        role = getattr(out, "role", "")
        kind = getattr(out, "kind", "")
        if kind == "reasoning":
            return "reasoning_output"
        if role == "assistant" and kind == "function_call":
            return "tool_call_history"
        if role == "assistant":
            return "assistant_history"
        return "other"

    def _estimate_downstream_breakdown(
        self,
        output_items: Sequence[object],
        output_tokens: int,
        reasoning_output_tokens: int,
    ) -> List[Tuple[str, int, int]]:
        allocations: Dict[str, int] = defaultdict(int)
        counts: Dict[str, int] = defaultdict(int)

        if reasoning_output_tokens > 0:
            allocations["reasoning_output"] += reasoning_output_tokens
            counts["reasoning_output"] += sum(1 for out in output_items if getattr(out, "kind", "") == "reasoning")

        weighted_items: List[Tuple[str, int]] = []
        for out in output_items:
            if getattr(out, "kind", "") == "reasoning":
                continue
            label = self._downstream_label(out)
            text = getattr(out, "text", "") or ""
            weight = max(len(text), 1)
            weighted_items.append((label, weight))
            counts[label] += 1

        if output_tokens > 0:
            total_weight = sum(weight for _label, weight in weighted_items)
            if total_weight <= 0:
                allocations["assistant_history"] += output_tokens
                counts["assistant_history"] += 1
            else:
                raw_allocations = [
                    (label, output_tokens * weight / total_weight)
                    for label, weight in weighted_items
                ]
                floored: Dict[str, int] = defaultdict(int)
                for label, value in raw_allocations:
                    floored[label] += int(value)
                remain = output_tokens - sum(floored.values())
                ranked = sorted(raw_allocations, key=lambda item: item[1] - int(item[1]), reverse=True)
                for idx in range(remain):
                    floored[ranked[idx % len(ranked)][0]] += 1
                for label, value in floored.items():
                    allocations[label] += value

        rows = [(label, allocations[label], counts[label]) for label in allocations]
        rows.sort(key=lambda item: item[1], reverse=True)
        return rows

    def _load_downstream_breakdown(self, item: RequestPoint) -> List[Tuple[str, int, int]]:
        if item.downstream_breakdown:
            return list(item.downstream_breakdown)
        parsed = parse_session(item.session_file)
        if item.call_index < 1 or item.call_index > len(parsed.calls):
            return []
        call = parsed.calls[item.call_index - 1]
        return self._estimate_downstream_breakdown(
            call.output_items,
            item.output_tokens,
            item.reasoning_output_tokens,
        )

    def _context_bucket(self, ctx: object, is_latest_user: bool) -> str:
        role = getattr(ctx, "role", "")
        kind = getattr(ctx, "kind", "")
        title = (getattr(ctx, "title", "") or "").lower()
        kind_lower = (kind or "").lower()

        if kind == "base_instructions" or role == "developer" or (role == "user" and is_latest_user):
            return "prompt"
        if kind == "turn_context":
            return "planner"
        if role == "tool" or (role == "assistant" and kind == "function_call"):
            return "tool"
        if "summary" in kind_lower or "summary" in title or "compact" in title or "compress" in title or "trunc" in title:
            return "truncation"
        return "memory"

    def _estimate_upstream_attribution(
        self,
        context_items: Sequence[object],
        input_tokens: int,
        cached_input_tokens: int,
    ) -> List[Tuple[str, str, int, float]]:
        total_input = max(input_tokens, 0)
        cached_tokens = max(0, min(cached_input_tokens, total_input))
        uncached_tokens = max(total_input - cached_tokens, 0)
        latest_user_index = None
        for idx, ctx in enumerate(context_items):
            if getattr(ctx, "role", "") == "user" and getattr(ctx, "kind", "") == "message":
                latest_user_index = idx

        weights: Dict[str, int] = defaultdict(int)
        for idx, ctx in enumerate(context_items):
            bucket = self._context_bucket(ctx, idx == latest_user_index)
            text = getattr(ctx, "text", "") or ""
            weights[bucket] += max(len(text), 1)

        allocations: Dict[str, int] = {key: 0 for key, _label, _color in UPSTREAM_ATTR_SPECS}
        allocations["cache"] = cached_tokens
        weight_total = sum(weights.values())

        if uncached_tokens > 0:
            if weight_total <= 0:
                allocations["prompt"] += uncached_tokens
            else:
                raw_allocations = [
                    (key, uncached_tokens * weight / weight_total)
                    for key, weight in weights.items()
                ]
                floored = {key: int(value) for key, value in raw_allocations}
                remain = uncached_tokens - sum(floored.values())
                ranked = sorted(raw_allocations, key=lambda item: item[1] - int(item[1]), reverse=True)
                for idx in range(remain):
                    floored[ranked[idx % len(ranked)][0]] += 1
                for key, value in floored.items():
                    allocations[key] += value

        rows: List[Tuple[str, str, int, float]] = []
        for key, label, _color in UPSTREAM_ATTR_SPECS:
            tokens = allocations.get(key, 0)
            pct = (tokens / total_input) if total_input > 0 else 0.0
            rows.append((key, label, tokens, pct))
        return rows

    def _category_label(self, ctx: object) -> str:
        role = getattr(ctx, "role", "")
        kind = getattr(ctx, "kind", "")
        title = getattr(ctx, "title", "")
        if kind == "base_instructions":
            return "system_prompt"
        if role == "developer":
            return "developer_prompt"
        if role == "user":
            return "user_message"
        if kind == "turn_context":
            return "runtime_context"
        if role == "tool":
            return "tool_output"
        if role == "assistant" and kind == "function_call":
            return "tool_call_history"
        if role == "assistant":
            return "assistant_history"
        return title or kind or role or "other"

    def _compact_snippet(self, text: str, max_chars: int = 140) -> str:
        merged = " ".join(line.strip() for line in text.splitlines() if line.strip())
        if not merged:
            return "(空)" if self.lang == "zh" else "(empty)"
        return shorten(merged, max_chars)

    def _tool_name(self, item: object) -> str:
        raw = getattr(item, "raw", {}) or {}
        name = raw.get("name")
        if name:
            return str(name)
        title = getattr(item, "title", "")
        if ":" in title:
            return title.split(":", 1)[1]
        return title or "unknown"

    def _build_compact_summary(self, session: SessionSnapshot, parsed) -> str:
        items = parsed.transcript_pool
        user_messages = [item for item in items if item.role == "user" and item.kind == "message"]
        assistant_messages = [item for item in items if item.role == "assistant" and item.kind == "message"]
        function_calls = [item for item in items if item.role == "assistant" and item.kind == "function_call"]
        tool_outputs = [item for item in items if item.role == "tool"]
        turn_ids = []
        for req in session.requests:
            if req.turn_id not in turn_ids:
                turn_ids.append(req.turn_id)
        latest_turn_id = session.requests[-1].turn_id if session.requests else None
        latest_turn_requests = [req for req in session.requests if latest_turn_id and req.turn_id == latest_turn_id]
        tool_counts: Dict[str, int] = defaultdict(int)
        for call in function_calls:
            tool_counts[self._tool_name(call)] += 1
        top_tools = sorted(tool_counts.items(), key=lambda item: (-item[1], item[0]))[:8]

        parts: List[str] = []
        parts.append(self._t("monitor.compact_summary.title"))
        parts.append(self._t("monitor.compact_summary.note"))
        parts.append("")
        parts.append("1. Session Overview" if self.lang == "en" else "一、会话概况")
        parts.append(f"- {'Title' if self.lang == 'en' else '标题'}: {session.title}")
        parts.append(f"- thread_id: {session.thread_id}")
        parts.append(f"- session_file: {session.session_file}")
        parts.append(f"- {'Model' if self.lang == 'en' else '模型'}: {parsed.model or 'unknown'}")
        parts.append(f"- {'Session total tokens' if self.lang == 'en' else '会话累计 token'}: {fmt_int(session.total_tokens)}")
        parts.append(f"- {'Requests' if self.lang == 'en' else '总往返'}: {len(session.requests)}{' requests' if self.lang == 'en' else ' 次'}")
        parts.append(f"- {'Turns' if self.lang == 'en' else '总轮次'}: {len(turn_ids)}{' turns' if self.lang == 'en' else ' 轮'}")
        if latest_turn_requests:
            parts.append(
                f"- {'Current turn' if self.lang == 'en' else '当前轮次'}: "
                f"{len(latest_turn_requests)}{' requests' if self.lang == 'en' else ' 次往返'} / "
                f"{fmt_k(sum(req.total_tokens for req in latest_turn_requests))}"
            )
        parts.append("")
        parts.append("2. Current Goal" if self.lang == "en" else "二、当前目标")
        if user_messages:
            parts.append(
                f"- {'Latest user request' if self.lang == 'en' else '最近用户要求'}: "
                f"{self._compact_snippet(user_messages[-1].text, 220)}"
            )
        else:
            parts.append(f"- {'Latest user request' if self.lang == 'en' else '最近用户要求'}: {'(not found)' if self.lang == 'en' else '(未找到)'}")
        parts.append("")
        parts.append("3. Recent User Messages" if self.lang == "en" else "三、最近用户消息")
        if user_messages:
            for idx, message in enumerate(user_messages[-6:], start=max(1, len(user_messages) - 5)):
                parts.append(f"{idx}. {self._compact_snippet(message.text, 180)}")
        else:
            parts.append("- None" if self.lang == "en" else "- 无")
        parts.append("")
        parts.append("4. Recent Tool Activity" if self.lang == "en" else "四、最近工具动作")
        if top_tools:
            for name, count in top_tools:
                parts.append(f"- {name}: {count}{' calls' if self.lang == 'en' else ' 次'}")
        else:
            parts.append("- No tool calls were recorded in this session" if self.lang == "en" else "- 本会话没有记录到工具调用")
        if function_calls:
            parts.append("- Recent call order:" if self.lang == "en" else "- 最近调用顺序:")
            for call in function_calls[-8:]:
                parts.append(f"  {self._tool_name(call)}")
        parts.append("")
        parts.append("5. Recent Key Outputs" if self.lang == "en" else "五、最近关键输出")
        if assistant_messages:
            for idx, message in enumerate(assistant_messages[-4:], start=1):
                parts.append(f"- {('Assistant ' if self.lang == 'en' else '助手')}{idx}: {self._compact_snippet(message.text, 220)}")
        else:
            parts.append("- Assistant messages: none" if self.lang == "en" else "- 助手消息: 无")
        if tool_outputs:
            for idx, output in enumerate(tool_outputs[-4:], start=1):
                parts.append(f"- {('Tool result ' if self.lang == 'en' else '工具结果')}{idx}: {self._compact_snippet(output.text, 220)}")
        parts.append("")
        parts.append("6. Continue Instruction" if self.lang == "en" else "六、继续对话可直接使用")
        parts.append(
            "Continue from the compact summary above without asking for background again; prioritize the current goal, completed actions, and recent tool results."
            if self.lang == "en"
            else "请基于以上压缩摘要继续，不必重复历史背景；优先延续当前目标、已完成动作和最近工具结果。"
        )
        return "\n".join(parts)

    def _load_upstream_attribution(self, item: RequestPoint) -> List[Tuple[str, str, int, float]]:
        parsed = parse_session(item.session_file)
        if item.call_index < 1 or item.call_index > len(parsed.calls):
            return []
        call = parsed.calls[item.call_index - 1]
        context_items = parsed.transcript_pool[: call.context_end_index]
        return self._estimate_upstream_attribution(context_items, item.upstream_tokens, item.cached_input_tokens)

    def _render_color_legend(self, snapshot: DashboardSnapshot) -> None:
        for child in self.legend_frame.winfo_children():
            child.destroy()

        items = self._visible_chart_items(snapshot)
        turn_order: List[str] = []
        for item in items:
            if item.turn_id not in turn_order:
                turn_order.append(item.turn_id)
        if not turn_order:
            return

        row = tk.Frame(self.legend_frame, bg=SURFACE_BG)
        row.pack(fill="x")
        turn_totals = self._turn_total_map(snapshot)
        turn_colors = self._turn_color_map(snapshot)
        for index, turn_id in enumerate(turn_order):
            turn_tag = chr(ord("A") + index) if index < 26 else f"T{index + 1}"
            total_tokens = turn_totals[turn_id]
            label = (
                f"{turn_tag} {fmt_eng_unit_compact(total_tokens)}"
                if self.lang == "en"
                else f"{turn_tag} 本轮 {fmt_k_compact(total_tokens)}"
            )
            turn_up_color, _turn_down_color = turn_colors.get(turn_id, TURN_PALETTE[index % len(TURN_PALETTE)])
            button = self._make_detail_action_button(
                row,
                text=label,
                command=lambda turn_id=turn_id: self._open_turn_detail(turn_id),
                kind="secondary",
                text_color=turn_up_color,
            )
            button.pack(side="left", padx=(0, 8), pady=(0, 2))

    def _draw_breakdown_pie(
        self,
        canvas: tk.Canvas,
        rows: Sequence[Tuple[str, int, int]],
        center_x: float,
        center_y: float,
        radius: float,
    ) -> None:
        total = sum(tokens for _label, tokens, _count in rows if tokens > 0)
        if total <= 0:
            canvas.create_oval(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                fill="#1f2937",
                outline="#334155",
                width=1,
            )
            canvas.create_text(center_x, center_y, text=self._t("detail.empty_chart"), fill="#94a3b8", font=self.tiny_font)
            return

        start = 0.0
        for idx, (label, tokens, _count) in enumerate(rows):
            if tokens <= 0:
                continue
            extent = 360.0 * tokens / total
            color = BREAKDOWN_COLORS.get(label, PIE_FALLBACK_COLORS[idx % len(PIE_FALLBACK_COLORS)])
            canvas.create_arc(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                start=start,
                extent=extent,
                fill=color,
                outline="#0f172a",
                width=2,
            )
            start += extent

        canvas.create_oval(
            center_x - radius * 0.46,
            center_y - radius * 0.46,
            center_x + radius * 0.46,
            center_y + radius * 0.46,
            fill="#111827",
            outline="#111827",
        )
        canvas.create_text(center_x, center_y - 8, text=self._t("detail.total"), fill="#94a3b8", font=self.tiny_font)
        canvas.create_text(center_x, center_y + 10, text=fmt_k(total), fill="#f8fafc", font=self.small_font)

    def _build_breakdown_rows_text(self, rows: Sequence[Tuple[str, int, int]]) -> str:
        lines: List[str] = []
        total = sum(tokens for _label, tokens, _count in rows if tokens > 0)
        for idx, (label, tokens, count) in enumerate(rows, start=1):
            pct = (tokens / total * 100.0) if total > 0 else 0.0
            lines.append(
                self._t(
                    "detail.breakdown.row",
                    idx=idx,
                    label=self._label(label),
                    tokens=fmt_k(tokens),
                    pct=pct,
                    count=count,
                )
            )
        return "\n".join(lines) if lines else self._t("detail.breakdown.none")

    def _attach_detail_chart(
        self,
        parent: tk.Widget,
        rows: Sequence[Tuple[str, int, int]],
        title: str,
    ) -> None:
        card = tk.Frame(parent, bg=DETAIL_BG)
        card.pack(fill="x", padx=12, pady=(0, 10))

        canvas = tk.Canvas(card, width=320, height=220, bg=DETAIL_BG, highlightthickness=0)
        canvas.pack(side="left", padx=(0, 16))
        canvas.create_text(160, 18, text=title, fill=DETAIL_ACCENT_BLUE, font=self.small_font)
        self._draw_breakdown_pie(canvas, rows, 110, 116, 72)

        legend = tk.Label(
            card,
            text=self._build_breakdown_rows_text(rows),
            fg="#cbd5e1",
            bg=DETAIL_BG,
            justify="left",
            anchor="nw",
            font=self.tiny_font,
        )
        legend.pack(side="left", fill="both", expand=True)

    def _copy_text(self, text: str, success_message: Optional[str] = None) -> None:
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.window.update()
        self.status_label.config(text=success_message or self._t("detail.copy.clipboard"))

    def _open_continue_summary_for_turn(self, turn_id: str, session_file: Path) -> None:
        if not session_file:
            return
        try:
            from codex_continue_summary import build_continue_summary

            summary_text = build_continue_summary(session_file, turn_id=turn_id, lang=self.lang)
            detail_window = self._create_detail_window(
                title=self._t("detail.turn_summary.title"),
                geometry="980x760+180+120",
                header_text=self._t("detail.turn_summary.header", turn_id=turn_id),
                subheader_text=self._t("detail.turn_summary.subheader"),
                subheader_fg=DETAIL_ACCENT_BLUE,
            )

            actions = tk.Frame(detail_window, bg=DETAIL_BG)
            actions.pack(fill="x", padx=12, pady=(0, 8))
            self._make_detail_action_button(
                actions,
                text=self._t("detail.button.copy_summary"),
                command=lambda: self._copy_text(summary_text, self._t("detail.turn_summary.copied")),
                kind="primary",
            ).pack(side="left", padx=(0, 8))
            self._make_detail_action_button(
                actions,
                text=self._t("detail.button.close"),
                command=detail_window.destroy,
                kind="secondary",
            ).pack(side="left")

            text = self._create_detail_text(detail_window)
            text.insert("1.0", summary_text)
            text.configure(state="disabled")
            self.status_label.config(text=self._t("detail.turn_summary.opened"))
        except Exception as exc:
            messagebox.showerror(self._t("detail.turn_summary.open_error_title"), str(exc))

    def _open_turn_detail(self, turn_id: str) -> None:
        snapshot = self.latest_snapshot
        if snapshot is None:
            return
        requests = [item for item in snapshot.all_requests if item.turn_id == turn_id]
        if not requests:
            return
        session_file = requests[-1].session_file
        self._open_continue_summary_for_turn(turn_id, session_file)

    def _open_continue_summary(self) -> None:
        snapshot = self.latest_snapshot
        if not snapshot or not snapshot.latest_session:
            messagebox.showinfo(self._t("detail.current_summary.none_title"), self._t("detail.current_summary.none_body"))
            return

        from codex_continue_summary import build_continue_summary

        summary_text = build_continue_summary(snapshot.latest_session.session_file, lang=self.lang)

        detail_window = self._create_detail_window(
            title=self._t("detail.current_summary.title"),
            geometry="980x760+160+120",
            header_text=self._t("detail.current_summary.header"),
            subheader_text=self._t("detail.current_summary.subheader"),
            subheader_fg=DETAIL_ACCENT_BLUE,
        )

        actions = tk.Frame(detail_window, bg=DETAIL_BG)
        actions.pack(fill="x", padx=12, pady=(0, 8))
        self._make_detail_action_button(
            actions,
            text=self._t("detail.button.copy_summary"),
            command=lambda: self._copy_text(summary_text, self._t("detail.current_summary.copied")),
            kind="primary",
        ).pack(side="left", padx=(0, 8))
        self._make_detail_action_button(
            actions,
            text=self._t("detail.button.close"),
            command=detail_window.destroy,
            kind="secondary",
        ).pack(side="left")

        text = self._create_detail_text(detail_window)
        text.insert("1.0", summary_text)
        text.configure(state="disabled")

    def _open_upstream_detail(self, item: RequestPoint) -> None:
        parsed = parse_session(item.session_file)
        if item.call_index < 1 or item.call_index > len(parsed.calls):
            return
        call = parsed.calls[item.call_index - 1]
        context_items = parsed.transcript_pool[: call.context_end_index]
        breakdown = self._estimate_upstream_breakdown(context_items, item.upstream_tokens)
        attribution = self._estimate_upstream_attribution(context_items, item.upstream_tokens, item.cached_input_tokens)

        detail_window = self._create_detail_window(
            title=self._t("detail.upstream.title"),
            geometry="980x760+120+120",
            header_text=self._t(
                "detail.upstream.header",
                time=item.timestamp.strftime("%Y-%m-%d %H:%M:%S") if item.timestamp else "-",
                up=fmt_k(item.upstream_tokens),
                down=fmt_k(item.downstream_tokens),
                cache=fmt_k(item.cached_input_tokens),
                total=fmt_k(item.total_tokens),
            ),
            subheader_text=self._t("detail.upstream.subheader"),
            subheader_fg="#93c5fd",
        )
        notebook = self._create_detail_notebook(detail_window)

        overview_tab = tk.Frame(notebook, bg=DETAIL_BG)
        categories_tab = tk.Frame(notebook, bg=DETAIL_BG)
        all_items_tab = tk.Frame(notebook, bg=DETAIL_BG)
        notebook.add(overview_tab, text="Overview" if self.lang == "en" else "概览")
        notebook.add(categories_tab, text="Categories" if self.lang == "en" else "分类")
        notebook.add(all_items_tab, text="All Items" if self.lang == "en" else "全部明细")

        overview_content = self._create_scrollable_detail_frame(overview_tab)
        self._attach_detail_chart(overview_content, breakdown, self._t("detail.upstream.pie_title"))
        self._build_breakdown_summary_panel(
            overview_content,
            [(label, tokens, count) for label, tokens, count in breakdown],
            title=self._t("detail.breakdown.title"),
            total_tokens=max(item.upstream_tokens, 1),
        )

        grouped_context: Dict[str, List[object]] = defaultdict(list)
        for ctx in context_items:
            grouped_context[self._category_label(ctx)].append(ctx)

        def render_context_item(text: scrolledtext.ScrolledText, ctx: object, idx: int, tag_name: str) -> None:
            self._append_content_block(text, self._t("detail.context_item", idx=idx), "", tag_name)
            self._append_meta_line(text, "role", ensure_text(getattr(ctx, "role", "")))
            self._append_meta_line(text, "kind", ensure_text(getattr(ctx, "kind", "")))
            self._append_meta_line(text, "title", ensure_text(getattr(ctx, "title", "")))
            self._append_meta_line(text, "category", self._label(self._category_label(ctx)), tag_name)
            self._append_meta_line(text, "content", "")
            text.insert("end", ensure_text(getattr(ctx, "text", "")) + "\n\n", ("body",))

        self._build_category_browser(categories_tab, grouped_context, render_context_item)

        all_text = self._create_tagged_detail_text(all_items_tab)
        self._append_meta_line(all_text, "session_file", str(item.session_file))
        self._append_meta_line(all_text, "thread_id", item.thread_id)
        self._append_meta_line(all_text, "turn_id", item.turn_id)
        self._append_meta_line(all_text, "call_index", str(item.call_index))
        all_text.insert("end", "\n", ("body",))
        for idx, (_key, label, tokens, pct) in enumerate(attribution, start=1):
            tag_name = f"attr_{label}"
            all_text.tag_configure(tag_name, foreground=self._detail_color(label, idx - 1), font=("Menlo", 11, "bold"))
            item_suffix = "items" if self.lang == "en" else "项"
            self._append_meta_line(
                all_text,
                f"{idx}. {self._label(label)}",
                f"{fmt_k(tokens)} / {pct * 100:.1f}% / {next((count for cat, _tokens, count in breakdown if cat == label), 0)} {item_suffix}",
                tag_name,
            )
        all_text.insert("end", "\n", ("body",))
        for idx, ctx in enumerate(context_items, start=1):
            category = self._category_label(ctx)
            tag_name = f"all_{category}"
            all_text.tag_configure(tag_name, foreground=self._detail_color(category, idx - 1), font=("Menlo", 12, "bold"))
            render_context_item(all_text, ctx, idx, tag_name)
        all_text.configure(state="disabled")

    def _open_downstream_detail(self, item: RequestPoint) -> None:
        parsed = parse_session(item.session_file)
        if item.call_index < 1 or item.call_index > len(parsed.calls):
            return
        call = parsed.calls[item.call_index - 1]

        detail_window = self._create_detail_window(
            title=self._t("detail.downstream.title"),
            geometry="980x720+140+140",
            header_text=self._t(
                "detail.downstream.header",
                time=item.timestamp.strftime("%Y-%m-%d %H:%M:%S") if item.timestamp else "-",
                down=fmt_k(item.downstream_tokens),
                output=fmt_k(item.output_tokens),
                reasoning=fmt_k(item.reasoning_output_tokens),
            ),
            subheader_text=self._t("detail.downstream.subheader"),
            subheader_fg=DETAIL_ACCENT_PINK,
        )

        breakdown = self._load_downstream_breakdown(item)
        notebook = self._create_detail_notebook(detail_window)

        overview_tab = tk.Frame(notebook, bg=DETAIL_BG)
        categories_tab = tk.Frame(notebook, bg=DETAIL_BG)
        all_items_tab = tk.Frame(notebook, bg=DETAIL_BG)
        notebook.add(overview_tab, text="Overview" if self.lang == "en" else "概览")
        notebook.add(categories_tab, text="Categories" if self.lang == "en" else "分类")
        notebook.add(all_items_tab, text="All Outputs" if self.lang == "en" else "全部输出")

        overview_content = self._create_scrollable_detail_frame(overview_tab)
        self._attach_detail_chart(overview_content, breakdown, self._t("detail.downstream.pie_title"))
        self._build_breakdown_summary_panel(
            overview_content,
            [(label, tokens, count) for label, tokens, count in breakdown],
            title=self._t("detail.downstream.pie_title"),
            total_tokens=max(item.downstream_tokens, 1),
        )

        grouped_outputs: Dict[str, List[object]] = defaultdict(list)
        for out in call.output_items:
            grouped_outputs[self._downstream_label(out)].append(out)

        def render_output_item(text: scrolledtext.ScrolledText, out: object, idx: int, tag_name: str) -> None:
            self._append_content_block(text, self._t("detail.output_item", idx=idx), "", tag_name)
            self._append_meta_line(text, "role", ensure_text(getattr(out, "role", "")))
            self._append_meta_line(text, "kind", ensure_text(getattr(out, "kind", "")))
            self._append_meta_line(text, "title", ensure_text(getattr(out, "title", "")))
            self._append_meta_line(text, "content", "")
            text.insert("end", ensure_text(getattr(out, "text", "")) + "\n\n", ("body",))

        self._build_category_browser(categories_tab, grouped_outputs, render_output_item)

        all_text = self._create_tagged_detail_text(all_items_tab)
        self._append_meta_line(all_text, "session_file", str(item.session_file))
        self._append_meta_line(all_text, "thread_id", item.thread_id)
        self._append_meta_line(all_text, "turn_id", item.turn_id)
        self._append_meta_line(all_text, "call_index", str(item.call_index))
        all_text.insert("end", "\n", ("body",))
        if not call.output_items:
            all_text.insert("end", self._t("detail.output.none"), ("body",))
        for idx, out in enumerate(call.output_items, start=1):
            category = self._downstream_label(out)
            tag_name = f"down_{category}"
            all_text.tag_configure(tag_name, foreground=self._detail_color(category, idx - 1), font=("Menlo", 12, "bold"))
            render_output_item(all_text, out, idx, tag_name)
        all_text.configure(state="disabled")

    def _draw_chart(self, snapshot: DashboardSnapshot, row_offset: float = 0.0) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self.chart_regions = []
        self.turn_label_regions = []
        viewport_width = max(canvas.winfo_width(), 900)
        height = max(canvas.winfo_height(), 360)
        left = 70
        top = 42
        bottom = height - 38

        items = self._chart_items(snapshot)
        visible_items = self._visible_chart_items(snapshot)

        if not visible_items:
            canvas.create_text(
                viewport_width / 2,
                height / 2,
                text=self._t("monitor.no_requests"),
                fill="#94a3b8",
                font=self.small_font,
            )
            return

        max_up = UPSTREAM_DISPLAY_CAP
        max_down = DOWNSTREAM_DISPLAY_CAP
        baseline = top + (bottom - top) * 0.52 + row_offset
        up_band = baseline - top - 14
        down_band = bottom - baseline - 32
        visible_right = viewport_width - 28
        visible_usable_width = visible_right - left
        slot = visible_usable_width / max(len(visible_items), 1)
        right = visible_right
        bar_width = max(18, min(34, slot * 0.58))

        turn_order: List[str] = []
        for item in visible_items:
            if item.turn_id not in turn_order:
                turn_order.append(item.turn_id)
        turn_colors = self._turn_color_map(snapshot)

        for factor in (0.25, 0.5, 0.75, 1.0):
            y_up = baseline - up_band * factor
            canvas.create_line(left, y_up, right, y_up, fill=GRID_COLOR, width=1)
        for factor in (0.5, 1.0):
            y_down = baseline + down_band * factor
            canvas.create_line(left, y_down, right, y_down, fill=GRID_COLOR, width=1)

        canvas.create_line(left, baseline, right, baseline, fill="#7c8ba3", width=2)
        canvas.create_text(left - 12, baseline - up_band, text=fmt_k_compact(max_up), fill=TEXT_MUTED, anchor="e", font=self.small_font)
        canvas.create_text(left - 12, baseline, text="0", fill=TEXT_MUTED, anchor="e", font=self.small_font)
        canvas.create_text(left - 12, baseline + down_band, text=fmt_k_compact(max_down), fill=TEXT_MUTED, anchor="e", font=self.small_font)
        last_turn_id = None
        for index, item in enumerate(visible_items):
            x = left + slot * index + slot / 2
            up_total_height = up_band * (clamp(item.upstream_tokens, max_up) / max_up)
            down_total_height = down_band * (clamp(item.downstream_tokens, max_down) / max_down)
            turn_up_color, turn_down_color = turn_colors[item.turn_id]

            if last_turn_id is not None and item.turn_id != last_turn_id:
                divider_x = x - slot / 2
                canvas.create_line(divider_x, top - 6, divider_x, bottom + 4, fill="#475569", width=1, dash=(4, 4))
            last_turn_id = item.turn_id

            if item.upstream_tokens > 0:
                canvas.create_rectangle(
                    x - bar_width / 2,
                    baseline - up_total_height,
                    x + bar_width / 2,
                    baseline,
                    fill=turn_up_color,
                    outline="",
                )
            if item.downstream_tokens > 0:
                canvas.create_rectangle(
                    x - bar_width / 2,
                    baseline,
                    x + bar_width / 2,
                    baseline + down_total_height,
                    fill=turn_down_color,
                    outline="",
                )

            outline = "#ffffff" if item is snapshot.latest_request else "#334155"
            outline_width = 2 if item is snapshot.latest_request else 0
            if item.upstream_tokens > 0:
                canvas.create_rectangle(
                    x - bar_width / 2,
                    baseline - up_total_height,
                    x + bar_width / 2,
                    baseline,
                    outline=outline,
                    width=outline_width,
                )
            if item.downstream_tokens > 0:
                canvas.create_rectangle(
                    x - bar_width / 2,
                    baseline,
                    x + bar_width / 2,
                    baseline + down_total_height,
                    outline=outline,
                    width=outline_width,
                )

            self.chart_regions.append(
                ((x - bar_width / 2, top - 6, x + bar_width / 2, baseline), item, "up")
            )
            self.chart_regions.append(
                ((x - bar_width / 2, baseline, x + bar_width / 2, bottom + 8), item, "down")
            )

            canvas.create_text(
                x,
                max(top + 10, baseline - up_total_height - 12),
                text=fmt_eng_unit_no_suffix(item.upstream_tokens, decimals=0),
                fill="#e2e8f0",
                font=self.small_font,
            )
            canvas.create_text(
                x,
                min(bottom - 10, baseline + down_total_height + 12),
                text=fmt_k_compact(item.downstream_tokens),
                fill="#f8fafc",
                font=self.small_font,
            )

    def close(self) -> None:
        if self.after_id is not None:
            self.window.after_cancel(self.after_id)
        if self.chart_animation_after is not None:
            self.window.after_cancel(self.chart_animation_after)
        self._save_state()
        self.window.destroy()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Floating Codex token monitor widget.")
    parser.add_argument("--codex-home", help="Path to Codex home. Defaults to $CODEX_HOME or ~/.codex")
    parser.add_argument("--refresh-ms", type=int, default=REFRESH_MS, help="Refresh interval in milliseconds")
    parser.add_argument("--lang", choices=("en", "zh"), help="UI language. Defaults to saved setting or English.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    codex_home = detect_codex_home(args.codex_home)
    widget = TokenMonitorWidget(codex_home=codex_home, refresh_ms=args.refresh_ms, lang=args.lang)
    widget.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
