"""Schema-driven normalization transforms for Audit.csv rows.

The functions here are deliberately small, deterministic pieces of arithmetic:
they read parameter rule types from ``tea-schema.json`` and conversion factors
from ``conventions/*.csv``. When a row is ambiguous, the transform leaves model
outputs blank and records a ``FLAGGED:`` step for the Phase 4.2 review queue.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .csvio import AUDIT_FIELDNAMES, blank_row
from .extraction import is_nullish
from .schema import Schema


CURRENCY_SYMBOLS = {"$": "USD"}
CURRENCY_CODES = {"USD", "EUR", "GBP", "JPY", "CNY", "CAD", "AUD", "CHF"}
MAGNITUDE_SUFFIXES = {
    "k": 1e3,
    "K": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "M": 1e6,
    "mm": 1e6,
    "MM": 1e6,
    "million": 1e6,
    "b": 1e9,
    "B": 1e9,
    "bn": 1e9,
    "BN": 1e9,
    "billion": 1e9,
}

NUMERIC_RULE_TYPES = {"MONETARY", "INTENSITY", "FRACTION", "RATE", "CAPEX"}

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*(?:[eE][+-]?\d+)?")
_RANGE_RE = re.compile(
    r"(?<![\w.])([+-]?\d[\d,]*(?:\.\d+)?)\s*(?:-|\u2013|\u2014|to)\s*"
    r"([+-]?\d[\d,]*(?:\.\d+)?)(?![\w.])",
    re.IGNORECASE,
)
_MASS_UNIT_RE = (
    r"short\s+tons?|long\s+tons?|metric\s+tonnes?|metric\s+tons?|"
    r"tonnes?|tons?|kilograms?|kgs?|kg|grams?|g|pounds?|lbs?|lb|MT|mt|t"
)

OUTPUT_COLUMNS = (
    "normalized_value",
    "normalized_units",
    "transform_steps",
    "capex_usd",
    "capex_form",
    "capex_basis_year",
    "capex_basis_scale",
    "capex_basis_scale_units",
    "capex_notes",
    "review_value",
    "review_units",
    "review_steps",
)


@dataclass
class StepLog:
    """Accumulated transform trail for one row."""

    steps: list[str] = field(default_factory=list)

    def add(self, step: str) -> None:
        self.steps.append(step)

    def flag(self, reason: str) -> None:
        self.steps.append(f"FLAGGED: {reason}")

    @property
    def flagged(self) -> bool:
        return any(step.startswith("FLAGGED:") for step in self.steps)

    def render(self) -> str:
        return " | ".join(self.steps)


@dataclass(frozen=True)
class NumericParse:
    value: float | None
    kind: str
    tokens: tuple[str, ...] = ()
    range_start: float | None = None
    range_end: float | None = None


@dataclass
class Conventions:
    """Loaded convention tables used by normalization transforms."""

    unit_conversions: dict[tuple[str, str], float] = field(default_factory=dict)
    currency_rates: dict[tuple[str, str, int], float] = field(default_factory=dict)
    indices: dict[str, dict[int, float]] = field(default_factory=dict)
    scaling_exponents: dict[str, float] = field(default_factory=dict)
    target_scale: float | None = None

    def currency_rate(self, from_currency: str, to_currency: str, year: int) -> float | None:
        src = from_currency.upper()
        dst = to_currency.upper()
        if src == dst:
            return 1.0
        return self.currency_rates.get((src, dst, year))

    def index_factor(self, index_name: str, source_year: int, target_year: int) -> float | None:
        idx = (index_name or "").strip().upper()
        if not idx or idx == "NONE" or source_year == target_year:
            return 1.0
        table = self.indices.get(idx, {})
        source = table.get(source_year)
        target = table.get(target_year)
        if source is None or target is None or source == 0:
            return None
        return target / source

    def conversion_factor(self, from_unit: str, to_unit: str) -> float | None:
        src = normalize_unit_name(from_unit)
        dst = normalize_unit_name(to_unit)
        if not src or not dst:
            return None
        if src == dst:
            return 1.0

        graph: dict[str, list[tuple[str, float]]] = {}
        for (u_from, u_to), factor in self.unit_conversions.items():
            a = normalize_unit_name(u_from)
            b = normalize_unit_name(u_to)
            if not a or not b or factor == 0:
                continue
            graph.setdefault(a, []).append((b, factor))
            graph.setdefault(b, []).append((a, 1.0 / factor))

        queue = deque([(src, 1.0)])
        seen = {src}
        while queue:
            unit, factor_so_far = queue.popleft()
            for nxt, factor in graph.get(unit, []):
                if nxt in seen:
                    continue
                combined = factor_so_far * factor
                if nxt == dst:
                    return combined
                seen.add(nxt)
                queue.append((nxt, combined))
        return None

    def unit_tokens(self) -> list[str]:
        tokens = set()
        for src, dst in self.unit_conversions:
            tokens.add(src)
            tokens.add(dst)
        tokens.update(
            {
                "GWh",
                "MWh",
                "kWh",
                "Wh",
                "MMBtu",
                "Btu",
                "GJ",
                "MJ",
                "kJ",
                "Therm",
                "kcal",
                "kg",
                "g",
                "lb",
                "tonne",
                "tonnes",
                "tokens",
                "token",
                "1M tokens",
            }
        )
        return sorted(tokens, key=len, reverse=True)


def _read_csv(path: Path, *, missing_ok: bool = True) -> list[dict[str, str]]:
    if missing_ok and not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _float(value: object) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _int_year(value: object) -> int | None:
    text = "" if value is None else str(value)
    match = re.search(r"\b(19|20)\d{2}\b", text)
    if match:
        return int(match.group(0))
    parsed = _float(text)
    return int(parsed) if parsed is not None else None


def load_conventions(schema: Schema, conventions_dir: str | Path = "conventions") -> Conventions:
    """Load conversion tables required by ``schema`` from ``conventions_dir``.

    Missing files yield empty tables; the transforms then flag only the rows
    that actually need missing factors.
    """

    conv_dir = Path(conventions_dir)
    conv = Conventions()

    for row in _read_csv(conv_dir / "unit-conversions.csv"):
        factor = _float(row.get("factor"))
        if factor is None:
            continue
        src = (row.get("from_unit") or "").strip()
        dst = (row.get("to_unit") or "").strip()
        if src and dst:
            conv.unit_conversions[(src, dst)] = factor

    for row in _read_csv(conv_dir / "currency-rates.csv"):
        factor = _float(row.get("rate"))
        year = _int_year(row.get("year"))
        src = (row.get("from_currency") or "").strip().upper()
        dst = (row.get("to_currency") or "").strip().upper()
        if factor is not None and year is not None and src and dst:
            conv.currency_rates[(src, dst, year)] = factor

    for index_name in ("CEPCI", "CPI", "PPI"):
        rows = _read_csv(conv_dir / f"{index_name.lower()}.csv")
        table: dict[int, float] = {}
        for row in rows:
            year = _int_year(row.get("year"))
            index = _float(row.get("index"))
            if year is not None and index is not None:
                table[year] = index
        if table:
            conv.indices[index_name] = table

    for row in _read_csv(conv_dir / "scaling-exponents.csv"):
        entity = (row.get("entity") or row.get("unit") or "").strip()
        exponent = _float(row.get("default_exponent") or row.get("exponent"))
        if entity and exponent is not None:
            conv.scaling_exponents[entity] = exponent
        target_scale = _float(row.get("target_scale") or row.get("target_scale_unit_output"))
        if target_scale is not None:
            conv.target_scale = target_scale

    del schema
    return conv


def _number(raw: str) -> float:
    return float(str(raw).replace(",", ""))


def parse_numeric_detail(raw: object) -> NumericParse:
    """Parse a scalar or simple numeric range from an extracted value."""

    if raw is None:
        return NumericParse(None, "none")
    text = str(raw).strip()
    if not text:
        return NumericParse(None, "none")
    numeric_text = text.replace(",", "")
    nums = tuple(_NUM_RE.findall(numeric_text))
    range_match = _RANGE_RE.search(text)
    if range_match:
        start = _number(range_match.group(1))
        end = _number(range_match.group(2))
        if len(nums) == 2:
            return NumericParse((start + end) / 2, "range", nums, start, end)
        return NumericParse(None, "multi", nums, start, end)
    if not nums:
        return NumericParse(None, "none")
    if len(nums) > 1:
        return NumericParse(None, "multi", nums)
    return NumericParse(float(nums[0]), "scalar", nums)


def parse_numeric(raw: object) -> float | None:
    return parse_numeric_detail(raw).value


def format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return f"{float(value):.8g}"


def normalize_unit_name(unit: object) -> str:
    text = "" if unit is None else str(unit)
    text = text.strip().replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_mass_unit(unit: str) -> str:
    token = re.sub(r"\s+", " ", (unit or "").strip().lower().replace(".", ""))
    if token in {"kg", "kgs", "kilogram", "kilograms"}:
        return "kg"
    if token in {"g", "gram", "grams"}:
        return "g"
    if token in {"lb", "lbs", "pound", "pounds"}:
        return "lb"
    if token in {"t", "mt", "tonne", "tonnes", "metric ton", "metric tons",
                 "metric tonne", "metric tonnes"}:
        return "tonne"
    if token in {"short ton", "short tons", "ton", "tons"}:
        return "short ton"
    if token in {"long ton", "long tons"}:
        return "long ton"
    return token


def mass_factor_to_kg(unit: str) -> float | None:
    return {
        "kg": 1.0,
        "g": 0.001,
        "lb": 0.45359237,
        "tonne": 1000.0,
        "short ton": 907.18474,
        "long ton": 1016.0469088,
    }.get(canonical_mass_unit(unit))


def find_leading_mass_unit(units: str) -> str | None:
    match = re.search(rf"^\s*(?:of\s+)?({_MASS_UNIT_RE})\b", units or "", re.IGNORECASE)
    return match.group(1) if match else None


def find_mass_denominator(units: str) -> tuple[float, str] | None:
    amount = r"(?:(\d[\d,]*\.?\d*)\s*)?"
    patterns = [
        rf"/\s*{amount}({_MASS_UNIT_RE})\b",
        rf"\bper\s+{amount}({_MASS_UNIT_RE})\b",
        rf"\b(?:produce|produced|production of|output of)\s+{amount}({_MASS_UNIT_RE})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, units or "", re.IGNORECASE)
        if match:
            qty = _number(match.group(1)) if match.group(1) else 1.0
            return qty, match.group(2)
    return None


def detect_currency(raw_value: object, raw_units: object, *, default: str) -> str:
    text = f"{raw_value or ''} {raw_units or ''}"
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    for code in sorted(CURRENCY_CODES | {default.upper()}):
        if re.search(rf"\b{re.escape(code)}\b", text, re.IGNORECASE):
            return code.upper()
    return default.upper()


def detect_magnitude(raw_value: object, raw_units: object) -> float:
    text = f"{raw_value or ''} {raw_units or ''}"
    for token, multiplier in MAGNITUDE_SUFFIXES.items():
        if re.search(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", text):
            return multiplier
    return 1.0


def _parse_value_for_numeric_rule(row: Mapping[str, object], log: StepLog) -> float | None:
    detail = parse_numeric_detail(row.get("raw_value"))
    if detail.kind == "multi":
        tokens = ", ".join(detail.tokens[:8])
        more = "" if len(detail.tokens) <= 8 else f", +{len(detail.tokens) - 8} more"
        log.flag(
            "raw_value contains multiple numeric candidates "
            f"({tokens}{more}); route to normalization-agent or reject"
        )
        return None
    if detail.value is None:
        log.flag(f"raw_value {row.get('raw_value')!r} is not numeric")
        return None
    if detail.kind == "range" and detail.range_start is not None and detail.range_end is not None:
        log.add(
            f"range midpoint {detail.range_start:g} to {detail.range_end:g} -> {detail.value:g}"
        )
    return detail.value


def _convert_currency(
    value: float,
    *,
    from_currency: str,
    to_currency: str,
    source_year: int,
    conv: Conventions,
    log: StepLog,
) -> float | None:
    rate = conv.currency_rate(from_currency, to_currency, source_year)
    if rate is None:
        log.flag(f"currency rate for {from_currency}->{to_currency} {source_year} is missing")
        return None
    if rate != 1.0:
        value *= rate
        log.add(f"currency {from_currency}->{to_currency} at {source_year}: x{rate:g}")
    else:
        log.add(f"currency already {to_currency}")
    return value


def _apply_inflation(
    value: float,
    *,
    schema: Schema,
    source_year: int,
    conv: Conventions,
    log: StepLog,
) -> float | None:
    index = schema.inflation_index
    factor = conv.index_factor(index, source_year, schema.base_year)
    if factor is None:
        log.flag(f"{index} index value missing for {source_year}->{schema.base_year}")
        return None
    if factor != 1.0:
        value *= factor
        log.add(f"{index} {source_year}->{schema.base_year}: x{factor:g}")
    elif index == "none":
        log.add("no inflation index declared")
    else:
        log.add(f"{index} basis already {schema.base_year}")
    return value


def _monetary_units(row: Mapping[str, object], schema: Schema, parameter: Mapping[str, object]) -> str:
    canonical = (parameter.get("canonical_unit") or parameter.get("units") or "").strip()
    if canonical:
        return canonical
    raw_units = (row.get("raw_units") or "").strip()
    if raw_units:
        text = raw_units
        for code in CURRENCY_CODES | {schema.currency.upper()}:
            text = re.sub(rf"\b{re.escape(code)}\b", schema.currency, text, flags=re.IGNORECASE)
        if "$" in text:
            text = text.replace("$", schema.currency)
        return text
    return schema.currency


def transform_monetary(
    row: dict[str, str],
    schema: Schema,
    parameter: Mapping[str, object],
    conv: Conventions,
    log: StepLog,
) -> None:
    value = _parse_value_for_numeric_rule(row, log)
    if value is None:
        return
    magnitude = detect_magnitude(row.get("raw_value"), row.get("raw_units"))
    if magnitude != 1.0:
        value *= magnitude
        log.add(f"applied magnitude x{magnitude:g}")

    source_year = _int_year(row.get("raw_basis_year"))
    if source_year is None:
        log.flag("raw_basis_year missing or unparseable for monetary escalation")
        return

    currency = detect_currency(row.get("raw_value"), row.get("raw_units"), default=schema.currency)
    value = _convert_currency(
        value,
        from_currency=currency,
        to_currency=schema.currency,
        source_year=source_year,
        conv=conv,
        log=log,
    )
    if value is None:
        return
    value = _apply_inflation(value, schema=schema, source_year=source_year, conv=conv, log=log)
    if value is None:
        return

    row["normalized_value"] = format_number(value)
    row["normalized_units"] = _monetary_units(row, schema, parameter)


def _detect_unit_from_text(text: str, target: str, conv: Conventions) -> str | None:
    stripped = (text or "").strip()
    if not stripped:
        return target or None

    def find_token(segment: str) -> str | None:
        matches: list[tuple[int, int, str]] = []
        for token in conv.unit_tokens():
            match = re.search(
                rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
                segment,
                re.IGNORECASE,
            )
            if match:
                matches.append((match.start(), -len(token), token))
        if not matches:
            return None
        matches.sort()
        return matches[0][2]

    numerator_segment = re.split(r"/|\bper\b", stripped, maxsplit=1, flags=re.IGNORECASE)[0]
    if numerator_segment and numerator_segment != stripped:
        token = find_token(numerator_segment)
        if token:
            return token
    token = find_token(stripped)
    if token:
        return token
    return target or None


def _convert_unit_value(
    value: float,
    *,
    from_unit: str,
    to_unit: str,
    conv: Conventions,
    log: StepLog,
) -> float | None:
    factor = conv.conversion_factor(from_unit, to_unit)
    if factor is None:
        log.flag(f"no unit conversion path {from_unit!r}->{to_unit!r}")
        return None
    if factor != 1.0:
        value *= factor
        log.add(f"{from_unit} -> {to_unit}: x{factor:g}")
    else:
        log.add(f"numerator already {to_unit}")
    return value


def _functional_unit_amount(schema: Schema) -> tuple[float, str] | None:
    label = schema.functional_unit_symbol or schema.functional_unit_name
    match = re.match(r"\s*(\d+(?:\.\d+)?)\s*([kKmM])?\s+(.+?)s?\s*$", label)
    if not match:
        return None
    amount = float(match.group(1))
    suffix = match.group(2)
    if suffix in {"k", "K"}:
        amount *= 1e3
    elif suffix in {"m", "M"}:
        amount *= 1e6
    unit = match.group(3).strip().lower()
    return amount, unit


def _functional_denominator_factor(raw_units: str, schema: Schema, log: StepLog) -> tuple[float, str] | None:
    raw = (raw_units or "").lower()
    label = schema.functional_unit_symbol or schema.functional_unit_name
    if label and label.lower() in raw:
        return 1.0, label

    components = _functional_unit_amount(schema)
    if components:
        target_amount, target_unit = components
        unit_pattern = re.escape(target_unit.rstrip("s"))
        amount = r"(?:(\d[\d,]*\.?\d*)\s*)?"
        match = re.search(rf"(?:/|\bper\s+){amount}({unit_pattern}s?)\b", raw, re.IGNORECASE)
        if match:
            source_amount = _number(match.group(1)) if match.group(1) else 1.0
            return source_amount / target_amount, label

    if raw_units:
        log.add(f"assumed raw denominator already matches functional unit ({label})")
    else:
        log.add(f"assumed per functional unit ({label})")
    return 1.0, label


def _denominator_factor(
    row: Mapping[str, object],
    schema: Schema,
    parameter: Mapping[str, object],
    log: StepLog,
) -> tuple[float, str] | None:
    raw_units = row.get("raw_units") or ""
    per = parameter.get("per") or "functional_unit"
    if per == "functional_unit":
        return _functional_denominator_factor(str(raw_units), schema, log)

    mass_den = find_mass_denominator(str(raw_units))
    if mass_den:
        amount, unit = mass_den
        factor = mass_factor_to_kg(unit)
        if factor is None:
            log.flag(f"denominator mass unit {unit!r} is not recognized")
            return None
        denom_kg = amount * factor
        log.add(f"per {amount:g} {canonical_mass_unit(unit)} -> per kg (/{denom_kg:g})")
        return denom_kg, "kg entity output"

    output_label = str(parameter.get("basis") or "entity output")
    if raw_units:
        log.add(f"assumed raw denominator already matches {output_label}")
    else:
        log.add(f"assumed per {output_label}")
    return 1.0, output_label


def transform_intensity(
    row: dict[str, str],
    schema: Schema,
    parameter: Mapping[str, object],
    conv: Conventions,
    log: StepLog,
) -> None:
    target_unit = (parameter.get("numerator_units") or "").strip()
    if not target_unit:
        log.flag("parameter has no numerator_units")
        return
    value = _parse_value_for_numeric_rule(row, log)
    if value is None:
        return

    raw_units = row.get("raw_units") or ""
    from_unit = _detect_unit_from_text(raw_units, target_unit, conv)
    if not from_unit:
        log.flag("could not infer numerator unit")
        return
    value = _convert_unit_value(value, from_unit=from_unit, to_unit=target_unit, conv=conv, log=log)
    if value is None:
        return

    denom = _denominator_factor(row, schema, parameter, log)
    if denom is None:
        return
    denom_factor, denom_label = denom
    if denom_factor == 0:
        log.flag("denominator factor is zero")
        return
    value /= denom_factor
    row["normalized_value"] = format_number(value)
    row["normalized_units"] = f"{target_unit}/{denom_label}"


def transform_fraction(
    row: dict[str, str],
    schema: Schema,
    parameter: Mapping[str, object],
    conv: Conventions,
    log: StepLog,
) -> None:
    del schema, conv
    value = _parse_value_for_numeric_rule(row, log)
    if value is None:
        return
    text = f"{row.get('raw_value') or ''} {row.get('raw_units') or ''}".lower()
    if "%" in text or "percent" in text:
        value /= 100.0
        log.add("percent -> fraction")
    elif value > 1.0:
        log.flag(f"fraction value {value:g} > 1 without percent marker")
        return
    else:
        log.add("treated as fraction")
    if not 0.0 <= value <= 1.0:
        log.flag(f"normalized fraction {value:g} outside [0,1]")
        return
    row["normalized_value"] = format_number(value)
    basis = (parameter.get("basis") or "dimensionless").strip()
    row["normalized_units"] = f"fraction ({basis})" if basis else "fraction"


def transform_rate(
    row: dict[str, str],
    schema: Schema,
    parameter: Mapping[str, object],
    conv: Conventions,
    log: StepLog,
) -> None:
    del schema
    target_units = (parameter.get("units") or parameter.get("canonical_unit") or "").strip()
    if not target_units:
        log.flag("RATE parameter has no target units")
        return
    value = _parse_value_for_numeric_rule(row, log)
    if value is None:
        return
    raw_units = (row.get("raw_units") or "").strip() or target_units
    value = _convert_unit_value(value, from_unit=raw_units, to_unit=target_units, conv=conv, log=log)
    if value is None:
        return
    row["normalized_value"] = format_number(value)
    row["normalized_units"] = target_units


def _parse_basis_scale(value: object) -> float | None:
    return parse_numeric(value)


def transform_capex(
    row: dict[str, str],
    schema: Schema,
    parameter: Mapping[str, object],
    conv: Conventions,
    log: StepLog,
) -> None:
    value = _parse_value_for_numeric_rule(row, log)
    if value is None:
        return
    magnitude = detect_magnitude(row.get("raw_value"), row.get("raw_units"))
    if magnitude != 1.0:
        value *= magnitude
        log.add(f"applied magnitude x{magnitude:g}")

    source_year = _int_year(row.get("raw_basis_year"))
    if source_year is None:
        log.flag("raw_basis_year missing or unparseable for CAPEX")
        return

    currency = detect_currency(row.get("raw_value"), row.get("raw_units"), default=schema.currency)
    value = _convert_currency(
        value,
        from_currency=currency,
        to_currency=schema.currency,
        source_year=source_year,
        conv=conv,
        log=log,
    )
    if value is None:
        return

    raw_units = row.get("raw_units") or ""
    declared_form = (parameter.get("capex_form") or "").strip()
    capex_form = declared_form or "unspecified"
    if re.search(r"\btotal\b", raw_units, re.IGNORECASE):
        capex_form = "total"
    elif capex_form == "unspecified":
        capex_form = "specific"

    basis_scale = _parse_basis_scale(row.get("raw_basis_scale"))
    basis_units = row.get("raw_basis_scale_units") or ""
    if capex_form == "total" and basis_scale is None:
        log.flag("total CAPEX row has no parseable raw_basis_scale")
        return

    row["capex_usd"] = format_number(value)
    row["capex_form"] = capex_form
    row["capex_basis_year"] = str(source_year)
    row["capex_basis_scale"] = format_number(basis_scale) if basis_scale is not None else (row.get("raw_basis_scale") or "")
    row["capex_basis_scale_units"] = basis_units
    row["capex_notes"] = (
        f"source-year {schema.currency}; no model escalation or scale normalization applied"
    )

    review_value = value
    review_log = StepLog()
    review_log.add("QA-only CAPEX comparison; not a model input")
    if capex_form == "total" and basis_scale:
        review_value /= basis_scale
        review_log.add(f"divided total CAPEX by basis scale {basis_scale:g}")
    factor = conv.index_factor(schema.inflation_index, source_year, schema.base_year)
    if factor is None:
        review_log.flag(f"{schema.inflation_index} missing for {source_year}->{schema.base_year}")
    elif factor != 1.0:
        review_value *= factor
        review_log.add(f"{schema.inflation_index} {source_year}->{schema.base_year}: x{factor:g}")

    entity = row.get("entity") or ""
    exponent = conv.scaling_exponents.get(entity)
    if basis_scale and exponent is not None and conv.target_scale:
        scale_factor = (basis_scale / conv.target_scale) ** (1.0 - exponent)
        review_value *= scale_factor
        review_log.add(
            f"scale rebase {basis_scale:g}->{conv.target_scale:g} at n={exponent:g}: x{scale_factor:g}"
        )
    elif basis_scale and exponent is None:
        review_log.add(f"no scaling exponent for entity {entity!r}")
    elif basis_scale and not conv.target_scale:
        review_log.add("no target_scale in scaling-exponents.csv")
    else:
        review_log.add("no basis scale; review value not scale-rebased")

    row["review_value"] = format_number(review_value)
    if capex_form == "total" and basis_units:
        row["review_units"] = f"{schema.currency}/{basis_units}, {schema.base_year} {schema.currency} (QA-only)"
    else:
        row["review_units"] = f"{schema.currency}, {schema.base_year} {schema.currency} (QA-only)"
    row["review_steps"] = review_log.render()


def transform_passthrough(
    row: dict[str, str],
    schema: Schema,
    parameter: Mapping[str, object],
    conv: Conventions,
    log: StepLog,
) -> None:
    del schema, parameter, conv
    row["normalized_value"] = row.get("raw_value", "")
    row["normalized_units"] = row.get("raw_units", "")
    log.add("passthrough (no math)")


def transform_json(
    row: dict[str, str],
    schema: Schema,
    parameter: Mapping[str, object],
    conv: Conventions,
    log: StepLog,
) -> None:
    del schema, parameter, conv
    raw = (row.get("raw_value") or "").strip()
    if not raw:
        return
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.flag(f"raw_value is not valid JSON: {exc.msg}")
        return
    row["normalized_value"] = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    row["normalized_units"] = "JSON"
    log.add("validated JSON")


TRANSFORMS = {
    "MONETARY": transform_monetary,
    "INTENSITY": transform_intensity,
    "FRACTION": transform_fraction,
    "RATE": transform_rate,
    "CAPEX": transform_capex,
    "PASSTHROUGH": transform_passthrough,
    "TEXT": transform_passthrough,
    "JSON": transform_json,
}


def normalize_audit_row(row: Mapping[str, object], schema: Schema, conv: Conventions) -> dict[str, str]:
    """Return one Audit-shaped row with normalized fields filled."""

    out = blank_row(AUDIT_FIELDNAMES)
    for key in AUDIT_FIELDNAMES:
        value = row.get(key, "")
        out[key] = "" if value is None else str(value)

    for key in OUTPUT_COLUMNS:
        out[key] = ""

    entity = (out.get("entity") or "").strip()
    parameter_id = (out.get("parameter") or "").strip()
    status = (out.get("relevance_status") or "").strip().lower()

    if status == "hold":
        out["transform_steps"] = "passthrough: unresolved extraction hold"
        return out
    if status == "reject":
        out["transform_steps"] = "passthrough: relevance_status=reject"
        return out
    if is_nullish(out.get("raw_value")):
        out["transform_steps"] = "passthrough: raw_value blank"
        return out

    log = StepLog()
    if not schema.has_parameter(parameter_id):
        log.flag(f"unknown parameter {parameter_id!r}")
    elif not schema.applies(parameter_id, entity):
        log.flag(f"parameter {parameter_id!r} does not apply to entity {entity!r}")
    else:
        parameter = schema.parameter(parameter_id)
        rule_type = schema.rule_type(parameter_id)
        transform = TRANSFORMS.get(rule_type)
        if transform is None:
            log.flag(f"unsupported rule_type {rule_type!r}")
        else:
            transform(out, schema, parameter, conv, log)

    out["transform_steps"] = log.render()
    out["normalization_status"] = "flagged" if log.flagged else "clear"
    if log.flagged:
        out["selected_for_model"] = ""
        out["cross_check_delta"] = ""
    return out
