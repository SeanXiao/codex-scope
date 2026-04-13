#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudgetPolicy:
    soft_limit_tokens: int = 120_000
    hard_limit_tokens: int = 160_000
    fixed_layer_cap: int = 10_000
    working_layer_cap: int = 20_000
    recent_raw_cap: int = 30_000
    turn_summary_cap: int = 20_000
    tool_summary_cap: int = 25_000
    reserve_cap: int = 15_000

    def pressure_level(self, input_tokens: int) -> str:
        if input_tokens >= self.hard_limit_tokens:
            return "hard"
        if input_tokens >= self.soft_limit_tokens:
            return "soft"
        return "normal"


def default_budget_policy() -> ContextBudgetPolicy:
    return ContextBudgetPolicy()
