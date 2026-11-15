from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pdfplumber

from .columns import Cells, detect_layout, split_row
from .extract import Line, page_lines
from .panels import (
    METHOD,
    ReportMeta,
    is_note_start,
    is_skippable,
    is_stop,
    method_lines,
    panel_title,
    report_meta,
    sample_type,
    starts_with_value,
    sub_section_of,
)


@dataclass(frozen=True)
class RawObservation:
    """One table row, split into cells but not yet mapped to a canonical analyte."""

    panel: str | None
    sub_section: str | None
    name_raw: str
    value_cell: str
    abs_cell: str
    unit_cell: str
    ref_cell: str
    method: str | None
    sample_type: str | None
    page: int
    column_ambiguous: bool


def _header_index(lines: list[Line]) -> int | None:
    """Locate the table header line.

    Scanning only below the header discards the repeated patient block, which
    otherwise yields rows such as ``Nombre : <surname> | <given names>`` -- the
    name splits across the name and result columns and parses as a result.

    Parameters
    ----------
    lines : list of Line
        De-noised lines of a page.

    Returns
    -------
    int or None
        Index of the header line, or None when the page has no table.
    """
    for i, ln in enumerate(lines):
        if any(w.text == "RESULTADO" for w in ln.words):
            return i
    return None


def _is_result_row(cells: Cells) -> bool:
    """Return whether a split row looks like an actual result.

    A result always carries something in the value or absolute column. The
    lipid page's interpretation guide (``Alto 160 - 189``, ``Deseable < 200``)
    lands wholly inside the name column and is rejected here.

    Parameters
    ----------
    cells : Cells
        Split row.

    Returns
    -------
    bool
        True when the row is a candidate result.
    """
    if not cells.name:
        return False
    if not (cells.value or cells.absolute):
        return False
    # Header echoes and section rules.
    return not (cells.name.startswith("_") or cells.name.upper() == "EXAMEN")


def scan_page(page: pdfplumber.page.Page, page_no: int) -> list[RawObservation]:
    """Extract candidate result rows from one page.

    Parameters
    ----------
    page : pdfplumber.page.Page
        Page to scan.
    page_no : int
        1-based page number, recorded for provenance.

    Returns
    -------
    list of RawObservation
        Candidate rows in reading order.
    """
    lines = page_lines(page)
    layout = detect_layout(lines)
    header_idx = _header_index(lines)
    if layout is None or header_idx is None:
        return []

    title = panel_title(lines)
    specimen = sample_type(lines)
    methods = method_lines(lines)
    # A titled panel declares one method for the whole table. The untitled pages
    # stack independent single-metric blocks, each followed by its own method.
    panel_method = methods[0][1] if (title and methods) else None

    out: list[RawObservation] = []
    sub_section: str | None = None
    in_note = False

    for ln in lines[header_idx + 1 :]:
        text = ln.text.strip()
        if is_stop(text):
            break
        if (sub := sub_section_of(text)) is not None:
            sub_section = sub
            continue
        if is_note_start(text):
            in_note = True
            continue
        if is_skippable(text):
            continue
        if METHOD.match(text):
            if title:
                # On a titled panel the method line closes the table and the
                # interpretation guide follows.
                break
            continue

        cells = split_row(ln, layout)
        if in_note:
            if not (starts_with_value(cells.value) or starts_with_value(cells.absolute)):
                continue
            in_note = False
        if not _is_result_row(cells):
            continue

        method = panel_method
        if method is None:
            method = next((m for top, m in methods if top > ln.top), None)

        out.append(
            RawObservation(
                panel=title,
                sub_section=sub_section,
                name_raw=cells.name,
                value_cell=cells.value,
                abs_cell=cells.absolute,
                unit_cell=cells.unit,
                ref_cell=cells.ref,
                method=method,
                sample_type=specimen,
                page=page_no,
                column_ambiguous=cells.ambiguous,
            )
        )
    return out


def scan_pdf(source: Path | BinaryIO | bytes) -> tuple[ReportMeta, list[RawObservation]]:
    """Scan a whole PDF from a path, file-like object, or raw bytes.

    Parameters
    ----------
    source : Path or BinaryIO or bytes
        PDF to read.

    Returns
    -------
    tuple of (ReportMeta, list of RawObservation)
        Report metadata and every candidate result row in the document.
    """
    rows: list[RawObservation] = []
    all_lines: list[Line] = []
    fp = BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(fp) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            all_lines.extend(page_lines(page))
            rows.extend(scan_page(page, i))
    return report_meta(all_lines), rows
