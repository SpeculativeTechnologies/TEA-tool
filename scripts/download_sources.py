"""Download approved public research sources without opening a browser dialog.

The research screener still returns metadata only. After the gate has selected
specific source keys, this script retrieves those sources over HTTP(S) and
writes inert copies into the run's source folder. It never opens or executes a
downloaded file.

Example:
    python scripts/download_sources.py --schema tea-schema.json \
        --input search-history/master-list.json \
        --output-dir "master list sources" \
        --approved-source-keys eia-electricity-price,doe-process-report
"""

from __future__ import annotations

import argparse
import ipaddress
import mimetypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from lib.schema import load_schema
from lib.search import (
    SUPPORTED_SOURCE_EXTENSIONS,
    Candidate,
    SearchValidationError,
    source_file_present_for,
    target_prefix,
    validate_search_file,
)


DEFAULT_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30
USER_AGENT = "General-TEA-Tool/1.0 (public research source retrieval)"
CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "text/plain": ".txt",
}


class DownloadError(ValueError):
    """Raised when an approved source cannot be materialized safely."""


@dataclass(frozen=True)
class DownloadedSource:
    source_key: str
    source_url: str
    final_url: str
    path: Path
    content_type: str
    size_bytes: int
    status: str


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _content_type(headers: object) -> str:
    getter = getattr(headers, "get_content_type", None)
    if callable(getter):
        return str(getter() or "").lower()
    raw = str(getattr(headers, "get", lambda *_: "")("Content-Type", ""))
    return raw.partition(";")[0].strip().lower()


def _extension_for(url: str, content_type: str, payload: bytes) -> str:
    mapped = CONTENT_TYPE_EXTENSIONS.get(content_type)
    if mapped:
        return mapped

    url_suffix = Path(urlparse(url).path).suffix.lower()
    if url_suffix in SUPPORTED_SOURCE_EXTENSIONS:
        return url_suffix
    if payload.startswith(b"%PDF-"):
        return ".pdf"
    if payload.startswith(b"PK\x03\x04") and url_suffix == ".docx":
        return ".docx"

    sample = payload[:4096].lstrip().lower()
    if sample.startswith((b"<!doctype html", b"<html", b"<?xml")):
        return ".html"
    if content_type.startswith("text/"):
        return ".txt"

    guessed = mimetypes.guess_extension(content_type or "")
    if guessed in SUPPORTED_SOURCE_EXTENSIONS:
        return guessed
    raise DownloadError(
        f"unsupported response type {content_type or '<missing>'!r}; "
        "only PDF, DOCX, HTML, and plain-text evidence is accepted"
    )


