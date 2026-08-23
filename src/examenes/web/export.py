"""Export DuckDB observations to static JSON for GitHub Pages deployment."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import SETTINGS
from ..store import connect
from .api import serialize_dataset


def export_static_json(output_paths: list[Path] | None = None) -> dict:
    """Read local data/labs.duckdb and write serialized JSON to output paths.

    Parameters
    ----------
    output_paths : list of Path, optional
        Paths to write data.json to. Defaults to frontend/public/data.json
        and src/examenes/web/static/data.json.

    Returns
    -------
    dict
        The serialized dataset payload.
    """
    db_path = SETTINGS.db_path
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database '{db_path}' does not exist. Run ingest first: python -m examenes.cli ingest"
        )

    con = connect(db_path)
    payload = serialize_dataset(con)
    con.close()

    if output_paths is None:
        root_dir = Path(__file__).resolve().parent.parent.parent.parent
        output_paths = [
            root_dir / "frontend" / "public" / "data.json",
            root_dir / "src" / "examenes" / "web" / "static" / "data.json",
        ]

    for out_path in output_paths:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"[*] Exported static data ({payload['kpis']['total_observations']} observations) -> {out_path}")

    return payload


def main() -> None:
    """CLI entry point for static JSON export."""
    export_static_json()


if __name__ == "__main__":
    main()
