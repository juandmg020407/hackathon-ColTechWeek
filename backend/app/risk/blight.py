"""
R2 - Gota (tizon tardio, Phytophthora infestans).

La enfermedad numero uno de la papa en Colombia. En condiciones favorables
arrasa un lote en una semana.

Lo valioso: el riesgo se calcula SOLO CON CLIMA, sin ver la planta. El
patogeno necesita humedad libre sobre la hoja y un rango de temperatura
estrecho. Si se acumulan suficientes horas favorables, el brote viene.

Sigue la logica clasica de acumulacion de horas favorables por ventana
(familia Blitecast / unidades de severidad). Los umbrales son conservadores
y estan para calibrar con un fitopatologo.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..schemas import Fuente, PorQue, Riesgo

HR_MINIMA = 90.0        # % humedad relativa: agua libre sobre la hoja
T_MIN, T_MAX = 10.0, 24.0
VENTANA_H = 48
UMBRAL_MEDIO = 10       # horas favorables en 48 h
UMBRAL_ALTO = 18
UMBRAL_CRITICO = 26


def evaluar(lat: float, lon: float, clima: dict) -> Riesgo | None:
    h = (clima or {}).get("hourly")
    if not h:
        return None

    tiempos = h["time"]
    favorable = [
        1 if (hr is not None and t is not None and hr >= HR_MINIMA and T_MIN <= t <= T_MAX) else 0
        for hr, t in zip(h["relative_humidity_2m"], h["temperature_2m"])
    ]

    # ventana deslizante de 48 h: nos quedamos con el peor tramo
    mejor = 0
    inicio = 0
    corriendo = sum(favorable[:VENTANA_H])
    mejor, inicio = corriendo, 0
    for i in range(VENTANA_H, len(favorable)):
        corriendo += favorable[i] - favorable[i - VENTANA_H]
        if corriendo > mejor:
            mejor, inicio = corriendo, i - VENTANA_H + 1

    if mejor < UMBRAL_MEDIO:
        return None

    if mejor >= UMBRAL_CRITICO:
        severidad, prob = "critica", 0.85
    elif mejor >= UMBRAL_ALTO:
        severidad, prob = "alta", 0.70
    else:
        severidad, prob = "media", 0.50

    desde = tiempos[inicio][:10]
    hasta = tiempos[min(inicio + VENTANA_H, len(tiempos) - 1)][:10]
    dias_vista = (datetime.fromisoformat(desde).date() - datetime.now().date()).days
    confianza = "alta" if dias_vista <= 3 else "media" if dias_vista <= 7 else "baja"

    return Riesgo(
        id=f"rk-gota-{desde}",
        tipo="gota",
        severidad=severidad,
        probabilidad=prob,
        confianza=confianza,
        ventana={"desde": desde, "hasta": hasta},
        titulo="Condiciones para que aparezca la gota",
        resumen=(
            f"{mejor} horas seguidas de humedad alta con temperatura templada "
            f"entre el {desde[8:10]} y el {hasta[8:10]}. Es el clima que la gota "
            f"necesita para arrancar."
        ),
        que_hacer=[
            "Revise las hojas de abajo: la gota empieza por ahi, con manchas de borde claro.",
            "Si va a fumigar preventivo, hagalo ANTES de que entre la humedad, no despues.",
            "Consulte con el tecnico de la UMATA que producto usar y en que dosis.",
            "Evite regar por aspersion estos dias: moja la hoja y le ayuda al hongo.",
        ],
        por_que=PorQue(
            modelo="blight/v1",
            entradas={
                "horas_favorables_en_48h": mejor,
                "umbral_medio": UMBRAL_MEDIO,
                "umbral_alto": UMBRAL_ALTO,
                "condicion": f"HR >= {HR_MINIMA}% y {T_MIN} C <= T <= {T_MAX} C",
            },
            regla=(
                "Acumulacion de horas favorables en ventana de 48 h. Phytophthora "
                "infestans necesita agua libre sobre la hoja y temperatura templada."
            ),
            fuentes=[Fuente(nombre="Open-Meteo Forecast", consultado=datetime.now(timezone.utc))],
        ),
    )
