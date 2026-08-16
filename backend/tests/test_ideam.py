from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx
import pytest

from app.config import BACKEND_ROOT
from app.repositories import SQLiteRepository
from app.sources.ideam import ENVELOPE, IdeamStationSource, _unique_by_timestamp

FIXTURE = BACKEND_ROOT / "config" / "climate" / "ideam-pasto-demo-v1.json"
PLOT = (1.24811, -77.267245)


def _source(tmp_path, handler=None, **kwargs) -> IdeamStationSource:
    repository = SQLiteRepository(tmp_path / "ideam.sqlite3")
    repository.migrate()
    return IdeamStationSource(
        repository,
        FIXTURE,
        external_enabled=handler is not None,
        transport=httpx.MockTransport(handler) if handler else None,
        max_retries=0,
        **kwargs,
    )


def test_duplicate_rows_are_discarded_before_aggregating():
    """El dataset republica la misma lectura; sumarla dos veces inventa lluvia."""
    rows = [
        {"fechaobservacion": "2026-08-15T10:00:00.000", "valorobservado": "4.0"},
        {"fechaobservacion": "2026-08-15T10:00:00.000", "valorobservado": "4.0"},
        {"fechaobservacion": "2026-08-15T10:00:00.000", "valorobservado": "4.0"},
        {"fechaobservacion": "2026-08-15T10:10:00.000", "valorobservado": "1.5"},
    ]
    series = _unique_by_timestamp(rows)
    assert len(series) == 2
    assert sum(series.values()) == pytest.approx(5.5)


def test_unusable_rows_are_skipped_instead_of_crashing():
    rows = [
        {"fechaobservacion": "2026-08-15T10:00:00.000", "valorobservado": "sin dato"},
        {"fechaobservacion": None, "valorobservado": "2.0"},
        {"valorobservado": "3.0"},
        {"fechaobservacion": "2026-08-15T11:00:00.000", "valorobservado": "2.5"},
    ]
    assert _unique_by_timestamp(rows) == {"2026-08-15T11:00:00.000": 2.5}


def test_offline_returns_the_versioned_fixture_marked_as_degraded(tmp_path):
    observed = asyncio.run(_source(tmp_path).observe(*PLOT))
    assert observed["available"] is True
    assert observed["degraded"] is True
    assert observed["station"]["distance_km"] < 5
    assert observed["sources"][0]["stale"] is True
    assert any("fixture" in warning for warning in observed["warnings"])


def test_fixture_declares_its_own_gaps():
    """El acumulado no cubre la ventana pedida, y el fixture debe decirlo."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rainfall = fixture["measurements"]["precipitation"]
    assert rainfall["days_with_data"] < fixture["window"]["days_requested"]
    assert rainfall["duplicate_rows_discarded"] > 0
    assert any("no es un total mensual" in limit for limit in fixture["limitations"])
    assert "no alimenta las reglas" in fixture["note"].lower()


def test_nearest_active_station_wins(tmp_path):
    stations = [
        {"nombreestacion": "LEJANA", "codigoestacion": "999", "latitud": "1.45",
         "longitud": "-77.45", "ultima": "2026-08-15T23:50:00.000"},
        {"nombreestacion": "  CERCANA   - AUT ", "codigoestacion": "111", "latitud": "1.25",
         "longitud": "-77.27", "ultima": "2026-08-15T23:50:00.000"},
    ]
    series = [
        {"fechaobservacion": "2026-08-15T10:00:00.000", "valorobservado": "3.0"},
        {"fechaobservacion": "2026-08-15T10:00:00.000", "valorobservado": "3.0"},
        {"fechaobservacion": "2026-08-14T10:00:00.000", "valorobservado": "1.0"},
    ]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        where = request.url.params.get("$where", "")
        seen.append(where)
        if "$group" in request.url.params:
            return httpx.Response(200, json=stations)
        return httpx.Response(200, json=series)

    observed = asyncio.run(_source(tmp_path, handler).observe(*PLOT, today=date(2026, 8, 16)))

    assert observed["station"]["code"] == "111"
    assert observed["station"]["name"] == "CERCANA - AUT"   # espacios normalizados
    assert observed["station"]["candidates_considered"] == 2
    assert observed["measurements"]["precipitation"]["accumulated"] == pytest.approx(4.0)
    assert observed["measurements"]["precipitation"]["duplicate_rows_discarded"] == 1
    assert observed["lag_days"] == 1
    assert observed["degraded"] is False
    # Las series se piden por codigo de estacion, no por nombre: el nombre trae
    # espacios inconsistentes en el dataset del IDEAM.
    assert any("codigoestacion='111'" in where for where in seen)


def test_a_failing_socrata_degrades_to_the_fixture(tmp_path):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    observed = asyncio.run(_source(tmp_path, handler).observe(*PLOT, today=date(2026, 8, 16)))
    assert observed["degraded"] is True
    assert observed["available"] is True
    assert observed["warnings"]


def test_observed_context_never_feeds_the_risk_rules(tmp_path):
    """Es evidencia observada, no una entrada del cálculo."""
    from app.sources.climate import ClimateFusion

    repository = SQLiteRepository(tmp_path / "fusion.sqlite3")
    repository.migrate()
    fusion = ClimateFusion(
        repository,
        BACKEND_ROOT / "config" / "climate" / "pasto-demo-v1.json",
        external_enabled=False,
        ideam=_source(tmp_path),
    )
    context = asyncio.run(fusion.evaluate(*PLOT))

    assert context["observed_context"]["station"]["operator"].startswith("IDEAM")
    assert any("IDEAM" in source["name"] for source in context["sources"])
    for risk in context["risks"]:
        assert not any("ideam" in str(key).lower() for key in risk["inputs"])


def test_climate_still_works_without_ideam(tmp_path):
    from app.sources.climate import ClimateFusion

    repository = SQLiteRepository(tmp_path / "no-ideam.sqlite3")
    repository.migrate()
    fusion = ClimateFusion(
        repository,
        BACKEND_ROOT / "config" / "climate" / "pasto-demo-v1.json",
        external_enabled=False,
    )
    context = asyncio.run(fusion.evaluate(*PLOT))
    assert context["observed_context"] is None
    assert len(context["risks"]) == 3
