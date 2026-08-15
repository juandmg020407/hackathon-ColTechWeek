"""
Genera el paquete de lote (GET /v1/plots/{id}/package) a partir de las
mediciones reales del sensor.

Este script es el prototipo del pipeline del backend: lo que hace aqui
offline es exactamente lo que hara el endpoint en caliente.

    python tools/build_mock.py

Salida: mock/package-nar-001.json
"""

import json
import pathlib

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.spatial import ConvexHull, Delaunay
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "data" / "data_ejemplo.csv.xlsx"
SALIDA = RAIZ / "mock" / "package-nar-001.json"

CELDA_M = 5.0          # resolucion de la grilla, en metros
SIGMA_NO_SE = 8.0      # por encima de esto el frente pinta la celda rayada
N_ZONAS = 3

# --- Calibracion provisional del sensor -------------------------------------
# El sensor entrega un indice entero, no ppm. Estos coeficientes son un
# ANCLAJE PROVISIONAL a rangos plausibles de un andisol de Narino.
# NO estan validados contra laboratorio. Reemplazar en cuanto haya pares
# sensor <-> analisis de suelos.
CAL = {
    "N": (8.0, 1.8),    # ppm = base + pendiente * lectura
    "P": (4.0, 2.5),
    "K": (60.0, 18.0),
}

# --- Parametros agronomicos para papa ---------------------------------------
# Calibrar con agronomo. Fuentes de referencia: QUEFTS / Nutrient Expert.
PAPA = {
    "rendimiento_objetivo_t_ha": 25.0,
    # kg de nutriente extraidos por tonelada de tuberculo
    "extraccion": {"N": 3.5, "P2O5": 1.4, "K2O": 5.5},
    # fraccion del nutriente aplicado que la planta alcanza a recuperar.
    # el fosforo es bajo a proposito: los andisoles lo fijan con fuerza.
    "eficiencia": {"N": 0.55, "P2O5": 0.20, "K2O": 0.60},
    # fraccion del nutriente del suelo que la planta alcanza a tomar durante
    # el ciclo. El potasio es bajo a proposito: en andisoles compite con
    # calcio y magnesio por el complejo de cambio y se lixivia con lluvia.
    "disponibilidad": {"N": 0.45, "P2O5": 0.30, "K2O": 0.30},
}

# ppm -> kg/ha en los primeros 20 cm de un andisol (densidad aparente ~0.9)
PPM_A_KG_HA = 1.8
P_A_P2O5 = 2.29
K_A_K2O = 1.20

# --- Catalogo de fertilizantes ----------------------------------------------
# PRECIOS PLACEHOLDER. Reemplazar con SIPSA (DANE) antes de mostrar en publico.
PRODUCTOS = [
    {"nombre": "DAP 18-46-0",  "N": 0.18, "P2O5": 0.46, "K2O": 0.00, "cop_bulto": 180_000},
    {"nombre": "KCl 0-0-60",   "N": 0.00, "P2O5": 0.00, "K2O": 0.60, "cop_bulto": 130_000},
    {"nombre": "Urea 46-0-0",  "N": 0.46, "P2O5": 0.00, "K2O": 0.00, "cop_bulto": 120_000},
    {"nombre": "13-26-6",      "N": 0.13, "P2O5": 0.26, "K2O": 0.06, "cop_bulto": 150_000},
]
KG_BULTO = 50

# Lo que el agricultor aplica hoy sin recomendacion: la practica por
# costumbre en la zona, mezcla completa en siembra mas urea en el aporque.
# Dosis conservadoras a proposito: el objetivo es una comparacion creible,
# no inflar el ahorro.
GENERICO = [
    {"producto": "13-26-6", "kg_ha": 800},
    {"producto": "Urea 46-0-0", "kg_ha": 200},
]


def a_metros(lat, lon, lat0, lon0):
    """Proyeccion equirectangular local. Sobra para un lote de una hectarea."""
    x = (lon - lon0) * 111_320.0 * np.cos(np.radians(lat0))
    y = (lat - lat0) * 110_540.0
    return x, y


def a_grados(x, y, lat0, lon0):
    lon = lon0 + x / (111_320.0 * np.cos(np.radians(lat0)))
    lat = lat0 + y / 110_540.0
    return lat, lon


