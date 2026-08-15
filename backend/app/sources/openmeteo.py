"""
Cliente de Open-Meteo. Sin llave, CC-BY 4.0.

Regla de oro: nada de red en el camino critico. Todo pasa por cache con TTL
y, si la fuente falla, se devuelve lo ultimo bueno marcando degradado.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import settings

FORECAST = "https://api.open-meteo.com/v1/forecast"
SEASONAL = "https://seasonal-api.open-meteo.com/v1/seasonal"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

TZ = "America/Bogota"


@dataclass
class Entrada:
    valor: Any
    guardado: float
    ttl: int

    @property
    def fresca(self) -> bool:
        return (time.time() - self.guardado) < self.ttl


@dataclass
class Cache:
    """Cache en memoria. En produccion vive en Postgres, la interfaz es la misma."""
    datos: dict[str, Entrada] = field(default_factory=dict)

    def get(self, clave: str) -> tuple[Any, bool]:
        """Devuelve (valor, fresca). Un valor vencido se entrega igual: vale
        mas un pronostico de hace seis horas que una pantalla en blanco."""
        e = self.datos.get(clave)
        if e is None:
            return None, False
        return e.valor, e.fresca

    def set(self, clave: str, valor: Any, ttl: int) -> None:
        self.datos[clave] = Entrada(valor, time.time(), ttl)


cache = Cache()


async def _pedir(cliente: httpx.AsyncClient, url: str, params: dict, clave: str, ttl: int):
    """Pide, cachea y degrada con elegancia. Nunca lanza por fallo de red."""
    guardado, fresca = cache.get(clave)
    if fresca:
        return guardado, False

    try:
        r = await cliente.get(url, params=params, timeout=12.0)
        r.raise_for_status()
        datos = r.json()
        cache.set(clave, datos, ttl)
        return datos, False
    except Exception:
        # si hay algo viejo, sirve; si no, degradado explicito
        return guardado, True


async def clima(lat: float, lon: float, dias: int = 16) -> tuple[dict, bool]:
    """
    Pronostico horario y diario. Alimenta helada, gota, deslizamiento y la
    ventana de aplicacion.
    """
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "hourly": ",".join([
            "temperature_2m", "relative_humidity_2m", "dew_point_2m",
            "cloud_cover", "wind_speed_10m", "precipitation",
            "soil_moisture_0_to_7cm", "soil_temperature_0cm",
        ]),
        "daily": ",".join([
            "temperature_2m_min", "temperature_2m_max",
            "precipitation_sum", "et0_fao_evapotranspiration",
        ]),
        "forecast_days": dias,
        "timezone": TZ,
    }
    clave = f"clima:{round(lat, 3)}:{round(lon, 3)}:{dias}"
    async with httpx.AsyncClient() as c:
        return await _pedir(c, FORECAST, params, clave, settings.ttl_clima)


async def estacional(lat: float, lon: float, dias: int = 180) -> tuple[dict, bool]:
    """
    ECMWF SEAS5. Es lo que permite hablar del ciclo completo del cultivo y no
    de la semana: 180 dias cubren de agosto a febrero, justo el pico de
    El Nino 2026-27.

    La respuesta trae la media y ademas cada miembro del ensemble
    (`_member01`, `_member02`, ...). La dispersion entre miembros es la
    incertidumbre del pronostico, y la usamos en vez de inventarnosla.
    """
    params = {
        "latitude": round(lat, 2),
        "longitude": round(lon, 2),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "forecast_days": dias,
        "timezone": TZ,
    }
    clave = f"estacional:{round(lat, 2)}:{round(lon, 2)}:{dias}"
    async with httpx.AsyncClient() as c:
        return await _pedir(c, SEASONAL, params, clave, settings.ttl_estacional)


async def normales(lat: float, lon: float, desde: str, hasta: str) -> tuple[dict, bool]:
    """ERA5 historico, para saber que es normal en este sitio y que no lo es."""
    params = {
        "latitude": round(lat, 2),
        "longitude": round(lon, 2),
        "start_date": desde,
        "end_date": hasta,
        "daily": "temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration",
        "timezone": TZ,
    }
    clave = f"normales:{round(lat, 2)}:{round(lon, 2)}:{desde}:{hasta}"
    async with httpx.AsyncClient() as c:
        return await _pedir(c, ARCHIVE, params, clave, 30 * 24 * 3600)


async def contexto(lat: float, lon: float) -> dict:
    """Trae todo lo climatico de una vez, en paralelo."""
    (c, deg1), (e, deg2) = await asyncio.gather(
        clima(lat, lon), estacional(lat, lon)
    )
    return {"clima": c, "estacional": e, "degradado": deg1 or deg2}
