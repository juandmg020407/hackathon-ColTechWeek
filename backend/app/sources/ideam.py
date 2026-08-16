"""Observación de estaciones del IDEAM a través de la API abierta de datos.gov.co.

Open-Meteo y NASA POWER son productos de modelo: interpolan y reanalizan. El
IDEAM opera pluviómetros y termómetros físicos, y publica sus lecturas como
datasets Socrata sin llave de API. Esta fuente aporta lo que a las otras dos les
falta —una observación real cerca del lote— y sirve para contrastar el modelo
contra el instrumento.

No alimenta las reglas de riesgo: es contexto observado y se presenta como tal.
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..repositories.contracts import CacheRepository
from .resilient import ResilientJSONSource, SourcePolicy, SourceResult

SOCRATA_ROOT = "https://www.datos.gov.co/resource"

# Un dataset por variable. El identificador es el recurso Socrata publicado por
# el IDEAM en el portal de datos abiertos de Colombia.
DATASETS: dict[str, dict[str, str]] = {
    "precipitation": {"resource": "s54a-sgyg", "unit": "mm", "label": "Precipitación"},
    "air_temperature": {"resource": "sbwg-7ju4", "unit": "°C", "label": "Temperatura del aire a 2 m"},
    "relative_humidity": {"resource": "uext-mhny", "unit": "%", "label": "Humedad relativa a 2 m"},
}

PORTAL_URL = "https://www.datos.gov.co/browse?q=IDEAM"
ENVELOPE = "rows"


def _distance_km(latitude: float, longitude: float, other_lat: float, other_lon: float) -> float:
    """Distancia plana local. A esta escala la diferencia con Haversine es de metros."""
    delta_lat = (latitude - other_lat) * 111.32
    delta_lon = (longitude - other_lon) * 111.32 * math.cos(math.radians(latitude))
    return math.hypot(delta_lat, delta_lon)


def _unique_by_timestamp(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Serie deduplicada por marca de tiempo.

    El dataset reexpone la misma lectura varias veces: se han observado 19
    registros idénticos para un mismo instante y sensor. Sumarlos sin deduplicar
    inflaba la lluvia acumulada un 31 % en la estación de Pasto (45,4 mm frente a
    los 34,6 mm reales), así que la deduplicación no es una limpieza cosmética.
    """
    series: dict[str, float] = {}
    for row in rows:
        stamp = row.get("fechaobservacion")
        raw = row.get("valorobservado")
        if not stamp or raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        series.setdefault(str(stamp), value)
    return series


