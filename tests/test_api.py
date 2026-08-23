"""Tests for the web API endpoints."""

from pathlib import Path

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

    response = client.get("/api/local")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["kpis"]["draw_count"] == 4
    assert data["kpis"]["total_observations"] == 300


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
