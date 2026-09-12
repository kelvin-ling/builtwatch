"""Configuration and hard spend guardrails.

Cost posture: idle cost is zero. Nothing here polls, spins, or keeps a connection open.
Every model call is bounded before it is made, and the run aborts rather than degrading
quietly when a ceiling is reached.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Bedrock on-demand pricing, USD per 1K tokens, us-east-1. Used for pre-flight estimates
# and for the running total that trips the ceiling. Update if AWS repricing occurs.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    # Anthropic — preferred. Strongest instruction-following for the grounding rules,
    # which is what keeps fabricated citations out of findings.
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": (0.001, 0.005),
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": (0.003, 0.015),
    # Amazon Nova — fallback. No model-provider agreement required, and dramatically
    # cheaper. Nova Lite screens for roughly 1/16th the cost of Claude Haiku.
    "us.amazon.nova-micro-v1:0": (0.000035, 0.00014),
    "us.amazon.nova-lite-v1:0": (0.00006, 0.00024),
    "us.amazon.nova-pro-v1:0": (0.0008, 0.0032),
}

# Ordered preference. `builtwatch doctor` probes these and picks the first pair that
# actually invokes, so an account without Anthropic entitlement still runs the product.
SCREEN_MODEL_LADDER: list[str] = [
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.amazon.nova-lite-v1:0",
    "us.amazon.nova-micro-v1:0",
]
ASSESS_MODEL_LADDER: list[str] = [
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.amazon.nova-pro-v1:0",
    "us.amazon.nova-lite-v1:0",
]

DEFAULT_SCREEN_MODEL = SCREEN_MODEL_LADDER[0]
DEFAULT_ASSESS_MODEL = ASSESS_MODEL_LADDER[0]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass
class Limits:
    """Bounds applied to every scan. These are ceilings, not targets."""

    # Per-run bounds — cap the blast radius of a single scan.
    # Keep the deliberate registry ceiling above the current curated set. Operators can
    # lower this with BW_MAX_SOURCES if a workspace needs a smaller watch pass.
    max_sources_per_run: int = field(default_factory=lambda: _env_int("BW_MAX_SOURCES", 20))
    max_systems_per_run: int = field(default_factory=lambda: _env_int("BW_MAX_SYSTEMS", 25))
    max_agent_iterations: int = field(default_factory=lambda: _env_int("BW_MAX_ITERATIONS", 12))
    max_output_tokens: int = field(default_factory=lambda: _env_int("BW_MAX_OUTPUT_TOKENS", 2000))

    # Truncation — a huge page must never turn into a huge bill.
    max_snapshot_chars: int = field(
        default_factory=lambda: _env_int("BW_MAX_SNAPSHOT_CHARS", 24000)
    )
    max_passage_chars: int = 1200

    # Spend ceilings.
    max_cost_per_run_usd: float = field(default_factory=lambda: _env_float("BW_MAX_RUN_USD", 0.25))
    max_cost_per_day_usd: float = field(default_factory=lambda: _env_float("BW_MAX_DAY_USD", 1.00))
    max_cost_per_month_usd: float = field(
        default_factory=lambda: _env_float("BW_MAX_MONTH_USD", 15.00)
    )

    # Network politeness / DoS resistance on the fetch side.
    fetch_timeout_seconds: float = 20.0
    max_fetch_bytes: int = 3_000_000
    fetch_delay_seconds: float = 0.5


@dataclass
class Settings:
    region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "us-east-1"))
    screen_model_id: str = field(
        default_factory=lambda: os.environ.get("BW_SCREEN_MODEL", DEFAULT_SCREEN_MODEL)
    )
    assess_model_id: str = field(
        default_factory=lambda: os.environ.get("BW_ASSESS_MODEL", DEFAULT_ASSESS_MODEL)
    )
    db_path: Path = field(
        default_factory=lambda: Path(os.environ.get("BW_DB", "data/builtwatch.db"))
    )
    registry_path: Path = field(
        default_factory=lambda: Path(os.environ.get("BW_REGISTRY", "sources/registry.yaml"))
    )
    replay_dir: Path = field(default_factory=lambda: Path(os.environ.get("BW_REPLAY", "replay")))
    limits: Limits = field(default_factory=Limits)

    # Public demo mode: read-only replay, no live fetch, no user-supplied sources.
    demo_mode: bool = field(
        default_factory=lambda: os.environ.get("BW_DEMO_MODE", "").lower() in {"1", "true", "yes"}
    )

    def price_for(self, model_id: str) -> tuple[float, float]:
        return MODEL_PRICES.get(model_id, (0.003, 0.015))

    def estimate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        pin, pout = self.price_for(model_id)
        return (input_tokens / 1000.0) * pin + (output_tokens / 1000.0) * pout


class BudgetExceeded(RuntimeError):
    """Raised to abort a run rather than silently spending past a ceiling."""


class CostMeter:
    """Tracks spend within a run and refuses to continue past the configured ceiling."""

    def __init__(self, settings: Settings, spent_today: float = 0.0, spent_month: float = 0.0):
        self.settings = settings
        self.run_cost = 0.0
        self.spent_today = spent_today
        self.spent_month = spent_month
        self.input_tokens = 0
        self.output_tokens = 0

    def check_before_call(self) -> None:
        lim = self.settings.limits
        if self.run_cost >= lim.max_cost_per_run_usd:
            raise BudgetExceeded(
                f"run ceiling reached: ${self.run_cost:.4f} >= ${lim.max_cost_per_run_usd:.2f}"
            )
        if self.spent_today + self.run_cost >= lim.max_cost_per_day_usd:
            raise BudgetExceeded(
                f"daily ceiling reached: ${self.spent_today + self.run_cost:.4f} "
                f">= ${lim.max_cost_per_day_usd:.2f}"
            )
        if self.spent_month + self.run_cost >= lim.max_cost_per_month_usd:
            raise BudgetExceeded(
                f"monthly ceiling reached: ${self.spent_month + self.run_cost:.4f} "
                f">= ${lim.max_cost_per_month_usd:.2f}"
            )

    def record(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        cost = self.settings.estimate_cost(model_id, input_tokens, output_tokens)
        self.run_cost += cost
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        return cost
