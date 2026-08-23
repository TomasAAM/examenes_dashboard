"""DuckDB persistence.

The store separates machine-derived data from human judgement:

``observations``
    Purely derived from the PDFs. Wiped and rebuilt for a file whenever it is
    re-ingested, so it can always be regenerated from source.
``overrides``
    Written only by a human, through the review loop. Never touched by ingest.
    This is what makes ``verified`` and manual corrections survive re-parsing.

``v_observations`` joins the two, so downstream readers see corrected,
verification-aware rows without needing to know the mechanism.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import duckdb

from .build import Observation
from .normalize import Catalog

OBSERVATION_COLUMNS = [
    "obs_key", "sample_date", "lab_name", "panel", "sub_section",
    "analyte_code", "analyte_name_raw", "value_num", "value_text",
    "unit", "unit_raw", "ref_low", "ref_high", "ref_operator", "ref_text",
    "method", "out_of_range", "asterisk_flag", "source_file", "source_page",
    "file_hash", "cod_lis", "source", "extracted_at", "verified",
    "confidence", "flags", "also_in_panels",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    file_hash    TEXT PRIMARY KEY,
    source_file  TEXT NOT NULL,
    cod_lis      TEXT,
    sample_date  DATE,
    lab_name     TEXT,
    page_count   INTEGER,
    ingested_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS analytes (
    analyte_code   TEXT PRIMARY KEY,
    display_name_es TEXT NOT NULL,
    display_name_en TEXT NOT NULL,
    category        TEXT NOT NULL,
    canonical_unit  TEXT,
    concerning_direction TEXT NOT NULL
);

-- Derived from the PDFs. Safe to delete and rebuild at any time.
CREATE TABLE IF NOT EXISTS observations (
    obs_key          TEXT PRIMARY KEY,
    sample_date      DATE,
    lab_name         TEXT,
    panel            TEXT,
    sub_section      TEXT,
    analyte_code     TEXT NOT NULL,
    analyte_name_raw TEXT NOT NULL,
    value_num        DOUBLE,
    value_text       TEXT,
    unit             TEXT,
    unit_raw         TEXT,
    ref_low          DOUBLE,
    ref_high         DOUBLE,
    ref_operator     TEXT,
    ref_text         TEXT,
    method           TEXT,
    out_of_range     BOOLEAN,
    asterisk_flag    BOOLEAN,
    source_file      TEXT,
    source_page      INTEGER,
    file_hash        TEXT NOT NULL,
    cod_lis          TEXT,
    source           TEXT NOT NULL,
    extracted_at     TIMESTAMP,
    verified         BOOLEAN,
    confidence       TEXT,
    flags            TEXT,
    also_in_panels   TEXT
);

-- Human layer. Never written by ingest.
CREATE TABLE IF NOT EXISTS overrides (
    obs_key    TEXT PRIMARY KEY,
    verified   BOOLEAN,
    value_num  DOUBLE,
    value_text TEXT,
    note       TEXT,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_obs_analyte_date ON observations (analyte_code, sample_date);
CREATE INDEX IF NOT EXISTS idx_obs_file ON observations (file_hash);
"""

VIEW = """
CREATE OR REPLACE VIEW v_observations AS
SELECT
    o.* REPLACE (
        COALESCE(ov.value_num,  o.value_num)  AS value_num,
        COALESCE(ov.value_text, o.value_text) AS value_text,
        COALESCE(ov.verified,   o.verified)   AS verified
    ),
    ov.note                            AS review_note,
    (ov.obs_key IS NOT NULL)           AS has_override
FROM observations o
LEFT JOIN overrides ov USING (obs_key);
"""


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Open the database, creating the schema when absent.

    Parameters
    ----------
    db_path : Path
        Path to the DuckDB file.

    Returns
    -------
    duckdb.DuckDBPyConnection
        Open connection with schema and view in place.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA)
    con.execute(VIEW)
    return con