class IdeamStationSource:
    """Selecciona la estación activa más cercana y resume lo que observó."""

    version = "ideam-socrata-station/1.0.0"
    operator = "IDEAM · Instituto de Hidrología, Meteorología y Estudios Ambientales"

    def __init__(
        self,
        repository: CacheRepository,
        fixture_path: str | Path,
        *,
        external_enabled: bool = False,
        timeout_seconds: float = 8.0,
        max_retries: int = 1,
        window_days: int = 30,
        search_radius_deg: float = 0.25,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        self.enabled = external_enabled
        self.window_days = window_days
        self.search_radius_deg = search_radius_deg
        # TTL largo a propósito: una estación publica cada diez minutos, pero el
        # package no necesita ese detalle y cada consulta mueve cientos de KB.
        policy = SourcePolicy(
            timeout_seconds=timeout_seconds, max_retries=max_retries, ttl_seconds=21_600
        )
        self._sources = {
            variable: ResilientJSONSource(
                name=f"IDEAM · {meta['label']}",
                url=f"{SOCRATA_ROOT}/{meta['resource']}.json",
                repository=repository,
                policy=policy,
                enabled=external_enabled,
                transport=transport,
                list_envelope_key=ENVELOPE,
            )
            for variable, meta in DATASETS.items()
        }

    async def observe(
        self, latitude: float, longitude: float, *, today: date | None = None
    ) -> dict[str, Any]:
        """Contexto observado alrededor del lote, o el fixture si no hay red."""
        if not self.enabled:
            return self._offline("el acceso a Internet está desactivado")

        today = today or date.today()
        station, discovery = await self._nearest_station(latitude, longitude, today)
        if station is None:
            return self._offline(discovery)

        # Las tres variables son datasets independientes: en serie costaban
        # ~7 s de reloj contra Socrata, y en paralelo cuestan lo que la más
        # lenta. El recálculo de un lote ya espera al GP; no debe esperar
        # además tres viajes encadenados.
        variables = list(DATASETS)
        results: list[SourceResult] = list(await asyncio.gather(
            *(self._series(variable, station["code"], today) for variable in variables)
        ))
        measurements: dict[str, Any] = {}
        for variable, result in zip(variables, results):
            rows = (result.payload or {}).get(ENVELOPE) or []
            summary = self._summarise(variable, _unique_by_timestamp(rows), len(rows))
            if summary:
                summary["unit"] = DATASETS[variable]["unit"]
                measurements[variable] = summary

        if not measurements:
            return self._offline("las series de la estación llegaron vacías")

        degraded = any(result.degraded for result in results) or discovery == "degraded"
        warnings = [result.warning for result in results if result.warning]
        last_seen = max(
            (item["last_observation"] for item in measurements.values() if item.get("last_observation")),
            default=None,
        )
        lag_days = self._lag_days(last_seen, today)

        return {
            "available": True,
            "station": station,
            "window": {
                "days_requested": self.window_days,
                "until": today.isoformat(),
            },
            "measurements": measurements,
            "last_observation": last_seen,
            "lag_days": lag_days,
            "degraded": degraded,
            "source_version": self.version,
            "note": (
                "Observación de estaciones físicas del IDEAM, no un pronóstico. "
                "No alimenta las reglas de riesgo: sirve para contrastar los "
                "productos de modelo contra un instrumento real cercano."
            ),
            "limitations": self._limitations(station, measurements, lag_days),
            "sources": [self._evidence(station, last_seen, degraded)],
            "warnings": [warning for warning in warnings if warning],
        }

    async def _nearest_station(
        self, latitude: float, longitude: float, today: date
    ) -> tuple[dict[str, Any] | None, str]:
        """La estación con dato reciente más próxima al lote.

        Se filtra por caja numérica sobre latitud y longitud en vez de por
        municipio: el lote no tiene por qué caer en el mismo municipio que su
        estación más cercana, y el nombre de estación trae espacios
        inconsistentes que lo hacen mal identificador.
        """
        since = (today - timedelta(days=7)).isoformat()
        source = self._sources["precipitation"]
        result = await source.fetch({
            "$select": "nombreestacion,codigoestacion,latitud,longitud,max(fechaobservacion) as ultima",
            "$where": (
                f"latitud between {latitude - self.search_radius_deg} "
                f"and {latitude + self.search_radius_deg} "
                f"AND longitud between {longitude - self.search_radius_deg} "
                f"and {longitude + self.search_radius_deg} "
                f"AND fechaobservacion > '{since}'"
            ),
            "$group": "nombreestacion,codigoestacion,latitud,longitud",
            "$limit": 200,
        })
        rows = (result.payload or {}).get(ENVELOPE) or []
        candidates = []
        for row in rows:
            try:
                station_lat = float(row["latitud"])
                station_lon = float(row["longitud"])
            except (KeyError, TypeError, ValueError):
                continue
            candidates.append((
                _distance_km(latitude, longitude, station_lat, station_lon),
                {
                    "code": str(row.get("codigoestacion", "")).strip(),
                    "name": " ".join(str(row.get("nombreestacion", "")).split()),
                    "latitude": station_lat,
                    "longitude": station_lon,
                    "last_seen": row.get("ultima"),
                },
            ))
        if not candidates:
            return None, "no se encontró una estación del IDEAM activa cerca del lote"
        distance, station = min(candidates, key=lambda item: item[0])
        station["distance_km"] = round(distance, 2)
        station["operator"] = self.operator
        station["candidates_considered"] = len(candidates)
        return station, "degraded" if result.degraded else "live"

    async def _series(self, variable: str, station_code: str, today: date) -> SourceResult:
        since = (today - timedelta(days=self.window_days)).isoformat()
        return await self._sources[variable].fetch({
            "$select": "fechaobservacion,valorobservado",
            "$where": f"codigoestacion='{station_code}' AND fechaobservacion > '{since}'",
            "$limit": 50_000,
        })

    def _summarise(
        self, variable: str, series: dict[str, float], raw_count: int
    ) -> dict[str, Any] | None:
        if not series:
            return None
        values = list(series.values())
        days = sorted({stamp[:10] for stamp in series})
        summary: dict[str, Any] = {
            "observations": len(series),
            "raw_rows": raw_count,
            "duplicate_rows_discarded": raw_count - len(series),
            "days_with_data": len(days),
            "first_observation": days[0],
            "last_observation": days[-1],
        }
        if variable == "precipitation":
            # Acumulado sobre los días QUE TIENEN dato, no sobre la ventana: la
            # estación de Pasto solo reportó 12 de los 30 días pedidos, y
            # presentar el total como mensual sería una lectura falsa.
            summary["accumulated"] = round(sum(values), 2)
        else:
            summary["minimum"] = round(min(values), 2)
            summary["maximum"] = round(max(values), 2)
            summary["mean"] = round(sum(values) / len(values), 2)
        return summary

    @staticmethod
    def _lag_days(last_seen: str | None, today: date) -> int | None:
        if not last_seen:
            return None
        try:
            return (today - datetime.fromisoformat(last_seen[:10]).date()).days
        except ValueError:
            return None

    def _limitations(
        self, station: dict[str, Any], measurements: dict[str, Any], lag_days: int | None
    ) -> list[str]:
        limitations = [
            f"La estación está a {station['distance_km']} km del lote: "
            "su lluvia y su temperatura no son las del lote.",
            "El dataset republica lecturas duplicadas; se deduplica por marca de "
            "tiempo antes de agregar.",
        ]
        rainfall = measurements.get("precipitation")
        if rainfall and rainfall["days_with_data"] < self.window_days:
            limitations.append(
                f"La serie cubre {rainfall['days_with_data']} de los "
                f"{self.window_days} días pedidos: el acumulado no es un total mensual."
            )
        if lag_days is not None and lag_days > 2:
            limitations.append(
                f"El último dato publicado tiene {lag_days} días de rezago."
            )
        return limitations

    def _evidence(
        self, station: dict[str, Any], last_seen: str | None, degraded: bool
    ) -> dict[str, Any]:
        return {
            "name": f"IDEAM · Estación {station['name']}",
            "url": PORTAL_URL,
            "fetched_at": last_seen,
            "degraded": degraded,
            "stale": degraded,
            "failed": False,
        }

    def _offline(self, reason: str) -> dict[str, Any]:
        """Fixture versionado, marcado como no actual.

        Devolver el fixture y decirlo es preferible a omitir la sección: el
        tablero muestra la misma estructura con o sin red, y la degradación
        viaja en la respuesta en vez de esconderse.
        """
        payload = dict(self.fixture)
        payload["available"] = True
        payload["degraded"] = True
        payload["source_version"] = self.version
        payload["warnings"] = [
            f"IDEAM: {reason}; se usa un fixture versionado. "
            "El dato no se presenta como actual."
        ]
        evidence = dict(payload.get("sources", [{}])[0]) if payload.get("sources") else {}
        evidence.update({"degraded": True, "stale": True, "failed": False})
        payload["sources"] = [evidence] if evidence else []
        return payload
