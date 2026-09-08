"""Environment and model-availability diagnosis.

Bedrock model entitlement varies by account in ways that are not visible from the control
plane: `ListFoundationModels` happily lists models an account cannot invoke. The only
reliable check is a real, tiny invocation.

`builtwatch doctor` walks the preference ladder, probes each model with a one-token call,
and reports the cheapest working pair. Costs a fraction of a cent and turns an opaque
`ValidationException` into an actionable answer.
"""

from __future__ import annotations

from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from .config import (
    ASSESS_MODEL_LADDER,
    MODEL_PRICES,
    SCREEN_MODEL_LADDER,
    Settings,
)

PROBE_HINT = {
    "AccessDeniedException": "IAM policy denies bedrock:InvokeModel for this principal.",
    "ValidationException": (
        "Account-level model access. Anthropic models need the one-time use-case form: "
        "Bedrock console -> Model catalog -> pick the model -> Open in Playground."
    ),
    "ResourceNotFoundException": "Model id not available in this region.",
    "ThrottlingException": "Throttled — the model is reachable but busy. Treat as available.",
}


@dataclass
class ProbeResult:
    model_id: str
    ok: bool
    error_code: str | None = None
    message: str | None = None
    input_price: float = 0.0
    output_price: float = 0.0

    @property
    def hint(self) -> str | None:
        return PROBE_HINT.get(self.error_code or "")


def probe_model(model_id: str, region: str) -> ProbeResult:
    """Invoke a model with the smallest possible request to prove entitlement."""
    prices = MODEL_PRICES.get(model_id, (0.0, 0.0))
    client = boto3.client("bedrock-runtime", region_name=region)
    try:
        client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "OK"}]}],
            inferenceConfig={"maxTokens": 1},
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        # Throttling proves the model is reachable; only entitlement failures matter here.
        if code == "ThrottlingException":
            return ProbeResult(model_id, True, code, "throttled but reachable", *prices)
        return ProbeResult(model_id, False, code, exc.response["Error"]["Message"], *prices)
    except Exception as exc:  # noqa: BLE001 - a probe must report, never raise
        return ProbeResult(model_id, False, type(exc).__name__, str(exc), *prices)
    return ProbeResult(model_id, True, None, None, *prices)


def diagnose(settings: Settings) -> dict:
    """Probe both ladders and recommend the cheapest working configuration."""
    identity: dict = {}
    try:
        identity = boto3.client("sts", region_name=settings.region).get_caller_identity()
    except Exception as exc:  # noqa: BLE001
        identity = {"error": f"{type(exc).__name__}: {exc}"}

    seen: dict[str, ProbeResult] = {}

    def probe_once(model_id: str) -> ProbeResult:
        if model_id not in seen:
            seen[model_id] = probe_model(model_id, settings.region)
        return seen[model_id]

    screen_results = [probe_once(m) for m in SCREEN_MODEL_LADDER]
    assess_results = [probe_once(m) for m in ASSESS_MODEL_LADDER]

    screen_pick = next((r.model_id for r in screen_results if r.ok), None)
    assess_pick = next((r.model_id for r in assess_results if r.ok), None)

    return {
        "account": identity.get("Account"),
        "arn": identity.get("Arn"),
        "region": settings.region,
        "screen_results": screen_results,
        "assess_results": assess_results,
        "screen_pick": screen_pick,
        "assess_pick": assess_pick,
        "usable": bool(screen_pick and assess_pick),
    }