def seed_analytes(con: duckdb.DuckDBPyConnection, catalog: Catalog) -> int:
    """Load the analyte dimension from the catalog, replacing existing rows.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open connection.
    catalog : Catalog
        Loaded configuration.

    Returns
    -------
    int
        Number of analytes written.
    """
    rows = [
        (a.code, a.display_es, a.display_en, a.category, a.canonical_unit, a.direction)
        for a in catalog.analytes.values()
    ]
    con.execute("DELETE FROM analytes")
    con.executemany("INSERT INTO analytes VALUES (?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def report_exists(con: duckdb.DuckDBPyConnection, file_hash: str) -> bool:
    """Return whether a file hash has already been ingested.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open connection.
    file_hash : str
        sha256 of the source file.

    Returns
    -------
    bool
        True when the report is already present.
    """
    row = con.execute(
        "SELECT 1 FROM reports WHERE file_hash = ?", [file_hash]
    ).fetchone()
    return row is not None


def _observation_rows(observations: list[Observation]) -> list[tuple[Any, ...]]:
    """Flatten observations into tuples matching the table column order."""
    return [tuple(asdict(o)[c] for c in OBSERVATION_COLUMNS) for o in observations]


def write_report(
    con: duckdb.DuckDBPyConnection,
    *,
    file_hash: str,
    source_file: str,
    cod_lis: str | None,
    sample_date,
    lab_name: str | None,
    page_count: int,
    observations: list[Observation],
) -> int:
    """Persist one report and its observations, replacing any previous ingest.

    Overrides are untouched, so verification and manual corrections survive.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open connection.
    file_hash : str
        sha256 of the source file, the idempotency key.
    source_file : str
        Original file name.
    cod_lis : str or None
        BioNet's per-report identifier.
    sample_date : datetime.date or None
        Draw date.
    lab_name : str or None
        Issuing laboratory.
    page_count : int
        Pages in the PDF.
    observations : list of Observation
        Parsed observations for this report.

    Returns
    -------
    int
        Number of observations written.
    """
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DELETE FROM observations WHERE file_hash = ?", [file_hash])
        con.execute("DELETE FROM reports WHERE file_hash = ?", [file_hash])
        con.execute(
            """
            INSERT INTO reports
                (file_hash, source_file, cod_lis, sample_date, lab_name, page_count, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, now())
            """,
            [file_hash, source_file, cod_lis, sample_date, lab_name, page_count],
        )
        if observations:
            placeholders = ", ".join(["?"] * len(OBSERVATION_COLUMNS))
            con.executemany(
                f"INSERT INTO observations VALUES ({placeholders})",
                _observation_rows(observations),
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(observations)


def apply_overrides(con: duckdb.DuckDBPyConnection, rows: Sequence[tuple[Any, ...]]) -> int:
    """Upsert human review decisions.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open connection.
    rows : sequence of tuple
        ``(obs_key, verified, value_num, value_text, note)`` per row.

    Returns
    -------
    int
        Number of override rows written.
    """
    if not rows:
        return 0
    con.executemany(
        """
        INSERT INTO overrides (obs_key, verified, value_num, value_text, note, updated_at)
        VALUES (?, ?, ?, ?, ?, now())
        ON CONFLICT (obs_key) DO UPDATE SET
            verified   = EXCLUDED.verified,
            value_num  = EXCLUDED.value_num,
            value_text = EXCLUDED.value_text,
            note       = EXCLUDED.note,
            updated_at = EXCLUDED.updated_at
        """,
        list(rows),
    )
    return len(rows)


def summary(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[tuple[Any, ...]]]:
    """Return a per-report summary of what is stored.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open connection.

    Returns
    -------
    tuple of (list of str, list of tuple)
        Column names and one row per report, with counts by confidence and
        verification state.
    """
    cur = con.execute(
        """
        SELECT
            r.sample_date,
            r.source_file,
            r.cod_lis,
            COUNT(*)                                        AS observations,
            SUM(CASE WHEN v.confidence = 'ok' THEN 1 ELSE 0 END)      AS ok,
            SUM(CASE WHEN v.confidence = 'check' THEN 1 ELSE 0 END)   AS check_,
            SUM(CASE WHEN v.confidence = 'suspect' THEN 1 ELSE 0 END) AS suspect,
            SUM(CASE WHEN v.verified THEN 1 ELSE 0 END)               AS verified
        FROM reports r
        JOIN v_observations v USING (file_hash)
        GROUP BY 1, 2, 3
        ORDER BY r.sample_date
        """
    )
    return [d[0] for d in cur.description], cur.fetchall()
