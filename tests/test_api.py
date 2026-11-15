"""Tests for the web API endpoints."""

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from examenes.web.api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "examenes-dashboard"


def test_demo_endpoint(client):
    response = client.get("/api/demo")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "kpis" in data
    assert data["kpis"]["draw_count"] >= 1
    assert data["kpis"]["total_observations"] > 0
    assert len(data["observations"]) > 0
    assert len(data["draws"]) >= 1


def test_local_endpoint_if_exists(client):
    db_path = Path("data/labs.duckdb")
    if not db_path.exists():
        pytest.skip("Local database does not exist")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        (report_count,) = con.execute("SELECT count(*) FROM reports").fetchone()
        (obs_count,) = con.execute("SELECT count(*) FROM v_observations").fetchone()
    finally:
        con.close()

    response = client.get("/api/local")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["kpis"]["draw_count"] == report_count
    assert data["kpis"]["total_observations"] == obs_count


def test_parse_single_pdf(client):
    pdf_path = Path("input/results-26748.pdf")
    if not pdf_path.exists():
        pytest.skip("Test input PDF not found")

    with pdf_path.open("rb") as fh:
        response = client.post(
            "/api/parse",
            files={"files": (pdf_path.name, fh, "application/pdf")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["kpis"]["draw_count"] == 1
    assert data["kpis"]["total_observations"] == 83
    assert len(data["unmapped"]) == 0


def test_parse_appended_upload_does_not_duplicate(client):
    """Re-sending an already loaded PDF with a new one must not double-count.

    The "Agregar PDF" button re-sends every previously uploaded file together
    with the new ones, relying on the sha256 idempotency key to deduplicate.
    """
    first = Path("input/results-26748.pdf")
    second = Path("input/results-26748-1.pdf")
    if not (first.exists() and second.exists()):
        pytest.skip("Test input PDFs not found")

    def post(paths: list[Path]) -> dict:
        handles = [p.open("rb") for p in paths]
        try:
            response = client.post(
                "/api/parse",
                files=[
                    ("files", (p.name, fh, "application/pdf"))
                    for p, fh in zip(paths, handles, strict=True)
                ],
            )
        finally:
            for fh in handles:
                fh.close()
        assert response.status_code == 200
        return response.json()

    combined = post([first, second])
    with_repeat = post([first, second, first])

    assert with_repeat["kpis"]["draw_count"] == 2
    assert with_repeat["kpis"] == combined["kpis"]
    assert len(with_repeat["observations"]) == len(combined["observations"])
