"""Search-lane helpers for candidate JSON, coverage validation, and files.

T3 keeps search outputs as candidate JSON until the analyst downloads and
approves source files. This module is the deterministic guardrail around those
LLM artifacts: every claimed ``field_coverage`` cell must resolve through the
config-driven schema, and every reference-value sub-query must stay
context-free instead of leaking the TEA/system context into a commodity search.
"""

from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
from xml.etree import ElementTree as ET

from .csvio import SOURCES_FIELDNAMES, blank_row
from .schema import GLOBAL_ENTITY_ID, Schema


SUPPORTED_SOURCE_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".txt"}
SOURCE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
OPEN_ACCESS_MARKERS = (
    "open access",
    "openly accessible",
    "publicly accessible",
    "free full text",
    "free to access",
    "public domain",
    "public dataset",
    "government website",
    "official public",
)
RESTRICTED_ACCESS_MARKERS = (
    "paywall",
    "subscription",
    "library access",
    "library-only",
    "purchase required",
    "request access",
    "technical report request",
    "login required",
    "abstract only",
)

STOPWORDS = {
    "about",
    "after",
    "also",
    "analysis",
    "and",
    "annual",
    "available",
    "based",
    "best",
    "case",
    "cost",
    "data",
    "development",
    "document",
    "economic",
    "energy",
    "evaluation",
    "from",
    "into",
    "life",
    "manufacturing",
    "process",
    "production",
    "reference",
    "report",
    "source",
    "study",
    "technical",
    "techno",
    "that",
    "the",
    "this",
    "through",
    "using",
    "with",
}


class SearchValidationError(ValueError):
    """Raised when candidate JSON violates the schema-driven search contract."""

    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True)
class Candidate:
    """One search candidate normalized from the JSON artifact."""

    source_key: str
    title: str
    authors: str
    year: str
    publisher_or_journal: str
    source_url: str
    doi: str
    quality_estimate: str
    access_notes: str
    field_coverage: tuple[tuple[str, str], ...]
    raw: Mapping[str, object]


@dataclass(frozen=True)
class FileProfile:
    """Searchable representation of a downloaded source file."""

    path: Path
    text: str
    normalized: str
    compact: str
    tokens: set[str]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ScoredMatch:
    """A proposed source-file-to-candidate match."""

    path: Path
    candidate: Candidate
    score: int
    details: str


def normalize_text(value: str) -> str:
    """Normalize arbitrary text for fuzzy matching and phrase checks."""

    ascii_text = (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_text)).strip()


def is_open_access_notes(value: object) -> bool:
    """Whether access metadata explicitly says the full evidence is inspectable."""

    text = normalize_text(str(value or ""))
    if any(marker in text for marker in RESTRICTED_ACCESS_MARKERS):
        return False
    return any(marker in text for marker in OPEN_ACCESS_MARKERS)


def compact_text(value: str) -> str:
    """Normalize text and remove token boundaries."""

    return re.sub(r"[^a-z0-9]+", "", normalize_text(value))


def tokens_for(value: str) -> set[str]:
    """Return useful, non-stopword tokens for fuzzy source matching."""

    return {
        token
        for token in normalize_text(value).split()
        if len(token) > 3 and token not in STOPWORDS
    }


def load_search_doc(path: str | Path) -> dict:
    """Load a search candidate JSON file."""

    path = Path(path)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        raise SearchValidationError([f"{path}: file not found"]) from None
    except json.JSONDecodeError as exc:
        raise SearchValidationError([f"{path}: invalid JSON: {exc}"]) from None
    if not isinstance(doc, dict):
        raise SearchValidationError([f"{path}: top-level JSON must be an object"])
    return doc


