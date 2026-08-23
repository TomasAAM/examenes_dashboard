"""FastAPI backend endpoints for the examenes web application."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import duckdb
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..build import Unmapped, build_observations
from ..config import SETTINGS
from ..extract import bytes_hash
from ..normalize import Catalog
from ..parse import scan_pdf
from ..store import SCHEMA, VIEW, connect, seed_analytes, write_report


def get_catalog() -> Catalog:
    """Load configuration catalog."""
    return Catalog.load(SETTINGS.config_dir)


def serialize_dataset(
    con: duckdb.DuckDBPyConnection,
    unmapped_items: list[Unmapped] | None = None,
) -> dict[str, Any]:
    """Serialize DuckDB tables and views into frontend-friendly JSON structure."""
    draws_cur = con.execute(
        """
        SELECT
            sample_date::TEXT AS sample_date,
            source_file,
            cod_lis,
            lab_name,
            page_count
        FROM reports
        ORDER BY sample_date ASC
        """
    )
    draw_cols = [c[0] for c in draws_cur.description]
    draws = [dict(zip(draw_cols, row, strict=False)) for row in draws_cur.fetchall()]

    obs_cur = con.execute(
        """
        SELECT
            v.obs_key,
            v.sample_date::TEXT AS sample_date,
            v.lab_name,
            v.panel,
            v.sub_section,
            v.analyte_code,
            COALESCE(a.display_name_es, v.analyte_name_raw) AS display_name_es,
            COALESCE(a.display_name_en, v.analyte_name_raw) AS display_name_en,
            COALESCE(a.category, 'Otros') AS category,
            a.canonical_unit,
            COALESCE(a.concerning_direction, 'both') AS concerning_direction,
            v.analyte_name_raw,
            v.value_num,
            v.value_text,
            v.unit,
            v.unit_raw,
            v.ref_low,
            v.ref_high,
            v.ref_operator,
            v.ref_text,
            v.method,
            v.out_of_range,
            v.asterisk_flag,
            v.source_file,
            v.source_page,
            v.cod_lis,
            v.confidence,
            v.flags,
            v.verified,
            v.also_in_panels
        FROM v_observations v
        LEFT JOIN analytes a USING (analyte_code)
        ORDER BY v.sample_date ASC, a.category ASC, display_name_es ASC
        """
    )
    obs_cols = [c[0] for c in obs_cur.description]
    observations = [dict(zip(obs_cols, row, strict=False)) for row in obs_cur.fetchall()]

    analytes_cur = con.execute(
        """
        SELECT
            analyte_code,
            display_name_es,
            display_name_en,
            category,
            canonical_unit,
            concerning_direction
        FROM analytes
        ORDER BY category, display_name_es
        """
    )
    ana_cols = [c[0] for c in analytes_cur.description]
    analytes = [dict(zip(ana_cols, row, strict=False)) for row in analytes_cur.fetchall()]

    # Collect distinct categories and panels present in data
    categories = sorted({o["category"] for o in observations if o["category"]})
    panels = sorted({o["panel"] for o in observations if o["panel"]})

    # Summary KPIs
    verified_count = sum(1 for o in observations if o.get("verified") is True)
    out_of_range_count = sum(1 for o in observations if o.get("out_of_range") is True)
    flagged_count = sum(1 for o in observations if o.get("confidence") != "ok")
    dates = [d["sample_date"] for d in draws if d["sample_date"]]

    kpis = {
        "draw_count": len(draws),
        "total_observations": len(observations),
        "unique_analytes": len({o["analyte_code"] for o in observations}),
        "verified_count": verified_count,
        "out_of_range_count": out_of_range_count,
        "flagged_count": flagged_count,
        "date_start": min(dates) if dates else None,
        "date_end": max(dates) if dates else None,
    }

    unmapped_payload = []
    if unmapped_items:
        for u in unmapped_items:
            unmapped_payload.append(
                {
                    "name_raw": u.name_raw,
                    "panel": u.panel,
                    "sub_section": u.sub_section,
                    "unit_raw": u.unit_raw,
                    "value_cell": u.value_cell,
                    "source_file": u.source_file,
                    "source_page": u.source_page,
                }
            )

    return {
        "status": "success",
        "kpis": kpis,
        "draws": draws,
        "categories": categories,
        "panels": panels,
        "analytes": analytes,
        "observations": observations,
        "unmapped": unmapped_payload,
    }


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Exámenes Lab Report Visualizer",
        description="Ephemeral in-memory visualization for BioNet lab reports",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "app": "examenes-dashboard"}

    @app.post("/api/parse")
    async def parse_files(files: list[UploadFile] = File(...)) -> dict[str, Any]:
        """Parse one or more uploaded PDF lab reports in-memory and return structured JSON."""
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded.")

        catalog = get_catalog()
        con = duckdb.connect(":memory:")
        con.execute(SCHEMA)
        con.execute(VIEW)
        seed_analytes(con, catalog)

        all_unmapped: list[Unmapped] = []
        parsed_count = 0

        for file in files:
            if not file.filename.lower().endswith(".pdf"):
                continue

            content = await file.read()
            if not content:
                continue

            fhash = bytes_hash(content)
            try:
                meta, rows = scan_pdf(content)
                observations, unmapped = build_observations(
                    meta, rows, catalog, file.filename, fhash
                )
                all_unmapped.extend(unmapped)

                with duckdb.connect(":memory:"):
                    pass  # no-op

                # Count pages
                import pdfplumber

                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    page_count = len(pdf.pages)

                write_report(
                    con,
                    file_hash=fhash,
                    source_file=file.filename,
                    cod_lis=meta.cod_lis,
                    sample_date=meta.sample_date,
                    lab_name=meta.lab_name,
                    page_count=page_count,
                    observations=observations,
                )
                parsed_count += 1
            except Exception as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"Failed parsing '{file.filename}': {e!s}",
                ) from e

        if parsed_count == 0:
            raise HTTPException(
                status_code=400, detail="No valid PDF files could be parsed."
            )

        payload = serialize_dataset(con, all_unmapped)
        con.close()
        return payload

    @app.get("/api/local")
    async def load_local() -> dict[str, Any]:
        """Load records from local data/labs.duckdb if present."""
        db_path = SETTINGS.db_path
        if not db_path.exists():
            raise HTTPException(
                status_code=404,
                detail=(
                    "Local database 'data/labs.duckdb' does not exist yet. "
                    "Run ingest first or upload PDFs."
                ),
            )

        con = connect(db_path)
        payload = serialize_dataset(con)
        con.close()
        return payload

    @app.get("/api/demo")
    async def load_demo() -> dict[str, Any]:
        """Load demo lab reports (from input/ if present, or self-contained demo)."""
        input_dir = SETTINGS.input_dir
        pdfs = sorted(input_dir.glob("*.pdf")) if input_dir.exists() else []

        catalog = get_catalog()
        con = duckdb.connect(":memory:")
        con.execute(SCHEMA)
        con.execute(VIEW)
        seed_analytes(con, catalog)

        all_unmapped: list[Unmapped] = []

        if pdfs:
            for pdf_path in pdfs:
                content = pdf_path.read_bytes()
                fhash = bytes_hash(content)
                meta, rows = scan_pdf(content)
                observations, unmapped = build_observations(
                    meta, rows, catalog, pdf_path.name, fhash
                )
                all_unmapped.extend(unmapped)

                import pdfplumber

                with pdfplumber.open(io.BytesIO(content)) as pdf:
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
        else:
            # Generate synthetic demo data if no input files exist on server
            from .demo_data import seed_synthetic_demo

            seed_synthetic_demo(con, catalog)

        payload = serialize_dataset(con, all_unmapped)
        con.close()
        return payload

    # Mount static assets if build exists
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
