"""
R3 - Deficit hidrico.

Balance simple: lo que entra por lluvia contra lo que sale por
evapotranspiracion de referencia. Open-Meteo ya calcula la ET0 con el
metodo FAO-56, asi que no hay que estimarla.

Un balance negativo sostenido significa que la mata esta gastando mas agua
de la que recibe. Para papa eso pega justo donde duele: la tuberizacion
necesita humedad constante.

Y hay una consecuencia que el agricultor no siempre ve: sin agua, el
nitrogeno que se aplica no se disuelve ni se absorbe. Se volatiliza. Es
plata tirada.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..schemas import Fuente, PorQue, Riesgo

DEFICIT_MEDIO = -15.0     # mm acumulados en el horizonte
DEFICIT_ALTO = -35.0
DEFICIT_CRITICO = -60.0


def evaluar(lat: float, lon: float, clima: dict) -> Riesgo | None:
    d = (clima or {}).get("daily")
    if not d:
        return None

    lluvia = d.get("precipitation_sum") or []
    et0 = d.get("et0_fao_evapotranspiration") or []
    fechas = d.get("time") or []
    if not lluvia or not et0:
        return None

    pares = [(p, e) for p, e in zip(lluvia, et0) if p is not None and e is not None]
    if len(pares) < 7:
        return None

    entra = sum(p for p, _ in pares)
    sale = sum(e for _, e in pares)
    balance = entra - sale
    dias = len(pares)

    # racha mas larga sin lluvia util
    racha = maxima = 0
    for p, _ in pares:
        racha = racha + 1 if p < 1.0 else 0
        maxima = max(maxima, racha)

    if balance > DEFICIT_MEDIO and maxima < 7:
        return None

    if balance <= DEFICIT_CRITICO or maxima >= 12:
        severidad, prob = "critica", 0.85
    elif balance <= DEFICIT_ALTO or maxima >= 9:
        severidad, prob = "alta", 0.70
    else:
        severidad, prob = "media", 0.50

    return Riesgo(
        id=f"rk-sequía-{fechas[0]}",
        tipo="sequia",
        severidad=severidad,
        probabilidad=prob,
        confianza="media",
        ventana={"desde": fechas[0], "hasta": fechas[min(dias - 1, len(fechas) - 1)]},
        titulo="Le va a faltar agua",
        resumen=(
            f"En los próximos {dias} días la mata va a gastar {sale:.0f} milímetros "
            f"de agua y solo le entran {entra:.0f}. Van {abs(balance):.0f} milímetros "
            f"de menos"
            + (f", con {maxima} días seguidos sin lluvia util." if maxima >= 7 else ".")
        ),
        que_hacer=[
            "Si tiene riego, priorice las zonas más altas del lote: se secan primero.",
            "Aporque para tapar el surco. El suelo tapado pierde menos agua.",
            "Aplace el nitrógeno. Sin agua no se disuelve, se volatiliza y pierde la plata.",
            "Deje la maleza cortada en el surco como cobertura, no la saque.",
        ],
        por_que=PorQue(
            modelo="drought/v1",
            entradas={
                "dias_evaluados": dias,
                "lluvia_mm": round(entra, 1),
                "evapotranspiracion_mm": round(sale, 1),
                "balance_mm": round(balance, 1),
                "racha_seca_dias": maxima,
            },
            regla=(
                f"Balance hídrico = lluvia acumulada menos ET0 FAO-56. Alerta bajo "
                f"{DEFICIT_MEDIO} mm o con siete días seguidos de lluvia bajo 1 mm."
            ),
            fuentes=[Fuente(nombre="Open-Meteo Forecast (ET0 FAO-56)",
                            consultado=datetime.now(timezone.utc))],
        ),
    )
