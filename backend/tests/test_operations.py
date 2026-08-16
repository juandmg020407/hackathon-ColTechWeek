"""Arranque en frío, códigos de error, autorización y localización.

Cubre lo que rompe una demo desplegada y no se ve en un happy path: que el lote
llegue con evidencia sin intervención manual, que cada fallo de dominio sea
distinguible por el cliente y que ninguna cadena en inglés se cuele a pantalla.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.bootstrap import seed_demo_readings

from conftest import EXCEL_PATH


def _settings(tmp_path, **overrides) -> Settings:
    return Settings(
        db_path=str(tmp_path / "iomido-ops.sqlite3"),
        external_sources_enabled=False,
        ai_explainer_enabled=False,
        log_level="WARNING",
        **overrides,
    )


# -- arranque en frío -------------------------------------------------


def test_cold_start_seeds_the_demo_plot_so_the_package_works(tmp_path):
    """En serverless la base vive en /tmp y nace vacía en cada arranque."""

    with TestClient(create_app(_settings(tmp_path, demo_auto_import=True))) as client:
        readings = client.get("/v1/plots/nar-001/readings")
        assert readings.status_code == 200
        assert readings.json()["count"] == 19

        package = client.get("/v1/plots/nar-001/package")
        assert package.status_code == 200, package.text
        assert package.json()["measurements"]["count"] == 19


def test_cold_start_leaves_the_demo_plot_already_computed(tmp_path):
    """El frontend pide tablero y package en paralelo: no puede haber carrera."""

    with TestClient(create_app(_settings(tmp_path, demo_auto_import=True))) as client:
        # Primera petición de la sesión: el tablero, sin tocar /package antes.
        dashboard = client.get("/v1/centers/center-pasto-demo/dashboard").json()["dashboard"]
        assert dashboard["summary"]["computed_plot_count"] == 1
        assert dashboard["producers"][0]["plots"][0]["package_id"]
        assert dashboard["producers"][0]["plots"][0]["needs_recompute"] is False

        # Y el asistente ya tiene evidencia sobre la que responder.
        agent = client.post(
            "/v1/agent/ask",
            json={"plot_id": "nar-001", "question": "¿qué tiene este lote?"},
        )
        assert agent.status_code == 200
        assert agent.json()["agent"]["grounded"] is True


def test_cold_start_without_auto_import_leaves_the_plot_empty(tmp_path):
    with TestClient(create_app(_settings(tmp_path, demo_auto_import=False))) as client:
        assert client.get("/v1/plots/nar-001/readings").json()["count"] == 0


def test_seeding_is_skipped_when_the_plot_already_has_readings(tmp_path):
    settings = _settings(tmp_path, demo_auto_import=True)
    application = create_app(settings)
    with TestClient(application):
        container = application.state.container
        # El primer arranque ya sembró; una segunda pasada no debe reimportar.
        seeded_again = seed_demo_readings(
            container.repository, container.importer, "nar-001", settings.demo_excel_path
        )
        assert seeded_again is False
        assert container.repository.count_readings("nar-001") == 19


def test_health_ready_reports_real_evidence_not_just_the_connection(tmp_path):
    with TestClient(create_app(_settings(tmp_path, demo_auto_import=True))) as client:
        body = client.get("/health/ready").json()
        assert body["status"] == "ready"
        assert body["data"] == {
            "centers": 1, "plots": 1, "plots_with_readings": 1, "readings": 19,
        }


# -- códigos de error distinguibles -----------------------------------


def test_plot_without_readings_is_a_distinguishable_state_not_a_generic_error(client):
    response = client.get("/v1/plots/nar-001/package")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "plot_has_no_readings"


def test_agent_without_evidence_reports_its_own_code(client):
    response = client.post(
        "/v1/agent/ask", json={"plot_id": "nar-001", "question": "¿qué tiene este lote?"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_package_evidence"


def test_a_bad_import_is_a_validation_error_not_a_server_fault(client):
    response = client.post(
        "/v1/readings/import?plot_id=nar-001",
        files={"file": ("notas.txt", b"esto no es una hoja de calculo")},
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "import_validation_error"
    assert ".xlsx" in body["message"]


def test_readings_outside_the_polygon_are_kept_but_excluded(client):
    created = client.post("/v1/readings", json={
        "plot_id": "nar-001",
        "latitude": 1.30000,
        "longitude": -77.30000,
        "npk_pct": {"N": 2, "P": 1, "K": 1},
        "measured_at": "2026-08-16T10:00:00Z",
        "client_id": "test:fuera-del-lote",
    })
    assert created.status_code == 201
    reading = created.json()
    assert reading["reading"]["valid_for_model"] is False
    # Queda registrada, pero no dispara un recálculo porque no alimenta el modelo.
    assert reading["recompute_required"] is False


# -- autorización de escritura ----------------------------------------


def test_write_endpoints_require_the_configured_api_key(tmp_path):
    settings = _settings(tmp_path, demo_auto_import=False, write_api_key="llave-secreta")
    payload = {
        "plot_id": "nar-001",
        "latitude": 1.248,
        "longitude": -77.267,
        "npk_pct": {"N": 2, "P": 1, "K": 1},
        "measured_at": "2026-08-16T10:00:00Z",
        "client_id": "test:con-llave",
    }
    with TestClient(create_app(settings)) as client:
        assert client.post("/v1/readings", json=payload).status_code == 401
        assert client.post(
            "/v1/readings", json=payload, headers={"X-API-Key": "llave-equivocada"}
        ).status_code == 401
        assert client.post(
            "/v1/readings", json=payload, headers={"X-API-Key": "llave-secreta"}
        ).status_code == 201
        # Las lecturas nunca exigen llave: el tablero es de solo lectura.
        assert client.get("/v1/centers").status_code == 200


# -- tablero del centro sobre proyecciones ligeras ---------------------


def test_dashboard_matches_the_package_without_reading_the_whole_snapshot(prepared_client):
    client, package, _ = prepared_client
    plot = client.get("/v1/centers/center-pasto-demo/dashboard").json()[
        "dashboard"]["producers"][0]["plots"][0]

    assert plot["package_id"] == package["id"]
    assert plot["package_generated_at"] == package["generated_at"]
    assert plot["degraded"] == package["degraded"]
    assert plot["validation_status"] == package["validation_status"]
    assert plot["area"]["value"] == pytest.approx(package["plot"]["area"]["value"])
    assert plot["measurement_count"] == package["measurements"]["count"]
    assert plot["valid_measurement_count"] == package["measurements"]["valid_for_model"]
    assert plot["highest_risk"]["type"] in {risk["type"] for risk in package["climate"]["risks"]}
    assert plot["needs_recompute"] is False


def test_a_newer_reading_marks_the_plot_for_recompute(client):
    with EXCEL_PATH.open("rb") as stream:
        client.post(
            "/v1/readings/import?plot_id=nar-001",
            files={"file": ("data_ejemplo.csv.xlsx", stream)},
        )
    assert client.post("/v1/plots/nar-001/recompute").status_code == 200

    def needs_recompute() -> bool:
        dashboard = client.get("/v1/centers/center-pasto-demo/dashboard").json()["dashboard"]
        return dashboard["producers"][0]["plots"][0]["needs_recompute"]

    assert needs_recompute() is False
    created = client.post("/v1/readings", json={
        "plot_id": "nar-001",
        "latitude": 1.24800,
        "longitude": -77.26700,
        "npk_pct": {"N": 3, "P": 2, "K": 2},
        "measured_at": "2030-01-01T10:00:00Z",
        "client_id": "test:medicion-nueva",
    })
    assert created.json()["recompute_required"] is True
    assert needs_recompute() is True


def test_quality_annotations_are_persisted_in_one_batch(prepared_client):
    client, package, _ = prepared_client
    stored = client.get("/v1/plots/nar-001/readings").json()["readings"]
    by_id = {item["id"]: item for item in stored}

    for point in package["measurements"]["points"]:
        quality = point["quality"]
        reading = by_id[point["id"]]
        assert reading["valid_for_model"] == quality["valid_for_model"]
        assert reading["suspicious"] == quality["suspicious"]
        assert reading["anomaly_reason"] == quality["reason"]
    assert sum(not item["valid_for_model"] for item in stored) == 1


# -- localización -----------------------------------------------------

# Palabras que solo aparecen en prosa inglesa. Se buscan en las cadenas que el
# frontend renderiza tal cual, no en claves ni versiones de modelo.
_ENGLISH = re.compile(
    r"\b(the|and|with|from|this|that|are|were|was|have|has|been|must|should|"
    r"not|before|after|because|which|their|its|for|used|using|use)\b",
    re.IGNORECASE,
)

# Rutas del package cuyo valor se muestra literalmente a una persona.
_HUMAN_TEXT_KEYS = {
    "reason", "warning", "warnings", "limitation", "limitations", "claim",
    "recommended_action", "why_this_combination_won", "summary", "detail",
    "unknowns", "statement", "effect", "threshold_method", "method",
    "technical_validation_reasons", "cluster_method",
}


def _human_strings(node, path=""):
    """Recorre el package y devuelve (ruta, texto) de cada cadena visible."""

    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else key
            if key in _HUMAN_TEXT_KEYS:
                yield from _leaf_strings(value, child)
            else:
                yield from _human_strings(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _human_strings(value, f"{path}[{index}]")


def _leaf_strings(node, path):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaf_strings(value, f"{path}[{index}]")
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _leaf_strings(value, f"{path}.{key}")


def test_no_human_facing_string_in_the_package_is_written_in_english(prepared_client):
    _, package, _ = prepared_client
    offenders = [
        (path, text)
        for path, text in _human_strings(package)
        if _ENGLISH.search(text)
    ]
    assert not offenders, "cadenas en inglés visibles para el usuario: " + json.dumps(
        offenders, ensure_ascii=False, indent=2
    )


def test_the_dashboard_speaks_spanish_too(prepared_client):
    client, _, _ = prepared_client
    dashboard = client.get("/v1/centers/center-pasto-demo/dashboard").json()["dashboard"]
    texts = [item["detail"] for item in dashboard["priority_queue"]]
    texts += [item["title"] for item in dashboard["priority_queue"]]
    texts.append(dashboard["data_scope"]["statement"])
    offenders = [text for text in texts if _ENGLISH.search(text)]
    assert not offenders, offenders


def test_versioned_configuration_uses_correct_spanish_orthography(prepared_client):
    client, package, _ = prepared_client
    assert package["plot"]["municipality"] == "Pasto, Nariño"
    assert package["crop_profile"]["scope"].startswith("lote demostrativo de Pasto, Nariño")
    assert package["climate"]["seasonal_context"]["enso"]["phase"] == "El Niño"
    # La regla de sequía normaliza la ñ, así que la fase sigue detectándose.
    drought = next(
        risk for risk in package["climate"]["risks"] if risk["type"] == "drought"
    )
    assert drought["inputs"]["enso_phase"] == "El Niño"
    assert drought["score"]["value"] > 0.3

    center = client.get("/v1/centers/center-pasto-demo").json()["center"]
    assert center["municipality"] == "Pasto, Nariño"
