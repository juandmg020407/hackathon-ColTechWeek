"""
IOmido — API.

    uvicorn app.main:app --reload

Documentacion interactiva en /docs
"""

from __future__ import annotations

import hashlib
import pathlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pandas as pd
from brotli_asgi import BrotliMiddleware
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .governance import audit, disclosure, proposals
from .ml import package as pkg
from .risk import engine
from .schemas import (
    Calidad, Explicacion, NuevaDecision, NuevaLectura, Package,
    RespuestaDecision, RespuestaLectura,
)

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
EXCEL = RAIZ / "data" / "data_ejemplo.csv.xlsx"

# Catalogo de lotes. En produccion sale de Postgres; para la demo, del Excel.
LOTES = {
    "nar-001": {
        "id": "nar-001",
        "nombre": "Lote El Rosal",
        "municipio": "Pasto, Nariño",
        "cultivo": "papa",
        "variedad": "Diacol Capiro",
        "fuente": EXCEL,
    }
}

@asynccontextmanager
async def ciclo(_: FastAPI):
    audit.preparar()      # esquema y candados del registro append-only
    yield


app = FastAPI(
    lifespan=ciclo,
    title="IOmido",
    version="0.1.0",
    description=(
        "Asistente agroclimatico para pequenos productores de papa. "
        "Sistema de apoyo a la decisión: propone, no decide. "
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


def _actualizado(lote_id: str) -> datetime:
    """
    Cuando cambiaron por ultima vez los datos del lote: la ultima lectura
    que entro, o la fecha del archivo si todavia no ha entrado ninguna.
    """
    meta = LOTES[lote_id]
    propias = [v["medido_en"] for v in _lecturas.values() if v["plot_id"] == lote_id]
    if propias:
        ultima = max(propias)
        if ultima.tzinfo is None:
            ultima = ultima.replace(tzinfo=timezone.utc)
        return ultima
    return datetime.fromtimestamp(meta["fuente"].stat().st_mtime, timezone.utc)


@v1.get("/plots")
async def listar_lotes():
    """
    La primera pantalla de la app. Va sin el modelo encima: el area sale de
    la misma geometria que el paquete pero sin correr el Proceso Gaussiano,
    para que abrir la lista no cueste siete segundos en 2G.
    """
    salida = []
    for k, m in LOTES.items():
        cacheado = _cache.get(k)
        if cacheado is not None:
            area, mediciones = cacheado.plot.area_ha, len(cacheado.puntos)
        else:
            r = pkg.resumen(_cargar(k))
            area, mediciones = r["area_ha"], r["mediciones"]
        salida.append({
            "id": m["id"], "nombre": m["nombre"], "municipio": m["municipio"],
            "area_ha": area, "cultivo": m["cultivo"], "variedad": m.get("variedad"),
            "mediciones": mediciones, "actualizado": _actualizado(k),
        })
    return {"plots": salida}


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
    # cada zona queda registrada como propuesta pendiente, con su costo
    # congelado: sin eso no hay nada que decidir ni que explicar despues
    proposals.registrar_del_paquete(p)
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


def _id_lectura(client_id: str) -> str:
    """
    Identificador estable derivado del client_id: el mismo reintento devuelve
    siempre el mismo id, que es lo que hace util la idempotencia rio abajo.
    """
    return "rd-" + hashlib.sha1(client_id.encode()).hexdigest()[:6]


@v1.post("/readings", response_model=RespuestaLectura)
async def ingesta(lectura: NuevaLectura):
    """
    Ingesta de una medicion. Idempotente por client_id: reintentar desde un
    telefono sin senal no duplica nada.

    Devuelve tres desenlaces distintos, y la diferencia importa:

      valida=False      la geometria dice que el punto no es de este lote.
                        Regla dura, no entra al modelo.
      sospechoso=True   el punto entra igual, pero el valor se sale del rango
                        del lote. Es una nota, no un error: con 18 muestras un
                        valor alto suele ser informacion.
      ninguno de los dos  todo en orden.
    """
    from .ml import soil

    meta = LOTES.get(lectura.plot_id)
    if meta is None:
        raise HTTPException(404, f"No existe el lote {lectura.plot_id}")

    if lectura.client_id in _lecturas:
        return RespuestaLectura(
            id=_id_lectura(lectura.client_id),
            calidad=Calidad(valida=True, sospechoso=False, confianza=1.0,
                            motivo="Ya estaba registrada."),
            recalcular=False,
        )

    df = _cargar(lectura.plot_id)
    valida, motivo = soil.calidad_de_punto(
        lectura.lat, lectura.lon,
        float(df.Latitud.median()), float(df.Longitud.median()),
    )

    sospechoso, nota = False, None
    if valida:
        sospechoso, nota = soil.rareza_de_punto(lectura.model_dump(), df)
        _lecturas[lectura.client_id] = lectura.model_dump()
        _cache.pop(lectura.plot_id, None)   # el paquete queda viejo

    confianza = 0.11 if not valida else 0.55 if sospechoso else 0.94
    return RespuestaLectura(
        id=_id_lectura(lectura.client_id),
        calidad=Calidad(valida=valida, sospechoso=sospechoso,
                        confianza=confianza, motivo=motivo or nota),
        recalcular=valida,
    )


# --------------------------------------------------------------- decisiones

@v1.post("/decisions", response_model=RespuestaDecision)
async def decidir(d: NuevaDecision):
    """
    Human-in-the-loop. El sistema propone; aqui alguien decide.

    Sobre el umbral de gasto configurado, aceptar no basta: la propuesta
    queda en `pendiente_revision` hasta que la firme un tecnico. Es la doble
    firma del articulo 14.

    De las cuatro acciones, `modificar` es la mas valiosa del sistema. Cuando
    un tecnico corrige una propuesta, esa correccion es una etiqueta de
    entrenamiento. Con 19 mediciones no se entrena nada; con miles de
    correcciones revisadas, si. La supervision humana es lo que llena el
    dataset.
    """
    fila = audit.propuesta(d.propuesta_id)
    if fila is None:
        raise HTTPException(
            404,
            f"No existe la propuesta {d.propuesta_id}. Pida el paquete del lote primero: "
            f"las propuestas se generan cuando se calcula la receta.",
        )

    estado, requiere, motivo = proposals.evaluar_decision(fila, d.accion, d.actor.tipo)
    decision_id = "dc-" + hashlib.sha1(
        f"{d.propuesta_id}|{d.actor.id}|{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:6]

    audit.guardar_decision(
        decision_id, d.propuesta_id, d.accion, estado,
        d.actor.tipo, d.actor.id, d.modificacion, d.nota,
    )
    audit.registrar(
        "decisión_registrada", "proposal", d.propuesta_id,
        entradas={"decision_id": decision_id, "accion": d.accion, "estado": estado,
                  "costo_cop": fila["costo_cop"], "modificacion": d.modificacion,
                  "nota": d.nota},
        actor=f"{d.actor.tipo}:{d.actor.id}",
    )

    return RespuestaDecision(
        decision_id=decision_id,
        estado=estado,
        requiere_revision_tecnica=requiere,
        motivo=motivo,
        notificado_a=settings.tecnico_de_guardia if requiere else None,
        registrado_en=datetime.now(timezone.utc),
    )


@v1.get("/decisions/{id_}/why", response_model=Explicacion)
async def por_que(id_: str):
    """
    El boton «¿por que me dice eso?».

    Acepta el id de la propuesta -para preguntar antes de decidir- o el de
    una decision ya tomada. `no_sabemos` nunca sale vacio.
    """
    propuesta_id = id_
    if id_.startswith("dc-"):
        registro = audit.decision(id_)
        if registro is None:
            raise HTTPException(404, f"No existe la decisión {id_}")
        propuesta_id = registro["proposal_id"]

    explicacion = proposals.explicar(propuesta_id)
    if explicacion is None:
        raise HTTPException(404, f"No existe la propuesta {propuesta_id}")
    return explicacion


@v1.get("/decisions/{id_}/history")
async def historial(id_: str):
    """
    El rastro completo de una propuesta: cada decision y cada linea de
    auditoria, en orden. Append-only, asi que lo que se ve aqui es todo lo
    que paso y nada se pudo reescribir.
    """
    if audit.propuesta(id_) is None:
        raise HTTPException(404, f"No existe la propuesta {id_}")
    return {
        "propuesta": id_,
        "decisiones": audit.decisiones_de(id_),
        "auditoria": audit.historial("proposal", id_),
    }


@v1.get("/governance")
async def gobernanza():
    """Que es este sistema, que no hace, y bajo que marco. AI Act art. 50."""
    return disclosure.ficha() | {"registro": audit.conteos()}


@app.get("/health")
async def health():
    return {"ok": True, "servicio": "sereno", "version": app.version}


app.include_router(v1)
