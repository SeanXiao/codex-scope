# Codex Context Throttling Plan

## Goal

Reduce Codex input-token growth without breaking task continuity.

Primary goals:

- Keep current task state stable.
- Stop historical tool outputs from repeatedly bloating input context.
- Preserve recoverability by keeping raw records outside the active prompt.
- Make token growth explainable by category and by turn.

Non-goals:

- Changing Codex's internal proprietary compaction logic.
- Replacing Codex with a new agent runtime.
- Lossless replay of every historical message in the active prompt.

## Problem Summary

From current monitoring, the dominant input category is usually `工具输出` rather than the user's message itself. That means the main waste comes from long tool result bodies being carried forward across multiple requests.

Typical pattern:

1. A tool produces long text output.
2. That output remains in the transcript pool.
3. Future requests resend the same content.
4. Input grows even when the task is already understood.

This is a harness problem, not primarily a model problem.

## Mental Model

Treat context as four layers:

1. Fixed layer
System instructions, developer instructions, long-lived policies, stable user constraints.

2. Working layer
Current goal, current todo list, recent conclusions, important files, current blockers.

3. Recent history layer
The last one to two raw turns that are still highly relevant.

4. Archive layer
Old tool outputs, old search results, old verbose assistant replies, old logs.

Only the first three layers should normally go into the next request.
The archive layer should be stored, summarized, and selectively recalled.

## Proposed Architecture

### 1. Raw Transcript Store

Store everything exactly once:

- user message
- assistant message
- tool call
- tool output
- token usage
- timestamps
- turn id

Purpose:

- auditing
- replay
- debugging
- delayed recall

This layer is not the same thing as the active model prompt.

### 2. Working Memory Store

Maintain a compact structured state:

- current_goal
- hard_constraints
- completed_items
- pending_items
- key_files
- key_findings
- latest_failures
- next_step

This is the highest-value context and should almost always survive compaction.

### 3. Summary Store

Maintain summaries at two granularities:

- turn summary
- session summary

Turn summary should include:

- user asked
- actions taken
- important tool findings
- files changed
- unresolved issues
- next action

### 4. Context Planner

Before each request, build the prompt from:

- fixed layer
- working layer
- latest turn summaries
- recent raw turns
- selected recalled archive items

Never assemble the next request directly from the full raw transcript by default.

## Token Budget Policy

Use a soft input budget of `120K` tokens and a hard budget of `160K`.

Suggested budget split:

- Fixed layer: 10K
- Working layer: 20K
- Recent raw turns: 30K
- Turn summaries: 20K
- Tool result summaries: 25K
- Reserve: 15K

When soft budget is exceeded:

1. Compress old tool outputs.
2. Replace older raw turns with turn summaries.
3. Trim verbose assistant history.

When hard budget is exceeded:

1. Keep only latest raw turn.
2. Keep only summaries for older turns.
3. Keep tool outputs as references plus summaries only.

## Tool Output Policy

This is the most important optimization area.

### A. Tool Output Classes

Class A: high-value outputs

- failing test excerpt
- final command result
- final API response summary
- exact error message
- final diff summary

Policy:

- keep concise excerpt
- keep structured summary
- keep raw body in archive

Class B: medium-value outputs

- search results
- file scans
- listings
- intermediate checks

Policy:

- keep summary only
- keep top 3 to 5 findings
- archive raw body

Class C: low-value outputs

- long logs
- repeated status lines
- duplicated listings
- progress chatter

Policy:

- do not keep raw body in active prompt
- archive only

### B. Tool-Specific Caps

Recommended defaults:

- shell output: keep conclusion plus top 20 relevant lines
- file read: keep summary plus matched excerpt only
- search results: keep top 3 hits plus one-line rationale each
- JSON/API: keep selected fields plus one-line summary
- diff/readback: keep changed files plus concise patch summary

### C. Output Normalization Template

Every tool result should be normalized before it becomes active context.

Template:

```text
[Tool Result Summary]
tool: <name>
status: success | failure | partial
conclusion: <one-line outcome>
key_points:
- ...
- ...
- ...
artifacts:
- <file / id / path / reference>
raw_output_ref: <archive id>
```

## Turn Compaction Policy

At the end of each turn, generate a structured turn summary:

