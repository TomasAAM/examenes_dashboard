"""Synthetic fallback demo data generator for public deployments without raw files."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import duckdb

from ..build import Observation
from ..normalize import Catalog
from ..store import write_report


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def seed_synthetic_demo(con: duckdb.DuckDBPyConnection, catalog: Catalog) -> None:
    """Populate DuckDB with realistic synthetic observations for 3 draws."""
    draws_data = [
        ("2025-01-15", "demo-draw-1.pdf", "10111221"),
        ("2025-07-20", "demo-draw-2.pdf", "10222332"),
        ("2026-02-10", "demo-draw-3.pdf", "10333443"),
    ]

    # Sample analytes with values across 3 draws:
    # (code, panel, unit, ref_low, ref_high, [val1, val2, val3])
    samples = [
        # Lipid
        ("cholesterol_total", "PERFIL LIPIDICO", "mg/dL", None, 200.0, [195.0, 215.0, 185.0]),
        ("hdl", "PERFIL LIPIDICO", "mg/dL", 40.0, None, [48.0, 52.0, 55.0]),
        ("ldl_calculated", "PERFIL LIPIDICO", "mg/dL", None, 130.0, [118.0, 138.0, 108.0]),
        ("triglycerides", "PERFIL LIPIDICO", "mg/dL", None, 150.0, [145.0, 162.0, 110.0]),
        # Liver
        ("alt", "PERFIL HEPATICO", "U/L", None, 41.0, [28.0, 45.0, 32.0]),
        ("ast", "PERFIL HEPATICO", "U/L", None, 38.0, [24.0, 35.0, 26.0]),
        ("ggt", "PERFIL HEPATICO", "U/L", 8.0, 61.0, [22.0, 31.0, 25.0]),
        ("bilirubin_total", "PERFIL HEPATICO", "mg/dL", 0.2, 1.2, [0.8, 0.9, 0.7]),
        # Metabolic / Kidney
        ("glucose", "GLICEMIA", "mg/dL", 70.0, 100.0, [88.0, 96.0, 91.0]),
        ("creatinine", "PERFIL BIOQUIMICO", "mg/dL", 0.7, 1.3, [0.95, 0.98, 0.92]),
        ("uric_acid", "PERFIL BIOQUIMICO", "mg/dL", 3.5, 7.2, [5.4, 6.1, 5.2]),
        ("calcium", "PERFIL BIOQUIMICO", "mg/dL", 8.6, 10.2, [9.4, 9.5, 9.6]),
        # Iron & Vitamins
        ("ferritin", "FERRITINA", "ng/mL", 30.0, 400.0, [145.0, 160.0, 182.0]),
        ("serum_iron", "CINECITICA DEL FIERRO", "ug/dL", 65.0, 175.0, [95.0, 110.0, 125.0]),
        ("transferrin_saturation", "CINECITICA DEL FIERRO", "%", 20.0, 50.0, [28.0, 33.0, 36.0]),
        ("vitamin_d_25oh", "VITAMINA D", "ng/mL", 30.0, 100.0, [24.0, 35.0, 42.0]),
        ("vitamin_b12", "VITAMINA B12", "pg/mL", 211.0, 911.0, [420.0, 480.0, 510.0]),
        # Haemogram
        ("hemoglobin_blood", "HEMOGRAMA", "g/dL", 13.5, 17.5, [15.2, 15.0, 15.4]),
        ("hematocrit", "HEMOGRAMA", "%", 40.0, 52.0, [45.1, 44.8, 45.6]),
        ("wbc", "HEMOGRAMA", "10^3/uL", 4.5, 11.0, [6.2, 7.1, 6.5]),
        ("platelets", "HEMOGRAMA", "10^3/uL", 150.0, 450.0, [240.0, 260.0, 255.0]),
    ]

    for draw_idx, (date_str, source_file, cod_lis) in enumerate(draws_data):
        y, m, d = (int(x) for x in date_str.split("-"))
        sdate = date(y, m, d)
        fhash = _hash(f"demo-{date_str}")
        obs_list: list[Observation] = []

        for code, panel, unit, r_low, r_high, vals in samples:
            val = vals[draw_idx]
            out_of_range = False
            if r_low is not None and val < r_low:
                out_of_range = True
            if r_high is not None and val > r_high:
                out_of_range = True

            if r_low is not None and r_high is not None:
                ref_text = f"{r_low} - {r_high}"
                ref_op = "range"
            elif r_high is not None:
                ref_text = f"< {r_high}"
                ref_op = "lt"
            elif r_low is not None:
                ref_text = f"> {r_low}"
                ref_op = "gt"
            else:
                ref_text = ""
                ref_op = "none"

            obs = Observation(
                obs_key=_hash(f"{fhash}|{code}"),
                sample_date=sdate,
                lab_name="Laboratorio BioNet Demo",
                panel=panel,
                sub_section=None,
                analyte_code=code,
                analyte_name_raw=code.replace("_", " ").upper(),
                value_num=val,
                value_text=None,
                unit=unit,
                unit_raw=unit,
                ref_low=r_low,
                ref_high=r_high,
                ref_operator=ref_op,
                ref_text=ref_text,
                method="Quimioluminiscencia / Automatizado",
                out_of_range=out_of_range,
                asterisk_flag=out_of_range,
                source_file=source_file,
                source_page=1,
                file_hash=fhash,
                cod_lis=cod_lis,
                source="pdf",
                extracted_at=datetime.now(UTC),
                verified=True,
                confidence="ok",
                flags="",
                also_in_panels=None,
            )
            obs_list.append(obs)

        write_report(
            con,
            file_hash=fhash,
            source_file=source_file,
            cod_lis=cod_lis,
            sample_date=sdate,
            lab_name="Laboratorio BioNet Demo",
            page_count=3,
            observations=obs_list,
        )
