"""
SERENO — API.

    uvicorn app.main:app --reload

Documentacion interactiva en /docs
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import pandas as pd
from brotli_asgi import BrotliMiddleware
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .governance import disclosure
from .ml import package as pkg
from .risk import engine
from .schemas import Calidad, NuevaLectura, Package, RespuestaLectura

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
EXCEL = RAIZ / "data" / "data_ejemplo.csv.xlsx"

# Catalogo de lotes. En produccion sale de Postgres; para la demo, del Excel.
LOTES = {
    "nar-001": {
        "id": "nar-001",
        "nombre": "Lote El Rosal",
        "municipio": "Pasto, Narino",
        "cultivo": "papa",
        "variedad": "Diacol Capiro",
        "fuente": EXCEL,
    }
}

app = FastAPI(
    title="Sereno",
    version="0.1.0",
    description=(
        "Asistente agroclimatico para pequenos productores de papa. "
        "Sistema de apoyo a la decision: propone, no decide. "
        "Toda salida incluye trazabilidad e incertidumbre."
    ),
)

app.add_middleware(BrotliMiddleware, quality=5, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origenes,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter(prefix="/v1")

# cache de paquetes en memoria; en produccion es la tabla packages
_cache: dict[str, Package] = {}
_lecturas: dict[str, dict] = {}


def _cargar(lote_id: str) -> pd.DataFrame:
    meta = LOTES.get(lote_id)
    if meta is None:
        raise HTTPException(404, f"No existe el lote {lote_id}")
    df = pd.read_excel(meta["fuente"])
    extra = [v for v in _lecturas.values() if v["plot_id"] == lote_id]
    if extra:
        df = pd.concat([df, pd.DataFrame([
            {"Latitud": e["lat"], "Longitud": e["lon"],
             "N": e["N_raw"], "p": e["P_raw"], "k": e["K_raw"]}
            for e in extra
        ])], ignore_index=True)
    return df


@v1.get("/plots")
async def listar_lotes():
    return {"plots": [
        {"id": m["id"], "nombre": m["nombre"], "municipio": m["municipio"],
         "cultivo": m["cultivo"], "mediciones": len(_cargar(k))}
        for k, m in LOTES.items()
    ]}


@v1.get("/plots/{lote_id}/package", response_model=Package)
async def paquete(lote_id: str, refrescar: bool = False):
    """
    Todo lo necesario para operar el lote sin red: suelo, zonas, receta
    ajustada por clima, riesgos y respuestas de voz precomputadas.
    """
    if not refrescar and lote_id in _cache:
        return _cache[lote_id]

    meta = LOTES.get(lote_id)
    if meta is None:
        raise HTTPException(404, f"No existe el lote {lote_id}")

    p = await pkg.construir(_cargar(lote_id), meta)
    _cache[lote_id] = p
    return p


@v1.get("/plots/{lote_id}/risk")
async def riesgos(lote_id: str):
    """Solo los riesgos, para refrescar sin recalcular el suelo."""
    meta = LOTES.get(lote_id)
    if meta is None:
        raise HTTPException(404, f"No existe el lote {lote_id}")
    df = _cargar(lote_id)
    lat, lon = float(df.Latitud.median()), float(df.Longitud.median())
    rs, est, degradado = await engine.evaluar(lat, lon)
    return {"riesgos": rs, "estacional": est, "degradado": degradado,
            "generado": datetime.now(timezone.utc)}


@v1.post("/readings", response_model=RespuestaLectura)
async def ingesta(lectura: NuevaLectura):
    """
    Ingesta de una medicion. Idempotente por client_id: reintentar desde un
    telefono sin senal no duplica nada.
    """
    from .ml import soil

    meta = LOTES.get(lectura.plot_id)
    if meta is None:
        raise HTTPException(404, f"No existe el lote {lectura.plot_id}")

    if lectura.client_id in _lecturas:
        return RespuestaLectura(
            id=f"rd-{lectura.client_id[:8]}",
            calidad=Calidad(valida=True, sospechoso=False, confianza=1.0,
                            motivo="Ya estaba registrada."),
            recalcular=False,
        )

    df = _cargar(lectura.plot_id)
    valida, motivo = soil.calidad_de_punto(
        lectura.lat, lectura.lon,
        float(df.Latitud.median()), float(df.Longitud.median()),
    )

    if valida:
        _lecturas[lectura.client_id] = lectura.model_dump()
        _cache.pop(lectura.plot_id, None)   # el paquete queda viejo

    return RespuestaLectura(
        id=f"rd-{lectura.client_id[:8]}",
        calidad=Calidad(valida=valida, sospechoso=False,
                        confianza=0.94 if valida else 0.11, motivo=motivo),
        recalcular=valida,
    )


@v1.get("/governance")
async def gobernanza():
    """Que es este sistema, que no hace, y bajo que marco. AI Act art. 50."""
    return disclosure.ficha()


@app.get("/health")
async def health():
    return {"ok": True, "servicio": "sereno", "version": app.version}


app.include_router(v1)
