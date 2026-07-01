"""schema.py — load, validate, and read `tea-schema.json`.

This is the contract between the Stage 0 LLM front-end (which *emits*
`tea-schema.json`) and the deterministic back-end (every script, which *reads*
it). No downstream script contains domain constants — entities, parameters,
conventions, and the functional unit all come from here. See plan.md §2/§4.

Public API
----------
- ``load_schema(path)`` -> ``Schema``  — read + validate + wrap a config file.
- ``validate_schema(data)`` -> ``ValidationReport`` — structural + semantic
  validation of an already-parsed config (no disk read).
- ``Schema`` — the accessor object every downstream script uses (entities,
  parameters, ``parameters_for``, ``skeleton_cells``, reference values, the
  comparable rubric, derived convention files, run defaults).
- ``SchemaError`` — raised by ``load_schema`` when a config has hard errors.

Validation is layered (see plan.md §4 and the JSON Schema header):

* **Structural** — types, enums, required core keys, ``additionalProperties``.
  Enforced against ``templates/tea-schema.schema.json`` via the ``jsonschema``
  package when it is installed, otherwise via a built-in validator that mirrors
  the same contract. A structural failure means the config is *malformed*.
* **Semantic** — cross-references and completeness that a structural schema
  can't easily express (``applies_to`` resolving to a real entity; an
  ``INTENSITY`` parameter declaring its numerator units; a comparables-using
  entity having a rubric). These surface as hard ``errors`` (referential
  integrity) or analyst-facing ``open_questions`` (ambiguity that Stage 0 must
  resolve rather than silently default — see TASKS.md T1 acceptance).

Open questions are *not* load failures: a config can be structurally valid yet
carry open questions. ``load_schema`` raises only on ``errors``; the report
(including open questions) is attached to the returned ``Schema`` as
``.report`` and is what Stage 0 renders into ``schema-open-questions.md``.

CLI
---
    python scripts/lib/schema.py path/to/tea-schema.json [--json]

Prints the validation report and exits non-zero if there are hard errors.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Vocabulary / constants (the only "constants" allowed here — they define the
# contract itself, not any one TEA's domain).
# ---------------------------------------------------------------------------

#: Reserved id for the synthetic global entity that carries reference-value
#: rows (D8, plan.md §12). It is never declared in ``entities``.
GLOBAL_ENTITY_ID = "REF"

RULE_TYPES = frozenset(
    {"MONETARY", "INTENSITY", "FRACTION", "RATE", "CAPEX", "PASSTHROUGH", "JSON", "TEXT"}
)
INFLATION_INDICES = frozenset({"CEPCI", "CPI", "PPI", "none"})
ESTIMATION_POLICIES = frozenset({"comparables_first", "first_principles_only", "either"})
PARAMETER_SCOPES = frozenset({"global", "entity"})
INTENSITY_DENOMINATORS = frozenset({"functional_unit", "entity_output"})
EXECUTION_MODES = frozenset({"auto_with_human_gates", "auto"})

#: Carried-forward Vicky TEA defaults (plan.md §13 item 4); overridable via the
#: config's ``defaults`` block.
DEFAULT_MASTER_LIST_CAP = 15
DEFAULT_GAP_FILL_CAP = 5
DEFAULT_EXTRACTION_BATCH = 8

_TEA_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_ENTITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_PARAM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

#: Allowed keys per object, mirroring ``additionalProperties: false`` in the
#: JSON Schema. Used by the built-in structural validator.
_TOPLEVEL_KEYS = frozenset(
    {
        "execution_mode", "schema_version", "tea_id", "display_name", "vocabulary", "functional_unit",
        "basis", "quality_tags", "entities", "parameters", "estimation",
        "conventions_needed", "validation_targets", "defaults",
    }
)
_TOPLEVEL_REQUIRED = (
    "tea_id", "display_name", "functional_unit", "basis", "quality_tags",
    "entities", "parameters", "estimation", "conventions_needed",
)
_ENTITY_KEYS = frozenset(
    {"id", "name", "output", "description", "scope_frame", "estimation_policy"}
)
_SCOPE_FRAME_KEYS = frozenset({"in_scope", "known_out_of_scope"})
_PARAMETER_KEYS = frozenset(
    {
        "id", "label", "rule_type", "applies_to", "search_targetable", "context_free",
        "reference_value", "scope", "units", "numerator_units", "per",
        "canonical_unit", "basis", "market_basis", "capex_form", "description", "notes",
    }
)
_BASIS_KEYS = frozenset({"currency", "base_year", "inflation_index", "geography"})
_FUNCTIONAL_UNIT_KEYS = frozenset({"name", "symbol"})
_VOCABULARY_KEYS = frozenset({"entity", "parameter"})
_ESTIMATION_KEYS = frozenset({"comparable_rubric"})
_RUBRIC_KEYS = frozenset({"dimensions", "hard_rule"})
_VALIDATION_TARGET_KEYS = frozenset({"metric", "range", "target", "unit", "source"})
_DEFAULTS_KEYS = frozenset(
    {"master_list_candidate_cap", "gap_fill_candidate_cap", "extraction_batch_size"}
)

_JSON_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "templates" / "tea-schema.schema.json"
)


# ---------------------------------------------------------------------------
# Reporting types
# ---------------------------------------------------------------------------


class SchemaError(ValueError):
    """Raised when a config fails validation in a way that blocks loading."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


