#!/usr/bin/env python3
"""
Shared localization helpers for Codex Scope desktop tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "zh")
SETTINGS_PATH = Path("~/.codex/codex_scope_settings.json").expanduser()


LABELS: Dict[str, Dict[str, str]] = {
    "system_prompt": {"en": "System prompt", "zh": "系统提示"},
    "developer_prompt": {"en": "Developer prompt", "zh": "开发者提示"},
    "user_message": {"en": "User message", "zh": "用户消息"},
    "runtime_context": {"en": "Runtime context", "zh": "运行上下文"},
    "tool_output": {"en": "Tool output", "zh": "工具输出"},
    "tool_call_history": {"en": "Tool call history", "zh": "历史工具调用"},
    "assistant_history": {"en": "Assistant output", "zh": "历史助手输出"},
    "reasoning_output": {"en": "Reasoning output", "zh": "推理输出"},
    "other": {"en": "Other", "zh": "其他"},
    "prompt": {"en": "Prompt", "zh": "提示词"},
    "memory": {"en": "Memory", "zh": "记忆"},
    "planner": {"en": "Planner", "zh": "规划"},
    "tool": {"en": "Tool", "zh": "工具"},
    "truncation": {"en": "Truncation", "zh": "截断"},
    "cache": {"en": "Cache", "zh": "缓存"},
}


STRINGS: Dict[str, Dict[str, str]] = {
    "language.toggle": {"en": "English", "zh": "中文"},
    "monitor.window_title": {"en": "Codex Token Monitor", "zh": "Codex Token 监控"},
    "monitor.status.loading": {"en": "Loading...", "zh": "加载中..."},
    "monitor.status.refreshing": {"en": "Refreshing...", "zh": "刷新中..."},
    "monitor.status.updated": {"en": "Updated {time}", "zh": "已更新 {time}"},
    "monitor.status.error": {"en": "Error: {message}", "zh": "错误: {message}"},
    "monitor.metric.today_title": {"en": "Today (active {duration})", "zh": "今日（耗时 {duration}）"},
    "monitor.metric.yesterday_title": {"en": "Yesterday (active {duration})", "zh": "昨日（耗时 {duration}）"},
    "monitor.metric.total_title": {"en": "All Time (active {duration})", "zh": "累计总量（耗时 {duration}）"},
    "monitor.metric.today_detail": {
        "en": "{sessions} sessions / {turns} turns / {round_trips} requests",
        "zh": "{sessions} 会话 / {turns} 轮 / {round_trips} 往返",
    },
    "monitor.metric.yesterday_detail": {
        "en": "{sessions} sessions / {turns} turns / {round_trips} requests",
        "zh": "{sessions} 会话 / {turns} 轮 / {round_trips} 往返",
    },
    "monitor.metric.total_detail": {
        "en": "{sessions} sessions / {turns} total turns / {round_trips} requests",
        "zh": "{sessions} 会话 / 累计 {turns} 轮 / {round_trips} 往返",
    },
    "monitor.metric.total_exact": {
        "en": "Exact: {tokens} tokens",
        "zh": "精确 token: {tokens}",
    },
    "monitor.header.latest": {"en": "Latest {time}", "zh": "最新 {time}"},
    "monitor.no_requests": {"en": "No token requests yet", "zh": "还没有 token 请求数据"},
    "monitor.turn_legend": {"en": "{tag} turn {tokens}", "zh": "{tag} 本轮 {tokens}"},
    "detail.empty_chart": {"en": "No data", "zh": "无数据"},
    "detail.total": {"en": "Total", "zh": "总量"},
    "detail.breakdown.none": {"en": "No breakdown data", "zh": "暂无分类数据"},
    "detail.breakdown.row": {
        "en": "{idx}. {label}: {tokens} / {pct:.1f}% / {count} items",
        "zh": "{idx}. {label}: {tokens} / {pct:.1f}% / {count} 项",
    },
    "detail.copy.clipboard": {"en": "Copied to clipboard", "zh": "已复制到剪贴板"},
    "detail.turn_summary.title": {"en": "Turn Continue Card", "zh": "本轮续聊卡"},
    "detail.turn_summary.header": {
        "en": "turn_id: {turn_id}  |  This card keeps only the dialogue for this turn.",
        "zh": "turn_id: {turn_id}  |  这张续聊卡只保留这一轮里你和 AI 的对话脉络。",
    },
    "detail.turn_summary.subheader": {
        "en": "Suggested use: after inspecting A/B/C/D below, copy this into a new session without tool details.",
        "zh": "推荐用法: 点底部 A/B/C/D 后，直接在这里复制到新会话继续，不必带工具细节。",
    },
    "detail.current_summary.title": {"en": "Current Session Continue Card", "zh": "当前会话续聊卡"},
    "detail.current_summary.header": {
        "en": "This card keeps only the dialogue context you and the AI need to continue in a new session.",
        "zh": "这张续聊卡只保留你和 AI 的对话脉络，适合直接复制到新会话里继续。",
    },
    "detail.current_summary.subheader": {
        "en": "Suggested use: inspect the monitor first, then copy this card into a new session to continue.",
        "zh": "推荐用法: 先看监控定位膨胀，再点这里复制续聊卡到新会话继续。",
    },
    "detail.button.copy_summary": {"en": "Copy continue card", "zh": "复制续聊卡"},
    "detail.button.close": {"en": "Close", "zh": "关闭"},
    "detail.turn_summary.copied": {"en": "Turn continue card copied", "zh": "已复制本轮续聊卡"},
    "detail.current_summary.copied": {"en": "Current session continue card copied", "zh": "已复制当前会话续聊卡"},
    "detail.turn_summary.opened": {"en": "Opened turn continue card", "zh": "已打开本轮续聊卡"},
    "detail.turn_summary.open_error_title": {"en": "Failed to open continue card", "zh": "打开续聊卡失败"},
    "detail.current_summary.none_title": {"en": "No session yet", "zh": "暂无会话"},
    "detail.current_summary.none_body": {
        "en": "There is no session data available yet to build a continue card.",
        "zh": "当前还没有可用于生成续聊卡的会话数据。",
    },
    "detail.upstream.title": {"en": "Request Input Details", "zh": "请求上行详情"},
    "detail.downstream.title": {"en": "Request Output Details", "zh": "请求下行详情"},
    "detail.upstream.header": {
        "en": "Time {time}  |  input {up}  |  output {down}  |  cache {cache}  |  total {total}",
        "zh": "时间 {time}  |  上行 {up}  |  下行 {down}  |  缓存 {cache}  |  总量 {total}",
    },
    "detail.downstream.header": {
        "en": "Time {time}  |  output {down}  |  output_only {output}  |  reasoning {reasoning}",
        "zh": "时间 {time}  |  下行 {down}  |  output {output}  |  reasoning {reasoning}",
    },
    "detail.upstream.subheader": {
        "en": "This view comes from local Codex session files. Total input tokens are exact; category splits are estimated by context length.",
        "zh": "以下内容来自本地 Codex 会话落盘。总上行 token 是精确值；下面的分类拆分是按上下文长度估算分摊。",
    },
    "detail.downstream.subheader": {
        "en": "This view shows the local record written after the request returned, including assistant messages and tool calls.",
        "zh": "这里展示的是这次请求返回后的本地记录，包括助手消息、工具调用等。",
    },
    "detail.upstream.pie_title": {"en": "Input Breakdown", "zh": "上行分类饼图"},
    "detail.downstream.pie_title": {"en": "Output Breakdown", "zh": "下行分类饼图"},
    "detail.attr.title": {"en": "### Attribution (estimated; cache exact)", "zh": "### 专业归因（估算；cache 精确）"},
    "detail.breakdown.title": {"en": "### Input breakdown (estimated)", "zh": "### 上行分类汇总（估算）"},
    "detail.context_item": {"en": "### Context Item {idx}", "zh": "### 上下文项 {idx}"},
    "detail.output_item": {"en": "### Output Item {idx}", "zh": "### 下行项 {idx}"},
    "detail.content": {"en": "content:", "zh": "content:"},
    "detail.category": {"en": "category: {label}", "zh": "category: {label}"},
    "detail.output.none": {"en": "There are no local output items for this request.", "zh": "这次下行没有可展示的本地输出项。"},
    "monitor.compact_summary.title": {"en": "[Current Session Compact Summary]", "zh": "【当前会话压缩摘要】"},
    "monitor.compact_summary.note": {
        "en": "Note: this compact summary is generated by an external monitor and does not rewrite Codex internal context.",
        "zh": "说明: 这是外部监控工具生成的压缩版摘要，不会直接改写 Codex 内部上下文。",
    },
    "continue.window_title": {"en": "Codex Continue Card", "zh": "Codex 续聊卡"},
    "continue.status.loading": {"en": "Loading...", "zh": "加载中..."},
    "continue.status.copied": {"en": "Continue card copied", "zh": "已复制续聊卡"},
    "continue.status.updated": {"en": "Updated {name}", "zh": "已更新 {name}"},
    "continue.status.error": {"en": "Error: {message}", "zh": "错误: {message}"},
    "continue.button.copy": {"en": "Copy continue card", "zh": "复制续聊卡"},
    "continue.button.refresh": {"en": "Refresh", "zh": "刷新"},
    "continue.helper": {
        "en": "Use this by copying it into a new session. It keeps only the dialogue context between you and the AI.",
        "zh": "用途: 复制到新会话里继续，只保留你和 AI 的对话脉络。",
    },
    "continue.section.title": {"en": "Continue Summary", "zh": "Continue Summary"},
    "continue.none_title": {"en": "Nothing to copy", "zh": "暂无内容"},
    "continue.none_body": {"en": "There is no continue card available yet.", "zh": "当前还没有可复制的续聊卡。"},
    "summary.card_title": {"en": "[AI Continue Card]", "zh": "【AI续聊卡】"},
    "summary.intro": {
        "en": "Treat the content below as machine input for a new session and continue directly without asking for background again. Preserve the current-turn focus and the prior turn history as much as possible.",
        "zh": "请把下面内容当作新会话的机器输入，直接继续任务，不要重复索要背景。这里优先保留当前轮重点和当前轮之前的全部 turn 脉络，尽量避免丢上下文。",
    },
    "summary.section.focus": {"en": "1. Focus", "zh": "一、Focus"},
    "summary.section.state": {"en": "2. Current Task State", "zh": "二、Current Task State"},
    "summary.section.dialogue": {"en": "3. Current Turn Dialogue", "zh": "三、当前轮对话"},
    "summary.section.files": {"en": "4. File Changes / Persisted Artifacts (Current Turn)", "zh": "四、文件变更 / 落盘痕迹（当前轮）"},
    "summary.section.signals": {"en": "5. Current Turn Signals", "zh": "五、Current Turn Signals"},
    "summary.section.history": {"en": "6. Prior Session History (Before Current Turn)", "zh": "六、此前 session 全量脉络（当前轮之前）"},
    "summary.section.instruction": {"en": "7. Continue Instruction", "zh": "七、Continue Instruction"},
    "summary.field.current_goal": {"en": "current_goal", "zh": "current_goal"},
    "summary.field.latest_user_request": {"en": "latest_user_request", "zh": "latest_user_request"},
    "summary.field.session_total_tokens": {"en": "session_total_tokens", "zh": "session_total_tokens"},
    "summary.field.session_round_trips": {"en": "session_round_trips", "zh": "session_round_trips"},
    "summary.field.focus_round_trips": {"en": "focus_round_trips", "zh": "focus_round_trips"},
    "summary.field.focus_tokens": {"en": "focus_tokens", "zh": "focus_tokens"},
    "summary.empty": {"en": "(not found)", "zh": "(未提取到)"},
    "summary.user": {"en": "User", "zh": "用户"},
    "summary.assistant": {"en": "Assistant", "zh": "助手"},
    "summary.none_short": {"en": "None", "zh": "暂无"},
    "summary.history.empty": {"en": "- This is the first turn in this session.", "zh": "- 这是本 session 的第一轮。"},
    "summary.instruction": {
        "en": "- Continue directly from current_goal, the current-turn dialogue, current-turn file traces, and the full prior session history. Do not ask for background again.",
        "zh": "- 直接基于 current_goal、当前轮对话、当前轮文件痕迹，以及此前 session 全量脉络继续推进；不要要求我重新补背景。",
    },
    "summary.completed": {"en": "Completed: ", "zh": "已完成: "},
    "summary.pending": {"en": "Pending: ", "zh": "待做: "},
    "summary.decisions.req_empty": {"en": "(none)", "zh": "(无)"},
    "summary.decisions.done_empty": {"en": "(none)", "zh": "(无)"},
    "summary.history.turn": {
        "en": "- Prior turn {index} | {round_trips} requests | input {upstream} | output {downstream} | cache {cached} | total {total}",
        "zh": "- 之前第 {index} 轮 | {round_trips} 次往返 | 上行 {upstream} | 下行 {downstream} | 缓存 {cached} | 总量 {total}",
    },
    "summary.history.files": {"en": "  Files: {files}", "zh": "  文件: {files}"},
}


def normalize_language(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANGUAGE
    lang = lang.lower()
    if lang.startswith("zh"):
        return "zh"
    return "en"


def load_language(default: str = DEFAULT_LANGUAGE) -> str:
    if SETTINGS_PATH.exists():
        try:
            payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return normalize_language(payload.get("language", default))
        except (OSError, json.JSONDecodeError):
            return normalize_language(default)
    return normalize_language(default)


def save_language(lang: str) -> str:
    normalized = normalize_language(lang)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"language": normalized}
    SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def get_label(key: str, lang: str) -> str:
    values = LABELS.get(key)
    if not values:
        return key
    return values.get(normalize_language(lang), values["en"])


def get_string(key: str, lang: str, **kwargs: object) -> str:
    values = STRINGS.get(key)
    if not values:
        template = key
    else:
        template = values.get(normalize_language(lang), values["en"])
    return template.format(**kwargs)
