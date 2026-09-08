"""Retrieval is the attack surface. It is locked down and it never fails silently."""

from __future__ import annotations

import pytest
import yaml

from builtwatch.config import Limits
from builtwatch.fetch import UnsafeURL, assert_safe_url, extract_text, fetch_replay
from builtwatch.models import FetchStatus, Source, SourceCategory


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/policy",             # plain http
        "https://localhost/admin",               # loopback
        "https://127.0.0.1/admin",               # loopback by ip
        "https://169.254.169.254/latest/meta-data/",  # cloud instance metadata
        "https://10.0.0.5/internal",             # private range
        "https://192.168.1.1/router",            # private range
    ],
)
def test_unsafe_urls_are_blocked(url):
    with pytest.raises(UnsafeURL):
        assert_safe_url(url)


def test_registry_rejects_non_https():
    with pytest.raises(ValueError):
        Source(
            id="bad",
            name="Bad",
            category=SourceCategory.SECURITY,
            url="http://insecure.example.com",
            publisher="nobody",
        )


def test_extract_text_drops_scripts_and_truncates():
    html = (
        "<html><body><script>alert('x')</script><style>p{}</style>"
        "<p>Real policy text.</p><nav>menu</nav></body></html>"
    )
    text = extract_text(html, limit=1000)
    assert "Real policy text." in text
    assert "alert" not in text
    assert "menu" not in text
    assert len(extract_text("<body>" + "x" * 5000 + "</body>", limit=100)) == 100


def test_missing_replay_file_is_a_recorded_failure(tmp_path, source):
    """A source with no snapshot must not look like a successful quiet check."""
    snap = fetch_replay(source, tmp_path, Limits())
    assert snap.fetch_status is FetchStatus.SKIPPED
    assert snap.succeeded is False
    assert "no replay snapshot" in snap.error


def test_malformed_replay_file_is_a_recorded_failure(tmp_path, source):
    (tmp_path / f"{source.id}.yaml").write_text("content: [unclosed", encoding="utf-8")
    snap = fetch_replay(source, tmp_path, Limits())
    assert snap.fetch_status is FetchStatus.PARSE_ERROR
    assert snap.succeeded is False


def test_empty_replay_file_is_a_recorded_failure(tmp_path, source):
    (tmp_path / f"{source.id}.yaml").write_text(
        yaml.safe_dump({"content": "   "}), encoding="utf-8"
    )
    snap = fetch_replay(source, tmp_path, Limits())
    assert snap.fetch_status is FetchStatus.PARSE_ERROR


def test_good_replay_file_loads_with_dates(tmp_path, source):
    (tmp_path / f"{source.id}.yaml").write_text(
        yaml.safe_dump(
            {
                "content": "Bulk senders must publish a DMARC policy.",
                "published_at": "2026-01-15",
                "effective_at": "2026-02-01",
            }
        ),
        encoding="utf-8",
    )
    snap = fetch_replay(source, tmp_path, Limits())
    assert snap.succeeded
    assert snap.mode == "replay"
    assert snap.published_at.isoformat() == "2026-01-15"
    assert snap.effective_at.isoformat() == "2026-02-01"
    assert snap.content_hash


def test_committed_replay_corpus_is_loadable():
    """The shipped demo corpus must actually load — guards against a broken capture."""
    from pathlib import Path

    from builtwatch.registry import enabled_sources, load_registry

    replay_dir = Path(__file__).resolve().parents[1] / "replay"
    registry = Path(__file__).resolve().parents[1] / "sources/registry.yaml"
    if not replay_dir.exists():
        pytest.skip("replay corpus not captured")

    for source in enabled_sources(load_registry(registry)):
        snap = fetch_replay(source, replay_dir, Limits())
        assert snap.succeeded, f"{source.id}: {snap.fetch_status.value} {snap.error}"
        assert snap.mode == "replay"