```text
turn_id:
user_intent:
actions_taken:
key_findings:
files_touched:
decisions:
unresolved:
next_step:
```

Then mark raw items in that turn for one of these retention modes:

- keep_raw
- keep_excerpt
- summary_only
- archive_only

Recommended default:

- most tool outputs -> summary_only
- large logs -> archive_only
- latest assistant final answer -> keep_excerpt
- latest user message -> keep_raw

## Context Assembly Algorithm

Pseudo-code:

```python
def assemble_request(new_user_msg, state):
    budget = 120_000

    fixed = load_fixed_layer()
    working = load_working_memory()
    recent_turns = load_recent_raw_turns(limit=2)
    turn_summaries = load_recent_turn_summaries(limit=8)
    recalled = []

    prompt = []
    prompt += fixed
    prompt += working
    prompt += recent_turns
    prompt += [new_user_msg]

    if estimate_tokens(prompt) > budget:
        prompt = []
        prompt += fixed
        prompt += working
        prompt += turn_summaries
        prompt += recent_turns[-1:]
        prompt += [new_user_msg]

    if estimate_tokens(prompt) > budget:
        prompt = []
        prompt += fixed
        prompt += working
        prompt += turn_summaries[-4:]
        prompt += [new_user_msg]

    refs = extract_needed_archive_refs(new_user_msg, working)
    recalled = recall_archive_items(refs, cap_tokens=20_000)
    prompt += recalled

    return prompt
```

## Working Memory Update Rules

After each assistant step or tool completion:

1. Update `current_goal` only if user intent changed.
2. Append completed tasks only when they are actually done.
3. Keep `pending_items` short and action-oriented.
4. Replace verbose discoveries with one-line findings.
5. Store file paths, not full file bodies.

Good working memory example:

```text
current_goal: Restore recent-request chart and keep popup drilldown.
hard_constraints:
- preserve current UI structure
- keep Chinese labels
completed_items:
- restored recent 20 request layout
- added pie chart in popup
pending_items:
- verify turn labels remain readable
key_files:
- /Users/sean_1/codex/codex-tool/codex_token_widget.py
key_findings:
- historical tool output dominates input size
next_step:
- reduce repeated tool-output carry-forward
```

## Recall Policy

Archive recall should be selective, not automatic.

Good recall triggers:

- user asks to revisit an earlier failure
- assistant needs exact previous error text
- assistant needs exact tool result fields
- assistant needs specific old file snippet

Bad recall triggers:

- generic continuation
- vague "keep going"
- routine refinement after the result is already summarized

## Monitoring and Success Metrics

Track these metrics in the monitor:

- latest request input tokens
- current turn total tokens
- tool output share of upstream
- historical tool call share of upstream
- cache share of upstream
- average requests per turn
- pre-compaction input
- post-compaction input
- compaction savings

Target improvements:

- tool output share reduced by 40%+
- average input per request reduced by 25%+
- current-turn continuity preserved
- fewer turns crossing 120K input

## Rollout Plan

### Phase 1: Safe Reduction

- normalize tool outputs
- add output caps
- add turn summaries
- keep recent two raw turns

Risk: low

### Phase 2: Structured Memory

- introduce working memory store
- build request assembler from structured state
- move older turns to summary-first mode

Risk: medium

### Phase 3: Smart Recall

- add archive reference ids
- add selective recall of archived tool outputs
- add budget-aware recall planner

Risk: medium

## Recommended Integration Points For This Project

Given the current monitor, the easiest evolution path is:

1. Keep using raw session logs for observation.
2. Add a separate `compaction simulator` module first.
3. Show estimated savings before changing any real request flow.
4. Once rules look stable, place a request-assembly layer in front of model calls.

For this repository, practical next files would be:

- `codex_context_throttler.py`
- `codex_context_budget.py`
- `codex_context_memory.py`

## Minimal First Implementation

If only one thing is implemented first, do this:

At the end of every turn:

- summarize all tool outputs into a short turn summary
- retain raw tool outputs only in archive
- include only summary plus latest raw turn in the next request

This single change will usually produce the biggest token reduction.

## Decision Rule

Use this default rule:

If a piece of text is not likely to be quoted verbatim in the next step, it should not remain as raw text in the active prompt.

That is the core throttling heuristic.