@dataclass(frozen=True)
class OpenQuestion:
    """An ambiguity Stage 0 must resolve with the analyst rather than guess.

    ``where`` locates it (e.g. ``parameters[electricity]``); ``question`` is a
    self-contained, analyst-facing prompt.
    """

    where: str
    question: str

    def __str__(self) -> str:
        return f"[{self.where}] {self.question}"

    def as_markdown(self) -> str:
        return f"- **{self.where}** — {self.question}"


@dataclass
class ValidationReport:
    """Outcome of validating a config. ``ok`` iff there are no hard errors."""

    errors: list[str] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def render_open_questions_md(self, *, tea_id: str | None = None) -> str:
        """Render ``schema-open-questions.md`` content (D2)."""
        header = "# Stage 0 — open questions"
        if tea_id:
            header += f" ({tea_id})"
        if not self.open_questions:
            return header + "\n\nNone — the schema compiled without ambiguity.\n"
        lines = [
            header,
            "",
            "Stage 0 could not resolve the following without guessing. Answer each, "
            "update the input docs, and re-compile — do not let the pipeline proceed "
            "past a genuine ambiguity.",
            "",
        ]
        lines += [q.as_markdown() for q in self.open_questions]
        lines.append("")
        return "\n".join(lines)

    def summary(self) -> str:
        return (
            f"{len(self.errors)} error(s), "
            f"{len(self.open_questions)} open question(s), "
            f"{len(self.warnings)} warning(s)"
        )


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