def control_calidad(df):
    """
    M1. Separa dos cosas que no se deben confundir:

      - descartado: la geometria dice que el punto no pertenece al lote.
        Regla dura y confiable, se excluye del modelo.
      - sospechoso: la lectura es estadisticamente rara. NO se excluye.
        Con 19 muestras, un valor alto es informacion, no un error: puede
        ser una zona realmente rica o donde ya abonaron. Solo se marca
        para que el tecnico lo confirme.
    """
    xy = df[["x", "y"]].to_numpy()
    centro = np.median(xy, axis=0)
    dist = np.linalg.norm(xy - centro, axis=1)

    df = df.copy()
    df["dist_centro_m"] = dist.round(1)
    df["valido"] = dist <= 300.0

    df["sospechoso"] = False
    dentro = df.valido
    if dentro.sum() >= 10:
        iso = IsolationForest(contamination=0.08, random_state=0)
        raro = iso.fit_predict(df.loc[dentro, ["N", "p", "k"]].to_numpy()) == -1
        df.loc[dentro, "sospechoso"] = raro
    return df


def calibrar(df):
    """M2, version provisional: indice del sensor -> ppm."""
    out = df.copy()
    for col, destino in (("N", "N_ppm"), ("p", "P_ppm"), ("k", "K_ppm")):
        base, pend = CAL[destino[0]]
        out[destino] = base + pend * df[col]
    return out


def interpolar(df, campo):
    """M3. Proceso Gaussiano sobre el lote: devuelve media y sigma por celda."""
    X = df[["x", "y"]].to_numpy()
    y = df[campo].to_numpy()

    kernel = (
        ConstantKernel(np.var(y) or 1.0, (1e-2, 1e6))
        * Matern(length_scale=25.0, length_scale_bounds=(5.0, 200.0), nu=1.5)
        + WhiteKernel(noise_level=max(np.var(y) * 0.05, 1e-3))
    )
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=3, random_state=0)
    gp.fit(X, y)
    return gp


def construir_grilla(df):
    """
    Grilla rectangular mas una mascara del contorno real del lote.

    El frente recibe siempre un rectangulo (indexar es trivial) y pinta
    solo las celdas con mascara 1, asi el mapa tiene forma de lote y no
    de rectangulo. El area se cuenta sobre las celdas de adentro.
    """
    margen = CELDA_M
    x0, x1 = df.x.min() - margen, df.x.max() + margen
    y0, y1 = df.y.min() - margen, df.y.max() + margen

    xs = np.arange(x0, x1 + CELDA_M, CELDA_M)
    ys = np.arange(y0, y1 + CELDA_M, CELDA_M)
    gx, gy = np.meshgrid(xs, ys)
    puntos = np.column_stack([gx.ravel(), gy.ravel()])

    # contorno: envolvente convexa de las mediciones, dilatada un margen
    xy = df[["x", "y"]].to_numpy()
    centro = xy.mean(axis=0)
    hull = ConvexHull(xy)
    borde = xy[hull.vertices]
    borde = centro + (borde - centro) * 1.18   # dilatacion suave

    contorno = Delaunay(borde)
    mascara = contorno.find_simplex(puntos) >= 0
    return xs, ys, puntos, mascara, borde


def requerimiento(n_ppm, p_ppm, k_ppm):
    """
    M4. Balance de nutrientes -> kg/ha a aplicar, y el semaforo.

    El nivel se deriva del faltante, no de umbrales de ppm sueltos. Asi el
    semaforo y la receta no pueden contradecirse: si la tarjeta dice
    "potasio critico", la receta pide potasio.
    """
    rend = PAPA["rendimiento_objetivo_t_ha"]
    aporte = {
        "N": n_ppm * PPM_A_KG_HA * PAPA["disponibilidad"]["N"],
        "P2O5": p_ppm * PPM_A_KG_HA * P_A_P2O5 * PAPA["disponibilidad"]["P2O5"],
        "K2O": k_ppm * PPM_A_KG_HA * K_A_K2O * PAPA["disponibilidad"]["K2O"],
    }
    req, niveles = {}, {}
    corto = {"N": "N", "P2O5": "P", "K2O": "K"}
    for nutriente, extrae in PAPA["extraccion"].items():
        demanda = extrae * rend
        faltante = max(demanda - aporte[nutriente], 0.0)
        req[nutriente] = round(faltante / PAPA["eficiencia"][nutriente])

        cubierto = 1.0 - faltante / demanda        # 1 = el suelo lo tiene todo
        niveles[corto[nutriente]] = (
            "critico" if cubierto < 0.40 else "bajo" if cubierto < 0.75 else "adecuado"
        )
    return req, niveles


