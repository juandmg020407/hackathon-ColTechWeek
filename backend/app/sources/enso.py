"""
Estado de ENSO (El Nino / La Nina).

NOAA CPC publica el diagnostico una vez al mes, en PDF y HTML, sin API en
JSON. Para un sistema que corre en 2G no vale la pena raspar una pagina en
el camino critico: se guarda el boletin vigente con su fecha y su fuente, y
se actualiza cuando sale el siguiente.

Es una decision consciente y esta declarada en la respuesta: el usuario ve
cuando se actualizo por ultima vez y de donde salio.

Actualizar mensualmente desde:
https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml
"""

from __future__ import annotations

from datetime import date

# Boletin vigente. Verificado el 15 de agosto de 2026.
BOLETIN = {
    "fenomeno": "El Niño",
    "estado": "activo y fortaleciéndose",
    "alerta": "Alerta de El Niño",
    "anomalia_nino34_c": 0.7,
    "prob_persiste_invierno": 0.97,
    "prob_muy_fuerte": 0.63,
    "pico_esperado": "noviembre 2026 a enero 2027",
    "actualizado": date(2026, 8, 4),
    "fuente": "NOAA Climate Prediction Center",
    "url": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml",
}

# Que significa cada fase en la region andina colombiana.
# El Nino en el altiplano: menos lluvia, cielos despejados, mas heladas.
IMPLICACION = {
    "El Niño": (
        "En el altiplano nariñense El Niño trae menos lluvia y noches más "
        "despejadas. Menos nubes de noche significa más heladas, y menos "
        "lluvia significa que el abono que se aplica no se alcanza a "
        "aprovechar."
    ),
    "La Niña": (
        "En el altiplano nariñense La Niña trae más lluvia de la normal. "
        "Sube el riesgo de gota y de que el abono se lave antes de que la "
        "mata lo tome."
    ),
    "Neutral": (
        "Sin fenómeno activo. Las condiciones deberían parecerse al promedio "
        "de los últimos años para esta época."
    ),
}


def estado() -> dict:
    b = dict(BOLETIN)
    b["implicacion_regional"] = IMPLICACION.get(b["fenomeno"], IMPLICACION["Neutral"])
    b["dias_desde_actualizacion"] = (date.today() - b["actualizado"]).days
    return b