def load_json_schema() -> dict:
    """Load the shipped JSON Schema (``templates/tea-schema.schema.json``)."""
    with open(_JSON_SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _structural_with_jsonschema(data: dict) -> list[str] | None:
    """Validate against the JSON Schema using ``jsonschema`` if importable.

    Returns a list of error strings, or ``None`` if ``jsonschema`` is absent
    (signalling the caller to use the built-in validator).
    """
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return None
    schema = load_json_schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{loc}: {err.message}")
    return errors


def _is_int(val) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _structural_builtin(data) -> list[str]:
    """Built-in structural validator mirroring the JSON Schema contract.

    Used when ``jsonschema`` is not installed. Faithful to the shipped
    ``tea-schema.schema.json`` for the constraints scripts actually depend on:
    required keys, types, enums, id patterns, and ``additionalProperties:
    false`` (unknown keys are errors).
    """
    errors: list[str] = []

    def err(where: str, msg: str) -> None:
        errors.append(f"{where}: {msg}")

    def check_unknown(obj: dict, allowed, where: str) -> None:
        for key in obj:
            if key not in allowed:
                err(where, f"unknown property {key!r}")

    def require(obj: dict, keys, where: str) -> None:
        for key in keys:
            if key not in obj:
                err(where, f"missing required property {key!r}")

    if not isinstance(data, dict):
        return ["<root>: expected an object"]

    check_unknown(data, _TOPLEVEL_KEYS, "<root>")
    require(data, _TOPLEVEL_REQUIRED, "<root>")

    tea_id = data.get("tea_id")
    if "tea_id" in data and not (isinstance(tea_id, str) and _TEA_ID_RE.match(tea_id)):
        err("tea_id", "must be a kebab-case string matching ^[a-z0-9][a-z0-9-]*$")
    if "display_name" in data and not _nonempty_str(data["display_name"]):
        err("display_name", "must be a non-empty string")
    if "schema_version" in data and not isinstance(data["schema_version"], str):
        err("schema_version", "must be a string")
    if "execution_mode" in data and data["execution_mode"] not in EXECUTION_MODES:
        err("execution_mode", f"must be one of {sorted(EXECUTION_MODES)}")

    # vocabulary
    vocab = data.get("vocabulary")
    if vocab is not None:
        if not isinstance(vocab, dict):
            err("vocabulary", "must be an object")
        else:
            check_unknown(vocab, _VOCABULARY_KEYS, "vocabulary")
            for k in ("entity", "parameter"):
                if k in vocab and not _nonempty_str(vocab[k]):
                    err(f"vocabulary/{k}", "must be a non-empty string")

    # functional_unit
    fu = data.get("functional_unit")
    if fu is not None:
        if not isinstance(fu, dict):
            err("functional_unit", "must be an object")
        else:
            check_unknown(fu, _FUNCTIONAL_UNIT_KEYS, "functional_unit")
            require(fu, ("name",), "functional_unit")
            if "name" in fu and not _nonempty_str(fu["name"]):
                err("functional_unit/name", "must be a non-empty string")
            if "symbol" in fu and not _nonempty_str(fu["symbol"]):
                err("functional_unit/symbol", "must be a non-empty string")

    # basis
    basis = data.get("basis")
    if basis is not None:
        if not isinstance(basis, dict):
            err("basis", "must be an object")
        else:
            check_unknown(basis, _BASIS_KEYS, "basis")
            require(basis, ("currency", "base_year", "inflation_index"), "basis")
            if "currency" in basis and not _nonempty_str(basis["currency"]):
                err("basis/currency", "must be a non-empty string")
            if "base_year" in basis and not _is_int(basis["base_year"]):
                err("basis/base_year", "must be an integer")
            if "inflation_index" in basis and basis["inflation_index"] not in INFLATION_INDICES:
                err("basis/inflation_index", f"must be one of {sorted(INFLATION_INDICES)}")
            if "geography" in basis and not _nonempty_str(basis["geography"]):
                err("basis/geography", "must be a non-empty string")

    # quality_tags
    qt = data.get("quality_tags")
    if qt is not None:
        if not isinstance(qt, list) or not qt:
            err("quality_tags", "must be a non-empty array")
        else:
            if any(not _nonempty_str(t) for t in qt):
                err("quality_tags", "every tag must be a non-empty string")
            if len(set(qt)) != len(qt):
                err("quality_tags", "tags must be unique")

    # entities
    entities = data.get("entities")
    if entities is not None:
        if not isinstance(entities, list) or not entities:
            err("entities", "must be a non-empty array")
        else:
            for i, ent in enumerate(entities):
                _structural_entity(ent, f"entities/{i}", err, check_unknown, require)

    # parameters
    params = data.get("parameters")
    if params is not None:
        if not isinstance(params, list) or not params:
            err("parameters", "must be a non-empty array")
        else:
            for i, p in enumerate(params):
                _structural_parameter(p, f"parameters/{i}", err, check_unknown, require)

    # estimation
    est = data.get("estimation")
    if est is not None:
        if not isinstance(est, dict):
            err("estimation", "must be an object")
        else:
            check_unknown(est, _ESTIMATION_KEYS, "estimation")
            rubric = est.get("comparable_rubric")
            if rubric is not None:
                if not isinstance(rubric, dict):
                    err("estimation/comparable_rubric", "must be an object")
                else:
                    check_unknown(rubric, _RUBRIC_KEYS, "estimation/comparable_rubric")
                    require(rubric, ("dimensions", "hard_rule"), "estimation/comparable_rubric")
                    dims = rubric.get("dimensions")
                    if dims is not None and (
                        not isinstance(dims, list) or not dims
                        or any(not _nonempty_str(d) for d in dims)
                    ):
                        err("estimation/comparable_rubric/dimensions",
                            "must be a non-empty array of non-empty strings")
                    if "hard_rule" in rubric and not _nonempty_str(rubric["hard_rule"]):
                        err("estimation/comparable_rubric/hard_rule", "must be a non-empty string")

    # conventions_needed
    cn = data.get("conventions_needed")
    if cn is not None:
        if not isinstance(cn, list):
            err("conventions_needed", "must be an array")
        elif any(not _nonempty_str(c) for c in cn):
            err("conventions_needed", "every entry must be a non-empty string")

    # validation_targets
    vt = data.get("validation_targets")
    if vt is not None:
        if not isinstance(vt, list):
            err("validation_targets", "must be an array")
        else:
            for i, t in enumerate(vt):
                _structural_validation_target(t, f"validation_targets/{i}", err, check_unknown, require)

    # defaults
    defaults = data.get("defaults")
    if defaults is not None:
        if not isinstance(defaults, dict):
            err("defaults", "must be an object")
        else:
            check_unknown(defaults, _DEFAULTS_KEYS, "defaults")
            for k, v in defaults.items():
                if k in _DEFAULTS_KEYS and not (_is_int(v) and v >= 1):
                    err(f"defaults/{k}", "must be an integer >= 1")

    return errors


def _structural_entity(ent, where, err, check_unknown, require) -> None:
    if not isinstance(ent, dict):
        err(where, "must be an object")
        return
    check_unknown(ent, _ENTITY_KEYS, where)
    require(ent, ("id", "name", "estimation_policy"), where)
    eid = ent.get("id")
    # The reserved-id check lives in the semantic layer (_semantic) so it runs
    # under both validation paths with one clear, analyst-facing message; the
    # JSON Schema's `not: {const: REF}` is the declarative belt-and-suspenders.
    if "id" in ent and not (isinstance(eid, str) and _ENTITY_ID_RE.match(eid)):
        err(f"{where}/id", "must match ^[A-Za-z0-9][A-Za-z0-9_-]*$")
    if "name" in ent and not _nonempty_str(ent["name"]):
        err(f"{where}/name", "must be a non-empty string")
    pol = ent.get("estimation_policy")
    if "estimation_policy" in ent and pol not in ESTIMATION_POLICIES:
        err(f"{where}/estimation_policy", f"must be one of {sorted(ESTIMATION_POLICIES)}")
    sf = ent.get("scope_frame")
    if sf is not None:
        if not isinstance(sf, dict):
            err(f"{where}/scope_frame", "must be an object")
        else:
            check_unknown(sf, _SCOPE_FRAME_KEYS, f"{where}/scope_frame")
            require(sf, ("in_scope",), f"{where}/scope_frame")
            if "in_scope" in sf and not _nonempty_str(sf["in_scope"]):
                err(f"{where}/scope_frame/in_scope", "must be a non-empty string")
            koos = sf.get("known_out_of_scope")
            if koos is not None and (
                not isinstance(koos, list) or any(not _nonempty_str(x) for x in koos)
            ):
                err(f"{where}/scope_frame/known_out_of_scope",
                    "must be an array of non-empty strings")


def _structural_parameter(p, where, err, check_unknown, require) -> None:
    if not isinstance(p, dict):
        err(where, "must be an object")
        return
    check_unknown(p, _PARAMETER_KEYS, where)
    require(p, ("id", "label", "rule_type"), where)
    pid = p.get("id")
    if "id" in p and not (isinstance(pid, str) and _PARAM_ID_RE.match(pid)):
        err(f"{where}/id", "must match ^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    if "label" in p and not _nonempty_str(p["label"]):
        err(f"{where}/label", "must be a non-empty string")
    if "rule_type" in p and p["rule_type"] not in RULE_TYPES:
        err(f"{where}/rule_type", f"must be one of {sorted(RULE_TYPES)}")
    applies = p.get("applies_to")
    if applies is not None and applies != "all":
        if not isinstance(applies, list) or not applies:
            err(f"{where}/applies_to", "must be 'all' or a non-empty array of entity ids")
        elif any(not _nonempty_str(x) for x in applies):
            err(f"{where}/applies_to", "entity ids must be non-empty strings")
        elif len(set(applies)) != len(applies):
            err(f"{where}/applies_to", "entity ids must be unique")
    for boolkey in ("search_targetable", "context_free", "reference_value"):
        if boolkey in p and not isinstance(p[boolkey], bool):
            err(f"{where}/{boolkey}", "must be a boolean")
    if "scope" in p and p["scope"] not in PARAMETER_SCOPES:
        err(f"{where}/scope", f"must be one of {sorted(PARAMETER_SCOPES)}")
    if "per" in p and p["per"] not in INTENSITY_DENOMINATORS:
        err(f"{where}/per", f"must be one of {sorted(INTENSITY_DENOMINATORS)}")
    for strkey in ("units", "numerator_units", "canonical_unit", "basis",
                   "market_basis", "capex_form", "description", "notes"):
        if strkey in p and not isinstance(p[strkey], str):
            err(f"{where}/{strkey}", "must be a string")


def _structural_validation_target(t, where, err, check_unknown, require) -> None:
    if not isinstance(t, dict):
        err(where, "must be an object")
        return
    check_unknown(t, _VALIDATION_TARGET_KEYS, where)
    require(t, ("metric",), where)
    if "metric" in t and not _nonempty_str(t["metric"]):
        err(f"{where}/metric", "must be a non-empty string")
    has_range = "range" in t
    has_target = "target" in t
    if not (has_range or has_target):
        err(where, "must declare a 'range' [low, high] or a single 'target'")
    if has_range:
        rng = t["range"]
        if (not isinstance(rng, list) or len(rng) != 2
                or any(not isinstance(x, (int, float)) or isinstance(x, bool) for x in rng)):
            err(f"{where}/range", "must be a 2-element array of numbers [low, high]")
    if has_target and (not isinstance(t["target"], (int, float)) or isinstance(t["target"], bool)):
        err(f"{where}/target", "must be a number")


def _nonempty_str(val) -> bool:
    return isinstance(val, str) and val.strip() != ""


# ---------------------------------------------------------------------------
# Semantic validation (cross-references + completeness)
# ---------------------------------------------------------------------------


def _semantic(data: dict, report: ValidationReport) -> None:
    """Cross-reference + completeness checks. Defensive against partial data."""
    entities = data.get("entities") if isinstance(data.get("entities"), list) else []
    parameters = data.get("parameters") if isinstance(data.get("parameters"), list) else []

    entity_ids = [e.get("id") for e in entities if isinstance(e, dict) and "id" in e]
    valid_entity_ids = {e for e in entity_ids if isinstance(e, str)}

    # Reserved global id must not be declared as a real entity (D8, §12). Owned
    # here so the message is identical whether jsonschema ran or not.
    for e in entities:
        if isinstance(e, dict) and e.get("id") == GLOBAL_ENTITY_ID:
            report.errors.append(
                f"entities[{GLOBAL_ENTITY_ID}]: {GLOBAL_ENTITY_ID!r} is reserved for the "
                "global reference entity; rename this entity."
            )

    # Duplicate ids (referential integrity -> hard error).
    for dup in _duplicates(entity_ids):
        report.errors.append(f"entities: duplicate entity id {dup!r}")
    param_ids = [p.get("id") for p in parameters if isinstance(p, dict) and "id" in p]
    for dup in _duplicates(param_ids):
        report.errors.append(f"parameters: duplicate parameter id {dup!r}")

    # Per-entity completeness.
    for e in entities:
        if not isinstance(e, dict):
            continue
        eid = e.get("id", "?")
        if "scope_frame" not in e:
            report.open_questions.append(
                OpenQuestion(
                    where=f"entities[{eid}]",
                    question=(
                        "No scope_frame declared. The relevance gate (Phase 3.2) needs an "
                        "in_scope description for this entity. What configuration is in scope, "
                        "and which named variants are out of scope?"
                    ),
                )
            )

    # Per-parameter completeness + applies_to resolution.
    entities_missing_output = [
        e.get("id", "?") for e in entities
        if isinstance(e, dict) and not _nonempty_str(e.get("output"))
    ]
    for p in parameters:
        if not isinstance(p, dict):
            continue
        pid = p.get("id", "?")
        rule = p.get("rule_type")
        is_ref = bool(p.get("reference_value"))

        # applies_to must resolve to real entities.
        applies = p.get("applies_to")
        if isinstance(applies, list):
            unknown = [a for a in applies if a not in valid_entity_ids]
            if unknown:
                report.errors.append(
                    f"parameters[{pid}]: applies_to references unknown entity id(s) "
                    f"{unknown!r}"
                )
            if is_ref:
                report.warnings.append(
                    f"parameters[{pid}]: reference_value parameter declares applies_to; "
                    "reference values are global (carried under the reserved 'REF' entity) "
                    "and ignore applies_to."
                )

        # Units completeness — ambiguity becomes an open question, never a
        # silent default (TASKS.md T1 acceptance).
        if rule == "INTENSITY" and not _nonempty_str(p.get("numerator_units")):
            report.open_questions.append(
                OpenQuestion(
                    where=f"parameters[{pid}]",
                    question=(
                        "INTENSITY parameter has no numerator_units. What are the numerator "
                        "units (e.g. 'kWh', 'kg'), and is the denominator the functional unit "
                        "or the entity output?"
                    ),
                )
            )
        if rule == "RATE" and not _nonempty_str(p.get("units")):
            report.open_questions.append(
                OpenQuestion(
                    where=f"parameters[{pid}]",
                    question="RATE parameter has no units. What per-time units apply (e.g. 'kg/h')?",
                )
            )
        if is_ref:
            if not _nonempty_str(p.get("canonical_unit")):
                report.open_questions.append(
                    OpenQuestion(
                        where=f"parameters[{pid}]",
                        question=(
                            "reference_value parameter has no canonical_unit. What unit should "
                            "the reference value be normalized to (e.g. 'USD/kWh')?"
                        ),
                    )
                )
            if "scope" not in p:
                report.open_questions.append(
                    OpenQuestion(
                        where=f"parameters[{pid}]",
                        question=(
                            "reference_value parameter has no scope. Should it be 'global' "
                            "(one value for the whole TEA) — the usual case — or 'entity'?"
                        ),
                    )
                )

        # per: entity_output needs the producing entity to declare an output.
        if rule == "INTENSITY" and p.get("per") == "entity_output" and not is_ref:
            targets = (
                valid_entity_ids if applies in (None, "all")
                else {a for a in applies if a in valid_entity_ids}
            )
            offenders = sorted(targets & set(entities_missing_output))
            if offenders:
                report.open_questions.append(
                    OpenQuestion(
                        where=f"parameters[{pid}]",
                        question=(
                            "normalizes 'per entity_output' but these entities declare no "
                            f"output: {offenders}. What is each entity's output basis?"
                        ),
                    )
                )

    # Comparable rubric required iff any entity uses comparables.
    uses_comparables = any(
        isinstance(e, dict) and e.get("estimation_policy") in ("comparables_first", "either")
        for e in entities
    )
    est = data.get("estimation") if isinstance(data.get("estimation"), dict) else {}
    rubric = est.get("comparable_rubric")
    if uses_comparables and not (isinstance(rubric, dict) and rubric.get("dimensions")):
        report.errors.append(
            "estimation.comparable_rubric is required: at least one entity uses a "
            "comparables-first (or 'either') estimation policy, so the scout needs a rubric."
        )

    # Phase 6 tags backed estimates 'E' and unbacked (loop 3) estimates 'U'.
    qt = data.get("quality_tags")
    if isinstance(qt, list):
        for tag in ("E", "U"):
            if tag not in qt:
                kind = "backed" if tag == "E" else "unbacked"
                report.warnings.append(
                    f"quality_tags does not include {tag!r}; Phase 6 tags {kind} estimates "
                    f"{tag!r}. Confirm the estimate tag if you renamed it."
                )

    # Numeric-only contract (both execution modes): every final TEA cell must end
    # with one finite numeric model value, so JSON/TEXT parameters are rejected in
    # Guided and Auto alike. Contextual text and structured context belong in the
    # starting documents and notes, not in model-input cells (orchestrator §2/§11).
    non_numeric = [
        str(p.get("id") or "<unknown>")
        for p in parameters
        if isinstance(p, dict) and p.get("rule_type") in {"JSON", "TEXT"}
    ]
    if non_numeric:
        report.errors.append(
            "every TEA cell must end with one finite numeric model value; JSON/TEXT "
            "parameters are not supported in either execution mode (keep contextual "
            f"text in documents and notes instead): {non_numeric}"
        )

    # conventions_needed vs. what the rule-types actually imply.
    declared = set(data.get("conventions_needed") or [])
    derived = _derive_convention_tokens(parameters, data.get("basis") or {})
    missing = derived - declared
    if missing:
        report.warnings.append(
            "conventions_needed is missing tokens implied by the rule-types in use: "
            f"{sorted(missing)}. Stage 0 should scaffold the matching conventions/*.csv."
        )


def _derive_convention_tokens(parameters: list, basis: dict) -> set[str]:
    """The convention tokens implied by the parameters' rule-types."""
    tokens: set[str] = set()
    rule_types = {
        p.get("rule_type") for p in parameters if isinstance(p, dict)
    }
    inflation = basis.get("inflation_index")
    if "MONETARY" in rule_types or "CAPEX" in rule_types:
        tokens.add("currency_rates")
    if "MONETARY" in rule_types and inflation and inflation != "none":
        tokens.add(f"inflation_index:{inflation}")
    if "INTENSITY" in rule_types or "RATE" in rule_types:
        tokens.add("unit_conversions")
    if "CAPEX" in rule_types:
        tokens.add("scaling_exponents")
    return tokens


def _duplicates(items: list) -> list:
    seen: set = set()
    dups: list = []
    for it in items:
        if it in seen and it not in dups:
            dups.append(it)
        seen.add(it)
    return dups


def _migrate_legacy_param_keys(data) -> None:
    """In-place migration of deprecated parameter keys before validation.

    ``first_class`` was renamed to ``search_targetable`` (the flag means "this
    parameter justifies spending a dedicated source search on it"). Externally
    authored schemas may still carry the old key; map it across so they keep
    loading. Runs before structural validation because the JSON Schema forbids
    unknown properties on a parameter.
    """
    if not isinstance(data, dict):
        return
    migrated = False
    for p in data.get("parameters", []):
        if isinstance(p, dict) and "first_class" in p and "search_targetable" not in p:
            p["search_targetable"] = p.pop("first_class")
            migrated = True
    if migrated:
        print(
            "warning: schema uses deprecated parameter key 'first_class'; "
            "treating it as 'search_targetable'. Please rename it.",
            file=sys.stderr,
        )


def validate_schema(data) -> ValidationReport:
    """Validate a parsed config. Returns a report (does not raise).

    Structural errors short-circuit semantic checks only when the top-level
    shape is unusable; otherwise both layers run so the analyst sees everything
    at once.
    """
    _migrate_legacy_param_keys(data)
    report = ValidationReport()
    structural = _structural_with_jsonschema(data) if isinstance(data, dict) else None
    if structural is None:
        structural = _structural_builtin(data)
    report.errors.extend(structural)
    if isinstance(data, dict):
        _semantic(data, report)
    return report


# ---------------------------------------------------------------------------
# Schema accessor
# ---------------------------------------------------------------------------


class Schema:
    """Read-only accessor over a validated ``tea-schema.json``.

    Every downstream script constructs one of these (via ``load_schema``) and
    asks it for entities, parameters, the functional unit, etc. — never reading
    the raw dict or hardcoding domain values.
    """

    def __init__(self, data: dict, report: ValidationReport | None = None):
        self._data = data
        self.report = report or validate_schema(data)
        self._entities_by_id = {e["id"]: e for e in data.get("entities", [])}
        self._params_by_id = {p["id"]: p for p in data.get("parameters", [])}

    # --- identity ---------------------------------------------------------
    @property
    def data(self) -> dict:
        return self._data

    @property
    def tea_id(self) -> str:
        return self._data["tea_id"]

    @property
    def display_name(self) -> str:
        return self._data["display_name"]

    @property
    def schema_version(self) -> str:
        return self._data.get("schema_version", "1.0")

    @property
    def execution_mode(self) -> str:
        return self._data.get("execution_mode", "auto_with_human_gates")

    @property
    def is_auto(self) -> bool:
        return self.execution_mode == "auto"

    # --- vocabulary (display labels for human-facing output, D13) ---------
    def label_for(self, kind: str) -> str:
        """Display label for 'entity' or 'parameter'; falls back to the term."""
        return self._data.get("vocabulary", {}).get(kind, kind)

    @property
    def entity_label(self) -> str:
        return self.label_for("entity")

    @property
    def parameter_label(self) -> str:
        return self.label_for("parameter")

    # --- functional unit --------------------------------------------------
    @property
    def functional_unit(self) -> dict:
        return self._data["functional_unit"]

    @property
    def functional_unit_name(self) -> str:
        return self._data["functional_unit"]["name"]

    @property
    def functional_unit_symbol(self) -> str:
        fu = self._data["functional_unit"]
        return fu.get("symbol", fu["name"])

    # --- basis ------------------------------------------------------------
    @property
    def basis(self) -> dict:
        return self._data["basis"]

    @property
    def currency(self) -> str:
        return self._data["basis"]["currency"]

    @property
    def base_year(self) -> int:
        return self._data["basis"]["base_year"]

    @property
    def inflation_index(self) -> str:
        return self._data["basis"]["inflation_index"]

    @property
    def geography(self) -> str | None:
        return self._data["basis"].get("geography")

    @property
    def quality_tags(self) -> list[str]:
        return list(self._data["quality_tags"])

    # --- entities ---------------------------------------------------------
    @property
    def entities(self) -> list[dict]:
        return list(self._data.get("entities", []))

    @property
    def entity_ids(self) -> list[str]:
        return [e["id"] for e in self._data.get("entities", [])]

    def has_entity(self, entity_id: str) -> bool:
        return entity_id in self._entities_by_id

    def entity(self, entity_id: str) -> dict:
        try:
            return self._entities_by_id[entity_id]
        except KeyError:
            raise KeyError(f"no entity with id {entity_id!r}") from None

    def scope_frame(self, entity_id: str) -> dict | None:
        return self.entity(entity_id).get("scope_frame")

    def estimation_policy(self, entity_id: str) -> str:
        return self.entity(entity_id).get("estimation_policy")

    # --- parameters -------------------------------------------------------
    @property
    def parameters(self) -> list[dict]:
        return list(self._data.get("parameters", []))

    @property
    def parameter_ids(self) -> list[str]:
        return [p["id"] for p in self._data.get("parameters", [])]

    def has_parameter(self, parameter_id: str) -> bool:
        return parameter_id in self._params_by_id

    def parameter(self, parameter_id: str) -> dict:
        try:
            return self._params_by_id[parameter_id]
        except KeyError:
            raise KeyError(f"no parameter with id {parameter_id!r}") from None

    def rule_type(self, parameter_id: str) -> str:
        return self.parameter(parameter_id)["rule_type"]

    def is_reference_value(self, parameter_id: str) -> bool:
        return bool(self.parameter(parameter_id).get("reference_value"))

    def is_context_free(self, parameter_id: str) -> bool:
        return bool(self.parameter(parameter_id).get("context_free"))

    def is_search_targetable(self, parameter_id: str) -> bool:
        return bool(self.parameter(parameter_id).get("search_targetable"))

    @property
    def reference_value_parameters(self) -> list[dict]:
        return [p for p in self._data.get("parameters", []) if p.get("reference_value")]

    @property
    def context_free_parameters(self) -> list[dict]:
        return [p for p in self._data.get("parameters", []) if p.get("context_free")]

    @property
    def search_targetable_parameters(self) -> list[dict]:
        return [p for p in self._data.get("parameters", []) if p.get("search_targetable")]

    @property
    def entity_parameters(self) -> list[dict]:
        """Per-entity parameters (everything that is not a global reference value)."""
        return [p for p in self._data.get("parameters", []) if not p.get("reference_value")]

    # --- applicability ----------------------------------------------------
    def applies(self, parameter_id: str, entity_id: str) -> bool:
        """Whether a parameter applies to an entity.

        Reference-value parameters apply only to the reserved global entity.
        """
        p = self.parameter(parameter_id)
        if p.get("reference_value"):
            return entity_id == GLOBAL_ENTITY_ID
        if entity_id == GLOBAL_ENTITY_ID:
            return False
        applies = p.get("applies_to", "all")
        return applies == "all" or (isinstance(applies, list) and entity_id in applies)

    def parameters_for(self, entity_id: str) -> list[dict]:
        """Parameters applicable to an entity.

        For the reserved global entity (``REF``), returns the reference-value
        parameters. For a real entity, returns its applicable non-reference
        parameters in catalog order.
        """
        if entity_id == GLOBAL_ENTITY_ID:
            return self.reference_value_parameters
        out = []
        for p in self._data.get("parameters", []):
            if p.get("reference_value"):
                continue
            applies = p.get("applies_to", "all")
            if applies == "all" or (isinstance(applies, list) and entity_id in applies):
                out.append(p)
        return out

    def skeleton_cells(self) -> list[tuple[str, str]]:
        """Every ``(entity_id, parameter_id)`` cell the Main Input skeleton needs.

        Real entities × their applicable parameters, plus one
        ``(REF, parameter_id)`` row per reference-value parameter (D8, §12).
        ``build_csvs.py`` (T2) consumes this directly.
        """
        cells: list[tuple[str, str]] = []
        for e in self._data.get("entities", []):
            for p in self.parameters_for(e["id"]):
                cells.append((e["id"], p["id"]))
        for p in self.reference_value_parameters:
            cells.append((GLOBAL_ENTITY_ID, p["id"]))
        return cells

    # --- estimation -------------------------------------------------------
    @property
    def comparable_rubric(self) -> dict | None:
        return self._data.get("estimation", {}).get("comparable_rubric")

    @property
    def rubric_dimensions(self) -> list[str]:
        rubric = self.comparable_rubric
        return list(rubric["dimensions"]) if rubric else []

    @property
    def rubric_hard_rule(self) -> str | None:
        rubric = self.comparable_rubric
        return rubric.get("hard_rule") if rubric else None

    def entities_by_policy(self, policy: str) -> list[str]:
        return [e["id"] for e in self._data.get("entities", [])
                if e.get("estimation_policy") == policy]

    # --- conventions ------------------------------------------------------
    @property
    def conventions_needed(self) -> list[str]:
        return list(self._data.get("conventions_needed", []))

    def required_convention_files(self) -> list[str]:
        """Concrete ``conventions/*.csv`` files implied by the rule-types in use.

        Stage 0 scaffolds exactly these (D4). The mapping mirrors plan.md §5:
        MONETARY -> currency-rates + the chosen inflation index; CAPEX ->
        currency-rates + scaling-exponents (no escalation at normalize time);
        INTENSITY/RATE -> unit-conversions.
        """
        files: list[str] = []

        def add(name: str) -> None:
            if name not in files:
                files.append(name)

        rule_types = {p.get("rule_type") for p in self._data.get("parameters", [])}
        if "MONETARY" in rule_types or "CAPEX" in rule_types:
            add("currency-rates.csv")
        if "MONETARY" in rule_types:
            idx = self.inflation_index
            if idx and idx != "none":
                add(f"{idx.lower()}.csv")
        if "INTENSITY" in rule_types or "RATE" in rule_types:
            add("unit-conversions.csv")
        if "CAPEX" in rule_types:
            add("scaling-exponents.csv")
        return files

    # --- validation targets / defaults -----------------------------------
    @property
    def validation_targets(self) -> list[dict]:
        return list(self._data.get("validation_targets", []))

    @property
    def defaults(self) -> dict:
        return dict(self._data.get("defaults", {}))

    @property
    def master_list_candidate_cap(self) -> int:
        return self.defaults.get("master_list_candidate_cap", DEFAULT_MASTER_LIST_CAP)

    @property
    def gap_fill_candidate_cap(self) -> int:
        return self.defaults.get("gap_fill_candidate_cap", DEFAULT_GAP_FILL_CAP)

    @property
    def extraction_batch_size(self) -> int:
        return self.defaults.get("extraction_batch_size", DEFAULT_EXTRACTION_BATCH)

    def __repr__(self) -> str:
        return (
            f"<Schema {self.tea_id!r}: {len(self.entity_ids)} entities, "
            f"{len(self.parameter_ids)} parameters>"
        )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_schema(path: str | Path, *, strict: bool = True) -> Schema:
    """Read, validate, and wrap a ``tea-schema.json`` file.

    Raises ``SchemaError`` when the config has hard errors and ``strict`` is
    True (the default). Open questions never block loading — they are attached
    to the returned ``Schema`` as ``.report`` for Stage 0 / the analyst.
    """
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise SchemaError(f"config not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{path}: invalid JSON — {exc}") from None

    report = validate_schema(data)
    if strict and not report.ok:
        raise SchemaError(
            f"{path}: config has {len(report.errors)} error(s):\n  - "
            + "\n  - ".join(report.errors),
            errors=report.errors,
        )
    return Schema(data, report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Validate a tea-schema.json config.")
    ap.add_argument("config", type=Path, help="path to tea-schema.json")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)

    try:
        with open(args.config, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = validate_schema(data)
    if args.json:
        print(json.dumps(
            {
                "ok": report.ok,
                "errors": report.errors,
                "open_questions": [{"where": q.where, "question": q.question}
                                   for q in report.open_questions],
                "warnings": report.warnings,
            },
            indent=2,
        ))
    else:
        print(f"{args.config}: {report.summary()}")
        for e in report.errors:
            print(f"  ERROR  {e}")
        for q in report.open_questions:
            print(f"  OPEN   {q}")
        for w in report.warnings:
            print(f"  WARN   {w}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
