"""Assemble canonical observation records from raw scanned rows."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path

from .normalize import Catalog, compute_out_of_range, parse_reference, parse_value
from .panels import ReportMeta
from .parse import RawObservation

# Flags that mean "a human should look at this before trusting the number".
SUSPECT_FLAGS = frozenset(
    {
        "column_ambiguous",
        "duplicate_value_conflict",
        "unit_unexpected",
        "asterisk_range_mismatch",
        "ref_missing_dash",
        "decimal_comma",
    }
)


def obs_key(file_hash: str, analyte_code: str, discriminator: str = "") -> str:
    """Build the stable primary key for an observation.

    Keyed on file hash and analyte so that re-parsing the same PDF reproduces
    identical keys, which is what lets ``verified`` and manual corrections
    survive a ``--force`` re-ingest.

    Parameters
    ----------
    file_hash : str
        sha256 of the source file.
    analyte_code : str
        Canonical analyte code.
    discriminator : str, optional
        Extra component used only to keep a conflicting duplicate distinct.

    Returns
    -------
    str
        Hex-encoded sha256 digest.
    """
    raw = f"{file_hash}|{analyte_code}|{discriminator}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Observation:
    """One analyte result for one draw, ready to persist."""

    obs_key: str
    sample_date: date | None
    lab_name: str | None
    panel: str | None
    sub_section: str | None
    analyte_code: str
    analyte_name_raw: str
    value_num: float | None
    value_text: str | None
    unit: str | None
    unit_raw: str | None
    ref_low: float | None
    ref_high: float | None
    ref_operator: str
    ref_text: str | None
    method: str | None
    out_of_range: bool | None
    asterisk_flag: bool
    source_file: str
    source_page: int
    file_hash: str
    cod_lis: str | None
    source: str
    extracted_at: datetime
    verified: bool
    confidence: str
    flags: str
    also_in_panels: str | None


@dataclass(frozen=True)
class Unmapped:
    """A raw analyte name with no alias, queued for review."""

    name_raw: str
    panel: str | None
    sub_section: str | None
    unit_raw: str
    value_cell: str
    source_file: str
    source_page: int


def _confidence(flags: list[str]) -> str:
    """Grade a row from its flags.

    Parameters
    ----------
    flags : list of str
        Flags raised while parsing the row.

    Returns
    -------
    str
        ``ok``, ``check`` or ``suspect``.
    """
    if any(f in SUSPECT_FLAGS for f in flags):
        return "suspect"
    return "check" if flags else "ok"


def _make(
    raw: RawObservation,
    code: str,
    value_cell: str,
    catalog: Catalog,
    meta: ReportMeta,
    source_file: str,
    file_hash: str,
    extracted_at: datetime,
    ref_cell: str | None = None,
    unit_cell: str | None = None,
) -> Observation:
    """Build one observation from a raw row and a resolved analyte code.

    ``ref_cell`` and ``unit_cell`` override the row's own cells. Differential
    rows need this: one printed reference and one printed unit are shared by two
    analytes but belong to different ones. In a differential row printed as
    ``Segmentados  NN | NNNN | uL | 50 - 75`` the range describes the percentage
    and ``uL`` describes the absolute count.
    """
    value = parse_value(value_cell)
    ref = parse_reference(raw.ref_cell if ref_cell is None else ref_cell)
    unit, unit_flags = catalog.normalize_unit(
        raw.unit_cell if unit_cell is None else unit_cell, code
    )

    out_of_range = compute_out_of_range(value.value_num, ref)

    flags = [*value.flags, *ref.flags, *unit_flags]
    if raw.column_ambiguous:
        flags.append("column_ambiguous")
    # The printed asterisk is corroboration, not the source of truth.
    if out_of_range is not None and value.asterisk != out_of_range:
        flags.append("asterisk_range_mismatch")

    return Observation(
        obs_key=obs_key(file_hash, code),
        sample_date=meta.sample_date,
        lab_name=meta.lab_name,
        panel=raw.panel,
        sub_section=raw.sub_section,
        analyte_code=code,
        analyte_name_raw=raw.name_raw,
        value_num=value.value_num,
        value_text=value.value_text,
        unit=unit,
        unit_raw=raw.unit_cell or None,
        ref_low=ref.ref_low,
        ref_high=ref.ref_high,
        ref_operator=ref.ref_operator,
        ref_text=ref.ref_text,
        method=raw.method,
        out_of_range=out_of_range,
        asterisk_flag=value.asterisk,
        source_file=source_file,
        source_page=raw.page,
        file_hash=file_hash,
        cod_lis=meta.cod_lis,
        source="pdf",
        extracted_at=extracted_at,
        verified=False,
        confidence=_confidence(flags),
        flags=";".join(sorted(set(flags))),
        also_in_panels=None,
    )


def _dedup(observations: list[Observation]) -> list[Observation]:
    """Collapse cross-panel repeats of the same analyte within one report.

    COLESTEROL TOTAL, FOSFATASA ALCALINA, BILIRRUBINA TOTAL and TRANSAMINASA
    OXALOACETICA are each printed in two panels with identical values. Matching
    repeats collapse to one row that records the other panel. Repeats that
    *disagree* are a parser bug, so both rows are kept and flagged rather than
    silently resolved.

    Parameters
    ----------
    observations : list of Observation
        Observations from one report.

    Returns
    -------
    list of Observation
        Deduplicated observations.
    """
    grouped: dict[str, list[Observation]] = {}
    for o in observations:
        grouped.setdefault(o.analyte_code, []).append(o)

    out: list[Observation] = []
    for code, group in grouped.items():
        if len(group) == 1:
            out.append(group[0])
            continue

        signature = {(o.value_num, o.value_text) for o in group}
        if len(signature) == 1:
            primary = group[0]
            others = sorted({o.panel for o in group[1:] if o.panel})
            out.append(replace(primary, also_in_panels=";".join(others) or None))
        else:
            for i, o in enumerate(group):
                flags = sorted(set(filter(None, o.flags.split(";"))) | {"duplicate_value_conflict"})
                out.append(
                    replace(
                        o,
                        obs_key=obs_key(o.file_hash, code, f"{o.panel}|{o.source_page}|{i}"),
                        flags=";".join(flags),
                        confidence="suspect",
                    )
                )
    return out


def build_observations(
    meta: ReportMeta,
    rows: list[RawObservation],
    catalog: Catalog,
    source_path: Path | str,
    file_hash: str,
) -> tuple[list[Observation], list[Unmapped]]:
    """Turn raw scanned rows into canonical observations.

    Parameters
    ----------
    meta : ReportMeta
        Report-level metadata.
    rows : list of RawObservation
        Raw rows from the scanner.
    catalog : Catalog
        Alias and analyte configuration.
    source_path : Path or str
        Source PDF, recorded for provenance.
    file_hash : str
        sha256 of the source PDF.

    Returns
    -------
    tuple of (list of Observation, list of Unmapped)
        Canonical observations and any names with no alias.
    """
    extracted_at = datetime.now(UTC)
    source_file = source_path if isinstance(source_path, str) else source_path.name
    built: list[Observation] = []
    unmapped: list[Unmapped] = []

    for raw in rows:
        code, differential = catalog.resolve(raw.name_raw, raw.panel, raw.sub_section)

        if differential is not None:
            if raw.value_cell:
                # The printed range is the percentage reference; the printed
                # unit belongs to the absolute count, so the percentage is "%".
                built.append(
                    _make(raw, differential["pct"], raw.value_cell, catalog, meta,
                          source_file, file_hash, extracted_at, unit_cell="%")
                )
            if raw.abs_cell:
                # The absolute count has no reference range of its own.
                built.append(
                    _make(raw, differential["abs"], raw.abs_cell, catalog, meta,
                          source_file, file_hash, extracted_at, ref_cell="")
                )
            continue

        if code is None:
            unmapped.append(
                Unmapped(
                    name_raw=raw.name_raw,
                    panel=raw.panel,
                    sub_section=raw.sub_section,
                    unit_raw=raw.unit_cell,
                    value_cell=raw.value_cell or raw.abs_cell,
                    source_file=source_file,
                    source_page=raw.page,
                )
            )
            continue

        # V.H.S and R.A.N. print their only value in the absolute-count column,
        # which the differential sub-header introduced. Fall back to it so a
        # single-valued analyte is never lost.
        cell = raw.value_cell or raw.abs_cell
        built.append(
            _make(raw, code, cell, catalog, meta, source_file, file_hash, extracted_at)
        )

    return _dedup(built), unmapped
