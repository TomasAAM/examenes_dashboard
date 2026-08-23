"""Word-level PDF extraction with hidden-text removal.

BioNet PDFs embed layout scaffolding as *white* text: ruler digits, the literal
strings ``linea``/``line``/``123``, and stray ``x``/``X`` markers. Left in place
these silently corrupt reference ranges, e.g. ``MAGNESIO 2.18 mg/dL 1.6 - 1 2.6``
where the ``1`` between the dash and the upper bound is white scaffolding and the
true range is 1.6-2.6. Dropping non-visible words removes the whole class of
corruption deterministically, without regex guesswork over which digits are real.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

WORD_ATTRS = ["size", "fontname", "non_stroking_color"]

# Words are grouped into a line when their `top` values fall in the same bucket.
# 3pt matches the body font (8pt) closely enough to keep wrapped cells together
# without merging adjacent table rows.
LINE_TOLERANCE = 3.0


def is_hidden(color: Sequence[float] | None) -> bool:
    """Return whether a colour tuple renders as white (invisible on white paper).

    Parameters
    ----------
    color : sequence of float or None
        pdfplumber ``non_stroking_color``. Always a tuple: length 1 for
        greyscale, 3 for RGB, 4 for CMYK.

    Returns
    -------
    bool
        True when the colour is white. Unknown or missing colours are treated as
        visible, so an unrecognised colour space can never silently delete a result.

    Examples
    --------
    >>> is_hidden((1.0, 1.0, 1.0))
    True
    >>> is_hidden((0.0,))
    False
    >>> is_hidden(None)
    False
    """
    if not color:
        return False
    try:
        vals = [float(c) for c in color]
    except (TypeError, ValueError):
        return False
    if not vals:
        return False
    if len(vals) == 4:
        # CMYK: white is the absence of ink.
        return all(v <= 0.01 for v in vals)
    return all(v >= 0.99 for v in vals)


@dataclass(frozen=True)
class Word:
    """A single visible word with its position on the page."""

    text: str
    x0: float
    x1: float
    top: float

    @property
    def mid(self) -> float:
        """Horizontal midpoint, used for column assignment."""
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class Line:
    """Visible words sharing a horizontal band, ordered left to right."""

    top: float
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        """The line rendered as plain text."""
        return " ".join(w.text for w in self.words)


def file_hash(path: Path) -> str:
    """Compute the sha256 of a file, used as the ingestion idempotency key.

    Parameters
    ----------
    path : Path
        File to hash.

    Returns
    -------
    str
        Hex-encoded sha256 digest.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bytes_hash(data: bytes) -> str:
    """Compute the sha256 of raw bytes.

    Parameters
    ----------
    data : bytes
        Data to hash.

    Returns
    -------
    str
        Hex-encoded sha256 digest.
    """
    return hashlib.sha256(data).hexdigest()


def visible_words(page: pdfplumber.page.Page) -> list[Word]:
    """Extract the visible words of a page, dropping white scaffolding.

    Parameters
    ----------
    page : pdfplumber.page.Page
        Page to read.

    Returns
    -------
    list of Word
        Visible words, unordered.
    """
    raw = page.extract_words(extra_attrs=WORD_ATTRS)
    return [
        Word(text=w["text"], x0=float(w["x0"]), x1=float(w["x1"]), top=float(w["top"]))
        for w in raw
        if not is_hidden(w.get("non_stroking_color"))
    ]


def hidden_words(page: pdfplumber.page.Page) -> list[str]:
    """Return the text of words dropped as hidden, for auditing the filter.

    Parameters
    ----------
    page : pdfplumber.page.Page
        Page to read.

    Returns
    -------
    list of str
        Text of every word the visibility filter removed.
    """
    return [
        w["text"]
        for w in page.extract_words(extra_attrs=WORD_ATTRS)
        if is_hidden(w.get("non_stroking_color"))
    ]


def group_lines(words: Iterable[Word], tolerance: float = LINE_TOLERANCE) -> list[Line]:
    """Group words into horizontal lines, ordered top to bottom.

    Parameters
    ----------
    words : iterable of Word
        Words to group.
    tolerance : float, optional
        Vertical bucket size in points.

    Returns
    -------
    list of Line
        Lines ordered by vertical position, words within each ordered by x0.
    """
    buckets: dict[int, list[Word]] = {}
    for w in words:
        buckets.setdefault(round(w.top / tolerance), []).append(w)
    lines = []
    for key in sorted(buckets):
        row = sorted(buckets[key], key=lambda w: w.x0)
        lines.append(Line(top=key * tolerance, words=tuple(row)))
    return lines


def page_lines(page: pdfplumber.page.Page) -> list[Line]:
    """Extract a page as visible, de-noised lines.

    Parameters
    ----------
    page : pdfplumber.page.Page
        Page to read.

    Returns
    -------
    list of Line
        Ordered lines of visible words.
    """
    return group_lines(visible_words(page))
