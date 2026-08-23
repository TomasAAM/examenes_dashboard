"""Manual entry for results that never arrived as a PDF."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from .build import Observation, obs_key
from .normalize import Catalog, compute_out_of_range, parse_reference

MANUAL_LAB_DEFAULT = "manual entry"


def synthetic_hash(sample_date: date, lab_name: str) -> str:
    """Build a stable pseudo file hash for a manually entered draw.

    Manual entries have no source file, but the store keys reports on a hash.
    Deriving it from the draw identity keeps re-loading the same YAML idempotent.

    Parameters
    ----------
    sample_date : date
        Draw date.
    lab_name : str
        Issuing laboratory.

    Returns
    -------
    str
        Hex-encoded sha256 digest.
    """
    return hashlib.sha256(f"manual|{sample_date.isoformat()}|{lab_name}".encode()).hexdigest()


def load_entries(path: Path, catalog: Catalog) -> dict[str, list[Observation]]:
    """Load manual results, grouped into synthetic reports by draw.

    Parameters
    ----------
    path : Path
        YAML file of manual entries.
    catalog : Catalog
        Loaded configuration, used to validate analyte codes.

    Returns
    -------
    dict of str to list of Observation
        Observations keyed by synthetic file hash.

    Raises
    ------
    ValueError
        If an entry names an analyte code that is not in the catalog, or omits
        a required field.
    """
    doc = yaml.safe_load(path.read_text("utf-8")) or {}
    entries = doc.get("entries") or []
    extracted_at = datetime.now(UTC)
    grouped: dict[str, list[Observation]] = {}

    for i, entry in enumerate(entries, start=1):
        for field in ("sample_date", "analyte_code"):
            if entry.get(field) in (None, ""):
                raise ValueError(f"manual entry #{i}: missing required field '{field}'")

        code = entry["analyte_code"]
        if code not in catalog.analytes:
            raise ValueError(
                f"manual entry #{i}: unknown analyte_code {code!r}. "
                "Add it to config/analytes.yaml first."
            )

        sample_date = entry["sample_date"]
        if isinstance(sample_date, str):
            sample_date = date.fromisoformat(sample_date)
        lab_name = entry.get("lab_name") or MANUAL_LAB_DEFAULT
        fhash = synthetic_hash(sample_date, lab_name)

        ref = parse_reference(str(entry.get("ref_text") or ""))
        ref_low = entry.get("ref_low", ref.ref_low)
        ref_high = entry.get("ref_high", ref.ref_high)
        operator = "range" if (ref_low is not None and ref_high is not None) else ref.ref_operator

        value_num = entry.get("value_num")
        rebuilt = parse_reference("")
        if ref_low is not None or ref_high is not None:
            rebuilt = type(ref)(ref_low, ref_high, operator, entry.get("ref_text"), ())

        analyte = catalog.analytes[code]
        grouped.setdefault(fhash, []).append(
            Observation(
                obs_key=obs_key(fhash, code),
                sample_date=sample_date,
                lab_name=lab_name,
                panel=entry.get("panel"),
                sub_section=entry.get("sub_section"),
                analyte_code=code,
                analyte_name_raw=entry.get("analyte_name_raw") or analyte.display_es,
                value_num=float(value_num) if value_num is not None else None,
                value_text=entry.get("value_text"),
                unit=entry.get("unit") or analyte.canonical_unit,
                unit_raw=entry.get("unit"),
                ref_low=ref_low,
                ref_high=ref_high,
                ref_operator=operator,
                ref_text=entry.get("ref_text"),
                method=entry.get("method"),
                out_of_range=compute_out_of_range(
                    float(value_num) if value_num is not None else None, rebuilt
                ),
                asterisk_flag=False,
                source_file=path.name,
                source_page=0,
                file_hash=fhash,
                cod_lis=entry.get("cod_lis"),
                source="manual",
                extracted_at=extracted_at,
                # Typed in by hand from the paper report, so already eyeballed.
                verified=True,
                confidence="ok",
                flags="",
                also_in_panels=None,
            )
        )
    return grouped
