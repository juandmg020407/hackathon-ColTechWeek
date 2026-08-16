"""Analog-year model and explicit climate risk rules."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


class AnalogYearModel:
    version = "climate-analog-nearest-neighbors/1.0.0"
    variables = ("rainfall_mm", "minimum_temperature_c", "mean_temperature_c", "enso_index")

    def select(
        self,
        historical_years: list[dict[str, Any]],
        current: dict[str, float],
        count: int = 3,
    ) -> list[dict[str, Any]]:
        if not historical_years:
            return []
        matrix = np.array([
            [float(item[name]) for name in self.variables] for item in historical_years
        ])
        query = np.array([[float(current[name]) for name in self.variables]])
        scaler = StandardScaler().fit(matrix)
        scaled = scaler.transform(matrix)
        neighbors = NearestNeighbors(n_neighbors=min(count, len(matrix)), metric="euclidean")
        neighbors.fit(scaled)
        distances, indices = neighbors.kneighbors(scaler.transform(query))
        output = []
        for distance, index in zip(distances[0], indices[0]):
            item = dict(historical_years[int(index)])
            item["distance"] = round(float(distance), 6)
            item["similarity"] = round(1.0 / (1.0 + float(distance)), 6)
            output.append(item)
        return output


def build_risks(
    forecast: dict[str, Any],
    seasonal: dict[str, Any],
    enso: dict[str, Any],
    source_evidence: list[dict[str, Any]],
    *,
    confidence_factor: float,
) -> list[dict[str, Any]]:
    today = date.today()
    window_end = today + timedelta(days=int(forecast.get("forecast_days", 16)))
    minimum_temperature = float(forecast.get("minimum_temperature_c", 99))
    precipitation = float(forecast.get("precipitation_mm", 0))
    evapotranspiration = float(forecast.get("evapotranspiration_mm", 0))
    water_balance = precipitation - evapotranspiration
    blight_hours = int(forecast.get("blight_favorable_hours_48h", 0))
    enso_phase = str(enso.get("phase", "unknown"))
    enso_dry = "nino" in enso_phase.lower().replace("ñ", "n")

    frost_probability = 0.1
    if minimum_temperature <= 0:
        frost_probability = 0.9
    elif minimum_temperature <= 2:
        frost_probability = 0.7
    elif minimum_temperature <= 4:
        frost_probability = 0.4
    if enso_dry:
        frost_probability = min(1.0, frost_probability + 0.08)

    drought_probability = 0.15
    if water_balance <= -40:
        drought_probability = 0.85
    elif water_balance <= -20:
        drought_probability = 0.65
    elif water_balance < 0:
        drought_probability = 0.4
    seasonal_anomaly = float(seasonal.get("rainfall_anomaly_pct", 0))
    if enso_dry or seasonal_anomaly <= -15:
        drought_probability = min(1.0, drought_probability + 0.15)

    blight_probability = min(0.95, max(0.05, blight_hours / 24))
    common_limitations = [
        "Rules are decision support and have not been locally validated as a supervised classifier.",
        "No synthetic labels were used; probabilities are transparent rule scores.",
    ]

    return [
        _risk(
            "frost", frost_probability * confidence_factor, confidence_factor,
            today, window_end,
            {"minimum_temperature_c": minimum_temperature, "enso_phase": enso_phase},
            source_evidence,
            "frost-rule/2.0.0",
            "Review the local station and protect exposed areas before the forecast minimum.",
            common_limitations + ["Coarse climate products can smooth high-altitude extremes."],
        ),
        _risk(
            "drought", drought_probability * confidence_factor, confidence_factor,
            today, window_end,
            {
                "precipitation_mm": precipitation,
                "evapotranspiration_mm": evapotranspiration,
                "water_balance_mm": round(water_balance, 3),
                "seasonal_rainfall_anomaly_pct": seasonal_anomaly,
                "enso_phase": enso_phase,
            },
            source_evidence,
            "drought-water-balance-rule/2.0.0",
            "Prioritize soil moisture verification and postpone nutrient application if water is unavailable.",
            common_limitations,
        ),
        _risk(
            "late_blight", blight_probability * confidence_factor, confidence_factor,
            today, today + timedelta(days=2),
            {"favorable_hours_48h": blight_hours},
            source_evidence,
            "late-blight-hours-rule/2.0.0",
            "Inspect lower leaves and ask the technician to validate preventive action.",
            common_limitations + ["Weather suitability is not evidence that the pathogen is present."],
        ),
    ]


def _severity(probability: float) -> str:
    if probability >= 0.75:
        return "critical"
    if probability >= 0.55:
        return "high"
    if probability >= 0.30:
        return "medium"
    return "low"


def _risk(
    risk_type: str,
    probability: float,
    confidence: float,
    start: date,
    end: date,
    inputs: dict[str, Any],
    sources: list[dict[str, Any]],
    version: str,
    action: str,
    limitations: list[str],
) -> dict[str, Any]:
    probability = round(float(np.clip(probability, 0, 1)), 6)
    return {
        "type": risk_type,
        "score": {"value": probability, "unit": "probability_0_1"},
        "severity": _severity(probability),
        "confidence": {"value": round(confidence, 6), "unit": "probability_0_1"},
        "window": {"start": start.isoformat(), "end": end.isoformat(), "unit": "date"},
        "inputs": inputs,
        "sources": sources,
        "model_version": version,
        "recommended_action": action,
        "limitations": limitations,
    }
