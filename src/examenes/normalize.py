"""Map raw cells onto canonical analytes, values, units and reference ranges."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

RefOperator = Literal["range", "lt", "lte", "gt", "gte", "text", "categorical", "none"]

_NUM = r"\d+(?:[.,]\d+)?"
_BOUND = re.compile(rf"^\s*(<=|>=|<|>)\s*({_NUM})\s*$")
_RANGE = re.compile(rf"^\s*({_NUM})\s*-\s*({_NUM})\s*$")
# PERFIL HEPATICO prints some ranges without a dash at all (`46 116`,
# `5.0 37.0`), while PERFIL BIOQUIMICO prints the same analytes as `46 - 116`.
_RANGE_NO_DASH = re.compile(rf"^\s*({_NUM})\s+({_NUM})\s*$")
_RANGE_PREFIX = re.compile(rf"^\s*({_NUM})\s*-\s*({_NUM})\b")
_VALUE_RANGE = re.compile(rf"^\s*{_NUM}\s*-\s*{_NUM}\s*$")
_PURE_NUM = re.compile(rf"^\s*{_NUM}\s*$")


def _to_float(text: str) -> float:
    """Convert a Chilean-formatted number to float.

    Parameters
    ----------
    text : str
        Numeric token, optionally using a comma as the decimal separator.

    Returns
    -------
    float
        Parsed value.
    """
    return float(text.replace(",", "."))


def normalize_key(name: str) -> str:
    """Normalise an analyte name for alias lookup.

    Case, trailing periods, accents and repeated whitespace vary between panels
    for the same analyte, so all four are folded away before matching.

    Parameters
    ----------
    name : str
        Raw analyte name as printed.

    Returns
    -------
    str
        Lookup key.

    Examples
    --------
    >>> normalize_key("BILIRRUBINA INDIRECTA.")
    'BILIRRUBINA INDIRECTA'
    >>> normalize_key("Deshidrogenasa  Láctica (LDH).")
    'DESHIDROGENASA LACTICA (LDH)'
    """
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = re.sub(r"\s+", " ", folded).strip().rstrip(".").strip()
    return folded.upper()


@dataclass(frozen=True)
class Analyte:
    """One row of the canonical analyte dimension."""

    code: str
    display_es: str
    display_en: str
    category: str
    canonical_unit: str | None
    direction: str


@dataclass
class Catalog:
    """Alias, analyte and unit configuration loaded from ``config/``."""

    analytes: dict[str, Analyte]
    simple: dict[str, str]
    contextual: list[dict] = field(default_factory=list)
    differential: dict[str, dict[str, str]] = field(default_factory=dict)
    unit_map: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, config_dir: Path) -> Catalog:
        """Load the catalog from a config directory.

        Parameters
        ----------
        config_dir : Path
            Directory holding ``analytes.yaml``, ``aliases.yaml`` and ``units.yaml``.

        Returns
        -------
        Catalog
            Fully populated catalog.
        """
        analytes_raw = yaml.safe_load((config_dir / "analytes.yaml").read_text("utf-8"))
        aliases_raw = yaml.safe_load((config_dir / "aliases.yaml").read_text("utf-8"))
        units_raw = yaml.safe_load((config_dir / "units.yaml").read_text("utf-8"))

        analytes = {
            code: Analyte(
                code=code,
                display_es=spec["es"],
                display_en=spec["en"],
                category=spec["category"],
                canonical_unit=spec.get("unit"),
                direction=spec.get("direction", "none"),
            )
            for code, spec in analytes_raw["analytes"].items()
        }
        simple = {normalize_key(k): v for k, v in (aliases_raw.get("aliases") or {}).items()}
        contextual = [
            {**rule, "key": normalize_key(rule["raw"])}
            for rule in (aliases_raw.get("contextual") or [])
        ]
        differential = {
            normalize_key(k): v for k, v in (aliases_raw.get("differential") or {}).items()
        }
        return cls(
            analytes=analytes,
            simple=simple,
            contextual=contextual,
            differential=differential,
            unit_map=units_raw.get("normalise") or {},
        )

    def resolve(
        self, name_raw: str, panel: str | None, sub_section: str | None
    ) -> tuple[str | None, dict[str, str] | None]:
        """Resolve a raw analyte name to a canonical code.

        Resolution order is differential, then contextual (most specific match
        on panel and sub-section), then the plain alias table.

        Parameters
        ----------
        name_raw : str
            Raw analyte name as printed.
        panel : str or None
            Panel the row appeared under.
        sub_section : str or None
            Sub-section within the panel, for ORINA COMPLETA.

        Returns
        -------
        tuple of (str or None, dict or None)
            ``(code, None)`` for a single analyte, ``(None, {"pct": ..., "abs": ...})``
            for a differential row, or ``(None, None)`` when unmapped.
        """
        key = normalize_key(name_raw)

        if key in self.differential:
            return None, self.differential[key]

        best: tuple[int, str] | None = None
        for rule in self.contextual:
            if rule["key"] != key:
                continue
            if rule.get("panel") and rule["panel"] != panel:
                continue
            if rule.get("sub_section") and rule["sub_section"] != sub_section:
                continue
            specificity = bool(rule.get("panel")) + bool(rule.get("sub_section"))
            if best is None or specificity > best[0]:
                best = (specificity, rule["code"])
        if best is not None:
            return best[1], None

        return self.simple.get(key), None

    def normalize_unit(self, unit_raw: str, code: str) -> tuple[str | None, list[str]]:
        """Apply cosmetic unit normalisation and check it against the catalog.

        No numeric conversion is performed. A mismatch is reported, never fixed.

        Parameters
        ----------
        unit_raw : str
            Unit as printed.
        code : str
            Canonical analyte code.

        Returns
        -------
        tuple of (str or None, list of str)
            Canonical unit spelling and any flags raised.
        """
        flags: list[str] = []
        unit = unit_raw.strip() or None
        if unit is not None:
            unit = self.unit_map.get(unit, unit)
        expected = self.analytes[code].canonical_unit if code in self.analytes else None
        if unit is not None and expected is not None and unit != expected:
            flags.append("unit_unexpected")
        return unit, flags


@dataclass(frozen=True)
class ParsedValue:
    """A result cell split into numeric and textual parts."""

    value_num: float | None
    value_text: str | None
    asterisk: bool
    flags: tuple[str, ...]


def parse_value(cell: str) -> ParsedValue:
    """Parse a result cell.

    Non-numeric results (``Negativo``, ``Muy escasas``, ``<0.01``) are kept in
    ``value_text`` so they can never corrupt ``value_num``.

    Parameters
    ----------
    cell : str
        Raw text of the result column.

    Returns
    -------
    ParsedValue
        Parsed value, out-of-range asterisk, and any flags raised.

    Examples
    --------
    >>> parse_value("* 3.7").value_num
    3.7
    >>> parse_value("* 3.7").asterisk
    True
    >>> parse_value("Muy escasas").value_text
    'Muy escasas'
    >>> parse_value("0 - 2").flags
    ('value_is_range',)
    """
    text = cell.strip()
    asterisk = text.startswith("*")
    if asterisk:
        text = text[1:].strip()
    # `INDICE FIB 4 : 0.44` prints the value after a colon.
    text = text.lstrip(":").strip()

    if not text:
        return ParsedValue(None, None, asterisk, ("empty_value",))

    if _PURE_NUM.match(text):
        flags = ("decimal_comma",) if "," in text else ()
        return ParsedValue(_to_float(text), None, asterisk, flags)

    if _VALUE_RANGE.match(text):
        return ParsedValue(None, text, asterisk, ("value_is_range",))

    if _BOUND.match(text):
        return ParsedValue(None, text, asterisk, ("value_is_bounded",))

    return ParsedValue(None, text, asterisk, ("value_is_text",))


@dataclass(frozen=True)
class ParsedReference:
    """A reference cell split into bounds, operator and original text."""

    ref_low: float | None
    ref_high: float | None
    ref_operator: RefOperator
    ref_text: str | None
    flags: tuple[str, ...]


def parse_reference(cell: str) -> ParsedReference:
    """Parse a reference-range cell.

    Handles the dash spacing this lab actually emits -- ``50 - 200``, ``15-85``,
    ``1.015- 1.025`` -- as well as ranges printed with no dash at all, and
    ranges carrying trailing descriptive text (``0-5 por campo (40x)``).

    Parameters
    ----------
    cell : str
        Raw text of the reference column.

    Returns
    -------
    ParsedReference
        Bounds, operator, original text and any flags raised.

    Examples
    --------
    >>> parse_reference("1.6 - 2.6").ref_high
    2.6
    >>> parse_reference("46 116").flags
    ('ref_missing_dash',)
    >>> parse_reference("< 150").ref_operator
    'lt'
    >>> parse_reference("Negativo").ref_operator
    'text'
    """
    text = cell.strip()
    if not text:
        return ParsedReference(None, None, "none", None, ("no_reference",))

    if m := _RANGE.match(text):
        return ParsedReference(_to_float(m.group(1)), _to_float(m.group(2)), "range", text, ())

    if m := _RANGE_NO_DASH.match(text):
        return ParsedReference(
            _to_float(m.group(1)),
            _to_float(m.group(2)),
            "range",
            text,
            ("ref_missing_dash",),
        )

    if m := _BOUND.match(text):
        op = {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}[m.group(1)]
        bound = _to_float(m.group(2))
        low = bound if op in ("gt", "gte") else None
        high = bound if op in ("lt", "lte") else None
        return ParsedReference(low, high, op, text, ())

    if m := _RANGE_PREFIX.match(text):
        return ParsedReference(
            _to_float(m.group(1)),
            _to_float(m.group(2)),
            "range",
            text,
            ("ref_has_trailing_text",),
        )

    return ParsedReference(None, None, "text", text, ())


def compute_out_of_range(
    value: float | None, ref: ParsedReference
) -> bool | None:
    """Decide whether a value falls outside its reference range.

    Computed from the numbers rather than taken from the printed asterisk: this
    lab does not mark every out-of-range result. In these reports urine ``pH 8.5``
    against a reference of ``5.0 - 7.0`` carries no asterisk at all.

    Parameters
    ----------
    value : float or None
        Numeric result.
    ref : ParsedReference
        Parsed reference range.

    Returns
    -------
    bool or None
        True or False when decidable, None when there is no numeric reference.
    """
    if value is None:
        return None
    if ref.ref_operator == "range" and ref.ref_low is not None and ref.ref_high is not None:
        return value < ref.ref_low or value > ref.ref_high
    if ref.ref_operator == "lt" and ref.ref_high is not None:
        return value >= ref.ref_high
    if ref.ref_operator == "lte" and ref.ref_high is not None:
        return value > ref.ref_high
    if ref.ref_operator == "gt" and ref.ref_low is not None:
        return value <= ref.ref_low
    if ref.ref_operator == "gte" and ref.ref_low is not None:
        return value < ref.ref_low
    return None
