"""
Fuentes de la NASA.

POWER  https://power.larc.nasa.gov/api/temporal/daily/point
       20 anos de datos diarios agroclimaticos para un punto, sin llave.
       Es lo que convierte un pronostico en una afirmacion con contexto:
       sin historia no se puede decir "esto es lo mas seco en veinte anos".

FIRMS  https://firms.modaps.eosdis.nasa.gov/api/area/
       Focos de incendio activos casi en tiempo real. Llave gratis por correo.

Sobre la resolucion, que importa y hay que decirlo:

  NASA POWER trabaja a 0.5 grados. Ese pixel promedia valles y montanas, asi
  que suaviza los extremos locales: en veinte anos su minima mas baja para
  este punto es 4.7 C, cuando en el altiplano narinense si hay heladas. Por
  eso POWER se usa para CLIMATOLOGIA (que es normal aqui, en que percentil
  cae lo que viene, que paso en anos parecidos) y nunca para predecir la
  helada de manana. Eso lo hace Open-Meteo, que corre a resolucion de
  kilometros.

  Cada fuente para lo que sirve. La fusion de las tres escalas -veinte anos
  de satelite, pronostico de alta resolucion y la medicion puntual del
  sensor- es justamente lo que un dron no da.
"""

from __future__ import annotations

import httpx

from ..config import settings
from .openmeteo import _pedir, cache

POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"
FIRMS = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Parametros agroclimaticos. Maximo 20 por peticion.
PARAMETROS = [
    "T2M",                  # temperatura media a 2 m
    "T2M_MIN",              # minima
    "T2M_MAX",              # maxima
    "T2MDEW",               # punto de rocio
    "RH2M",                 # humedad relativa
    "PRECTOTCORR",          # precipitacion corregida
    "ALLSKY_SFC_SW_DWN",    # radiacion solar en superficie
    "WS2M",                 # viento a 2 m
]

TTL_POWER = 30 * 24 * 3600      # la climatologia no cambia de un dia a otro


async def power(lat: float, lon: float, desde: str, hasta: str) -> tuple[dict, bool]:
    """
    Serie diaria historica del punto. Fechas en formato YYYYMMDD.

    Veinte anos de historia son unos 7.300 dias por parametro: es la base de
    datos con la que se calculan percentiles, anomalias y anos analogos.
    """
    params = {
        "parameters": ",".join(PARAMETROS),
        "community": "AG",
        "longitude": round(lon, 3),
        "latitude": round(lat, 3),
        "start": desde,
        "end": hasta,
        "format": "JSON",
    }
    clave = f"power:{round(lat, 2)}:{round(lon, 2)}:{desde}:{hasta}"
    async with httpx.AsyncClient() as c:
        return await _pedir(c, POWER, params, clave, TTL_POWER)


async def incendios(lat: float, lon: float, radio_km: float = 50.0,
                    dias: int = 3) -> tuple[list[dict], bool]:
    """
    Focos activos alrededor del lote. Sin llave configurada devuelve vacio
    en vez de fallar: el sistema degrada, no se cae.
    """
    if not settings.firms_map_key:
        return [], False

    grados = radio_km / 111.0
    bbox = f"{lon - grados},{lat - grados},{lon + grados},{lat + grados}"
    url = f"{FIRMS}/{settings.firms_map_key}/VIIRS_SNPP_NRT/{bbox}/{dias}"
    clave = f"firms:{round(lat, 2)}:{round(lon, 2)}:{radio_km}:{dias}"

    guardado, fresca = cache.get(clave)
    if fresca:
        return guardado, False

    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(url, timeout=15.0)
            r.raise_for_status()
        filas = _csv(r.text)
        cache.set(clave, filas, settings.ttl_incendios)
        return filas, False
    except Exception:
        return (guardado or []), True


def _csv(texto: str) -> list[dict]:
    lineas = [l for l in texto.strip().splitlines() if l.strip()]
    if len(lineas) < 2:
        return []
    cabecera = [c.strip() for c in lineas[0].split(",")]
    salida = []
    for linea in lineas[1:]:
        campos = linea.split(",")
        if len(campos) != len(cabecera):
            continue
        salida.append(dict(zip(cabecera, campos)))
    return salida


def serie(datos: dict, parametro: str) -> dict[str, float]:
    """Extrae una serie de POWER quitando los faltantes (-999)."""
    if not datos:
        return {}
    crudo = (datos.get("properties") or {}).get("parameter", {}).get(parametro, {})
    return {k: v for k, v in crudo.items() if v is not None and v > -900}


def elevacion(datos: dict) -> float | None:
    """POWER devuelve la altura del pixel como tercera coordenada."""
    try:
        return float(datos["geometry"]["coordinates"][2])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
