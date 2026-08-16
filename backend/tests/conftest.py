from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from app.config import Settings
from app.main import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXCEL_PATH = REPOSITORY_ROOT / "data" / "data_ejemplo.csv.xlsx"


@pytest.fixture()
def client(tmp_path):
    application = create_app(Settings(
        db_path=str(tmp_path / "iomido-test.sqlite3"),
        demo_auto_import=False,
        external_sources_enabled=False,
        ai_explainer_enabled=False,
        log_level="WARNING",
    ))
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def prepared_client(tmp_path_factory):
    database = tmp_path_factory.mktemp("prepared") / "iomido.sqlite3"
    application = create_app(Settings(
        db_path=str(database),
        demo_auto_import=False,
        external_sources_enabled=False,
        ai_explainer_enabled=False,
        log_level="WARNING",
    ))
    with TestClient(application) as test_client:
        with EXCEL_PATH.open("rb") as stream:
            imported = test_client.post(
                "/v1/readings/import?plot_id=nar-001",
                files={"file": ("data_ejemplo.csv.xlsx", stream)},
            )
        assert imported.status_code == 201, imported.text
        response = test_client.post("/v1/plots/nar-001/recompute")
        assert response.status_code == 200, response.text
        yield test_client, response.json(), imported.json()
