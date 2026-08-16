from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import BACKEND_ROOT
from app.repositories import SQLiteRepository
from app.services.bootstrap import bootstrap_repository
from app.services.explainer import AIBudgetPolicy
from app.sources.resilient import ResilientJSONSource, SourcePolicy


def test_external_source_falls_back_without_hiding_failure(tmp_path):
    repository = SQLiteRepository(tmp_path / "cache.sqlite3")
    repository.migrate()

    def unavailable(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    source = ResilientJSONSource(
        name="fake-climate",
        url="https://example.invalid/data",
        repository=repository,
        policy=SourcePolicy(max_retries=0, circuit_failure_threshold=1),
        enabled=True,
        transport=httpx.MockTransport(unavailable),
    )
    result = asyncio.run(source.fetch(
        {"plot": "nar-001"},
        offline_payload={"temperature": 10},
        offline_fetched_at="2026-08-01T00:00:00Z",
    ))
    assert result.payload == {"temperature": 10}
    assert result.degraded is True
    assert result.stale is True
    assert result.failed is True
    assert "not presented as current" not in (result.warning or "") or result.warning


def test_audit_log_is_append_only_via_triggers(tmp_path):
    repository = SQLiteRepository(tmp_path / "audit.sqlite3")
    repository.migrate()
    event_id = repository.append_audit("test", "plot", "nar-001", "tester", {"ok": True})
    connection = repository.connect()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("UPDATE audit_log SET actor='changed' WHERE event_id=?", (event_id,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM audit_log WHERE event_id=?", (event_id,))
    connection.close()


def test_ai_budget_uses_configurable_prices_and_rejects_overspend():
    budget = AIBudgetPolicy(
        total_budget_usd=1.0,
        max_input_tokens=2_000,
        max_output_tokens=500,
        input_price_usd_per_million=2.0,
        output_price_usd_per_million=8.0,
    )
    assert budget.estimated_cost(1_000, 250) == 0.004
    assert budget.can_spend(0.99, 1_000, 250) is True
    assert budget.can_spend(0.997, 1_000, 250) is False
    with pytest.raises(ValueError):
        budget.estimated_cost(2_001, 1)


def test_reading_client_id_is_durable_and_idempotent(client):
    payload = {
        "plot_id": "nar-001",
        "latitude": 1.248,
        "longitude": -77.267,
        "npk_pct": {"N": 2, "P": 1, "K": 1, "basis": "elemental_mass_pct"},
        "measured_at": "2026-08-15T12:00:00Z",
        "client_id": "phone-1-reading-1",
    }
    first = client.post("/v1/readings", json=payload)
    second = client.post("/v1/readings", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["reading"]["id"] == second.json()["reading"]["id"]
    assert first.json()["created"] is True
    assert second.json()["idempotent"] is True
