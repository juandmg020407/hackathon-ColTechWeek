"""
Schemas de la API. Espejo exacto de los tipos en FRONTEND.md.

Si algo cambia aqui, cambia alla, y se avisa antes de tocar codigo.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Nivel = Literal["critico", "bajo", "adecuado"]
Severidad = Literal["baja", "media", "alta", "critica"]
Confianza = Literal["baja", "media", "alta"]
TipoRiesgo = Literal["helada", "sequia", "gota", "incendio", "deslizamiento", "estacional"]


# --------------------------------------------------------------- suelo

class Plot(BaseModel):
    id: str
    nombre: str
    municipio: str
    area_ha: float
    cultivo: str
    variedad: str | None = None
    centro: tuple[float, float]


class Grid(BaseModel):
    celda_m: float
    cols: int
    rows: int
    origen: tuple[float, float]
    unidad: Literal["ppm"] = "ppm"
    N: list[int]
    P: list[int]
    K: list[int]
    sigma: list[int]
    sigma_umbral: float
    mask: list[int]


class Punto(BaseModel):
    lat: float
    lon: float
    N: int
    P: int
    K: int
    sospechoso: bool = False


class PuntoDescartado(BaseModel):
    lat: float
    lon: float
    motivo: str


class Producto(BaseModel):
    nombre: str
    bultos: int
    costo_cop: int


class Zona(BaseModel):
    id: str
    area_ha: float
    celdas: list[int]
    promedio_ppm: dict[str, float]
    nivel: dict[str, Nivel]
    kg_ha: dict[str, int]
    productos: list[Producto]
    costo_cop: int
    # con este id el frontend decide sobre la zona: POST /v1/decisions y
    # GET /v1/decisions/{id}/why. Toda propuesta nace pendiente.
    propuesta_id: str | None = None


class NextSample(BaseModel):
    punto: tuple[float, float]
    razon: str
    sigma: float


class Ventana(BaseModel):
    desde: str
    hasta: str
    motivo: str


class Receta(BaseModel):
    costo_total_cop: int
    costo_generico_cop: int
    ahorro_cop: int
    generico_detalle: str
    ventana: Ventana
    ajustes: list["Ajuste"] = Field(default_factory=list)


class Ajuste(BaseModel):
    """Un cambio a la receta motivado por un riesgo. Nunca se aplica en silencio."""
    nutriente: Literal["N", "P2O5", "K2O"]
    factor: float
    motivo: str
    riesgo: TipoRiesgo


# --------------------------------------------------------------- riesgo

class Fuente(BaseModel):
    nombre: str
    consultado: datetime | None = None
    url: str | None = None


class PorQue(BaseModel):
    """Trazabilidad. AI Act art. 12: entradas, modelo y fuentes de cada salida."""
    modelo: str
    entradas: dict[str, Any]
    regla: str
    fuentes: list[Fuente] = Field(default_factory=list)


class Riesgo(BaseModel):
    id: str
    tipo: TipoRiesgo
    severidad: Severidad
    probabilidad: float
    confianza: Confianza
    ventana: dict[str, str]
    titulo: str
    resumen: str
    que_hacer: list[str]
    por_que: PorQue
    requiere_confirmacion: bool = True


class Estacional(BaseModel):
    fenomeno: str
    estado: str
    anomalia_nino34_c: float | None = None
    prob_muy_fuerte: float | None = None
    pico_esperado: str | None = None
    implicacion_local: str
    horizonte_meses: int
    fuente: Fuente


# --------------------------------------------------------------- paquete

class AnoAnalogo(BaseModel):
    """Un ano pasado con la misma fase de El Nino, y que paso en el."""
    ano: int
    oni: float
    fase: str
    parecido: float
    lluvia_mm: int
    temperatura_minima_c: float
    meses: list[int]


class Climatologia(BaseModel):
    """Veinte anos de NASA POWER convertidos en contexto."""
    mes_evaluado: int
    anos_de_historia: int
    dias_de_historia: int
    lluvia_normal_mm: dict[str, float] | None = None
    temperatura_minima_normal_c: dict[str, float] | None = None
    percentil_lluvia_pronosticada: int | None = None
    anos_analogos: list[AnoAnalogo] = Field(default_factory=list)
    fuente: str
    advertencia_resolucion: str


class Package(BaseModel):
    plot: Plot
    grid: Grid
    contorno: list[tuple[float, float]]
    puntos: list[Punto]
    descartados: list[PuntoDescartado]
    zonas: list[Zona]
    next_sample: NextSample
    receta: Receta
    riesgos: list[Riesgo] = Field(default_factory=list)
    estacional: Estacional | None = None
    climatologia: Climatologia | None = None
    voz: list["RespuestaVoz"] = Field(default_factory=list)
    generado: datetime
    ttl_horas: int = 72
    degradado: bool = False
    aviso: str | None = None


class RespuestaVoz(BaseModel):
    id: str
    claves: list[str]
    texto: str
    audio: str | None = None


# --------------------------------------------------------------- ingesta

class NuevaLectura(BaseModel):
    plot_id: str
    lat: float
    lon: float
    N_raw: int
    P_raw: int
    K_raw: int
    medido_en: datetime
    client_id: str


class Calidad(BaseModel):
    valida: bool
    sospechoso: bool
    confianza: float
    motivo: str | None = None


class RespuestaLectura(BaseModel):
    ok: bool = True
    id: str
    calidad: Calidad
    recalcular: bool


# --------------------------------------------------------------- decisiones

Accion = Literal["aceptar", "rechazar", "derivar", "modificar"]


class Actor(BaseModel):
    tipo: Literal["agricultor", "tecnico", "sistema"]
    id: str


class NuevaDecision(BaseModel):
    propuesta_id: str
    accion: Accion
    actor: Actor
    modificacion: dict[str, Any] | None = None
    nota: str | None = None


class RespuestaDecision(BaseModel):
    ok: bool = True
    decision_id: str
    estado: Literal["aceptada", "rechazada", "derivada", "modificada", "pendiente_revision"]
    requiere_revision_tecnica: bool = False
    motivo: str | None = None
    notificado_a: str | None = None
    registrado_en: datetime


class PasoExplicacion(BaseModel):
    paso: str
    detalle: str
    confianza: Confianza | None = None
    nota: str | None = None


class Explicacion(BaseModel):
    propuesta: str
    que_recomendamos: str
    porque: list[PasoExplicacion]
    no_sabemos: list[str]          # nunca va vacio
    modelo: dict[str, str]
    decidido_por: Actor | None = None
    estado: str


Receta.model_rebuild()
Package.model_rebuild()
