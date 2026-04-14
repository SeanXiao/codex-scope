---
name: codex-scope
description: Use this skill when the user wants to inspect local Codex session traffic, launch the floating token monitor, open or generate an AI continue card, or replay what was sent to the model from persisted ~/.codex session data.
---

# Codex Scope

This skill is for local Codex session observability and continuation.

Use it when the user wants to:

- watch recent upstream/downstream token traffic in a floating monitor
- click through recent turns and open a turn-scoped continue card
- generate a continue card for a session or turn and paste it into a new chat
- inspect exact token totals or dump the context for a specific call

Do not use this skill for generic prompt engineering or remote service tracing. It works from local persisted Codex data under `~/.codex`.

## Quick routing

- Main entry point: use the monitor launcher first
- For a live visual dashboard: run `bash ../scripts/launch_monitor.sh`
- For a standalone continue-card window: run `scripts/codex_continue_summary.py`
- For CLI inspection, totals, sessions, or context dumps: run `scripts/codex_context_inspector.py`

## Commands

From this skill directory:

```bash
bash ../scripts/launch_monitor.sh
```

```bash
bash ../scripts/launch_continue_summary.sh
```

```bash
python3 scripts/codex_context_inspector.py summary --latest
```

```bash
python3 scripts/codex_context_inspector.py sessions --limit 10
```

```bash
python3 scripts/codex_context_inspector.py calls --latest
```

```bash
python3 scripts/codex_context_inspector.py dump-context --latest --call 1 --max-chars 1200
```

## Workflow

1. If the user is debugging token growth or wants a persistent monitor, launch the floating monitor first.
2. If the user wants to continue work in a fresh conversation, open the continue card and copy the generated machine input.
3. If the user asks why a specific request was large, use the inspector CLI to dump the exact call context or list recent calls.

## Notes

- The monitor and continue-card windows are mac-friendly Tk apps.
- The continue card is meant for a new chat; it does not mutate the current Codex conversation state.
- The inspector reads Codex local persistence only; it is not a websocket/network sniffer.
