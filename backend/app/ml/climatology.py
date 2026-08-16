"""
Climatologia: convierte veinte anos de NASA POWER en contexto accionable.

Un pronostico solo dice "van a caer 40 mm". Sin historia, ese numero no
significa nada: puede ser mucho o poco segun el sitio y la epoca. Con
historia se puede decir "40 mm es el percentil 8 de los ultimos veinte anos
para este mes", que si es una afirmacion util.

Tres cosas se calculan aqui:

  normal       que es lo normal en este punto para esta epoca del ano
  percentil    en que lugar de la distribucion historica cae lo que viene
  analogos     que anos se parecieron a este y que paso en ellos

Los analogos son la pieza mas valiosa y la mas honesta. En vez de pedirle a
un modelo que prediga a nueve meses -donde nadie acierta-, se buscan los
anos con la misma fase de El Nino y se muestra lo que efectivamente ocurrio.
Es razonamiento por casos: interpretable, verificable y con datos reales.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

# Indice Oceanico del Nino (ONI), pico del evento por temporada.
# Fuente: NOAA CPC. Positivo = El Nino, negativo = La Nina.
# Verificar contra la tabla oficial antes de citar en publico.
ONI_PICO = {
    2006: 1.0, 2007: -1.6, 2008: -0.7, 2009: 1.6, 2010: -1.6,
    2011: -1.1, 2012: 0.1, 2013: -0.4, 2014: 0.7, 2015: 2.6,
    2016: -0.7, 2017: -0.9, 2018: 0.9, 2019: 0.5, 2020: -1.0,
    2021: -1.0, 2022: -0.9, 2023: 2.0, 2024: -0.6, 2025: 0.3,
}

# el evento actual, del boletin vigente
ONI_ACTUAL = 1.3    # proyeccion de pico para 2026-27


def _por_ano_mes(serie: dict[str, float]) -> dict[tuple[int, int], list[float]]:
    """Agrupa una serie diaria YYYYMMDD por (ano, mes)."""
    grupos: dict[tuple[int, int], list[float]] = defaultdict(list)
    for fecha, valor in serie.items():
        grupos[(int(fecha[:4]), int(fecha[4:6]))].append(valor)
    return grupos


def normal(serie: dict[str, float], mes: int, agregacion: str = "suma") -> dict | None:
    """
    Que es normal en este punto para este mes, segun los ultimos veinte anos.
    Devuelve mediana y los percentiles que enmarcan la variabilidad.
    """
    grupos = _por_ano_mes(serie)
    valores = []
    for (_, m), vs in grupos.items():
        if m != mes or not vs:
            continue
        valores.append(sum(vs) if agregacion == "suma" else statistics.mean(vs))

    if len(valores) < 5:
        return None

    valores.sort()
    return {
        "mediana": round(statistics.median(valores), 1),
        "p10": round(_percentil(valores, 10), 1),
        "p90": round(_percentil(valores, 90), 1),
        "minimo": round(valores[0], 1),
        "maximo": round(valores[-1], 1),
        "anos": len(valores),
    }


def percentil_de(valor: float, serie: dict[str, float], mes: int,
                 agregacion: str = "suma") -> int | None:
    """
    En que percentil historico cae un valor. Es la forma de decir "esto no es
    normal" con un numero detras en vez de con un adjetivo.
    """
    grupos = _por_ano_mes(serie)
    referencia = []
    for (_, m), vs in grupos.items():
        if m != mes or not vs:
            continue
        referencia.append(sum(vs) if agregacion == "suma" else statistics.mean(vs))

    if len(referencia) < 5:
        return None
    debajo = sum(1 for v in referencia if v < valor)
    return round(debajo / len(referencia) * 100)


def _percentil(ordenados: list[float], p: float) -> float:
    if not ordenados:
        return 0.0
    k = (len(ordenados) - 1) * p / 100.0
    bajo, alto = int(k), min(int(k) + 1, len(ordenados) - 1)
    return ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (k - bajo)


def analogos(lluvia: dict[str, float], tmin: dict[str, float],
             oni_actual: float = ONI_ACTUAL, cuantos: int = 3) -> list[dict]:
    """
    Anos con una fase de El Nino parecida a la actual, y que paso en ellos
    durante los meses que vienen.

    Esta es la respuesta honesta a "que va a pasar en noviembre": no la
    prediccion de un modelo a nueve meses, sino el registro de lo que ocurrio
    las ultimas veces que el oceano estuvo asi.
    """
    hoy = date.today()
    meses_adelante = [((hoy.month + i - 1) % 12) + 1 for i in range(1, 5)]

    candidatos = sorted(
        ((ano, abs(oni - oni_actual)) for ano, oni in ONI_PICO.items()),
        key=lambda x: x[1],
    )[:cuantos]

    lluvia_mes = _por_ano_mes(lluvia)
    tmin_mes = _por_ano_mes(tmin)

    salida = []
    for ano, distancia in candidatos:
        acumulado, minimas = 0.0, []
        completo = True
        for m in meses_adelante:
            # los meses que caen despues de diciembre son del ano siguiente
            a = ano if m >= hoy.month else ano + 1
            vs_ll = lluvia_mes.get((a, m))
            vs_tm = tmin_mes.get((a, m))
            if not vs_ll or not vs_tm:
                completo = False
                break
            acumulado += sum(vs_ll)
            minimas.append(min(vs_tm))

        if not completo:
            continue

        salida.append({
            "ano": ano,
            "oni": ONI_PICO[ano],
            "fase": _fase(ONI_PICO[ano]),
            "parecido": round(1.0 - min(distancia / 2.0, 1.0), 2),
            "lluvia_mm": round(acumulado),
            "temperatura_minima_c": round(min(minimas), 1),
            "meses": meses_adelante,
        })
    return salida


def _fase(oni: float) -> str:
    if oni >= 1.5:
        return "El Nino fuerte"
    if oni >= 0.5:
        return "El Nino"
    if oni <= -1.5:
        return "La Nina fuerte"
    if oni <= -0.5:
        return "La Nina"
    return "Neutral"


def resumen(lluvia: dict[str, float], tmin: dict[str, float],
            lluvia_pronosticada: float | None = None) -> dict:
    """
    El bloque de climatologia que viaja en el paquete. Todo lo que se puede
    afirmar del sitio con veinte anos de satelite detras.
    """
    hoy = date.today()
    siguiente = (hoy.month % 12) + 1

    n_lluvia = normal(lluvia, siguiente, "suma")
    n_tmin = normal(tmin, siguiente, "media")
    casos = analogos(lluvia, tmin)

    pct = None
    if lluvia_pronosticada is not None:
        pct = percentil_de(lluvia_pronosticada, lluvia, siguiente, "suma")

    return {
        "mes_evaluado": siguiente,
        "anos_de_historia": len({f[:4] for f in lluvia}),
        "dias_de_historia": len(lluvia),
        "lluvia_normal_mm": n_lluvia,
        "temperatura_minima_normal_c": n_tmin,
        "percentil_lluvia_pronosticada": pct,
        "anos_analogos": casos,
        "fuente": "NASA POWER, comunidad agroclimatologia, resolución 0.5 grados",
        "advertencia_resolucion": (
            "El píxel de 0.5 grados promedía valles y montanas, así que suaviza "
            "los extremos locales. Sirve para saber que es normal aquí, no para "
            "predecir la helada de manana."
        ),
    }
