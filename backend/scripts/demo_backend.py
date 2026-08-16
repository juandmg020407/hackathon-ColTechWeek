"""Run the complete backend demo without Internet or paid services.

Usage from ``backend``::

    python scripts/demo_backend.py

The default creates an isolated temporary SQLite database and exercises the
FastAPI application in-process. Nothing is sent over the network.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def show(step: int, title: str, payload) -> None:
    print(f"\n{step}. {title}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="iomido-demo-") as directory:
        app = create_app(Settings(
            db_path=str(Path(directory) / "demo.sqlite3"),
            external_sources_enabled=False,
            log_level="WARNING",
        ))
        with TestClient(app) as client:
            health = {
                "live": client.get("/health/live").json(),
                "ready": client.get("/health/ready").json(),
            }
            show(1, "Health", health)

            excel = REPOSITORY_ROOT / "data" / "data_ejemplo.csv.xlsx"
            with excel.open("rb") as stream:
                imported_response = client.post(
                    "/v1/readings/import?plot_id=nar-001",
                    files={"file": (excel.name, stream)},
                )
            imported_response.raise_for_status()
            show(2, "Importación de 19 mediciones", imported_response.json()["import"])

            package_response = client.get("/v1/plots/nar-001/package")
            package_response.raise_for_status()
            package = package_response.json()
            show(3, "Package v2", {
                "id": package["id"],
                "contract_version": package["contract_version"],
                "measurements": package["measurements"]["count"],
                "proposal_id": package["proposal"]["id"],
            })
            show(4, "Predicciones e incertidumbre", {
                "model_run": package["model_run"],
                "zone_centroids": [zone["centroid_npk"] for zone in package["spatial"]["zones"]],
                "uncertainty": package["spatial"]["grid"]["combined_uncertainty"],
            })
            show(5, "Siguiente punto", package["spatial"]["next_sample"])

            risk_response = client.get("/v1/plots/nar-001/risk")
            risk_response.raise_for_status()
            show(6, "Riesgo climático", risk_response.json()["climate"])

            plans = [
                {
                    "zone_id": recommendation["zone_id"],
                    "plan": recommendation["integer_plan"],
                }
                for recommendation in package["proposal"]["recommendations"]
            ]
            show(7, "Formulaciones candidatas enteras", plans)

            proposal_id = package["proposal"]["id"]
            why = client.get(f"/v1/proposals/{proposal_id}/why")
            why.raise_for_status()
            show(8, "Explicación de la propuesta", why.json()["explanation"])

            decision = client.post("/v1/decisions", json={
                "proposal_id": proposal_id,
                "action": "refer",
                "actor": {"type": "farmer", "id": "demo-farmer"},
                "note": "Solicitar validación del técnico del centro.",
            })
            decision.raise_for_status()
            show(9, "Decisión humana", decision.json()["decision"])

            audit = client.get(
                "/v1/audit", params={"entity_type": "proposal", "entity_id": proposal_id}
            )
            audit.raise_for_status()
            show(10, "Auditoría append-only", audit.json()["events"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
