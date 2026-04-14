# GitHub Launch Kit

This file collects the final copy for publishing `codex-scope` on GitHub and sharing it with the broader developer community.

## GitHub About

Recommended short description:

`Local observability toolkit for Codex sessions with exact token accounting, context inspection, and continue cards.`

Alternative shorter version:

`Local observability toolkit for Codex sessions with token monitoring, context inspection, and continue cards.`

## Suggested Topics

- `codex`
- `observability`
- `token-monitoring`
- `developer-tools`
- `python`
- `tkinter`
- `desktop-tool`
- `session-inspection`

## Main Entry

macOS / Linux:

```bash
bash scripts/launch_monitor.sh --lang en
```

Windows:

```bat
scripts\launch_monitor.cmd --lang en
```

## Product Hunt / Hacker News Style Post

Suggested title:

`Show HN: Codex Scope — local token and context observability for Codex sessions`

Suggested post body:

```text
I built and open-sourced Codex Scope, a local observability toolkit for Codex sessions.

The goal is simple: make it easier to understand what is actually happening inside long Codex workflows without relying on rough token guesses or network sniffing.

Codex Scope reads local Codex persistence data on your machine and helps you:
- inspect exact token usage
- replay what actually entered context
- monitor recent requests in a desktop dashboard
- generate continue cards for restarting a task in a fresh session

What I wanted was a tool that answered questions like:
- Why did this session suddenly get expensive?
- What context actually made it into the model call?
- How can I continue a long task without dragging all prior context forever?

Current support:
- macOS
- Windows launcher scripts included
- MIT licensed

Main entry:
- macOS / Linux: bash scripts/launch_monitor.sh --lang en
- Windows: scripts\launch_monitor.cmd --lang en

Repo:
https://github.com/SeanXiao/codex-scope
```

## Shorter Social Post

```text
I open-sourced Codex Scope: a local observability toolkit for Codex sessions.

It helps you inspect exact token usage, replay real context, monitor recent requests, and generate continue cards for fresh sessions.

MIT licensed:
https://github.com/SeanXiao/codex-scope
```

## GitHub Repository Notes

- Set the default branch to `codex/intl`
- Keep the repository `Public`
- Keep `MIT` as the project license
- Prefer the script launchers as the supported entry points in public docs
