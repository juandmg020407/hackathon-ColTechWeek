"""
Ensambla el paquete completo de un lote: suelo + riesgos + receta ajustada.

Es lo que devuelve GET /v1/plots/{id}/package, y es la unica llamada que el
frontend hace para operar un lote entero. Objetivo de peso: bajo 20 KB
comprimido.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import adjust
from ..risk import engine
from ..schemas import (
    Ajuste, Climatologia, Grid, NextSample, Package, Plot, Producto, Punto,
    PuntoDescartado, Receta, RespuestaVoz, Ventana, Zona,
)
from ..sources import nasa
from . import climatology, soil

AVISO = (
    "La calibracion del sensor a ppm es provisional y no esta validada contra "
    "laboratorio. Los precios de fertilizante son de referencia."
)


def _suelo(df: pd.DataFrame, meta: dict) -> dict:
    """Corre M1 a M5 y devuelve las piezas del paquete que dependen del suelo."""
    lat0, lon0 = float(df.Latitud.median()), float(df.Longitud.median())
    df = df.copy()
    df["x"], df["y"] = soil.a_metros(df.Latitud.values, df.Longitud.values, lat0, lon0)

    df = soil.quality(df)
    descartados = df[~df.valido]
    ok = soil.calibrate(df[df.valido]).reset_index(drop=True)

    xs, ys, puntos, dentro, borde = soil.grid(ok)
    campos = soil.interpolate(ok, puntos)
    sigma = soil.incertidumbre(campos)

    # zonas de manejo sobre las celdas de adentro
    rasgos = np.column_stack([campos[c][0] for c in campos])
    norm = (rasgos - rasgos.mean(axis=0)) / (rasgos.std(axis=0) + 1e-9)
    from sklearn.cluster import KMeans
    etiquetas = np.full(len(puntos), -1)
    etiquetas[dentro] = KMeans(n_clusters=soil.N_ZONAS, n_init=10,
                               random_state=0).fit_predict(norm[dentro])

    area_celda = (soil.CELDA_M ** 2) / 10_000.0
    area_total = round(int(dentro.sum()) * area_celda, 2)

    zonas: list[Zona] = []
    for z in range(soil.N_ZONAS):
        m = etiquetas == z
        if not m.any():
            continue
        n_med = float(campos["N_ppm"][0][m].mean())
        p_med = float(campos["P_ppm"][0][m].mean())
        k_med = float(campos["K_ppm"][0][m].mean())
        area_z = round(int(m.sum()) * area_celda, 3)
        req, niveles = soil.requirement(n_med, p_med, k_med)
        zonas.append(Zona(
            id=f"z{z + 1}", area_ha=area_z, celdas=np.where(m)[0].tolist(),
            promedio_ppm={"N": round(n_med, 1), "P": round(p_med, 1), "K": round(k_med, 1)},
            nivel=niveles, kg_ha=req, productos=[], costo_cop=0,
        ))
    zonas.sort(key=lambda z: -z.area_ha)

    peor = int(np.argmax(np.where(dentro, sigma, -np.inf)))
    lat_s, lon_s = soil.a_grados(puntos[peor, 0], puntos[peor, 1], lat0, lon0)

    origen_lat, origen_lon = soil.a_grados(xs[0], ys[0], lat0, lon0)

    return {
        "lat0": lat0, "lon0": lon0, "area_total": area_total, "zonas": zonas,
        "grid": Grid(
            celda_m=soil.CELDA_M, cols=len(xs), rows=len(ys),
            origen=(round(float(origen_lat), 6), round(float(origen_lon), 6)),
            N=[round(float(v)) for v in campos["N_ppm"][0]],
            P=[round(float(v)) for v in campos["P_ppm"][0]],
            K=[round(float(v)) for v in campos["K_ppm"][0]],
            sigma=[round(float(v)) for v in sigma],
            sigma_umbral=soil.SIGMA_NO_SE,
            mask=[int(v) for v in dentro],
        ),
        "contorno": [
            (round(float(soil.a_grados(px, py, lat0, lon0)[0]), 6),
             round(float(soil.a_grados(px, py, lat0, lon0)[1]), 6))
            for px, py in borde
        ],
        "puntos": [
            Punto(lat=round(float(r.Latitud), 6), lon=round(float(r.Longitud), 6),
                  N=int(r.N), P=int(r.p), K=int(r.k), sospechoso=bool(r.sospechoso))
            for r in ok.itertuples()
        ],
        "descartados": [
            PuntoDescartado(
                lat=round(float(r.Latitud), 6), lon=round(float(r.Longitud), 6),
                motivo=f"Este punto queda a {r.dist_centro_m / 1000:.1f} km del lote. Se equivoco de finca?")
            for r in descartados.itertuples()
        ],
        "next_sample": NextSample(
            punto=(round(float(lat_s), 6), round(float(lon_s), 6)),
            razon="Es el punto del lote donde el modelo tiene menos certeza.",
            sigma=round(float(sigma[peor]), 1),
        ),
    }


def _ventana(riesgos: list) -> Ventana:
    """Cuando aplicar, mirando lo que viene."""
    hoy = datetime.now().date()
    for r in riesgos:
        if r.tipo == "helada" and r.severidad in ("alta", "critica"):
            return Ventana(desde=r.ventana["hasta"], hasta=r.ventana["hasta"],
                           motivo="Espere a que pase la helada. La mata estresada no aprovecha el abono.")
        if r.tipo == "sequia" and r.severidad in ("alta", "critica"):
            return Ventana(desde=hoy.isoformat(), hasta=hoy.isoformat(),
                           motivo="Aplique solo si tiene riego. Sin agua el abono no sirve.")
    return Ventana(desde=hoy.isoformat(), hasta=hoy.isoformat(),
                   motivo="No hay nada que lo impida en los proximos dias.")


def _voz(zonas: list[Zona], receta: Receta, riesgos: list,
         clima: Climatologia | None = None) -> list[RespuestaVoz]:
    """
    Respuestas precomputadas que viajan en el paquete. El telefono responde
    sin red si la pregunta hace match; solo va al agente si es algo nuevo.
    """
    principal = zonas[0] if zonas else None
    salida = [
        RespuestaVoz(
            id="v1", claves=["cuanto", "abono", "echo", "fertilizante", "abonar"],
            texto=(f"A su lote le faltan {soil.frase_bultos([p.model_dump() for p in principal.productos])}."
                   if principal else "Todavia no tengo suficientes mediciones de su lote."),
        ),
        RespuestaVoz(
            id="v2", claves=["cuando", "aplico", "dia", "lluvia", "echar"],
            texto=receta.ventana.motivo,
        ),
        RespuestaVoz(
            id="v3", claves=["cuanto", "cuesta", "vale", "precio", "plata"],
            texto=f"Le cuesta {receta.costo_total_cop:,} pesos.".replace(",", "."),
        ),
    ]
    if riesgos:
        r = riesgos[0]
        salida.append(RespuestaVoz(
            id="v4", claves=["que", "viene", "clima", "tiempo", "pasa", "cuidado"],
            texto=f"{r.titulo}. {r.resumen}",
        ))

    # el analogo historico: la respuesta honesta a "que va a pasar"
    if clima and clima.anos_analogos:
        a = clima.anos_analogos[0]
        salida.append(RespuestaVoz(
            id="v5",
            claves=["antes", "pasado", "otras", "veces", "historia", "similar"],
            texto=(
                f"La ultima vez que el clima estuvo asi fue en {a.ano}. "
                f"En los meses que siguieron cayeron {a.lluvia_mm} milimetros de lluvia "
                f"y la temperatura bajo hasta {a.temperatura_minima_c} grados."
            ),
        ))
    return salida


async def _climatologia(lat: float, lon: float) -> tuple[Climatologia | None, bool]:
    """Veinte anos de NASA POWER: que es normal aqui y que paso en anos parecidos."""
    hoy = datetime.now().date()
    desde = f"{hoy.year - 20}0101"
    hasta = f"{hoy.year - 1}1231"

    datos, degradado = await nasa.power(lat, lon, desde, hasta)
    if not datos:
        return None, degradado

    lluvia = nasa.serie(datos, "PRECTOTCORR")
    tmin = nasa.serie(datos, "T2M_MIN")
    if not lluvia or not tmin:
        return None, degradado

    return Climatologia(**climatology.resumen(lluvia, tmin)), degradado


async def construir(df: pd.DataFrame, meta: dict) -> Package:
    """Pipeline completo: suelo, clima historico, riesgos, ajuste y mezcla."""
    s = _suelo(df, meta)
    lat, lon = s["lat0"], s["lon0"]

    (riesgos, estacional, deg_riesgo), (clima_hist, deg_nasa) = await asyncio.gather(
        engine.evaluar(lat, lon),
        _climatologia(lat, lon),
    )
    degradado = deg_riesgo or deg_nasa

    # el ajuste se calcula ANTES de optimizar la mezcla, para que los
    # bultos ya reflejen lo que viene
    ajustes: list[Ajuste] = adjust.calcular(riesgos)
    zonas = adjust.aplicar(s["zonas"], ajustes)

    finales: list[Zona] = []
    for z in zonas:
        plan, costo = soil.blend(z.kg_ha, z.area_ha)
        finales.append(z.model_copy(update={
            "productos": [Producto(**p) for p in plan],
            "costo_cop": costo,
        }))

    total = sum(z.costo_cop for z in finales)
    generico, detalle = soil.costo_generico(s["area_total"])

    receta = Receta(
        costo_total_cop=total,
        costo_generico_cop=generico,
        ahorro_cop=generico - total,
        generico_detalle=detalle,
        ventana=_ventana(riesgos),
        ajustes=ajustes,
    )

    return Package(
        plot=Plot(
            id=meta["id"], nombre=meta["nombre"], municipio=meta["municipio"],
            area_ha=s["area_total"], cultivo=meta.get("cultivo", "papa"),
            variedad=meta.get("variedad"),
            centro=(round(lat, 6), round(lon, 6)),
        ),
        grid=s["grid"], contorno=s["contorno"], puntos=s["puntos"],
        descartados=s["descartados"], zonas=finales,
        next_sample=s["next_sample"], receta=receta,
        riesgos=riesgos, estacional=estacional, climatologia=clima_hist,
        voz=_voz(finales, receta, riesgos, clima_hist),
        generado=datetime.now(timezone.utc), ttl_horas=72,
        degradado=degradado, aviso=AVISO,
    )
