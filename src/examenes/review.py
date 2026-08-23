"""Verification artifacts: the review CSV round-trip and the unmapped queue."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import duckdb

from .build import Unmapped
from .store import apply_overrides

# Columns the reviewer edits. Everything else in the CSV is read-only context.
EDITABLE = ("verified", "value_num", "value_text", "note")

# Suspect rows first, so the riskiest parses sit at the top of the file.
CONFIDENCE_ORDER = "CASE confidence WHEN 'suspect' THEN 0 WHEN 'check' THEN 1 ELSE 2 END"

REVIEW_QUERY = f"""
SELECT
    obs_key,
    confidence,
    flags,
    verified,
    review_note AS note,
    sample_date,
    panel,
    sub_section,
    analyte_code,
    analyte_name_raw,
    value_num,
    value_text,
    unit,
    unit_raw,
    ref_low,
    ref_high,
    ref_operator,
    ref_text,
    out_of_range,
    asterisk_flag,
    method,
    also_in_panels,
    source_file,
    source_page
FROM v_observations
ORDER BY {CONFIDENCE_ORDER}, sample_date, analyte_code
"""


def _sql_literal(path: Path) -> str:
    """Quote a path for use as a SQL string literal."""
    return "'" + str(path).replace("'", "''") + "'"


def export_review(con: duckdb.DuckDBPyConnection, review_dir: Path) -> tuple[Path, int]:
    """Write a review CSV of every stored observation.

    Rows are ordered worst-confidence first and carry ``source_file`` and
    ``source_page`` so each number can be checked against the original PDF.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open connection.
    review_dir : Path
        Directory to write into.

    Returns
    -------
    tuple of (Path, int)
        Path written and the number of rows.
    """
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / f"review_{datetime.now():%Y%m%d-%H%M%S}.csv"
    con.execute(f"COPY ({REVIEW_QUERY}) TO {_sql_literal(path)} (HEADER, DELIMITER ',')")
    rows = con.execute(f"SELECT count(*) FROM ({REVIEW_QUERY})").fetchone()[0]
    return path, rows


def _as_bool(value: str | None) -> bool:
    """Interpret a spreadsheet truthy string."""
    return str(value or "").strip().lower() in {"true", "1", "yes", "y", "si", "sí", "t"}


def _as_float(value: str | None) -> float | None:
    """Parse a numeric cell, tolerating blanks and comma decimals."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def import_review(con: duckdb.DuckDBPyConnection, csv_path: Path) -> tuple[int, int]:
    """Read an edited review CSV and store the reviewer's decisions.

    Only rows the reviewer actually touched become overrides: a row counts as
    edited when it is marked verified, carries a note, or its value differs from
    what the parser produced. Untouched rows are ignored, so the override table
    stays a record of human judgement rather than a copy of the parse.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open connection.
    csv_path : Path
        Edited review CSV.

    Returns
    -------
    tuple of (int, int)
        Overrides written, and rows skipped because their ``obs_key`` is unknown.

    Raises
    ------
    ValueError
        If the CSV is missing required columns.
    """
    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if rows:
        missing = {"obs_key", *EDITABLE} - set(rows[0])
        if missing:
            raise ValueError(f"review CSV missing columns: {sorted(missing)}")

    parsed = {
        key: (num, text)
        for key, num, text in con.execute(
            "SELECT obs_key, value_num, value_text FROM observations"
        ).fetchall()
    }

    overrides: list[tuple] = []
    unknown = 0
    for row in rows:
        key = (row.get("obs_key") or "").strip()
        if key not in parsed:
            unknown += 1
            continue

        verified = _as_bool(row.get("verified"))
        note = (row.get("note") or "").strip() or None
        value_num = _as_float(row.get("value_num"))
        value_text = (row.get("value_text") or "").strip() or None

        was_num, was_text = parsed[key]
        changed = value_num != was_num or value_text != was_text
        if verified or note or changed:
            overrides.append((key, verified, value_num, value_text, note))

    return apply_overrides(con, overrides), unknown


def write_unmapped(unmapped: list[Unmapped], review_dir: Path) -> Path | None:
    """Write the unmapped-analyte queue.

    An unrecognised analyte is never dropped. It lands here and the ingest exits
    non-zero, so a name the parser does not understand cannot silently vanish.

    Parameters
    ----------
    unmapped : list of Unmapped
        Unresolved raw names.
    review_dir : Path
        Directory to write into.

    Returns
    -------
    Path or None
        Path written, or None when there was nothing to write.
    """
    path = review_dir / "unmapped_analytes.csv"
    if not unmapped:
        path.unlink(missing_ok=True)
        return None

    review_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[tuple, Unmapped] = {}
    for u in unmapped:
        seen.setdefault((u.name_raw, u.panel, u.sub_section), u)

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["name_raw", "panel", "sub_section", "unit_raw",
             "example_value", "source_file", "source_page"]
        )
        for u in sorted(seen.values(), key=lambda x: x.name_raw):
            writer.writerow(
                [u.name_raw, u.panel, u.sub_section, u.unit_raw,
                 u.value_cell, u.source_file, u.source_page]
            )
    return path
