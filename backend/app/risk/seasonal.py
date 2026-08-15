"""
R4 - Contexto estacional (ENSO + pronostico a nueve meses).

Este es el motor que justifica el giro del producto. Los otros miran dias;
este mira el ciclo completo del cultivo.

La papa en el altiplano narinense tarda unos cinco meses de siembra a
cosecha. Un pronostico a 16 dias no alcanza a cubrir ni una tercera parte.
SEAS5 llega a nueve meses, asi que si podemos decirle a alguien que va a
sembrar en septiembre que su cosecha cae en el pico de El Nino.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..schemas import Estacional, Fuente, PorQue, Riesgo
from ..sources import enso

# meses del ciclo de la papa que mas sufren con deficit hidrico:
# tuberizacion y llenado de tuberculo
CICLO_CRITICO_MESES = 3


def contexto(lat: float, lon: float, estacional_raw: dict | None) -> Estacional:
    """El bloque `estacional` del paquete: que fenomeno hay y que significa aca."""
    e = enso.estado()

    implicacion = e["implicacion_regional"]
    if e["fenomeno"] == "El Nino" and e.get("prob_muy_fuerte", 0) >= 0.5:
        implicacion += (
            f" Se espera que pegue mas duro entre {e['pico_esperado']}, "
            f"justo cuando la papa sembrada ahora este llenando tuberculo."
        )

    return Estacional(
        fenomeno=e["fenomeno"],
        estado=e["estado"],
        anomalia_nino34_c=e["anomalia_nino34_c"],
        prob_muy_fuerte=e["prob_muy_fuerte"],
        pico_esperado=e["pico_esperado"],
        implicacion_local=implicacion,
        horizonte_meses=9,
        fuente=Fuente(
            nombre=e["fuente"],
            consultado=datetime.combine(e["actualizado"], datetime.min.time(), timezone.utc),
            url=e["url"],
        ),
    )


def evaluar(lat: float, lon: float, estacional_raw: dict | None) -> Riesgo | None:
    """Convierte el contexto estacional en una alerta accionable, si aplica."""
    e = enso.estado()
    if e["fenomeno"] == "Neutral":
        return None

    prob = e.get("prob_muy_fuerte") or 0.0
    if prob >= 0.6:
        severidad = "alta"
    elif prob >= 0.35:
        severidad = "media"
    else:
        severidad = "baja"

    # si SEAS5 esta disponible, se mira el deficit de lluvia proyectado
    deficit = _deficit_proyectado(estacional_raw)
    if deficit is not None and deficit < -25 and severidad == "alta":
        severidad = "critica"

    # la dispersion del ensemble manda sobre la confianza: si los 51
    # miembros no se ponen de acuerdo, no vamos a fingir que si
    dispersion = dispersion_ensemble(estacional_raw)
    confianza = "media"
    if dispersion is not None:
        confianza = "media" if dispersion < 35 else "baja"

    seco = e["fenomeno"] == "El Nino"
    return Riesgo(
        id=f"rk-estacional-{e['actualizado'].isoformat()}",
        tipo="estacional",
        severidad=severidad,
        probabilidad=round(e.get("prob_persiste_invierno", 0.9), 2),
        confianza=confianza,
        ventana={"desde": e["actualizado"].isoformat(), "hasta": "2027-01-31"},
        titulo=f"Viene {e['fenomeno']} y va a pegar duro",
        resumen=(
            f"{e['fenomeno']} ya esta activo. Hay {int(prob * 100)} por ciento de "
            f"probabilidad de que sea muy fuerte, con lo peor entre "
            f"{e['pico_esperado']}. " + e["implicacion_regional"]
        ),
        que_hacer=(
            [
                "Piense la siembra para que el llenado de tuberculo no caiga en lo mas seco.",
                "Suba el potasio: ayuda a la mata a aguantar frio y falta de agua.",
                "Guarde agua ahora si tiene con que. Reservorio, tanque, lo que sea.",
                "No se exceda con el nitrogeno: sin lluvia no se aprovecha y se pierde la plata.",
            ]
            if seco
            else [
                "Prepare drenajes: el exceso de agua pudre el tuberculo.",
                "Revise el calendario de fungicida: con mas lluvia la gota aparece antes.",
                "Fraccione el abono en mas aplicaciones para que no se lave.",
            ]
        ),
        por_que=PorQue(
            modelo="seasonal/v1",
            entradas={
                "fenomeno": e["fenomeno"],
                "anomalia_nino34_c": e["anomalia_nino34_c"],
                "prob_muy_fuerte": prob,
                "prob_persiste_invierno": e.get("prob_persiste_invierno"),
                "deficit_lluvia_proyectado_pct": deficit,
                "dispersion_ensemble_pct": dispersion,
                "boletin_dias_de_antiguedad": e["dias_desde_actualizacion"],
            },
            regla=(
                "Estado ENSO del boletin vigente de NOAA CPC, cruzado con el "
                "pronostico estacional ECMWF SEAS5 a nueve meses para el punto "
                "del lote. La severidad sube si el deficit de lluvia proyectado "
                "supera el 25 por ciento."
            ),
            fuentes=[
                Fuente(nombre=e["fuente"], url=e["url"],
                       consultado=datetime.combine(e["actualizado"], datetime.min.time(), timezone.utc)),
                Fuente(nombre="Open-Meteo Seasonal (ECMWF SEAS5)",
                       consultado=datetime.now(timezone.utc)),
            ],
        ),
    )


def _deficit_proyectado(raw: dict | None) -> float | None:
    """
    Deficit de lluvia de los meses criticos del ciclo, en porcentaje respecto
    al promedio de todo el horizonte. Devuelve None si SEAS5 no responde.

    SEAS5 entrega dias, no meses, asi que agregamos por mes calendario.
    """
    if not raw:
        return None
    diario = raw.get("daily") or {}
    fechas = diario.get("time")
    lluvia = diario.get("precipitation_sum")
    if not fechas or not lluvia:
        return None

    por_mes: dict[str, float] = {}
    for f, v in zip(fechas, lluvia):
        if v is None:
            continue
        por_mes[f[:7]] = por_mes.get(f[:7], 0.0) + v

    # el mes en curso esta incompleto, se descarta
    meses = sorted(por_mes)[1:]
    if len(meses) < CICLO_CRITICO_MESES + 1:
        return None

    valores = [por_mes[m] for m in meses]
    promedio = sum(valores) / len(valores)
    if promedio <= 0:
        return None
    criticos = sum(valores[:CICLO_CRITICO_MESES]) / CICLO_CRITICO_MESES
    return round((criticos - promedio) / promedio * 100, 1)


def dispersion_ensemble(raw: dict | None) -> float | None:
    """
    Cuanto discrepan los 51 miembros del ensemble sobre la lluvia total.
    Mucha discrepancia significa poca confianza, y hay que decirlo.
    """
    if not raw:
        return None
    diario = raw.get("daily") or {}
    totales = []
    for clave, serie in diario.items():
        if "_member" not in clave or not clave.startswith("precipitation_sum"):
            continue
        validos = [v for v in serie if v is not None]
        if validos:
            totales.append(sum(validos))
    if len(totales) < 5:
        return None
    media = sum(totales) / len(totales)
    if media <= 0:
        return None
    var = sum((t - media) ** 2 for t in totales) / len(totales)
    return round(var ** 0.5 / media * 100, 1)
