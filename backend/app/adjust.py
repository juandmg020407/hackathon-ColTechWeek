"""
Ajuste de la receta segun lo que viene.

Aqui es donde el producto deja de ser un mapa de calor. El suelo dice que
tiene; el pronostico dice que va a pasar; la recomendacion sale del cruce.

Cada ajuste queda registrado con su factor y su motivo. Nunca se aplica en
silencio: el agricultor ve que se le cambio la receta y por que.

Los factores son conservadores y estan para calibrar con un agronomo. La
direccion de cada uno si esta respaldada:

  - Sin agua, el nitrogeno aplicado no se disuelve ni se absorbe: se
    volatiliza. Aplicar la dosis completa en sequia es tirar plata.
  - El potasio regula el potencial osmotico de la celula y el cierre
    estomatico. Sube la tolerancia de la planta al frio y a la falta de agua.
  - El fosforo es poco movil y se fija en andisoles: no tiene sentido
    moverlo por clima de corto plazo.
"""

from __future__ import annotations

from .schemas import Ajuste, Riesgo, Zona

FACTOR_N_SEQUIA = 0.75
FACTOR_K_HELADA = 1.15
FACTOR_K_SEQUIA = 1.10

GRAVES = ("alta", "critica")


def _es_fase_seca(riesgo: Riesgo) -> bool:
    """
    Si la fase de ENSO que viene es de las que secan el altiplano.

    Sale de `por_que.entradas`, que es el mismo dato que el agricultor ve
    cuando abre «¿por que?». La decision agronomica y su explicacion salen
    de la misma fuente, asi que no pueden separarse.
    """
    fenomeno = (riesgo.por_que.entradas or {}).get("fenomeno", "")
    return "Niño" in fenomeno or "Nino" in fenomeno


def calcular(riesgos: list[Riesgo]) -> list[Ajuste]:
    """Traduce los riesgos activos en ajustes de dosis."""
    ajustes: list[Ajuste] = []
    activos = {r.tipo: r for r in riesgos if r.severidad in GRAVES}

    seco = activos.get("sequia")
    helada = activos.get("helada")
    estacional = activos.get("estacional")

    # Un El Nino fuerte cuenta como sequia anunciada aunque el pronostico de
    # 16 dias todavia no la muestre. Se mira el fenomeno declarado en las
    # entradas del riesgo, no el titulo: el titulo es texto para el
    # agricultor y puede cambiar sin que cambie la agronomia.
    if estacional and not seco and _es_fase_seca(estacional):
        seco = estacional

    if seco:
        ajustes.append(Ajuste(
            nutriente="N", factor=FACTOR_N_SEQUIA, riesgo=seco.tipo,
            motivo=(
                "Se baja el nitrógeno porque sin agua no se alcanza a absorber. "
                "Se volatiliza y es plata perdida."
            ),
        ))
        ajustes.append(Ajuste(
            nutriente="K2O", factor=FACTOR_K_SEQUIA, riesgo=seco.tipo,
            motivo="Se sube el potasio: ayuda a la mata a manejar la falta de agua.",
        ))

    if helada:
        ajustes.append(Ajuste(
            nutriente="K2O", factor=FACTOR_K_HELADA, riesgo="helada",
            motivo="Se sube el potasio: mejora la tolerancia de la mata al frío.",
        ))

    return _fusionar(ajustes)


def _fusionar(ajustes: list[Ajuste]) -> list[Ajuste]:
    """Si dos riesgos tocan el mismo nutriente, se combinan los factores."""
    por_nutriente: dict[str, Ajuste] = {}
    for a in ajustes:
        previo = por_nutriente.get(a.nutriente)
        if previo is None:
            por_nutriente[a.nutriente] = a
            continue
        por_nutriente[a.nutriente] = Ajuste(
            nutriente=a.nutriente,
            factor=round(previo.factor * a.factor, 3),
            riesgo=previo.riesgo,
            motivo=f"{previo.motivo} {a.motivo}",
        )
    return list(por_nutriente.values())


def aplicar(zonas: list[Zona], ajustes: list[Ajuste]) -> list[Zona]:
    """
    Devuelve las zonas con las dosis ajustadas. No recalcula la mezcla:
    eso lo hace el optimizador aguas abajo con los kg/ha nuevos.
    """
    if not ajustes:
        return zonas

    factores = {a.nutriente: a.factor for a in ajustes}
    salida: list[Zona] = []
    for z in zonas:
        nuevos = {
            k: max(0, round(v * factores.get(k, 1.0)))
            for k, v in z.kg_ha.items()
        }
        salida.append(z.model_copy(update={"kg_ha": nuevos}))
    return salida