def _read_bounded(response: object, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise DownloadError("max_bytes must be positive")
    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise DownloadError(f"response exceeds the {max_bytes}-byte download limit")
    if not payload:
        raise DownloadError("response body is empty")
    return payload


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise DownloadError("source_url must be an absolute HTTP(S) URL")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise DownloadError("source_url must identify a public host")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise DownloadError("source_url must not target a private, loopback, or reserved address")


def _download_one(
    candidate: Candidate,
    output_dir: Path,
    *,
    prefix_mode: str,
    max_bytes: int,
    timeout_seconds: int,
    opener: Callable[..., object],
) -> DownloadedSource:
    existing = source_file_present_for(candidate.source_key, output_dir)
    if existing is not None:
        return DownloadedSource(
            candidate.source_key,
            candidate.source_url,
            candidate.source_url,
            existing,
            "",
            existing.stat().st_size,
            "already_present",
        )

    _validate_public_url(candidate.source_url)

    request = Request(
        candidate.source_url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            payload = _read_bounded(response, max_bytes)
            final_url = str(getattr(response, "geturl", lambda: candidate.source_url)())
            _validate_public_url(final_url)
            content_type = _content_type(response.headers)
    except DownloadError:
        raise
    except HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code} while retrieving source") from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise DownloadError(f"could not retrieve source: {exc}") from exc

    extension = _extension_for(final_url, content_type, payload)
    filename = f"{target_prefix(candidate, prefix_mode)}_{candidate.source_key}{extension}"
    target = output_dir / filename
    partial = output_dir / f".{filename}.part"
    partial.write_bytes(payload)
    partial.replace(target)
    return DownloadedSource(
        candidate.source_key,
        candidate.source_url,
        final_url,
        target,
        content_type,
        len(payload),
        "downloaded",
    )


def download_sources(
    *,
    schema_path: str | Path,
    input_path: str | Path,
    output_dir: str | Path,
    approved_source_keys: Iterable[str],
    mode: str = "master",
    entity_id: str | None = None,
    uncovered_parameters: Iterable[str] = (),
    previously_approved_source_keys: Iterable[str] = (),
    prefix_mode: str = "auto",
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[..., object] = urlopen,
) -> dict[str, object]:
    """Retrieve only the explicitly approved candidates from a search artifact."""

    approved = {str(key).strip() for key in approved_source_keys if str(key).strip()}
    if not approved:
        raise DownloadError("approved_source_keys must name at least one screened source")

    schema = load_schema(schema_path)
    candidates = validate_search_file(
        input_path,
        schema,
        mode=mode,
        entity_id=entity_id,
        uncovered_parameters=uncovered_parameters,
        approved_source_keys=previously_approved_source_keys,
    )
    by_key = {candidate.source_key: candidate for candidate in candidates}
    unknown = sorted(approved - by_key.keys())
    if unknown:
        raise DownloadError(
            "approved source key(s) not found in candidate JSON: " + ", ".join(unknown)
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[DownloadedSource] = []
    failed: list[dict[str, str]] = []
    for key in sorted(approved):
        candidate = by_key[key]
        try:
            downloaded.append(
                _download_one(
                    candidate,
                    output_dir,
                    prefix_mode=prefix_mode,
                    max_bytes=max_bytes,
                    timeout_seconds=timeout_seconds,
                    opener=opener,
                )
            )
        except DownloadError as exc:
            failed.append(
                {"source_key": key, "source_url": candidate.source_url, "error": str(exc)}
            )

    return {"downloaded": downloaded, "failed": failed, "output_dir": output_dir}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True, help="Validated search candidate JSON")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Run-local canonical source folder"
    )
    parser.add_argument(
        "--approved-source-keys",
        required=True,
        help="Comma-separated source keys approved by the Guided or Auto gate",
    )
    parser.add_argument("--mode", choices=("master", "gap"), default="master")
    parser.add_argument("--entity", dest="entity_id")
    parser.add_argument("--uncovered-parameters")
    parser.add_argument(
        "--previously-approved-source-keys",
        help="Comma-separated master-list keys used by the gap duplicate guard",
    )
    parser.add_argument(
        "--prefix-mode", choices=("auto", "chain", "primary-entity"), default="auto"
    )
    parser.add_argument(
        "--max-mib", type=int, default=50, help="Per-source size limit (default: 50 MiB)"
    )
    parser.add_argument("--timeout", type=int, default=30, help="Per-source timeout in seconds")
    args = parser.parse_args(argv)

    try:
        result = download_sources(
            schema_path=args.schema,
            input_path=args.input,
            output_dir=args.output_dir,
            approved_source_keys=_split_csv(args.approved_source_keys),
            mode=args.mode,
            entity_id=args.entity_id,
            uncovered_parameters=_split_csv(args.uncovered_parameters),
            previously_approved_source_keys=_split_csv(args.previously_approved_source_keys),
            prefix_mode=args.prefix_mode,
            max_bytes=args.max_mib * 1024 * 1024,
            timeout_seconds=args.timeout,
        )
    except (DownloadError, FileNotFoundError, SearchValidationError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for item in result["downloaded"]:
        print(f"{item.status}: {item.source_key} -> {item.path} ({item.size_bytes} bytes)")
    for item in result["failed"]:
        print(
            f"FAILED: {item['source_key']} ({item['source_url']}): {item['error']}",
            file=sys.stderr,
        )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
