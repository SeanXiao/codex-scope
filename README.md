# Codex Scope

Codex Scope is an unofficial local diagnostics toolkit for Codex sessions.

It reads data already stored on your machine and helps you understand:

- how many tokens each model call actually used
- what content was included in the effective context
- how usage changes across recent turns
- how to generate a compact "continue card" for starting a fresh session

![Codex Scope monitor dashboard](assets/monitor-dashboard.png)

The screenshot above shows the floating monitor dashboard for recent token activity, daily totals, and cumulative usage.

## What It Reads

Codex Scope works with local Codex data only:

- `~/.codex/sessions/**/*.jsonl`
- `~/.codex/state_*.sqlite`

It does not rely on packet capture or proxying model traffic.

## Features

- Exact token accounting
  Reads persisted `event_msg.token_count.info` usage records instead of estimating token counts locally.

- Context inspection
  Reconstructs the context pool used before a model call so you can inspect what was actually sent.

- Floating monitor window
  Provides a draggable always-on-top desktop widget for recent activity, grouped turns, and token trends.

- Continue card generation
  Builds a compact machine-oriented summary you can paste into a new session to resume work faster.

- Bilingual desktop UI
  Lets you switch between English and Chinese, with English as the default language.

## UI Preview

- A floating desktop dashboard for recent token activity
- Daily, previous-day, and cumulative usage totals
- Grouped turn visibility for spotting spikes quickly

## Project Layout

- `codex_context_inspector.py`
  Session scanning, context export, and exact token summaries.

- `codex_token_widget.py`
  Floating desktop monitor window.

- `codex_continue_summary.py`
  Continue-card UI and summary generation logic.

## Quick Start

Show a summary for the latest session:

```bash
cd /Users/sean_1/codex/codex-tool
python3 codex_context_inspector.py summary --latest
```

Launch the monitor widget:

```bash
cd /Users/sean_1/codex/codex-tool
/opt/homebrew/bin/python3.13 codex_token_widget.py
```

Launch the continue-card tool:

```bash
cd /Users/sean_1/codex/codex-tool
/opt/homebrew/bin/python3.13 codex_continue_summary.py
```

Launch with Chinese UI explicitly:

```bash
/opt/homebrew/bin/python3.13 codex_token_widget.py --lang zh
```

On macOS you can also launch:

- `启动 Codex Token 监控.command`
- `Codex Token 监控.app`

## Common Commands

List recent sessions:

```bash
python3 codex_context_inspector.py sessions --limit 10
```

Show exact total token usage across all sessions:

```bash
python3 codex_context_inspector.py totals --exact
```

Inspect calls from the latest session:

```bash
python3 codex_context_inspector.py calls --latest
```

Dump the reconstructed context before a specific call:

```bash
python3 codex_context_inspector.py dump-context --latest --call 1 --max-chars 1000
```

Dump the same context as JSON:

```bash
python3 codex_context_inspector.py dump-context --latest --call 1 --json
```

Print a continue card for the latest session:

```bash
/opt/homebrew/bin/python3.13 codex_continue_summary.py --latest
```

## Privacy

This project analyzes local Codex persistence data on your own machine.
It does not require sending your session history to an external service.

## Notes

- The monitor shows real requests that already happened.
- The continue card is intended for bootstrapping a new session, not rewriting the current internal context.
- Widget position and related state are stored in `~/.codex/codex_token_widget.json`.

## Naming Recommendation

Recommended public GitHub repository name:

`codex-scope`

Recommended product title:

`Codex Scope`

Why this name works:

- it matches the current codebase and artifacts
- it is short and easy to remember
- it communicates inspection, visibility, and diagnostics

If you want a more neutral public-facing alternative, consider:

- `scope-for-codex`
- `codex-session-scope`
- `codex-session-inspector`
