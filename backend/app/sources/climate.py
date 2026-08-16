"""Open-Meteo, NASA POWER and versioned ENSO fusion."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..ml.climate import AnalogYearModel, build_risks
from ..repositories.contracts import CacheRepository
from .resilient import ResilientJSONSource, SourcePolicy, SourceResult

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


class ClimateFusion:
    def __init__(
        self,
        repository: CacheRepository,
        fixture_path: str | Path,
        *,
        external_enabled: bool = False,
        timeout_seconds: float = 5.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        common = dict(
            repository=repository,
            enabled=external_enabled,
            transport=transport,
        )
        self.open_meteo = ResilientJSONSource(
            name="Open-Meteo Forecast",
            url=OPEN_METEO_URL,
            policy=SourcePolicy(
                timeout_seconds=timeout_seconds, max_retries=max_retries, ttl_seconds=10_800
            ),
            **common,
        )
        self.nasa_power = ResilientJSONSource(
            name="NASA POWER",
            url=NASA_POWER_URL,
            policy=SourcePolicy(
                timeout_seconds=timeout_seconds, max_retries=max_retries, ttl_seconds=2_592_000
            ),
            **common,
        )
        self.analog_model = AnalogYearModel()

    async def evaluate(self, latitude: float, longitude: float) -> dict[str, Any]:
        today = date.today()
        forecast_result = await self.open_meteo.fetch(
            {
                "latitude": round(latitude, 4),
                "longitude": round(longitude, 4),
                "forecast_days": 16,
                "daily": (
                    "temperature_2m_min,temperature_2m_max,precipitation_sum,"
                    "et0_fao_evapotranspiration"
                ),
                "hourly": "temperature_2m,relative_humidity_2m,precipitation",
                "timezone": "America/Bogota",
            },
            offline_payload=self.fixture["open_meteo"],
            offline_fetched_at=self.fixture["generated_at"],
        )
        start = today.replace(year=today.year - 20).strftime("%Y%m%d")
        end = (today - timedelta(days=1)).strftime("%Y%m%d")
        power_result = await self.nasa_power.fetch(
            {
                "parameters": "T2M,T2M_MIN,PRECTOTCORR",
                "community": "AG",
                "longitude": round(longitude, 3),
                "latitude": round(latitude, 3),
                "start": start,
                "end": end,
                "format": "JSON",
            },
            offline_payload=self.fixture["nasa_power"],
            offline_fetched_at=self.fixture["generated_at"],
        )

        warnings: list[str] = []
        forecast = self._normalise_forecast(forecast_result, warnings)
        historical = self._normalise_power(power_result, warnings)
        seasonal = dict(self.fixture["seasonal"])
        enso = dict(self.fixture["enso"])
        enso_evidence = {
            "name": "NOAA Climate Prediction Center ENSO advisory",
            "url": enso["source_url"],
            "fetched_at": enso["published_at"],
            "degraded": False,
            "stale": False,
            "failed": False,
        }
        source_results = [forecast_result, power_result]
        source_evidence = [result.evidence() for result in source_results] + [enso_evidence]
        degraded = any(result.degraded for result in source_results)
        warnings.extend(result.warning for result in source_results if result.warning)
        confidence_factor = 0.65 if degraded else 0.90

        current_vector = {
            "rainfall_mm": float(seasonal["rainfall_mm"]),
            "minimum_temperature_c": float(forecast["minimum_temperature_c"]),
            "mean_temperature_c": float(seasonal["mean_temperature_c"]),
            "enso_index": float(enso["index_c"]),
        }
        analogs = self.analog_model.select(historical, current_vector)
        risks = build_risks(
            forecast,
            seasonal,
            enso,
            source_evidence,
            confidence_factor=confidence_factor,
        )
        return {
            "risks": risks,
            "seasonal_context": {
                "forecast": seasonal,
                "enso": enso,
                "analog_years": analogs,
                "analog_model": {
                    "name": "NearestNeighbors",
                    "version": self.analog_model.version,
                    "variables": list(self.analog_model.variables),
                    "normalization": "StandardScaler",
                },
            },
            "sources": source_evidence,
            "degraded": degraded,
            "warnings": list(dict.fromkeys(warnings)),
        }

    def _normalise_forecast(
        self, result: SourceResult, warnings: list[str]
    ) -> dict[str, Any]:
        payload = result.payload or {}
        if "minimum_temperature_c" in payload:
            return payload
        try:
            daily = payload["daily"]
            hourly = payload["hourly"]
            temperatures = [float(value) for value in hourly["temperature_2m"] if value is not None]
            humidity = [float(value) for value in hourly["relative_humidity_2m"] if value is not None]
            favorable = sum(
                1 for temperature, relative_humidity in zip(temperatures[:48], humidity[:48])
                if 10 <= temperature <= 24 and relative_humidity >= 90
            )
            return {
                "minimum_temperature_c": min(float(value) for value in daily["temperature_2m_min"]),
                "maximum_temperature_c": max(float(value) for value in daily["temperature_2m_max"]),
                "precipitation_mm": sum(float(value or 0) for value in daily["precipitation_sum"]),
                "evapotranspiration_mm": sum(
                    float(value or 0) for value in daily["et0_fao_evapotranspiration"]
                ),
                "blight_favorable_hours_48h": favorable,
                "forecast_days": len(daily["time"]),
            }
        except (KeyError, TypeError, ValueError) as error:
            warnings.append(
                f"No se pudo normalizar la respuesta de Open-Meteo ({error}); se usó el fixture."
            )
            return dict(self.fixture["open_meteo"])

    def _normalise_power(
        self, result: SourceResult, warnings: list[str]
    ) -> list[dict[str, Any]]:
        payload = result.payload or {}
        if "historical_years" in payload:
            return list(payload["historical_years"])
        try:
            parameters = payload["properties"]["parameter"]
            buckets: dict[int, dict[str, list[float]]] = {}
            for key, rainfall in parameters["PRECTOTCORR"].items():
                year = int(key[:4])
                buckets.setdefault(year, {"rain": [], "min": [], "mean": []})
                if float(rainfall) > -900:
                    buckets[year]["rain"].append(float(rainfall))
                minimum = float(parameters["T2M_MIN"].get(key, -999))
                mean = float(parameters["T2M"].get(key, -999))
                if minimum > -900:
                    buckets[year]["min"].append(minimum)
                if mean > -900:
                    buckets[year]["mean"].append(mean)
            historical = []
            for year, values in buckets.items():
                if not all(values.values()):
                    continue
                historical.append({
                    "year": year,
                    "rainfall_mm": sum(values["rain"]),
                    "minimum_temperature_c": min(values["min"]),
                    "mean_temperature_c": sum(values["mean"]) / len(values["mean"]),
                    "enso_index": 0.0,
                    "enso_note": "ENSO index unavailable in NASA POWER response",
                })
            if not historical:
                raise ValueError("no complete years")
            return historical
        except (KeyError, TypeError, ValueError) as error:
            warnings.append(
                f"No se pudo normalizar la respuesta de NASA POWER ({error}); se usó el fixture."
            )
            return list(self.fixture["nasa_power"]["historical_years"])
