from __future__ import annotations

import json
from pathlib import Path


REQUIRED_METADATA = {
    "contract_version",
    "units",
    "npk_convention",
    "validation_status",
    "sources",
    "model_versions",
    "generated_at",
    "degraded",
    "warnings",
}

OPENAPI_SNAPSHOT = Path(__file__).resolve().parents[1] / "openapi-v2.json"


def test_offline_excel_to_audit_flow(prepared_client):
    client, package, imported = prepared_client
    first_imported = imported["import"]["first_reading"]
    first_packaged = package["measurements"]["points"][0]
    assert (first_imported["N"], first_imported["P"], first_imported["K"]) == (2, 1, 1)
    assert (first_packaged["N"], first_packaged["P"], first_packaged["K"]) == (2, 1, 1)
    assert first_imported["unit"] == "mass_pct"
    assert imported["import"]["conversion_applied"] is False
    assert package["model_run"]["model_name"] == "GaussianProcessRegressor-Matern"
    assert package["spatial"]["next_sample"]["reason"]
    assert package["climate"]["degraded"] is True

    proposal_id = package["proposal"]["id"]
    proposal = client.get(f"/v1/proposals/{proposal_id}")
    explanation = client.get(f"/v1/proposals/{proposal_id}/why")
    assert proposal.status_code == explanation.status_code == 200
    assert proposal.json()["proposal"]["status"] == "pending"
    decision = client.post("/v1/decisions", json={
        "proposal_id": proposal_id,
        "action": "accept",
        "actor": {"type": "farmer", "id": "farmer-integration"},
    })
    assert decision.status_code == 201
    assert decision.json()["decision"]["applied"] is False
    assert decision.json()["decision"]["resulting_status"] == "pending_technical_review"
    decision_id = decision.json()["decision"]["id"]
    history = client.get(f"/v1/decisions/{decision_id}/history")
    assert history.status_code == 200
    assert history.json()["history"]["decisions"]
    assert history.json()["history"]["audit"]


def test_contract_has_no_legacy_units_products_or_money(prepared_client):
    _, package, _ = prepared_client
    encoded = json.dumps(package, ensure_ascii=False).lower()
    assert "ppm" not in encoded
    for forbidden in (
        "dap 18-46-0", "kcl 0-0-60", "urea 46-0-0", "13-26-6",
        "cop_bulto", "costo_cop", "ahorro_cop", "price", "savings",
    ):
        assert forbidden not in encoded
    assert REQUIRED_METADATA.issubset(package)
    assert package["measurements"]["unit"] == "mass_pct"
    assert package["model_versions"]["spatial"]


def test_openapi_contains_required_v2_operations(prepared_client):
    client, _, _ = prepared_client
    response = client.get("/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert document["info"]["version"] == "2.0.0"
    required = {
        "/health/live", "/health/ready", "/v1/governance", "/v1/models",
        "/v1/models/{model_id}/metrics", "/v1/centers", "/v1/centers/{center_id}",
        "/v1/centers/{center_id}/dashboard", "/v1/centers/{center_id}/producers",
        "/v1/producers/{producer_id}", "/v1/producers/{producer_id}/plots",
        "/v1/centers/{center_id}/formulations",
        "/v1/centers/{center_id}/formulations/{formulation_id}",
        "/v1/crop-profiles", "/v1/crop-profiles/{profile_id}",
        "/v1/plots", "/v1/plots/{plot_id}", "/v1/plots/{plot_id}/readings",
        "/v1/plots/{plot_id}/package",
        "/v1/plots/{plot_id}/recompute", "/v1/plots/{plot_id}/risk",
        "/v1/readings", "/v1/readings/bulk", "/v1/readings/import",
        "/v1/proposals/{proposal_id}", "/v1/proposals/{proposal_id}/why",
        "/v1/decisions", "/v1/decisions/{decision_id}",
        "/v1/decisions/{identifier}/history", "/v1/agent/ask",
    }
    assert required.issubset(document["paths"])
    assert document == json.loads(OPENAPI_SNAPSHOT.read_text(encoding="utf-8"))


def test_errors_are_consistent_contract_objects(client):
    response = client.get("/v1/plots/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["contract_version"] == "2.0"
    assert set(body["error"]) == {"code", "message", "request_id", "details"}
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]


def test_agent_is_grounded_for_supported_intents(prepared_client):
    client, package, _ = prepared_client
    questions = {
        "¿qué tiene este lote?": "plot_status",
        "¿por qué recomienda esa formulación?": "formulation_reason",
        "¿dónde debo medir ahora?": "next_measurement",
        "¿qué riesgo climático existe?": "climate_risk",
        "¿qué datos faltan?": "missing_data",
        "¿qué tan segura es la predicción?": "prediction_confidence",
    }
    for question, expected_intent in questions.items():
        response = client.post(
            "/v1/agent/ask", json={"plot_id": "nar-001", "question": question}
        )
        assert response.status_code == 200
        agent = response.json()["agent"]
        assert agent["intent"] == expected_intent
        assert agent["grounded"] is True
        assert agent["llm_used"] is False
        assert agent["evidence_ids"]

    unsupported = client.post(
        "/v1/agent/ask", json={"plot_id": "nar-001", "question": "cuéntame un chiste"}
    )
    assert unsupported.json()["agent"]["answered"] is False


def test_center_dashboard_is_persisted_and_honest(prepared_client):
    client, package, _ = prepared_client
    response = client.get("/v1/centers/center-pasto-demo/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    dashboard = body["dashboard"]

    assert dashboard["summary"]["producer_count"] == 1
    assert dashboard["summary"]["plot_count"] == 1
    assert dashboard["summary"]["measurement_count"] == 19
    assert dashboard["summary"]["computed_plot_count"] == 1
    assert dashboard["data_scope"]["contains_demonstration_data"] is True
    assert dashboard["producers"][0]["data_origin"] == "demonstration"
    assert dashboard["producers"][0]["plots"][0]["package_id"] == package["id"]
    assert dashboard["producers"][0]["plots"][0]["location"] == {
        "latitude": 1.24811,
        "longitude": -77.267245,
    }
    assert body["model_versions"]["network"] == "center-network-summary/1.0.0"
    audit = client.get(
        "/v1/audit?entity_type=producer&entity_id=producer-el-rosal-demo"
    ).json()["events"]
    assert [event["event_type"] for event in audit] == ["producer_created"]


def test_producer_and_reading_endpoints_support_frontend_drilldown(prepared_client):
    client, _, _ = prepared_client
    producer_id = "producer-el-rosal-demo"

    producer = client.get(f"/v1/producers/{producer_id}")
    plots = client.get(f"/v1/producers/{producer_id}/plots")
    filtered = client.get(f"/v1/plots?producer_id={producer_id}")
    readings = client.get("/v1/plots/nar-001/readings?valid_only=true")

    assert producer.status_code == plots.status_code == filtered.status_code == 200
    assert producer.json()["producer"]["display_name"] == "Productor demo El Rosal"
    assert [item["id"] for item in plots.json()["plots"]] == ["nar-001"]
    assert [item["id"] for item in filtered.json()["plots"]] == ["nar-001"]
    assert readings.status_code == 200
    assert readings.json()["count"] == 18
    assert all(item["valid_for_model"] for item in readings.json()["readings"])
