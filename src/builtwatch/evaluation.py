"""Offline passage-level benchmark. Never retrieves sources or instantiates a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .models import FetchStatus, Source, SourceSnapshot, SystemPassport
from .rules import ENGINE, assess


def evaluate(path: Path) -> dict[str, Any]:
    corpus = json.loads(path.read_text())
    tp = fp = fn = 0
    failures = []
    for case in corpus["cases"]:
        passport = SystemPassport(
            id="benchmark",
            name="Benchmark",
            purpose="Offline evaluation",
            services=case["dependencies"],
        )
        source = Source(
            id=case["source_id"],
            name="Benchmark source",
            category=case["category"],
            url="https://example.com/source",
            publisher="Fixture",
        )
        snapshot = SourceSnapshot(
            id="snap_benchmark",
            source_id=source.id,
            mode="replay",
            fetch_status=FetchStatus.OK,
            content="No evidence supplied." if case["forged"] else "\n".join(case["passages"]),
            added_passages=[] if case["baseline"] else case["passages"],
        )
        findings, problems = assess(
            passport, {snapshot.id: snapshot}, {source.id: source}, "run_eval"
        )

        def normal(text: str) -> str:
            return " ".join(text.lower().split())

        expected = {normal(case["passages"][i]) for i in case["expected"]}
        actual = {normal(e.passage) for f in findings for e in f.evidence}
        tp += len(actual & expected)
        fp += len(actual - expected)
        fn += len(expected - actual)
        if actual != expected or problems:
            failures.append(
                {
                    "id": case["id"],
                    "missed": sorted(expected - actual),
                    "unexpected": sorted(actual - expected),
                    "grounding": problems,
                }
            )
    return {
        "engine": ENGINE,
        "cases": len(corpus["cases"]),
        "passed": len(corpus["cases"]) - len(failures),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "failures": failures,
        "scope": corpus["description"],
        "model_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("tests/fixtures/rules_benchmark.json"))
    args = parser.parse_args()
    report = evaluate(args.corpus)
    print(json.dumps(report, indent=2))
    raise SystemExit(bool(report["failures"]))


if __name__ == "__main__":
    main()
