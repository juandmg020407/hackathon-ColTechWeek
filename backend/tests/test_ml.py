from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import REPOSITORY_ROOT
from app.domain.models import NPKPercent, Plot, Reading
from app.ml.geometry import point_in_polygon
from app.ml.quality import annotate_quality
from app.ml.spatial import SoilSpatialEngine
from app.services.importer import rows_from_excel


@pytest.fixture(scope="module")
def plot():
    return Plot(
        id="nar-001",
        center_id="center-pasto-demo",
        crop_profile_id="potato-pasto-demo-v1",
        name="Lote",
        municipality="Pasto",
        boundary=[
            (1.24750, -77.26767),
            (1.24872, -77.26767),
            (1.24872, -77.26682),
            (1.24750, -77.26682),
        ],
    )


@pytest.fixture(scope="module")
def demo_readings():
    excel = (REPOSITORY_ROOT / "data" / "data_ejemplo.csv.xlsx").read_bytes()
    return [
        Reading(
            id=f"reading-{index}",
            plot_id="nar-001",
            latitude=row["Latitud"],
            longitude=row["Longitud"],
            npk_pct=NPKPercent(N=row["N"], P=row["p"], K=row["k"]),
            measured_at=datetime.now(timezone.utc),
            client_id=f"test-{index}",
        )
        for index, row in enumerate(rows_from_excel(excel))
    ]


def test_geometry_excludes_outside_point_but_value_anomalies_remain(plot, demo_readings):
    annotations = annotate_quality(plot, demo_readings)
    outside = [item for item in annotations if not item.valid_for_model]
    suspicious = [item for item in annotations if item.suspicious]
    assert len(outside) == 1
    assert outside[0].method == "geometry/polygon-v1"
    assert all(item.valid_for_model for item in suspicious)
    assert any("isolation-forest" in (item.method or "") for item in suspicious)


@pytest.mark.parametrize("count", [1, 2, 3, 19])
def test_spatial_engine_safely_handles_small_sample_counts(plot, demo_readings, count):
    selected = demo_readings[:count]
    if count < 19:
        selected = [reading for reading in demo_readings if reading.latitude > 1.2475][:count]
    result = SoilSpatialEngine(cell_size_m=15, seed=42).run(plot, selected)
    valid_count = len(result["valid_reading_ids"])
    assert valid_count >= 1
    assert set(result["grid"]["nutrients"]) == {"N", "P", "K"}
    assert result["grid"]["combined_uncertainty"]["unit"] == "percentage_points"
    assert point_in_polygon(
        result["next_sample"]["point"]["latitude"],
        result["next_sample"]["point"]["longitude"],
        plot.boundary,
    )
    if valid_count < 3:
        assert len(result["zones"]) == 1
        assert result["model_run"]["metrics"]["available"] is False


def test_benchmark_has_per_nutrient_metrics_and_small_data_limitation(plot, demo_readings):
    result = SoilSpatialEngine(cell_size_m=15, seed=42).run(plot, demo_readings)
    metrics = result["model_run"]["metrics"]
    assert metrics["available"] is True
    assert set(metrics["per_nutrient"]) == {"N", "P", "K"}
    for nutrient in "NPK":
        assert set(metrics["per_nutrient"][nutrient]) == {"unit", "gp", "idw"}
        assert "interval_95_coverage" in metrics["per_nutrient"][nutrient]["gp"]
    assert isinstance(metrics["gp_better_than_idw"], bool)
    assert any("Conjunto pequeño" in item for item in result["model_run"]["limitations"])


def test_seed_makes_zones_and_active_sample_reproducible(plot, demo_readings):
    engine = SoilSpatialEngine(cell_size_m=20, seed=42)
    left = engine.run(plot, demo_readings[:5])
    right = engine.run(plot, demo_readings[:5])
    assert left["zones"] == right["zones"]
    assert left["next_sample"] == right["next_sample"]
