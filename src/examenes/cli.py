"""Command line interface."""

from __future__ import annotations

import shutil
from pathlib import Path

import pdfplumber
import typer

from .build import build_observations
from .config import SETTINGS
from .extract import file_hash
from .manual import load_entries
from .normalize import Catalog
from .parse import scan_pdf
from .review import export_review, import_review, write_unmapped
from .store import connect, report_exists, seed_analytes, summary, write_report

app = typer.Typer(add_completion=False, help="Ingest BioNet lab PDFs into DuckDB.")
review_app = typer.Typer(help="Verification workflow.")
manual_app = typer.Typer(help="Manual entry for results that never came as a PDF.")
app.add_typer(review_app, name="review")
app.add_typer(manual_app, name="manual")


def _catalog() -> Catalog:
    """Load the analyte catalog from the configured config directory."""
    return Catalog.load(SETTINGS.config_dir)


@app.command()
def ingest(
    path: Path = typer.Argument(None, help="A PDF, or a directory of PDFs. Defaults to input/."),
    force: bool = typer.Option(False, "--force", help="Re-parse files already ingested."),
    allow_unmapped: bool = typer.Option(
        False, "--allow-unmapped", help="Continue despite unrecognised analyte names."
    ),
    archive: bool = typer.Option(True, "--archive/--no-archive", help="Copy PDFs to data/raw/."),
) -> None:
    """Parse lab PDFs and load them into DuckDB.

    Idempotent: a file already ingested is skipped unless ``--force``. Manual
    corrections and verification live in a separate table and are never lost.
    """
    SETTINGS.ensure_dirs()
    target = path or SETTINGS.input_dir
    pdfs = sorted(target.glob("*.pdf")) if target.is_dir() else [target]
    if not pdfs:
        typer.secho(f"No PDFs found in {target}", fg=typer.colors.YELLOW)
        raise typer.Exit(0)

    catalog = _catalog()
    con = connect(SETTINGS.db_path)
    seed_analytes(con, catalog)

    all_unmapped = []
    ingested = skipped = 0

    for pdf_path in pdfs:
        fhash = file_hash(pdf_path)
        if report_exists(con, fhash) and not force:
            typer.echo(f"  skip   {pdf_path.name}  (already ingested)")
            skipped += 1
            continue

        meta, rows = scan_pdf(pdf_path)
        observations, unmapped = build_observations(meta, rows, catalog, pdf_path, fhash)
        all_unmapped.extend(unmapped)

        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)

        write_report(
            con,
            file_hash=fhash,
            source_file=pdf_path.name,
            cod_lis=meta.cod_lis,
            sample_date=meta.sample_date,
            lab_name=meta.lab_name,
            page_count=page_count,
            observations=observations,
        )
        if archive:
            shutil.copy2(pdf_path, SETTINGS.raw_dir / f"{fhash}.pdf")

        ingested += 1
        typer.echo(
            f"  ok     {pdf_path.name}  {meta.sample_date}  "
            f"{len(observations)} observations"
            + (f"  {len(unmapped)} UNMAPPED" if unmapped else "")
        )

    unmapped_path = write_unmapped(all_unmapped, SETTINGS.review_dir)
    review_path, review_rows = export_review(con, SETTINGS.review_dir)
    con.close()

    typer.echo(f"\ningested {ingested}, skipped {skipped}")
    typer.echo(f"review artifact: {review_path}  ({review_rows} rows)")

    if unmapped_path is not None:
        typer.secho(
            f"\n{len(all_unmapped)} unmapped analyte name(s) -> {unmapped_path}\n"
            "Add them to config/aliases.yaml and config/analytes.yaml, then re-run.",
            fg=typer.colors.RED,
        )
        if not allow_unmapped:
            raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show what is currently stored, per report."""
    con = connect(SETTINGS.db_path)
    columns, rows = summary(con)
    con.close()
    if not rows:
        typer.echo("Nothing ingested yet.")
        return
    widths = [
        max(len(c), *(len(str(r[i])) for r in rows)) for i, c in enumerate(columns)
    ]
    typer.echo("  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)))
    typer.echo("  ".join("-" * w for w in widths))
    for row in rows:
        typer.echo("  ".join(str(v).ljust(w) for v, w in zip(row, widths, strict=True)))


@review_app.command("export")
def review_export() -> None:
    """Write a review CSV of every stored observation."""
    SETTINGS.ensure_dirs()
    con = connect(SETTINGS.db_path)
    path, rows = export_review(con, SETTINGS.review_dir)
    con.close()
    typer.echo(f"wrote {path}  ({rows} rows)")


@review_app.command("import")
def review_import(
    csv_path: Path = typer.Argument(..., help="The edited review CSV."),
) -> None:
    """Load an edited review CSV, storing verification and corrections."""
    con = connect(SETTINGS.db_path)
    written, unknown = import_review(con, csv_path)
    con.close()
    typer.echo(f"applied {written} override(s)")
    if unknown:
        typer.secho(f"{unknown} row(s) had an unknown obs_key and were ignored",
                    fg=typer.colors.YELLOW)


@manual_app.command("load")
def manual_load(
    path: Path = typer.Argument(None, help="Defaults to config/manual_entries.yaml."),
) -> None:
    """Load manually entered results from YAML."""
    SETTINGS.ensure_dirs()
    entries_path = path or (SETTINGS.config_dir / "manual_entries.yaml")
    if not entries_path.exists():
        typer.secho(f"No manual entries file at {entries_path}", fg=typer.colors.YELLOW)
        raise typer.Exit(0)

    catalog = _catalog()
    con = connect(SETTINGS.db_path)
    seed_analytes(con, catalog)

    total = 0
    for fhash, observations in load_entries(entries_path, catalog).items():
        first = observations[0]
        write_report(
            con,
            file_hash=fhash,
            source_file=entries_path.name,
            cod_lis=first.cod_lis,
            sample_date=first.sample_date,
            lab_name=first.lab_name,
            page_count=0,
            observations=observations,
        )
        total += len(observations)
        typer.echo(f"  ok     {first.sample_date}  {len(observations)} manual observations")
    con.close()
    typer.echo(f"\nloaded {total} manual observation(s)")


@app.command("export-static")
def export_static() -> None:
    """Export local database to static JSON for GitHub Pages deployment."""
    from .web.export import export_static_json

    try:
        payload = export_static_json()
        typer.secho(
            f"Successfully exported {payload['kpis']['total_observations']} observations for static deployment.",
            fg=typer.colors.GREEN,
        )
    except Exception as e:
        typer.secho(f"Export failed: {e!s}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
