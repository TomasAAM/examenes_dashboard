"""Header-anchored column geometry for BioNet result tables.

Results are laid out in fixed columns whose x positions are declared by the
table header (``RESULTADO`` / ``UNIDAD`` / ``VALOR DE REFERENCIA``). Assigning
words to cells by x position -- rather than splitting a flattened line with a
regex -- is what makes the genuinely ambiguous rows tractable:

* ``CELULAS EPITELIALES  Muy escasas | Escasa Cantidad`` -- a multi-word value
  followed by a multi-word reference, with no delimiter between them.
* ``Segmentados  NN | NNNN | uL | 50 - 75`` -- the haemogram differential, whose
  percentage and absolute count are two distinct numbers on one row.
* Reference cells with irregular dash spacing (``50 - 200``, ``15-85``,
  ``1.015- 1.025``) become a single cell parsed as a unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from .extract import Line, Word

# A word starting this far left of the RESULTADO anchor belongs to the analyte
# name. Needed because long names (`R.A.N. (Recuento absoluto de neutrofilos)`)
# extend well past the midpoint between the name and result columns.
NAME_MARGIN = 20.0

# Sub-header marking the haemogram differential, which introduces an extra
# "absolute count" column between the result and unit columns.
ABS_HEADER_TOKENS = ("RCTO.", "ABSOLUTO")


@dataclass(frozen=True)
class ColumnLayout:
    """Column anchor positions for one page's result table."""

    value_x: float
    ref_x: float | None = None
    unit_x: float | None = None
    abs_x: float | None = None

    @property
    def name_cutoff(self) -> float:
        """Words starting left of this x belong to the analyte name."""
        return self.value_x - NAME_MARGIN

    def _anchors(self) -> list[tuple[str, float]]:
        """Ordered (column, x) anchors for everything right of the name."""
        out = [("value", self.value_x)]
        if self.abs_x is not None:
            out.append(("abs", self.abs_x))
        if self.unit_x is not None:
            out.append(("unit", self.unit_x))
        if self.ref_x is not None:
            out.append(("ref", self.ref_x))
        return sorted(out, key=lambda a: a[1])

    def column_of(self, word: Word) -> str:
        """Assign a word to a column.

        Parameters
        ----------
        word : Word
            Word to place.

        Returns
        -------
        str
            One of ``name``, ``value``, ``abs``, ``unit``, ``ref``.
        """
        if word.x0 < self.name_cutoff:
            return "name"
        anchors = self._anchors()
        chosen = anchors[0][0]
        for (_, x_lo), (name_hi, x_hi) in pairwise(anchors):
            if word.x0 >= (x_lo + x_hi) / 2:
                chosen = name_hi
        return chosen

    def is_ambiguous(self, word: Word) -> bool:
        """Return whether a word sits close enough to a boundary to be doubtful.

        Parameters
        ----------
        word : Word
            Word to test.

        Returns
        -------
        bool
            True when the word starts within 4pt of a column boundary.
        """
        anchors = self._anchors()
        bounds = [self.name_cutoff] + [(a[1] + b[1]) / 2 for a, b in pairwise(anchors)]
        return any(abs(word.x0 - b) < 4.0 for b in bounds)


@dataclass(frozen=True)
class Cells:
    """One table row split into its columns."""

    name: str
    value: str
    absolute: str
    unit: str
    ref: str
    ambiguous: bool


def detect_layout(lines: list[Line]) -> ColumnLayout | None:
    """Infer column anchors from a page's table header.

    The header is the line containing ``RESULTADO``. ``UNIDAD`` and the
    reference heading may appear on that same line or, for the reference, be
    split across two lines as ``VALOR DE`` / ``REFERENCIA``.

    Parameters
    ----------
    lines : list of Line
        De-noised lines of a page, in reading order.

    Returns
    -------
    ColumnLayout or None
        Layout, or None when the page has no result table.
    """
    header = None
    for line in lines:
        if any(w.text == "RESULTADO" for w in line.words):
            header = line
            break
    if header is None:
        return None

    by_text = {w.text: w for w in header.words}
    value_x = by_text["RESULTADO"].x0
    unit_x = by_text["UNIDAD"].x0 if "UNIDAD" in by_text else None

    # The reference heading is "VALOR DE REFERENCIA", but the leading words may
    # sit on the line above, so anchor on whichever part appears furthest left
    # while still being right of the unit column. FOLATO SERICO has no reference
    # heading at all -- its range is categorical and printed below the table.
    ref_parts = [
        w.x0
        for w in header.words
        if w.text in {"VALOR", "DE", "REFERENCIA"} and (unit_x is None or w.x0 > unit_x)
    ]
    ref_x = min(ref_parts) if ref_parts else None

    # The differential sub-header appears lower on the page and adds a column.
    abs_x = None
    for line in lines:
        texts = [w.text for w in line.words]
        if all(t in texts for t in ABS_HEADER_TOKENS):
            abs_x = min(w.x0 for w in line.words if w.text in ABS_HEADER_TOKENS)
            break

    return ColumnLayout(value_x=value_x, ref_x=ref_x, unit_x=unit_x, abs_x=abs_x)


def split_row(line: Line, layout: ColumnLayout) -> Cells:
    """Split one line into column cells.

    Parameters
    ----------
    line : Line
        Line to split.
    layout : ColumnLayout
        Column anchors for the page.

    Returns
    -------
    Cells
        Joined text per column, plus a boundary-ambiguity flag.
    """
    buckets: dict[str, list[str]] = {k: [] for k in ("name", "value", "abs", "unit", "ref")}
    ambiguous = False
    for w in line.words:
        buckets[layout.column_of(w)].append(w.text)
        if layout.is_ambiguous(w):
            ambiguous = True
    return Cells(
        name=" ".join(buckets["name"]).strip(),
        value=" ".join(buckets["value"]).strip(),
        absolute=" ".join(buckets["abs"]).strip(),
        unit=" ".join(buckets["unit"]).strip(),
        ref=" ".join(buckets["ref"]).strip(),
        ambiguous=ambiguous,
    )
