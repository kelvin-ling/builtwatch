"""Source retrieval.

Two modes:

* ``replay`` reads committed, dated snapshots from ``replay/`` — real historical material,
  clearly labelled as a replay so a demo is reproducible and free.
* ``live`` performs a real HTTPS fetch of a registry URL.

The live path is deliberately hostile to misuse:

* only URLs that appear in the committed registry are ever requested;
* https only, and the resolved IP must be public (blocks SSRF at cloud metadata,
  localhost and private ranges);
* redirects are not followed across hosts;
* responses are size-capped while streaming, so a huge or endless body cannot run up
  memory or token cost;
* a failed fetch produces a stored snapshot with a failure status. It never silently
  becomes "nothing changed".
"""

from __future__ import annotations

import ipaddress
import socket
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from selectolax.parser import HTMLParser

from .config import Limits
from .models import FetchStatus, Source, SourceSnapshot
from .store import new_id

HTTP_ERROR_THRESHOLD = 400
REDIRECT_CODES = (301, 302, 303, 307, 308)


class UnsafeURL(ValueError):
    pass


def assert_safe_url(url: str) -> None:
    """Reject anything that is not a plain public HTTPS endpoint."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UnsafeURL(f"only https is allowed: {url}")
    host = parsed.hostname
    if not host:
        raise UnsafeURL(f"no host in url: {url}")

    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL(f"cannot resolve host {host}: {exc}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURL(f"host {host} resolves to non-public address {ip}")


def extract_text(html: str, limit: int) -> str:
    """Strip markup down to readable text, dropping script/style/nav noise."""
    tree = HTMLParser(html)
    for tag in ("script", "style", "noscript", "svg", "nav", "footer", "header"):
        for node in tree.css(tag):
            node.decompose()
    body = tree.body or tree.root
    text = body.text(separator="\n", strip=True) if body else ""
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)
    return cleaned[:limit]


def _parse_meta_date(html: str) -> date | None:
    """Best-effort publication date from common meta tags. None when absent."""
    tree = HTMLParser(html)
    selectors = [
        'meta[property="article:published_time"]',
        'meta[name="publish-date"]',
        'meta[name="date"]',
        "time[datetime]",
    ]
    for sel in selectors:
        node = tree.css_first(sel)
        if node is None:
            continue
        value = node.attributes.get("content") or node.attributes.get("datetime")
        if not value:
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return None


def fetch_live(source: Source, limits: Limits) -> SourceSnapshot:
    """Fetch one registry source. Never raises for network problems — it records them."""
    snapshot = SourceSnapshot(
        id=new_id("snap"),
        source_id=source.id,
        mode="live",
        retrieved_at=datetime.now(timezone.utc),
    )
    try:
        assert_safe_url(source.url)
    except UnsafeURL as exc:
        snapshot.fetch_status = FetchStatus.NETWORK_ERROR
        snapshot.error = f"blocked unsafe url: {exc}"
        return snapshot

    try:
        with httpx.Client(
            timeout=limits.fetch_timeout_seconds,
            follow_redirects=False,
            headers={
                "User-Agent": "BuiltWatch/0.1 (+https://builtwatch.org) source-monitor",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            },
        ) as client, client.stream("GET", source.url) as response:
            snapshot.http_status = response.status_code
            if response.status_code >= HTTP_ERROR_THRESHOLD:
                snapshot.fetch_status = FetchStatus.HTTP_ERROR
                snapshot.error = f"HTTP {response.status_code}"
                return snapshot
            if response.status_code in REDIRECT_CODES:
                snapshot.fetch_status = FetchStatus.HTTP_ERROR
                snapshot.error = (
                    f"redirect to {response.headers.get('location')!r} not followed; "
                    "update the registry url if this is legitimate"
                )
                return snapshot

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > limits.max_fetch_bytes:
                    snapshot.fetch_status = FetchStatus.HTTP_ERROR
                    snapshot.error = f"response exceeded {limits.max_fetch_bytes} bytes"
                    return snapshot
                chunks.append(chunk)
            body = b"".join(chunks).decode("utf-8", errors="replace")
    except httpx.HTTPError as exc:
        snapshot.fetch_status = FetchStatus.NETWORK_ERROR
        snapshot.error = f"{type(exc).__name__}: {exc}"
        return snapshot

    try:
        snapshot.content = extract_text(body, limits.max_snapshot_chars)
        snapshot.published_at = _parse_meta_date(body)
    except Exception as exc:  # parsing is best-effort; a failure is recorded, not fatal
        snapshot.fetch_status = FetchStatus.PARSE_ERROR
        snapshot.error = f"{type(exc).__name__}: {exc}"
        return snapshot

    if not snapshot.content.strip():
        snapshot.fetch_status = FetchStatus.PARSE_ERROR
        snapshot.error = "fetched page produced no readable text"
        return snapshot

    snapshot.content_hash = snapshot.compute_hash()
    return snapshot


def fetch_replay(source: Source, replay_dir: Path, limits: Limits) -> SourceSnapshot:
    """Load a committed historical snapshot. Clearly marked mode='replay'."""
    snapshot = SourceSnapshot(
        id=new_id("snap"),
        source_id=source.id,
        mode="replay",
        retrieved_at=datetime.now(timezone.utc),
    )
    path = Path(replay_dir) / f"{source.id}.yaml"
    if not path.exists():
        snapshot.fetch_status = FetchStatus.SKIPPED
        snapshot.error = f"no replay snapshot committed for source '{source.id}'"
        return snapshot

    import yaml

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        snapshot.content = str(raw.get("content", ""))[: limits.max_snapshot_chars]
        if raw.get("published_at"):
            snapshot.published_at = date.fromisoformat(str(raw["published_at"]))
        if raw.get("effective_at"):
            snapshot.effective_at = date.fromisoformat(str(raw["effective_at"]))
        if raw.get("retrieved_at"):
            snapshot.retrieved_at = datetime.fromisoformat(str(raw["retrieved_at"]))
        if raw.get("fetch_status"):
            snapshot.fetch_status = FetchStatus(str(raw["fetch_status"]))
            snapshot.error = raw.get("error")
    except Exception as exc:
        snapshot.fetch_status = FetchStatus.PARSE_ERROR
        snapshot.error = f"malformed replay file {path.name}: {exc}"
        return snapshot

    if snapshot.fetch_status == FetchStatus.OK and not snapshot.content.strip():
        snapshot.fetch_status = FetchStatus.PARSE_ERROR
        snapshot.error = "replay file has no content"
        return snapshot

    snapshot.content_hash = snapshot.compute_hash()
    return snapshot


def fetch(source: Source, mode: str, replay_dir: Path, limits: Limits) -> SourceSnapshot:
    if mode == "replay":
        return fetch_replay(source, replay_dir, limits)
    snap = fetch_live(source, limits)
    time.sleep(limits.fetch_delay_seconds)
    return snap
