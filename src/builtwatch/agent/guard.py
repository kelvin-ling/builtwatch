"""Runtime guard rails applied to every agent invocation.

These are Strands hooks rather than prompt text, because a ceiling a model can talk its
way past is not a ceiling. The guard aborts the run; it never trims quality silently.

A note on how usage is read, because it is easy to get wrong and fails silently when you
do: `AfterModelCallEvent.stop_response` carries only the message and stop reason — no
token counts. Worse, neither model hook fires at all for the deprecated
`Agent.structured_output()` path. Usage therefore comes from the agent's live
`event_loop_metrics.accumulated_usage`, read as a delta after each model call, and every
call site must invoke the agent with `structured_output_model` set rather than calling
`structured_output()`.
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


def _usage_totals(agent) -> tuple[int, int]:
    """Read cumulative token usage off an agent's event loop metrics."""
    metrics = getattr(agent, "event_loop_metrics", None)
    usage = getattr(metrics, "accumulated_usage", None) or {}
    if not isinstance(usage, dict):
        usage = {
            "inputTokens": getattr(usage, "inputTokens", 0),
            "outputTokens": getattr(usage, "outputTokens", 0),
        }
    return int(usage.get("inputTokens", 0) or 0), int(usage.get("outputTokens", 0) or 0)


class BudgetGuard(HookProvider):
    """Meters token spend and enforces run/day/month ceilings plus an iteration cap."""

    def __init__(self, meter: CostMeter, model_id: str, max_iterations: int):
        self.meter = meter
        self.model_id = model_id
        self.max_iterations = max_iterations
        self.model_calls = 0
        self.tool_calls = 0
        self._seen_input = 0
        self._seen_output = 0

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
        self._record_delta(event.agent)

    def _before_tool(self, event: BeforeToolCallEvent) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_iterations * 3:
            raise BudgetExceeded(f"tool call cap reached: {self.tool_calls}")

    def _record_delta(self, agent) -> float:
        """Charge only what has accrued since the last reading."""
        total_in, total_out = _usage_totals(agent)
        delta_in = max(0, total_in - self._seen_input)
        delta_out = max(0, total_out - self._seen_output)
        self._seen_input, self._seen_output = total_in, total_out
        if not (delta_in or delta_out):
            return 0.0
        cost = self.meter.record(self.model_id, delta_in, delta_out)
        logger.debug(
            "model call %s: %s in / %s out / $%.5f (run total $%.5f)",
            self.model_calls,
            delta_in,
            delta_out,
            cost,
            self.meter.run_cost,
        )
        return cost

    def reconcile(self, agent) -> None:
        """Final safety net: charge anything the hooks missed.

        Called after an agent invocation returns. If the SDK ever stops firing
        AfterModelCallEvent, spend still lands in the ledger rather than vanishing.
        """
        self._record_delta(agent)
