"""
Pipeline de suelo: M1 a M5.

    M1  quality      control de calidad de las lecturas
    M2  calibrate    indice del sensor -> ppm
    M3  interpolate  Proceso Gaussiano -> mapa con incertidumbre
    M4  requirement  balance de nutrientes -> kg/ha
    M5  blend        optimizacion de la mezcla -> bultos y pesos

Un hallazgo que define todo el modulo: en los datos reales del sensor la
correlacion entre P y K es de 0.9917 y P ~ 0.356*N. El aparato deriva los
tres valores de una sola senal de conductividad, asi que tiene un grado de
libertad, no tres. Recuperar los tres exige informacion externa. Hasta que
haya pares sensor-laboratorio, la calibracion de M2 es un anclaje
provisional y esta declarado como tal en la salida.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.spatial import ConvexHull, Delaunay
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

CELDA_M = 5.0
SIGMA_NO_SE = 8.0
N_ZONAS = 3
RADIO_LOTE_M = 300.0

# --- calibracion PROVISIONAL, sin validar contra laboratorio ---------------
CAL = {"N": (8.0, 1.8), "P": (4.0, 2.5), "K": (60.0, 18.0)}

# --- parametros agronomicos para papa --------------------------------------
PAPA = {
    "rendimiento_objetivo_t_ha": 25.0,
    "extraccion": {"N": 3.5, "P2O5": 1.4, "K2O": 5.5},
    "eficiencia": {"N": 0.55, "P2O5": 0.20, "K2O": 0.60},
    "disponibilidad": {"N": 0.45, "P2O5": 0.30, "K2O": 0.30},
}
PPM_A_KG_HA = 1.8
P_A_P2O5 = 2.29
K_A_K2O = 1.20

# --- catalogo: PRECIOS DE REFERENCIA, reemplazar con SIPSA -----------------
PRODUCTOS = [
    {"nombre": "DAP 18-46-0", "N": 0.18, "P2O5": 0.46, "K2O": 0.00, "cop_bulto": 180_000},
    {"nombre": "KCl 0-0-60", "N": 0.00, "P2O5": 0.00, "K2O": 0.60, "cop_bulto": 130_000},
    {"nombre": "Urea 46-0-0", "N": 0.46, "P2O5": 0.00, "K2O": 0.00, "cop_bulto": 120_000},
    {"nombre": "13-26-6", "N": 0.13, "P2O5": 0.26, "K2O": 0.06, "cop_bulto": 150_000},
]
KG_BULTO = 50
GENERICO = [
    {"producto": "13-26-6", "kg_ha": 800},
    {"producto": "Urea 46-0-0", "kg_ha": 200},
]


# --------------------------------------------------------------- geometria

def a_metros(lat, lon, lat0, lon0):
    x = (lon - lon0) * 111_320.0 * np.cos(np.radians(lat0))
    y = (lat - lat0) * 110_540.0
    return x, y


def a_grados(x, y, lat0, lon0):
    lon = lon0 + x / (111_320.0 * np.cos(np.radians(lat0)))
    lat = lat0 + y / 110_540.0
    return lat, lon


# --------------------------------------------------------------- M1

def quality(df: pd.DataFrame) -> pd.DataFrame:
    """
    Separa dos cosas que no se deben confundir:

      descartado  la geometria dice que no pertenece al lote. Regla dura.
      sospechoso  la lectura es rara. NO se excluye: con pocas muestras un
                  valor alto es informacion, no un error.
    """
    xy = df[["x", "y"]].to_numpy()
    centro = np.median(xy, axis=0)
    dist = np.linalg.norm(xy - centro, axis=1)

    out = df.copy()
    out["dist_centro_m"] = dist.round(1)
    out["valido"] = dist <= RADIO_LOTE_M
    out["sospechoso"] = False

    dentro = out.valido
    if dentro.sum() >= 10:
        iso = IsolationForest(contamination=0.08, random_state=0)
        out.loc[dentro, "sospechoso"] = (
            iso.fit_predict(out.loc[dentro, ["N", "p", "k"]].to_numpy()) == -1
        )
    return out


def calidad_de_punto(lat, lon, centro_lat, centro_lon) -> tuple[bool, str | None]:
    """Version puntual de M1, para la ingesta de una lectura suelta."""
    x, y = a_metros(np.array([lat]), np.array([lon]), centro_lat, centro_lon)
    d = float(np.hypot(x[0], y[0]))
    if d > RADIO_LOTE_M:
        return False, (
            f"Este punto queda a {d / 1000:.1f} km del lote. Se equivoco de finca?"
        )
    return True, None


# --------------------------------------------------------------- M2

def calibrate(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col, destino in (("N", "N_ppm"), ("p", "P_ppm"), ("k", "K_ppm")):
        base, pend = CAL[destino[0]]
        out[destino] = base + pend * df[col]
    return out


# --------------------------------------------------------------- M3

def _gp(df: pd.DataFrame, campo: str) -> GaussianProcessRegressor:
    X = df[["x", "y"]].to_numpy()
    y = df[campo].to_numpy()
    kernel = (
        ConstantKernel(np.var(y) or 1.0, (1e-2, 1e6))
        * Matern(length_scale=25.0, length_scale_bounds=(5.0, 200.0), nu=1.5)
        + WhiteKernel(noise_level=max(np.var(y) * 0.05, 1e-3))
    )
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True,
                                  n_restarts_optimizer=3, random_state=0)
    gp.fit(X, y)
    return gp


def grid(df: pd.DataFrame):
    """Grilla rectangular mas mascara del contorno real del lote."""
    m = CELDA_M
    xs = np.arange(df.x.min() - m, df.x.max() + 2 * m, m)
    ys = np.arange(df.y.min() - m, df.y.max() + 2 * m, m)
    gx, gy = np.meshgrid(xs, ys)
    puntos = np.column_stack([gx.ravel(), gy.ravel()])

    xy = df[["x", "y"]].to_numpy()
    centro = xy.mean(axis=0)
    borde = xy[ConvexHull(xy).vertices]
    borde = centro + (borde - centro) * 1.18
    mascara = Delaunay(borde).find_simplex(puntos) >= 0
    return xs, ys, puntos, mascara, borde


def interpolate(df: pd.DataFrame, puntos: np.ndarray) -> dict:
    campos = {}
    for campo in ("N_ppm", "P_ppm", "K_ppm"):
        media, sigma = _gp(df, campo).predict(puntos, return_std=True)
        campos[campo] = (np.clip(media, 0, None), sigma)
    return campos


def incertidumbre(campos: dict) -> np.ndarray:
    """Sigma combinado y normalizado al rango de cada nutriente, en porcentaje."""
    return np.mean([
        campos[c][1] / max(campos[c][0].max() - campos[c][0].min(), 1e-6)
        for c in campos
    ], axis=0) * 100.0


# --------------------------------------------------------------- M4

def requirement(n_ppm: float, p_ppm: float, k_ppm: float) -> tuple[dict, dict]:
    """
    Balance de nutrientes -> kg/ha, y el semaforo.

    El nivel se deriva del faltante, no de umbrales de ppm sueltos, para que
    el semaforo y la receta no puedan contradecirse.
    """
    rend = PAPA["rendimiento_objetivo_t_ha"]
    aporte = {
        "N": n_ppm * PPM_A_KG_HA * PAPA["disponibilidad"]["N"],
        "P2O5": p_ppm * PPM_A_KG_HA * P_A_P2O5 * PAPA["disponibilidad"]["P2O5"],
        "K2O": k_ppm * PPM_A_KG_HA * K_A_K2O * PAPA["disponibilidad"]["K2O"],
    }
    corto = {"N": "N", "P2O5": "P", "K2O": "K"}
    req, niveles = {}, {}
    for nutriente, extrae in PAPA["extraccion"].items():
        demanda = extrae * rend
        faltante = max(demanda - aporte[nutriente], 0.0)
        req[nutriente] = round(faltante / PAPA["eficiencia"][nutriente])
        cubierto = 1.0 - faltante / demanda
        niveles[corto[nutriente]] = (
            "critico" if cubierto < 0.40 else "bajo" if cubierto < 0.75 else "adecuado"
        )
    return req, niveles


# --------------------------------------------------------------- M5

def blend(req: dict, area_ha: float) -> tuple[list[dict], int]:
    """Minimiza el costo sujeto a cubrir N, P2O5 y K2O."""
    costo = [p["cop_bulto"] for p in PRODUCTOS]
    A_ub, b_ub = [], []
    for nutriente in ("N", "P2O5", "K2O"):
        A_ub.append([-p[nutriente] * KG_BULTO for p in PRODUCTOS])
        b_ub.append(-req[nutriente] * area_ha)

    res = linprog(costo, A_ub=A_ub, b_ub=b_ub,
                  bounds=[(0, None)] * len(PRODUCTOS), method="highs")
    if not res.success:
        return [], 0

    plan = []
    for producto, bultos in zip(PRODUCTOS, res.x):
        entero = int(np.ceil(bultos - 1e-9))
        if entero > 0:
            plan.append({
                "nombre": producto["nombre"],
                "bultos": entero,
                "costo_cop": entero * producto["cop_bulto"],
            })
    return plan, sum(p["costo_cop"] for p in plan)


def costo_generico(area_ha: float) -> tuple[int, str]:
    total, detalle = 0, []
    for item in GENERICO:
        producto = next(p for p in PRODUCTOS if p["nombre"] == item["producto"])
        bultos = int(np.ceil(item["kg_ha"] * area_ha / KG_BULTO))
        total += bultos * producto["cop_bulto"]
        detalle.append(f"{bultos} bultos de {item['producto']}")
    return total, " + ".join(detalle)


def frase_bultos(productos: list[dict]) -> str:
    partes = [
        f"{p['bultos']} {'bulto' if p['bultos'] == 1 else 'bultos'} de {p['nombre'].split()[0]}"
        for p in productos
    ]
    if not partes:
        return "nada por ahora"
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]
