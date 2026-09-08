"""Capture the replay corpus.

Runs a real live fetch of every registry source and writes the result to ``replay/`` with
its retrieval date. The demo therefore runs against material that was genuinely retrieved
from the cited publisher, not material written by hand — and every replay file records
exactly when it was captured and from where.

Re-run this to refresh the corpus:

    python scripts/capture_replay.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from builtwatch.config import Settings  # noqa: E402
from builtwatch.fetch import fetch_live  # noqa: E402
from builtwatch.registry import enabled_sources, load_registry  # noqa: E402


def main() -> int:
    settings = Settings()
    replay_dir = Path(settings.replay_dir)
    replay_dir.mkdir(parents=True, exist_ok=True)

    sources = enabled_sources(load_registry(settings.registry_path))
    failures = 0

    for source in sources:
        snapshot = fetch_live(source, settings.limits)
        if not snapshot.succeeded:
            print(f"FAIL {source.id}: {snapshot.fetch_status.value} {snapshot.error}")
            failures += 1
            continue

        payload = {
            "source_id": source.id,
            "source_name": source.name,
            "publisher": source.publisher,
            "url": source.url,
            "retrieved_at": snapshot.retrieved_at.isoformat(),
            "captured_by": "scripts/capture_replay.py",
            "published_at": snapshot.published_at.isoformat() if snapshot.published_at else None,
            "effective_at": None,
            "fetch_status": "ok",
            "content": snapshot.content,
        }
        path = replay_dir / f"{source.id}.yaml"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(
                "# Replay snapshot. Real content retrieved from the publisher URL below\n"
                f"# on {snapshot.retrieved_at.date().isoformat()} by scripts/capture_replay.py.\n"
                "# Quoted in findings as historical material, clearly labelled mode='replay'.\n"
            )
            yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False, width=100)
        print(f"ok   {source.id}: {len(snapshot.content)} chars -> {path}")

    print(f"\ncaptured {len(sources) - failures}/{len(sources)} sources at "
          f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
