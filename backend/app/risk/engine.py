"""
Orquestador de riesgos.

Corre los motores, ordena por lo que mas importa y se queda con los tres
primeros. Mas de tres alertas es ruido: el agricultor deja de leerlas y el
sistema pierde su unica funcion.
"""

from __future__ import annotations

from ..schemas import Estacional, Riesgo
from ..sources import openmeteo
from . import blight, drought, frost, seasonal

MAX_ALERTAS = 3

PESO_SEVERIDAD = {"critica": 4.0, "alta": 3.0, "media": 2.0, "baja": 1.0}
PESO_CONFIANZA = {"alta": 1.0, "media": 0.8, "baja": 0.6}


def _prioridad(r: Riesgo) -> float:
    return PESO_SEVERIDAD[r.severidad] * r.probabilidad * PESO_CONFIANZA[r.confianza]


async def evaluar(lat: float, lon: float) -> tuple[list[Riesgo], Estacional, bool]:
    """
    Devuelve (riesgos ordenados, contexto estacional, degradado).

    Si el clima no llega, se devuelve igual el contexto estacional: ENSO
    esta cacheado y no depende de la red.
    """
    ctx = await openmeteo.contexto(lat, lon)
    clima = ctx.get("clima")
    estacional_raw = ctx.get("estacional")
    degradado = bool(ctx.get("degradado"))

    candidatos: list[Riesgo | None] = [
        seasonal.evaluar(lat, lon, estacional_raw),
    ]

    if clima:
        candidatos += [
            frost.evaluar(lat, lon, clima),
            drought.evaluar(lat, lon, clima),
            blight.evaluar(lat, lon, clima),
        ]

    riesgos = [r for r in candidatos if r is not None]
    riesgos.sort(key=_prioridad, reverse=True)

    contexto_est = seasonal.contexto(lat, lon, estacional_raw)
    return riesgos[:MAX_ALERTAS], contexto_est, degradado