def candidate_source_url(raw: Mapping[str, object]) -> str:
    """Read the locator field from current or legacy candidate JSON keys."""

    for key in ("source_url", "url", "url_or_doi"):
        value = raw.get(key)
        if value:
            return str(value).strip()
    return ""


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def coverage_pairs(raw: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Normalize candidate coverage entries to ``(entity, parameter)`` pairs.

    The new contract uses ``entity``/``parameters``. Legacy Vicky-shaped JSON
    with ``unit``/``fields`` is accepted only as an input convenience.
    """

    pairs: list[tuple[str, str]] = []
    for item in _as_list(raw.get("field_coverage")):
        if not isinstance(item, Mapping):
            continue
        entity = str(item.get("entity") or item.get("unit") or "").strip()
        parameters = item.get("parameters", item.get("fields"))
        if isinstance(parameters, str):
            param_values = [parameters]
        elif isinstance(parameters, list):
            param_values = parameters
        else:
            param_values = []
        for parameter in param_values:
            parameter_id = str(parameter or "").strip()
            if entity or parameter_id:
                pairs.append((entity, parameter_id))
    return tuple(pairs)


def candidate_from_raw(raw: Mapping[str, object]) -> Candidate:
    """Build a normalized ``Candidate`` without validating cross-references."""

    return Candidate(
        source_key=str(raw.get("source_key", "") or "").strip(),
        title=str(raw.get("title", "") or ""),
        authors=str(raw.get("authors", "") or ""),
        year=str(raw.get("year", "") or ""),
        publisher_or_journal=str(raw.get("publisher_or_journal", "") or ""),
        source_url=candidate_source_url(raw),
        doi=str(raw.get("doi", "") or ""),
        quality_estimate=str(raw.get("quality_estimate", "") or ""),
        access_notes=str(raw.get("access_notes", "") or ""),
        field_coverage=coverage_pairs(raw),
        raw=raw,
    )


def _allowed_quality_tags(schema: Schema) -> set[str]:
    tags = set(schema.quality_tags)
    non_estimate = tags - {"E"}
    return non_estimate or tags


def _reference_subquery_context_errors(doc: Mapping[str, object], schema: Schema) -> list[str]:
    errors: list[str] = []
    subqueries = doc.get("reference_value_subqueries", [])
    if subqueries in (None, ""):
        return errors
    if not isinstance(subqueries, list):
        return ["reference_value_subqueries: must be a list when present"]

    forbidden_phrases = context_forbidden_phrases(schema)
    for idx, raw in enumerate(subqueries):
        where = f"reference_value_subqueries[{idx}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{where}: must be an object")
            continue
        parameter = str(raw.get("parameter", "") or "").strip()
        query = str(raw.get("query") or raw.get("search_query") or "").strip()
        if not parameter:
            errors.append(f"{where}: missing parameter")
        elif not schema.has_parameter(parameter):
            errors.append(f"{where}: unknown parameter {parameter!r}")
        elif not schema.is_reference_value(parameter) or not schema.is_context_free(parameter):
            errors.append(
                f"{where}: parameter {parameter!r} is not a context_free reference_value"
            )
        if not query:
            errors.append(f"{where}: missing query")
            continue
        normalized_query = normalize_text(query)
        for phrase in forbidden_phrases:
            if phrase and phrase in normalized_query:
                errors.append(
                    f"{where}: query for {parameter!r} includes TEA/system context "
                    f"{phrase!r}; make the query context-free"
                )
    return errors


def context_forbidden_phrases(schema: Schema) -> tuple[str, ...]:
    """Phrases that must not appear in context-free reference-value searches."""

    raw_phrases = [
        schema.tea_id,
        schema.display_name,
        schema.functional_unit_name,
        schema.functional_unit_symbol,
    ]
    # Full entity names are context, but single-token names can be legitimate
    # market words (e.g. "networking"). Keep the guardrail precise.
    for entity in schema.entities:
        name = str(entity.get("name", "") or "")
        if len(normalize_text(name).split()) >= 2:
            raw_phrases.append(name)

    phrases: list[str] = []
    for phrase in raw_phrases:
        normalized = normalize_text(phrase)
        if len(normalized) >= 4 and normalized not in phrases:
            phrases.append(normalized)
    return tuple(phrases)


def validate_search_doc(
    doc: Mapping[str, object],
    schema: Schema,
    *,
    mode: str = "master",
    entity_id: str | None = None,
    uncovered_parameters: Iterable[str] | None = None,
    approved_source_keys: Iterable[str] = (),
    satisfied_cells: Iterable[tuple[str, str]] = (),
) -> list[Candidate]:
    """Validate and return normalized candidates from a search JSON artifact.

    ``mode`` is ``"master"`` or ``"gap"``. Gap mode adds the per-entity,
    URL-only, duplicate, uncovered-parameter, and search-targetable eligibility checks
    required by T3.
    """

    if mode not in {"master", "gap"}:
        raise ValueError("mode must be 'master' or 'gap'")

    errors: list[str] = []
    candidates_raw = doc.get("candidates")
    if not isinstance(candidates_raw, list):
        raise SearchValidationError(["candidates: missing top-level list"])

    if entity_id and not schema.has_entity(entity_id):
        errors.append(f"entity_id: unknown entity {entity_id!r}")

    uncovered = {str(p).strip() for p in (uncovered_parameters or []) if str(p).strip()}
    for parameter in sorted(uncovered):
        if not schema.has_parameter(parameter):
            errors.append(f"uncovered_parameters: unknown parameter {parameter!r}")
        elif entity_id and not schema.applies(parameter, entity_id):
            errors.append(
                f"uncovered_parameters: parameter {parameter!r} does not apply to "
                f"entity {entity_id!r}"
            )

    errors.extend(_reference_subquery_context_errors(doc, schema))

    approved = {str(key).strip() for key in approved_source_keys if str(key).strip()}
    satisfied = {
        (str(entity).strip(), str(parameter).strip())
        for entity, parameter in satisfied_cells
        if str(entity).strip() and str(parameter).strip()
    }
    seen_keys: set[str] = set()
    candidates: list[Candidate] = []
    allowed_quality = _allowed_quality_tags(schema)

    for idx, raw in enumerate(candidates_raw):
        where = f"candidates[{idx}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{where}: must be an object")
            continue
        candidate = candidate_from_raw(raw)
        candidates.append(candidate)

        if not candidate.source_key:
            errors.append(f"{where}: missing source_key")
        elif not SOURCE_KEY_RE.match(candidate.source_key):
            errors.append(
                f"{where}: source_key {candidate.source_key!r} must be kebab-case "
                "and at most 64 characters"
            )
        elif candidate.source_key in seen_keys:
            errors.append(f"{where}: duplicate source_key {candidate.source_key!r}")
        seen_keys.add(candidate.source_key)

        for field in ("title", "authors", "year", "publisher_or_journal"):
            if not getattr(candidate, field):
                errors.append(f"{where}: missing {field}")
        if not candidate.source_url:
            errors.append(f"{where}: missing source_url")
        if schema.is_auto and not is_open_access_notes(candidate.access_notes):
            errors.append(
                f"{where}: Auto mode requires open-access/openly inspectable evidence; "
                "access_notes must explicitly confirm full public access and must not "
                "indicate a paywall, subscription, login, purchase, or access request"
            )
        if candidate.quality_estimate and candidate.quality_estimate not in allowed_quality:
            errors.append(
                f"{where}: quality_estimate {candidate.quality_estimate!r} is not "
                f"one of {sorted(allowed_quality)}"
            )

        if not candidate.field_coverage:
            errors.append(f"{where}: field_coverage must include at least one cell")

        non_ref_parameters: list[str] = []
        reference_parameters: list[str] = []
        for entity, parameter in candidate.field_coverage:
            if not entity:
                errors.append(f"{where}: field_coverage has blank entity")
                continue
            if not parameter:
                errors.append(f"{where}: field_coverage for {entity!r} has blank parameter")
                continue
            if entity != GLOBAL_ENTITY_ID and not schema.has_entity(entity):
                errors.append(f"{where}: unknown entity {entity!r}")
                continue
            if not schema.has_parameter(parameter):
                errors.append(f"{where}: unknown parameter {parameter!r}")
                continue
            if not schema.applies(parameter, entity):
                errors.append(
                    f"{where}: parameter {parameter!r} does not apply to entity {entity!r}"
                )
                continue
            if (entity, parameter) in satisfied:
                errors.append(
                    f"{where}: field_coverage includes satisfied cell ({entity!r}, {parameter!r}); "
                    "satisfied shared inputs must be skipped"
                )
            if entity == GLOBAL_ENTITY_ID:
                reference_parameters.append(parameter)
            else:
                non_ref_parameters.append(parameter)

            if mode == "gap":
                if entity_id and entity not in {entity_id, GLOBAL_ENTITY_ID}:
                    errors.append(
                        f"{where}: gap-fill coverage entity {entity!r} is outside "
                        f"target entity {entity_id!r}"
                    )
                if uncovered and entity != GLOBAL_ENTITY_ID and parameter not in uncovered:
                    errors.append(
                        f"{where}: parameter {parameter!r} is not in uncovered_parameters"
                    )

        if mode == "gap":
            if not HTTP_URL_RE.match(candidate.source_url):
                errors.append(f"{where}: gap-fill source_url must be an HTTP(S) URL")
            if "doi.org/" in candidate.source_url.lower():
                errors.append(f"{where}: gap-fill source_url must not be a DOI resolver URL")
            if candidate.source_key in approved and not raw.get("is_retargeting_of_master_list_source"):
                errors.append(
                    f"{where}: duplicate approved source_key {candidate.source_key!r}; "
                    "retargeting must use a new key and set is_retargeting_of_master_list_source"
                )
            if non_ref_parameters and not any(schema.is_search_targetable(p) for p in non_ref_parameters):
                errors.append(
                    f"{where}: gap-fill candidates must cover at least one "
                    "search_targetable parameter from the schema"
                )
            if reference_parameters and not all(
                schema.is_reference_value(p) and schema.is_context_free(p)
                for p in reference_parameters
            ):
                errors.append(
                    f"{where}: REF coverage is only allowed for context_free reference values"
                )

    if errors:
        raise SearchValidationError(errors)
    return candidates


def validate_search_file(
    path: str | Path,
    schema: Schema,
    *,
    mode: str = "master",
    entity_id: str | None = None,
    uncovered_parameters: Iterable[str] | None = None,
    approved_source_keys: Iterable[str] = (),
    satisfied_cells: Iterable[tuple[str, str]] = (),
) -> list[Candidate]:
    """Load and validate a search JSON file."""

    doc = load_search_doc(path)
    return validate_search_doc(
        doc,
        schema,
        mode=mode,
        entity_id=entity_id,
        uncovered_parameters=uncovered_parameters,
        approved_source_keys=approved_source_keys,
        satisfied_cells=satisfied_cells,
    )


def candidate_entities(candidate: Candidate, *, include_ref: bool = False) -> tuple[str, ...]:
    """Return coverage entities in first-seen order."""

    entities: list[str] = []
    for entity, _parameter in candidate.field_coverage:
        if entity == GLOBAL_ENTITY_ID and not include_ref:
            continue
        if entity not in entities:
            entities.append(entity)
    return tuple(entities)


def target_prefix(candidate: Candidate, prefix_mode: str = "auto") -> str:
    """Return the filename prefix for ``{entity_or_chain}_{source_key}.{ext}``."""

    if prefix_mode not in {"auto", "chain", "primary-entity"}:
        raise ValueError("prefix_mode must be auto, chain, or primary-entity")
    if prefix_mode == "chain":
        return "chain"

    entities = candidate_entities(candidate)
    if prefix_mode == "primary-entity":
        return entities[0] if entities else GLOBAL_ENTITY_ID
    if len(entities) == 1:
        return entities[0]
    if not entities and candidate_entities(candidate, include_ref=True):
        return GLOBAL_ENTITY_ID
    return "chain"


def target_path_for(match: ScoredMatch, source_dir: Path, prefix_mode: str) -> Path:
    """Return the normalized filename path for a matched source file."""

    prefix = target_prefix(match.candidate, prefix_mode)
    return source_dir / f"{prefix}_{match.candidate.source_key}{match.path.suffix.lower()}"


def xml_text(blob: bytes) -> str:
    """Extract text from one XML blob, best-effort."""

    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return ""
    return " ".join(text for text in root.itertext() if text and text.strip())


def extract_docx_text(path: Path) -> tuple[str, list[str]]:
    """Extract DOCX metadata/body text using the standard library."""

    warnings: list[str] = []
    parts: list[str] = [path.name]
    try:
        with zipfile.ZipFile(path) as zf:
            for name in ("docProps/core.xml", "docProps/app.xml", "word/document.xml"):
                try:
                    parts.append(xml_text(zf.read(name)))
                except KeyError:
                    continue
    except Exception as exc:  # pragma: no cover - corrupt-file diagnostics
        warnings.append(f"{path.name}: DOCX extraction failed: {exc}")
    return "\n".join(parts), warnings


def extract_pdf_text(path: Path, max_pages: int) -> tuple[str, list[str]]:
    """Extract front-matter PDF text with optional pypdf support."""

    warnings: list[str] = []
    parts: list[str] = [path.name]
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        return path.name, [f"{path.name}: pypdf unavailable; filename-only match ({exc})"]

    try:
        reader = PdfReader(str(path))
        if reader.metadata:
            parts.extend(str(value) for value in reader.metadata.values() if value)
        page_count = min(max_pages, len(reader.pages))
        for idx in range(page_count):
            try:
                parts.append(reader.pages[idx].extract_text() or "")
            except Exception as exc:  # pragma: no cover - rare corrupt-page path
                warnings.append(f"{path.name}: page {idx + 1} extraction failed: {exc}")
    except Exception as exc:
        warnings.append(f"{path.name}: PDF extraction failed: {exc}")
    return "\n".join(parts), warnings


def profile_file(path: Path, max_pages: int = 6) -> FileProfile:
    """Build a searchable profile for one source file."""

    if path.suffix.lower() == ".pdf":
        text, warnings = extract_pdf_text(path, max_pages)
    elif path.suffix.lower() == ".docx":
        text, warnings = extract_docx_text(path)
    else:
        try:
            text = path.name + "\n" + path.read_text(encoding="utf-8", errors="ignore")[:20000]
            warnings = []
        except OSError as exc:
            text = path.name
            warnings = [f"{path.name}: text extraction failed: {exc}"]

    normalized = normalize_text(text)
    return FileProfile(
        path=path,
        text=text,
        normalized=normalized,
        compact=compact_text(text),
        tokens=tokens_for(text),
        warnings=tuple(warnings),
    )


def identifier_terms(locator: str) -> set[str]:
    """Return distinctive tokens from a URL, DOI, or report identifier."""

    terms = tokens_for(locator)
    for piece in re.split(r"[^a-zA-Z0-9]+", locator):
        piece_norm = normalize_text(piece)
        if len(piece_norm) >= 4 and not piece_norm.isdigit():
            terms.add(piece_norm)
    return terms


def score_candidate(candidate: Candidate, profile: FileProfile) -> tuple[int, str]:
    """Score one candidate against one source-file profile."""

    score = 0
    details: list[str] = []
    stem_norm = normalize_text(profile.path.stem)

    if candidate.source_key.lower() in profile.path.stem.lower():
        score += 220
        details.append("source_key in filename")

    source_key_tokens = tokens_for(candidate.source_key.replace("-", " "))
    stem_tokens = set(stem_norm.split())
    if source_key_tokens and stem_tokens:
        hits = source_key_tokens & stem_tokens
        if hits:
            score += min(60, 15 * len(hits))
            details.append("source_key filename tokens (" + ", ".join(sorted(hits)[:5]) + ")")

    title_compact = compact_text(candidate.title)
    if title_compact and title_compact in profile.compact:
        score += 120
        details.append("exact title")

    title_tokens = tokens_for(candidate.title)
    if title_tokens:
        hits = title_tokens & profile.tokens
        if hits:
            score += round(85 * (len(hits) / len(title_tokens)))
            details.append(f"title tokens {len(hits)}/{len(title_tokens)}")

    author_tokens = tokens_for(candidate.authors)
    if author_tokens:
        hits = author_tokens & profile.tokens
        if hits:
            score += min(35, 7 * len(hits))
            details.append("author tokens (" + ", ".join(sorted(hits)[:5]) + ")")

    publisher_tokens = tokens_for(candidate.publisher_or_journal)
    if publisher_tokens:
        hits = publisher_tokens & profile.tokens
        if hits:
            score += min(25, 5 * len(hits))
            details.append("publisher tokens (" + ", ".join(sorted(hits)[:5]) + ")")

    id_terms = identifier_terms(candidate.source_url or candidate.doi)
    if id_terms:
        hits = id_terms & (profile.tokens | set(stem_norm.split()))
        if hits:
            score += min(35, 7 * len(hits))
            details.append("identifier tokens (" + ", ".join(sorted(hits)[:5]) + ")")

    if candidate.year and candidate.year in profile.normalized:
        score += 15
        details.append("year")

    if candidate.source_key.lower() == profile.path.stem.lower():
        score += 40
        details.append("filename is source_key")

    return score, "; ".join(details) or "weak textual overlap"


def best_match_for_file(
    profile: FileProfile, candidates: Iterable[Candidate], min_score: int
) -> ScoredMatch | None:
    """Return the best candidate for a profiled source file."""

    best: ScoredMatch | None = None
    for candidate in candidates:
        score, details = score_candidate(candidate, profile)
        match = ScoredMatch(profile.path, candidate, score, details)
        if best is None or match.score > best.score:
            best = match
    if best is None or best.score < min_score:
        return None
    return best


def discover_files(source_dir: str | Path) -> list[Path]:
    """List supported downloaded source files in a directory."""

    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        return []
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SOURCE_EXTENSIONS
    )


def resolve_matches(matches: list[ScoredMatch]) -> tuple[list[ScoredMatch], list[ScoredMatch]]:
    """Choose a one-to-one set of source-file matches by descending score."""

    selected: list[ScoredMatch] = []
    rejected: list[ScoredMatch] = []
    used_files: set[Path] = set()
    used_keys: set[str] = set()

    for match in sorted(matches, key=lambda item: item.score, reverse=True):
        key = match.candidate.source_key
        if match.path in used_files or key in used_keys:
            rejected.append(match)
            continue
        selected.append(match)
        used_files.add(match.path)
        used_keys.add(key)

    return sorted(selected, key=lambda item: item.candidate.source_key), rejected


def source_file_present_for(source_key: str, source_dir: str | Path) -> Path | None:
    """Return the approved source file whose stem matches ``source_key``."""

    key = (source_key or "").strip().lower()
    if not key:
        return None
    suffix = f"_{key}"
    for entry in discover_files(source_dir):
        stem = entry.stem.lower()
        if stem == key or stem.endswith(suffix):
            return entry
    return None


def candidate_to_source_row(
    candidate: Candidate,
    *,
    access_date: str,
    source_role: str = "extraction",
) -> dict[str, str]:
    """Convert a validated candidate into a Sources.csv row."""

    row = blank_row(SOURCES_FIELDNAMES)
    row.update(
        {
            "source_key": candidate.source_key,
            "authors": candidate.authors,
            "title": candidate.title,
            "year": candidate.year,
            "publisher_or_journal": candidate.publisher_or_journal,
            "source_url": candidate.source_url,
            "doi": candidate.doi,
            "access_date": access_date,
            "page_or_table_reference": "",
            "source_role": source_role,
        }
    )
    notes: list[str] = []
    if candidate.quality_estimate:
        notes.append(f"search_quality_estimate={candidate.quality_estimate}")
    if candidate.access_notes:
        notes.append(f"access_notes={candidate.access_notes}")
    row["notes"] = "; ".join(notes)
    return row
