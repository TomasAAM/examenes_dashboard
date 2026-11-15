"""Panel, sub-section and report-metadata detection for BioNet pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .extract import Line

SEPARATOR = re.compile(r"^_{20,}$")

# Everything below these markers on a page is interpretive prose, morphology
# narrative or the page footer -- never results.
STOP_MARKERS = (
    "GUIA PARA",
    "CARACTERISTICAS MORFOLOGICAS",
    "EJECUTADO Y EMITIDO POR:",
    "VALOR DE REFERENCIA:",
    # The FIB-4 interpretation table. It must stop the scan, but only *after*
    # `INDICE FIB 4`, which is a genuine result printed just above it.
    "PUNTAJE INDICE FIB",
    "LOS RESULTADOS DE LOS EXÁMENES",
    "LABORATORIO ADSCRITO",
    "* = RESULTADO FUERA",
)

# Lines to ignore without ending the table. `Nota :` annotations are interleaved
# between real results on PERFIL HEPATICO, so they cannot be stop markers.
SKIP_PREFIXES = ("Nota", "RESULTADO", "Bibliografía", "Valores de referencia")

# A `Nota` can wrap onto further lines of prose, which split into cells like a
# result row would. Those continuation lines are skipped until a line whose
# value cell starts with a number, which is how every real result in the
# note-bearing panels begins.
NOTE_PREFIX = "Nota"
_VALUE_START = re.compile(r"^[:*<>≤≥\s]*[-+]?\d")

# `Método` is context-dependent: on a titled panel it introduces the
# interpretation guide and ends the table, but on the untitled stacked-metric
# pages it merely separates one single-metric block from the next.
METHOD = re.compile(r"^Método\s*:\s*(.+)$")

SUB_SECTIONS = {
    "EXAMEN FÍSICO": "fisico",
    "EXAMEN QUÍMICO": "quimico",
    "ANÁLISIS ELEMENTOS FIGURADOS": "elementos_figurados",
}

_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
_TOMA = re.compile(r"Toma Muestra\s*:\s*(\d{1,2}/\d{1,2}/\d{2,4})")
_CODLIS = re.compile(r"Cod\.Lis\s*:\s*(\S+)")
_SUCURSAL = re.compile(r"Sucursal\s*:\s*(.+?)\s*(?:F\.Nac|$)")
_MUESTRA = re.compile(r"(?:Tipo de muestra|Muestra)\s*:\s*([A-Za-zÁÉÍÓÚÑáéíóúñ/, ]+)")


def parse_chilean_date(text: str) -> date | None:
    """Parse a Chilean D/M/YY (or D/M/YYYY) date.

    Chilean reports use day-first ordering. This is not assumed from locale: it
    is confirmed per report by cross-checking the printed ``Edad`` against
    ``F.Nac``. For a patient born ``15/03/1985``, a report dated ``4/2/24``
    showing age 38 can only be 4 February 2024, since reading it as 2 April 2024
    would make them 39. Both sample sets used to build this parser resolve the
    same way.

    Parameters
    ----------
    text : str
        Text containing a date.

    Returns
    -------
    date or None
        Parsed date, or None when no date is present or the fields are invalid.

    Examples
    --------
    >>> parse_chilean_date("Toma Muestra : 4/2/24 8:11")
    datetime.date(2024, 2, 4)
    """
    m = _DATE.search(text)
    if not m:
        return None
    day, month, year = (int(g) for g in m.groups())
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return date(year, month, day)
    except ValueError:
        return None


@dataclass(frozen=True)
class ReportMeta:
    """Report-level metadata, identical on every page of a report."""

    sample_date: date | None
    cod_lis: str | None
    lab_name: str | None


def report_meta(all_lines: list[Line]) -> ReportMeta:
    """Extract report-level metadata from every line of a document.

    Parameters
    ----------
    all_lines : list of Line
        Lines from all pages of one PDF.

    Returns
    -------
    ReportMeta
        Sample date, Cod.Lis and lab name where found.
    """
    sample_date = cod_lis = lab = None
    for line in all_lines:
        t = line.text
        if sample_date is None and (m := _TOMA.search(t)):
            sample_date = parse_chilean_date(m.group(1))
        if cod_lis is None and (m := _CODLIS.search(t)):
            cod_lis = m.group(1)
        if lab is None and (m := _SUCURSAL.search(t)):
            lab = m.group(1).strip()
    return ReportMeta(sample_date=sample_date, cod_lis=cod_lis, lab_name=lab)


def panel_title(lines: list[Line]) -> str | None:
    """Detect a page's panel title.

    The title sits between the first horizontal rule and the ``Toma Muestra``
    line. Pages carrying stacked single-metric blocks have nothing there.

    Parameters
    ----------
    lines : list of Line
        De-noised lines of a page.

    Returns
    -------
    str or None
        Panel title with trailing punctuation stripped, or None when untitled.
    """
    sep_idx = next((i for i, ln in enumerate(lines) if SEPARATOR.match(ln.text.strip())), None)
    toma_idx = next((i for i, ln in enumerate(lines) if "Toma Muestra" in ln.text), None)
    if sep_idx is None or toma_idx is None or toma_idx <= sep_idx:
        return None
    for ln in lines[sep_idx + 1 : toma_idx]:
        candidate = ln.text.strip().rstrip(".").strip()
        if len(candidate) > 3 and not SEPARATOR.match(candidate) and candidate.upper() == candidate:
            return candidate
    return None


def sample_type(lines: list[Line]) -> str | None:
    """Extract the specimen type declared on a page.

    Parameters
    ----------
    lines : list of Line
        De-noised lines of a page.

    Returns
    -------
    str or None
        Specimen type, e.g. ``Suero`` or ``Sangre / EDTA``.
    """
    for ln in lines:
        if (m := _MUESTRA.search(ln.text)) and "Toma" not in m.group(1):
            return m.group(1).strip() or None
    return None


def method_lines(lines: list[Line]) -> list[tuple[float, str]]:
    """Return every ``Método:`` declaration on a page with its vertical position.

    Parameters
    ----------
    lines : list of Line
        De-noised lines of a page.

    Returns
    -------
    list of (float, str)
        ``(top, method_text)`` pairs in reading order.
    """
    out = []
    for ln in lines:
        if m := METHOD.match(ln.text.strip()):
            out.append((ln.top, m.group(1).strip().rstrip(".")))
    return out


def is_stop(text: str) -> bool:
    """Return whether a line ends the result table.

    Parameters
    ----------
    text : str
        Line text.

    Returns
    -------
    bool
        True when the line is a stop marker.
    """
    upper = text.strip().upper()
    return any(m in upper for m in STOP_MARKERS)


def is_skippable(text: str) -> bool:
    """Return whether a line should be ignored without ending the table.

    Parameters
    ----------
    text : str
        Line text.

    Returns
    -------
    bool
        True for interleaved annotations and repeated column headings.
    """
    return text.strip().startswith(SKIP_PREFIXES)


def is_note_start(text: str) -> bool:
    """Return whether a line opens a ``Nota`` annotation.

    Parameters
    ----------
    text : str
        Line text.

    Returns
    -------
    bool
        True when the line starts with ``Nota``.
    """
    return text.strip().startswith(NOTE_PREFIX)


def starts_with_value(cell: str | None) -> bool:
    """Return whether a value cell begins with a number.

    Used to tell a real result apart from a wrapped ``Nota`` continuation line.

    Parameters
    ----------
    cell : str or None
        Value or absolute cell text.

    Returns
    -------
    bool
        True for cells such as ``28.0``, ``* 1.17``, ``< 0.5`` or ``: 0.44``.

    Examples
    --------
    >>> starts_with_value("* 1.17")
    True
    >>> starts_with_value("en reemplazo")
    False
    """
    return bool(cell) and bool(_VALUE_START.match(cell.strip()))


def sub_section_of(text: str) -> str | None:
    """Map an ORINA sub-section heading to its code.

    Disambiguates the three distinct ``LEUCOCITOS`` analytes: urine chemistry
    (qualitative), urine microscopy (a count range) and the haemogram count.

    Parameters
    ----------
    text : str
        Line text.

    Returns
    -------
    str or None
        Sub-section code, or None when the line is not a heading.
    """
    stripped = text.strip().rstrip(":").strip()
    return SUB_SECTIONS.get(stripped.upper())
