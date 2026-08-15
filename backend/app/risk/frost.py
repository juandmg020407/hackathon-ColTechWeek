"""
R1 - Helada.

El riesgo mas grave para papa en el altiplano narinense, y el que trae
El Nino: cielos despejados y aire seco.

Helada de radiacion: en noches despejadas, sin viento y con aire seco, la
superficie irradia calor al espacio y se enfria por debajo de la temperatura
del aire. Por eso no basta con mirar la minima: hay que mirar nubosidad,
punto de rocio y viento juntos.

Ojo con la altura de medicion: el pronostico da temperatura a 2 m, y en una
noche de inversion termica el dosel del cultivo puede estar 2-4 grados mas
frio. Por eso el umbral de alerta esta por encima de cero.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..schemas import Fuente, PorQue, Riesgo

# temperatura del aire a 2 m bajo la cual el dosel puede llegar a cero
T_ALERTA = 4.0
T_GRAVE = 2.0
NUBOSIDAD_MAX = 40      # %  mas nubes = manta que retiene el calor
VIENTO_MAX = 2.5        # m/s  el viento mezcla el aire y evita la inversion
HORAS_NOCHE = (0, 1, 2, 3, 4, 5, 6)


def evaluar(lat: float, lon: float, clima: dict) -> Riesgo | None:
    h = (clima or {}).get("hourly")
    d = (clima or {}).get("daily")
    if not h or not d:
        return None

    noches: list[dict] = []
    tiempos = h["time"]

    for i, t in enumerate(tiempos):
        hora = int(t[11:13])
        if hora not in HORAS_NOCHE:
            continue
        temp = h["temperature_2m"][i]
        nubes = h["cloud_cover"][i]
        rocio = h["dew_point_2m"][i]
        viento = h["wind_speed_10m"][i]
        if temp is None:
            continue

        radiativa = nubes <= NUBOSIDAD_MAX and viento <= VIENTO_MAX
        if temp <= T_ALERTA and radiativa:
            noches.append({
                "fecha": t[:10], "hora": t[11:16], "t": temp,
                "nubes": nubes, "rocio": rocio, "viento": viento,
                "grave": temp <= T_GRAVE,
            })

    if not noches:
        return None

    fechas = sorted({n["fecha"] for n in noches})
    graves = [n for n in noches if n["grave"]]
    t_min = min(n["t"] for n in noches)

    if graves and len(fechas) >= 3:
        severidad, prob = "critica", 0.85
    elif graves:
        severidad, prob = "alta", 0.70
    elif len(fechas) >= 2:
        severidad, prob = "media", 0.50
    else:
        severidad, prob = "baja", 0.30

    # a mas de 10 dias vista el pronostico horario ya no manda tanto
    dias_vista = (datetime.fromisoformat(fechas[0]).date() - datetime.now().date()).days
    confianza = "alta" if dias_vista <= 3 else "media" if dias_vista <= 7 else "baja"

    plural = len(fechas) > 1
    return Riesgo(
        id=f"rk-helada-{fechas[0]}",
        tipo="helada",
        severidad=severidad,
        probabilidad=prob,
        confianza=confianza,
        ventana={"desde": fechas[0], "hasta": fechas[-1]},
        titulo=f"Riesgo de helada {'estas noches' if plural else 'esta noche'}",
        resumen=(
            f"{len(fechas)} {'noches' if plural else 'noche'} con cielo despejado, "
            f"aire seco y minima cerca de {t_min:.0f} grados. Es la combinacion "
            f"que quema la mata."
        ),
        que_hacer=[
            "Riegue en la tarde. El suelo humedo suelta calor de noche y sube la temperatura del surco.",
            "Si tiene con que, cubra las partes mas bajas del lote: el aire frio se acumula abajo.",
            "No aplique nitrogeno estos dias. La mata estresada no lo aprovecha.",
            "Si tiene papa proxima a cosecha, considere adelantarla.",
        ],
        por_que=PorQue(
            modelo="frost/v1",
            entradas={
                "noches_en_riesgo": len(fechas),
                "temperatura_minima_c": round(t_min, 1),
                "nubosidad_pct": [round(n["nubes"]) for n in noches[:5]],
                "punto_rocio_c": [round(n["rocio"], 1) for n in noches[:5]],
                "viento_ms": [round(n["viento"], 1) for n in noches[:5]],
            },
            regla=(
                f"Temperatura a 2 m bajo {T_ALERTA} C con nubosidad bajo {NUBOSIDAD_MAX}% "
                f"y viento bajo {VIENTO_MAX} m/s, en horas de madrugada. El umbral esta "
                f"por encima de cero porque el dosel se enfria mas que el aire a 2 m."
            ),
            fuentes=[Fuente(nombre="Open-Meteo Forecast", consultado=datetime.now(timezone.utc))],
        ),
    )
