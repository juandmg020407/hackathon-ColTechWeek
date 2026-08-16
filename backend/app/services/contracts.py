"""Shared contract v2 metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def contract_metadata(
    *,
    validation_status: str = "requires_technical_validation",
    sources: list[dict[str, Any]] | None = None,
    model_versions: dict[str, str] | None = None,
    degraded: bool = False,
    warnings: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": "2.0",
        "units": {
            "soil_npk": "mass_pct",
            "formulation_npk": "mass_pct",
            "nutrient_amount": "kg or kg/ha as labelled",
            "distance": "m",
            "area": "ha",
        },
        "npk_convention": {
            "basis": "elemental_mass_pct",
            "components": ["N", "P", "K"],
            "oxide_grades": "rejected unless passed through an explicit adapter",
        },
        "validation_status": validation_status,
        "sources": sources or [],
        "model_versions": model_versions or {},
        "generated_at": generated_at or utc_now(),
        "degraded": degraded,
        "warnings": list(dict.fromkeys(warnings or [])),
    }
