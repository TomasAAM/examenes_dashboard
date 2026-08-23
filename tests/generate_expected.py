"""Generate the golden snapshot the end-to-end tests assert against.

    python tests/generate_expected.py

The snapshot records real result values, so it is gitignored. It is what lets
the test suite be a regression net without committing health data.

READ THIS BEFORE REGENERATING
-----------------------------
The snapshot is *golden*: it captures parser output at a moment the output was
known to be correct. Regenerating it makes the tests agree with whatever the
parser currently does, which will happily bless a regression.

Only regenerate when either:

* you have re-checked the affected values against the source PDFs by eye, or
* you added new source PDFs and the existing entries are unchanged.

The script refuses to overwrite an existing snapshot unless `--force` is given,
and prints a diff of what would change so a regression is visible rather than
silently absorbed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conftest import (
    CONFIG_DIR,
    EXPECTED_PATH,
    INPUT_DIR,
    observation_id,
    snapshot_of,
)

from examenes.build import build_observations
from examenes.extract import file_hash
from examenes.normalize import Catalog
from examenes.parse import scan_pdf


def build_snapshot() -> dict:
    """Parse every PDF and collect the fields the tests assert on."""
    catalog = Catalog.load(CONFIG_DIR)
    observations = []
    for pdf in sorted(INPUT_DIR.glob("*.pdf")):
        meta, rows = scan_pdf(pdf)
        obs, unmapped = build_observations(meta, rows, catalog, pdf, file_hash(pdf))
        if unmapped:
            names = sorted({u.name_raw for u in unmapped})
            raise SystemExit(
                f"refusing to snapshot: {pdf.name} has unmapped analytes {names}. "
                "Map them in config/aliases.yaml first."
            )
        observations.extend(obs)

    if not observations:
        raise SystemExit(f"no observations parsed from {INPUT_DIR}")

    return {
        "_comment": (
            "Golden snapshot of parser output. Contains real result values -- "
            "gitignored. Regenerate only after verifying against the PDFs."
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "draws": sorted({str(o.sample_date) for o in observations}),
        "observations": {observation_id(o): snapshot_of(o) for o in observations},
    }


def diff(old: dict, new: dict) -> list[str]:
    """Describe how a new snapshot differs from the stored one."""
    old_obs, new_obs = old.get("observations", {}), new["observations"]
    lines = []
    for key in sorted(set(old_obs) - set(new_obs)):
        lines.append(f"  REMOVED  {key}")
    for key in sorted(set(new_obs) - set(old_obs)):
        lines.append(f"  ADDED    {key}")
    for key in sorted(set(old_obs) & set(new_obs)):
        if old_obs[key] != new_obs[key]:
            changes = [
                f"{f}: {old_obs[key].get(f)!r} -> {new_obs[key].get(f)!r}"
                for f in new_obs[key]
                if old_obs[key].get(f) != new_obs[key].get(f)
            ]
            lines.append(f"  CHANGED  {key}  ({'; '.join(changes)})")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="overwrite an existing snapshot"
    )
    args = parser.parse_args()

    snapshot = build_snapshot()

    if EXPECTED_PATH.exists():
        existing = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        changes = diff(existing, snapshot)
        if not changes:
            print(f"snapshot unchanged ({len(snapshot['observations'])} observations)")
            return 0
        print(f"{len(changes)} difference(s) against the stored snapshot:\n")
        print("\n".join(changes[:60]))
        if len(changes) > 60:
            print(f"  ... and {len(changes) - 60} more")
        if not args.force:
            print(
                "\nRefusing to overwrite. If every change above is correct "
                "against the PDFs, re-run with --force."
            )
            return 1

    EXPECTED_PATH.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {EXPECTED_PATH.name}: "
        f"{len(snapshot['observations'])} observations across {len(snapshot['draws'])} draws"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
