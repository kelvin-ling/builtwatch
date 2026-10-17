from __future__ import annotations

from pathlib import Path

from builtwatch.evaluation import evaluate


def test_labeled_rules_benchmark():
    result = evaluate(Path(__file__).parent / "fixtures/rules_benchmark.json")
    assert not result["failures"], result["failures"]
    assert result["passed"] == result["cases"]
    assert result["model_calls"] == 0
