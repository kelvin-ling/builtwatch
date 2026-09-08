"""Runtime guard rails applied to every agent invocation.

These are Strands hooks rather than prompt text, because a ceiling a model can talk its
way past is not a ceiling. The guard aborts the run; it never trims quality silently.
"""

from __future__ import annotations

import logging

from strands.hooks import (
    AfterModelCallEvent,
    BeforeModelCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

from ..config import BudgetExceeded, CostMeter

logger = logging.getLogger(__name__)


class BudgetGuard(HookProvider):
    """Meters token spend and enforces run/day/month ceilings plus an iteration cap."""

    def __init__(self, meter: CostMeter, model_id: str, max_iterations: int):
        self.meter = meter
        self.model_id = model_id
        self.max_iterations = max_iterations
        self.model_calls = 0
        self.tool_calls = 0

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeModelCallEvent, self._before_model)
        registry.add_callback(AfterModelCallEvent, self._after_model)
        registry.add_callback(BeforeToolCallEvent, self._before_tool)

    def _before_model(self, event: BeforeModelCallEvent) -> None:
        self.model_calls += 1
        if self.model_calls > self.max_iterations:
            raise BudgetExceeded(
                f"iteration cap reached: {self.model_calls} model calls > {self.max_iterations}"
            )
        self.meter.check_before_call()

    def _after_model(self, event: AfterModelCallEvent) -> None:
        usage = self._extract_usage(event)
        if usage is None:
            return
        input_tokens, output_tokens = usage
        cost = self.meter.record(self.model_id, input_tokens, output_tokens)
        logger.debug(
            "model call %s: %s in / %s out / $%.5f (run total $%.5f)",
            self.model_calls,
            input_tokens,
            output_tokens,
            cost,
            self.meter.run_cost,
        )

    def _before_tool(self, event: BeforeToolCallEvent) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_iterations * 3:
            raise BudgetExceeded(f"tool call cap reached: {self.tool_calls}")

    @staticmethod
    def _extract_usage(event: AfterModelCallEvent) -> tuple[int, int] | None:
        """Pull token usage off the model response, tolerating SDK shape differences."""
        candidates = [
            getattr(event, "usage", None),
            getattr(getattr(event, "stop_response", None), "usage", None),
            getattr(getattr(event, "response", None), "usage", None),
        ]
        for usage in candidates:
            if usage is None:
                continue
            if isinstance(usage, dict):
                inp = usage.get("inputTokens") or usage.get("input_tokens")
                out = usage.get("outputTokens") or usage.get("output_tokens")
            else:
                inp = getattr(usage, "inputTokens", None) or getattr(usage, "input_tokens", None)
                out = getattr(usage, "outputTokens", None) or getattr(usage, "output_tokens", None)
            if inp is not None and out is not None:
                return int(inp), int(out)
        return None
