"""The curated source registry.

BuiltWatch watches an explicit, short list of sources. It never claims to watch
"the whole world", and it never fetches a URL that a user, a document, or a model
asked it to fetch. The registry file is the only place a fetchable URL can come from.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import Source, SourceCategory


class RegistryError(ValueError):
    pass


def load_registry(path: Path | str) -> list[Source]:
    path = Path(path)
    if not path.exists():
        raise RegistryError(f"source registry not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("sources")
    if not isinstance(entries, list):
        raise RegistryError("registry must contain a top-level 'sources' list")

    sources: list[Source] = []
    seen: set[str] = set()
    for entry in entries:
        source = Source.model_validate(entry)
        if source.id in seen:
            raise RegistryError(f"duplicate source id in registry: {source.id}")
        seen.add(source.id)
        sources.append(source)
    return sources


def enabled_sources(sources: list[Source]) -> list[Source]:
    return [s for s in sources if s.enabled]


def by_category(sources: list[Source]) -> dict[SourceCategory, list[Source]]:
    grouped: dict[SourceCategory, list[Source]] = {}
    for s in sources:
        grouped.setdefault(s.category, []).append(s)
    return grouped


def coverage_statement(sources: list[Source]) -> str:
    """Human-readable statement of exactly what is and is not covered."""
    grouped = by_category(enabled_sources(sources))
    lines = ["BuiltWatch is currently watching these sources and no others:"]
    for category in SourceCategory:
        items = grouped.get(category, [])
        if not items:
            lines.append(f"  {category.value}: (none configured)")
            continue
        lines.append(f"  {category.value}:")
        for s in items:
            lines.append(f"    - {s.name} ({s.publisher})")
    return "\n".join(lines)