def optimizar_mezcla(req, area_ha):
    """M5. Minimiza el costo sujeto a cubrir N, P2O5 y K2O."""
    costo = [p["cop_bulto"] for p in PRODUCTOS]
    # -A_ub x <= -b  ==  aporte >= requerimiento
    A_ub, b_ub = [], []
    for nutriente in ("N", "P2O5", "K2O"):
        A_ub.append([-p[nutriente] * KG_BULTO for p in PRODUCTOS])
        b_ub.append(-req[nutriente] * area_ha)

    res = linprog(costo, A_ub=A_ub, b_ub=b_ub, bounds=[(0, None)] * len(PRODUCTOS), method="highs")
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


def costo_generico(area_ha):
    total, detalle = 0, []
    for item in GENERICO:
        producto = next(p for p in PRODUCTOS if p["nombre"] == item["producto"])
        bultos = int(np.ceil(item["kg_ha"] * area_ha / KG_BULTO))
        total += bultos * producto["cop_bulto"]
        detalle.append(f"{bultos} bultos de {item['producto']}")
    return total, " + ".join(detalle)


def bultos_frase(productos):
    """'3 bultos de DAP, 1 bulto de KCl y 2 bultos de Urea'"""
    partes = [
        f"{p['bultos']} {'bulto' if p['bultos'] == 1 else 'bultos'} de {p['nombre'].split()[0]}"
        for p in productos
    ]
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def main():
    df = pd.read_excel(ENTRADA)
    lat0, lon0 = df.Latitud.median(), df.Longitud.median()
    df["x"], df["y"] = a_metros(df.Latitud.values, df.Longitud.values, lat0, lon0)

    df = control_calidad(df)
    descartados = df[~df.valido]
    print(f"puntos totales: {len(df)}  validos: {int(df.valido.sum())}  descartados: {len(descartados)}")
    for _, fila in descartados.iterrows():
        print(f"  descartado: ({fila.Latitud:.6f}, {fila.Longitud:.6f}) a {fila.dist_centro_m:.0f} m del centro")

    ok = calibrar(df[df.valido]).reset_index(drop=True)

    xs, ys, puntos, dentro, borde = construir_grilla(ok)
    cols, rows = len(xs), len(ys)

    campos = {}
    for campo in ("N_ppm", "P_ppm", "K_ppm"):
        gp = interpolar(ok, campo)
        media, sigma = gp.predict(puntos, return_std=True)
        campos[campo] = (np.clip(media, 0, None), sigma)
        print(f"{campo}: media {media.mean():6.1f} ppm   sigma medio {sigma.mean():5.2f}")

    # incertidumbre combinada, normalizada al rango de cada nutriente
    sigma_rel = np.mean([
        campos[c][1] / max(campos[c][0].max() - campos[c][0].min(), 1e-6)
        for c in campos
    ], axis=0) * 100.0

    # zonas de manejo, solo sobre las celdas que estan dentro del lote
    rasgos = np.column_stack([campos[c][0] for c in campos])
    rasgos_norm = (rasgos - rasgos.mean(axis=0)) / (rasgos.std(axis=0) + 1e-9)
    etiquetas = np.full(len(puntos), -1)
    etiquetas[dentro] = KMeans(n_clusters=N_ZONAS, n_init=10, random_state=0).fit_predict(rasgos_norm[dentro])

    area_celda_ha = (CELDA_M ** 2) / 10_000.0
    area_total = round(int(dentro.sum()) * area_celda_ha, 2)

    zonas = []
    for z in range(N_ZONAS):
        mascara = etiquetas == z
        n_med = float(campos["N_ppm"][0][mascara].mean())
        p_med = float(campos["P_ppm"][0][mascara].mean())
        k_med = float(campos["K_ppm"][0][mascara].mean())
        area_z = round(int(mascara.sum()) * area_celda_ha, 3)
        req, niveles = requerimiento(n_med, p_med, k_med)
        plan, costo = optimizar_mezcla(req, area_z)
        zonas.append({
            "id": f"z{z + 1}",
            "area_ha": area_z,
            "celdas": np.where(mascara)[0].tolist(),
            "promedio_ppm": {"N": round(n_med, 1), "P": round(p_med, 1), "K": round(k_med, 1)},
            "nivel": niveles,
            "kg_ha": req,
            "productos": plan,
            "costo_cop": costo,
        })
    zonas.sort(key=lambda z: -z["area_ha"])

    # active learning: donde el modelo tiene menos certeza, dentro del lote
    sigma_dentro = np.where(dentro, sigma_rel, -np.inf)
    peor = int(np.argmax(sigma_dentro))
    lat_s, lon_s = a_grados(puntos[peor, 0], puntos[peor, 1], lat0, lon0)

    costo_total = sum(z["costo_cop"] for z in zonas)
    generico, generico_detalle = costo_generico(area_total)

    paquete = {
        "plot": {
            "id": "nar-001",
            "nombre": "Lote El Rosal",
            "municipio": "Pasto, Narino",
            "area_ha": area_total,
            "cultivo": "papa",
            "variedad": "Diacol Capiro",
            "centro": [round(float(lat0), 6), round(float(lon0), 6)],
        },
        "grid": {
            "celda_m": CELDA_M,
            "cols": cols,
            "rows": rows,
            "origen": [round(float(a_grados(xs[0], ys[0], lat0, lon0)[0]), 6),
                       round(float(a_grados(xs[0], ys[0], lat0, lon0)[1]), 6)],
            "unidad": "ppm",
            "N": [round(float(v)) for v in campos["N_ppm"][0]],
            "P": [round(float(v)) for v in campos["P_ppm"][0]],
            "K": [round(float(v)) for v in campos["K_ppm"][0]],
            "sigma": [round(float(v)) for v in sigma_rel],
            "sigma_umbral": SIGMA_NO_SE,
            "mask": [int(v) for v in dentro],
        },
        "contorno": [
            [round(float(a_grados(px, py, lat0, lon0)[0]), 6),
             round(float(a_grados(px, py, lat0, lon0)[1]), 6)]
            for px, py in borde
        ],
        "puntos": [
            {"lat": round(float(r.Latitud), 6), "lon": round(float(r.Longitud), 6),
             "N": int(r.N), "P": int(r.p), "K": int(r.k),
             "sospechoso": bool(r.sospechoso)}
            for r in ok.itertuples()
        ],
        "descartados": [
            {"lat": round(float(r.Latitud), 6), "lon": round(float(r.Longitud), 6),
             "motivo": f"Este punto queda a {r.dist_centro_m / 1000:.1f} km del lote. Se equivoco de finca?"}
            for r in descartados.itertuples()
        ],
        "zonas": zonas,
        "next_sample": {
            "punto": [round(float(lat_s), 6), round(float(lon_s), 6)],
            "razon": "Es el punto del lote donde el modelo tiene menos certeza.",
            "sigma": round(float(sigma_rel[peor]), 1),
        },
        "receta": {
            "costo_total_cop": costo_total,
            "costo_generico_cop": generico,
            "ahorro_cop": generico - costo_total,
            "generico_detalle": generico_detalle,
            "ventana": {
                "desde": "2026-08-20",
                "hasta": "2026-08-22",
                "motivo": "Llueve fuerte el sabado. Si aplica antes, se lava.",
            },
        },
        "voz": [
            {"id": "v1", "claves": ["cuanto", "abono", "echo", "fertilizante"],
             "texto": f"A su lote le faltan {bultos_frase(zonas[0]['productos'])}.",
             "audio": "/audio/v1.opus"},
            {"id": "v2", "claves": ["cuando", "aplico", "dia", "lluvia"],
             "texto": "Aplique el jueves veinte. El sabado llueve fuerte y se le lava el abono.",
             "audio": "/audio/v2.opus"},
            {"id": "v3", "claves": ["cuanto", "cuesta", "vale", "precio"],
             "texto": f"Le cuesta {costo_total:,.0f} pesos.".replace(",", "."),
             "audio": "/audio/v3.opus"},
        ],
        "generado": "2026-08-15T14:47:00Z",
        "ttl_horas": 72,
        "_aviso": (
            "Calibracion sensor->ppm PROVISIONAL, sin validar contra laboratorio. "
            "Precios de fertilizante son placeholder, reemplazar con SIPSA."
        ),
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(paquete, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    crudo = len(json.dumps(paquete, ensure_ascii=False, separators=(",", ":")).encode())
    print()
    print(f"grilla {cols}x{rows} = {cols * rows} celdas, {int(dentro.sum())} dentro del lote = {area_total} ha")
    print(f"sospechosos (no excluidos): {int(ok.sospechoso.sum())}")
    print(f"zonas: " + "  ".join(f"{z['id']}={z['area_ha']}ha/{z['nivel']['K']}" for z in zonas))
    print(f"receta: {costo_total:,} COP   generico: {generico:,} COP   ahorro: {generico - costo_total:,} COP")
    print(f"next_sample: {lat_s:.6f}, {lon_s:.6f}  (sigma {sigma_rel[peor]:.1f})")
    print(f"paquete: {crudo / 1024:.1f} KB sin comprimir -> ~{crudo / 1024 / 4:.1f} KB con brotli")
    print(f"escrito en {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
