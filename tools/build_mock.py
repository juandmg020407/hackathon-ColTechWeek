"""Regenerate checked-in contract v2 mocks through SoilIntelligenceEngine."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="iomido-mock-") as directory:
        app = create_app(Settings(
            db_path=str(Path(directory) / "mock.sqlite3"),
            external_sources_enabled=False,
            log_level="WARNING",
        ))
        with TestClient(app) as client:
            excel = ROOT / "data" / "data_ejemplo.csv.xlsx"
            with excel.open("rb") as stream:
                imported = client.post(
                    "/v1/readings/import?plot_id=nar-001",
                    files={"file": (excel.name, stream)},
                )
            imported.raise_for_status()
            response = client.post("/v1/plots/nar-001/recompute")
            response.raise_for_status()
            package = response.json()

    encoded = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
    # Solo frontend/mock: es el que sirve la pagina, porque Vercel publica
    # frontend/ como outputDirectory y ahi /mock/... resuelve.
    target = ROOT / "frontend" / "mock" / "package-nar-001.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(encoded, encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
