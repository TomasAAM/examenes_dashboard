"""Shared fixtures for the end-to-end tests.

Real result values and draw dates are health data, so they are not committed.
They live in a gitignored golden snapshot, `tests/expected_values.json`, which
the tests load. See `tests/generate_expected.py` for how to create it.

Tests that need the snapshot skip cleanly when it is absent, exactly as the
end-to-end tests already skip without the source PDFs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from examenes.build import build_observations
from examenes.extract import file_hash
from examenes.normalize import Catalog
from examenes.parse import scan_pdf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "input"
CONFIG_DIR = PROJECT_ROOT / "config"
EXPECTED_PATH = Path(__file__).resolve().parent / "expected_values.json"

# Fields captured per observation in the golden snapshot.
SNAPSHOT_FIELDS = (
    "value_num", "value_text", "unit", "ref_low", "ref_high",
    "ref_operator", "out_of_range", "asterisk_flag", "confidence", "flags",
)


def observation_id(observation) -> str:
    """Build the snapshot key for an observation."""
    return f"{observation.analyte_code}@{observation.sample_date}"


def snapshot_of(observation) -> dict[str, Any]:
    """Extract the snapshot fields from an observation."""
    return {f: getattr(observation, f) for f in SNAPSHOT_FIELDS}


@dataclass(frozen=True)
class Expected:
    """Golden values loaded from the gitignored snapshot."""

    draws: tuple[str, ...]
    observations: dict[str, dict[str, Any]]

    @property
    def latest(self) -> str:
        """The most recent draw date, as an ISO string."""
        return self.draws[-1]

    def get(self, code: str, draw: str) -> dict[str, Any]:
        """Return the recorded snapshot for one analyte on one draw."""
        key = f"{code}@{draw}"
        if key not in self.observations:
            pytest.fail(f"{key} is absent from the golden snapshot")
        return self.observations[key]

    def num(self, code: str, draw: str) -> float | None:
        """Recorded numeric value."""
        return self.get(code, draw)["value_num"]

    def text(self, code: str, draw: str) -> str | None:
        """Recorded text value."""
        return self.get(code, draw)["value_text"]


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    """The analyte catalog, loaded once."""
    return Catalog.load(CONFIG_DIR)


@pytest.fixture(scope="session")
def parsed(catalog):
    """Parse every available PDF once.

    Returns
    -------
    tuple of (list of Observation, list of Unmapped)
    """
    if not list(INPUT_DIR.glob("*.pdf")):
        pytest.skip("no source PDFs available")
    observations, unmapped = [], []
    for pdf in sorted(INPUT_DIR.glob("*.pdf")):
        meta, rows = scan_pdf(pdf)
        obs, un = build_observations(meta, rows, catalog, pdf, file_hash(pdf))
        observations.extend(obs)
        unmapped.extend(un)
    return observations, unmapped


@pytest.fixture(scope="session")
def by_code(parsed):
    """Parsed observations indexed by analyte code."""
    index: dict[str, list] = {}
    for o in parsed[0]:
        index.setdefault(o.analyte_code, []).append(o)
    return index


@pytest.fixture(scope="session")
def expected() -> Expected:
    """Golden values from the gitignored snapshot."""
    if not EXPECTED_PATH.exists():
        pytest.skip(
            f"no golden snapshot at {EXPECTED_PATH.name}; "
            "run `python tests/generate_expected.py` to create it"
        )
    doc = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    return Expected(draws=tuple(doc["draws"]), observations=doc["observations"])


def observation_on(by_code, code: str, draw: str):
    """Fetch the single parsed observation for an analyte on a given draw."""
    matches = [o for o in by_code.get(code, []) if str(o.sample_date) == draw]
    assert matches, f"no {code} on {draw}"
    return matches[0]
