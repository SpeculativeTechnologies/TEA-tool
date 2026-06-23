"""Denormalize source URLs from Sources.csv.

Sources.csv is the single source of truth for URLs. Files that carry a
``source_key`` also carry a denormalized ``source_url`` for reviewer ergonomics
(D12); deterministic scripts should use this helper when writing those rows.
"""

from __future__ import annotations

from pathlib import Path

from .csvio import read_rows


class SourceUrlError(ValueError):
    """Raised when a required source URL cannot be resolved."""


def load_source_urls(sources_path: str | Path = "Sources.csv") -> dict[str, str]:
    """Return ``{source_key: source_url}`` from a Sources.csv file.

    Empty source keys are ignored. If duplicate keys exist, the first non-empty
    URL wins; a later conflicting non-empty URL is treated as a data error.
    """

    rows = read_rows(sources_path, required_columns=["source_key", "source_url"], missing_ok=True)
    urls: dict[str, str] = {}
    for row in rows:
        key = (row.get("source_key") or "").strip()
        url = (row.get("source_url") or "").strip()
        if not key:
            continue
        if key in urls:
            existing = urls[key]
            if existing and url and existing != url:
                raise SourceUrlError(
                    f"{sources_path}: conflicting source_url values for source_key {key!r}"
                )
            if not existing and url:
                urls[key] = url
        else:
            urls[key] = url
    return urls


def source_url_for(
    source_key: str | None,
    sources_path: str | Path = "Sources.csv",
    *,
    required: bool = False,
) -> str:
    """Look up a source URL by key.

    Missing/blank keys and absent Sources.csv files return ``""`` by default so
    empty skeleton rows stay easy to write. Pass ``required=True`` when a writer
    is processing a populated source-bearing row and should fail closed.
    """

    key = (source_key or "").strip()
    if not key:
        if required:
            raise SourceUrlError("source_key is required to resolve source_url")
        return ""

    urls = load_source_urls(sources_path)
    url = urls.get(key, "")
    if required and not url:
        raise SourceUrlError(f"no source_url found for source_key {key!r} in {sources_path}")
    return url
