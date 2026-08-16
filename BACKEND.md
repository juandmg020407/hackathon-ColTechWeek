# IOmido — arquitectura del backend

Este documento describe tanto el backend que existe hoy (`v0.1`) como el contrato
objetivo (`v0.2`). La distinción es intencional: los jurados y colaboradores deben
poder separar código ejecutable de trabajo pendiente.

## Objetivo del backend

Recibir lecturas NPK georreferenciadas de las fincas proveedoras de un centro de
acopio, convertir pocos puntos en una representación espacial con incertidumbre y
crear propuestas de formulación que un técnico pueda revisar.

El backend no compra insumos, no ejecuta aplicaciones y no decide por el productor.

## Stack actual

```text
Python 3
FastAPI + Pydantic          API y contrato
pandas + openpyxl           fuente Excel de la demo
NumPy + SciPy               geometría y optimización
scikit-learn                Isolation Forest, GP y KMeans
httpx                       fuentes climáticas
SQLite                      propuestas, decisiones y auditoría local
Brotli ASGI                 compresión del package
```

Postgres, autenticación, colas y cache durable son objetivos de producción, no
dependencias activas de la demo.

## Estructura real

```text
backend/app/
├── main.py                  API `/v1`, catálogo demo y caches en memoria
├── schemas.py               modelos Pydantic del contrato `v0.1`
├── config.py                entorno y parámetros operativos
├── adjust.py                ajustes explícitos por riesgo
├── ml/
│   ├── soil.py              calidad, GP, zonas, balance y mezcla heredada
│   ├── climatology.py       contexto histórico y años análogos
│   └── package.py           ensambla el paquete completo
├── risk/
│   ├── engine.py            prioriza y limita alertas
│   ├── frost.py             helada
│   ├── drought.py           déficit hídrico
│   ├── blight.py            condiciones para gota
│   └── seasonal.py          contexto ENSO/estacional
├── sources/
│   ├── openmeteo.py         pronóstico y estacional
│   ├── nasa.py              climatología y cliente FIRMS
│   └── enso.py              boletín ENSO versionado manualmente
└── governance/
    ├── disclosure.py        límites y divulgación
    ├── proposals.py         propuestas, explicación y revisión
    └── audit.py             SQLite append-only local
```

## API implementada

| Método | Ruta | Estado |
|---|---|---|
| GET | `/health` | Implementado |
| GET | `/v1/plots` | Implementado; un lote de demo |
| GET | `/v1/plots/{id}/package` | Implementado; contrato `v0.1` |
| GET | `/v1/plots/{id}/risk` | Implementado |
| POST | `/v1/readings` | Implementado en memoria |
| POST | `/v1/decisions` | Implementado con SQLite local |
| GET | `/v1/decisions/{id}/why` | Implementado |
| GET | `/v1/decisions/{id}/history` | Implementado |
| GET | `/v1/governance` | Implementado |
| POST | `/v1/agent/ask` | No implementado |
| `/v1/auth/*` | No implementado |

## Semántica canónica `v0.2`

### Lecturas del sensor

Los datos originales son porcentajes NPK. El código actual usa `N_raw`, `P_raw`,
`K_raw` y todavía convierte parte del pipeline a ppm; esa conversión se retirará.

Contrato objetivo:

```json
{
  "plot_id": "nar-001",
  "lat": 1.247822,
  "lon": -77.267613,
  "npk_pct": { "N": 2, "P": 1, "K": 1 },
  "measured_at": "2026-08-15T14:30:00-05:00",
  "client_id": "phone-7-reading-104"
}
```

Reglas:

- unidad única: `%`;
- rango válido por componente: 0 a 100;
- se conserva la lectura original sin transformación destructiva;
- cualquier dato derivado debe indicar modelo, versión y unidad;
- no se afirma equivalencia con laboratorio.

### Formulaciones disponibles

No habrá catálogo de marcas ni productos químicos en el dominio central. Cada
centro registra grados NPK disponibles:

```json
{
  "id": "grade-30-30-40",
  "label": "30-30-40",
  "npk_pct": { "N": 30, "P": 30, "K": 40 },
  "bag_weight_kg": 50,
  "available": true,
  "source": "configuración del centro",
  "valid_from": "2026-08-15"
}
```

`bag_weight_kg` tampoco debe ser una constante global: diferentes proveedores o
regiones pueden usar presentaciones distintas.

Si una integración externa expresa fósforo o potasio como P₂O₅/K₂O, el adaptador
de esa fuente realiza la conversión antes de ingresar al dominio y registra la
convención. El núcleo de IOmido solo compara variables con la misma base.

### Perfiles agronómicos

Los objetivos y factores dejan de vivir dentro de `soil.py`. Se cargan como datos:

```json
{
  "id": "potato-diacol-capiro-v1",
  "crop": "papa",
  "variety": "Diacol Capiro",
  "stage": "establecimiento",
  "target_npk_pct": null,
  "response_kg_ha_per_pct_point": null,
  "application_limits_kg_ha": null,
  "source": "pendiente de validación agronómica",
  "version": "draft-1"
}
```

Los números anteriores son **estructura de ejemplo, no valores agronómicos**. Un
perfil no puede activarse como validado hasta tener fuente y revisión técnica.

## Pipeline `v0.2`

### 1. Calidad

- validar esquema, rangos y coordenadas;
- separar `fuera_del_lote` de `atipica`;
- conservar las atípicas válidas con su bandera;
- usar un polígono real cuando exista; el radio actual es solo fallback de demo.

### 2. Campo espacial

Para cada componente N, P y K:

- entrenar GP sobre porcentajes;
- predecir media y desviación por celda;
- enmascarar con el contorno;
- derivar el umbral de incertidumbre del espaciamiento de muestreo;
- elegir la celda válida con mayor incertidumbre como `next_sample`.

La salida sigue expresada en porcentaje.

### 3. Requerimiento

Para una zona `z` y nutriente `i`:

```text
deficit_pct[z,i] = max(target_pct[i] - estimated_pct[z,i], 0)
required_kg_ha[z,i] = deficit_pct[z,i] × response_kg_ha_per_pct_point[i]
```

Los ajustes climáticos se aplican después y viajan como una lista explícita. No se
modifica ninguna recomendación en silencio.

### 4. Optimización sin precios

Variables enteras:

```text
x[z,f] = número de bultos de formulación f asignados a zona z
```

Aporte de una formulación:

```text
supplied_kg[z,i] = Σf x[z,f] × bag_weight_kg[f] × npk_pct[f,i] / 100
```

Objetivo lexicográfico:

1. minimizar faltantes de N, P y K;
2. minimizar exceso total ponderado;
3. minimizar el número de bultos;
4. preferir menos formulaciones distintas si hay empate.

Restricciones y pesos proceden de configuración versionada. La implementación debe
usar MILP o una búsqueda entera acotada; no se acepta resolver continuo y redondear
producto por producto.

### 5. Gobernanza

Cada recomendación nace como propuesta pendiente. Como ya no hay precio, la revisión
técnica no se activa por dinero. El contrato objetivo la activa por:

- confianza baja;
- dosis superior al límite del perfil;
- formulación no disponible;
- cambio climático superior al rango permitido;
- modificación manual solicitada por el productor;
- regla explícita del centro.

Ningún cliente puede autodeclararse técnico: producción necesita autenticación y
roles verificados.

## Package objetivo `v0.2`

Ejemplo reducido:

```json
{
  "contract_version": "2.0",
  "plot": {
    "id": "nar-001",
    "name": "Lote El Rosal",
    "crop": "papa",
    "center_id": "acopio-demo"
  },
  "grid": {
    "unit": "pct",
    "N_pct": [2, 3, 3],
    "P_pct": [1, 1, 2],
    "K_pct": [1, 2, 2],
    "sigma_pct": [0.4, 0.8, 1.2],
    "sigma_threshold_pct": 0.9
  },
  "zones": [
    {
      "id": "z1",
      "mean_npk_pct": { "N": 2.4, "P": 1.2, "K": 1.6 },
      "recommendation": {
        "formulations": [
          { "grade": "30-30-40", "bags": 2, "bag_weight_kg": 50 }
        ],
        "reason": "Es la combinación disponible que cubre mejor el faltante con menor exceso.",
        "proposal_id": "rec-nar-001-z1-rev-001"
      }
    }
  ],
  "risks": [],
  "degraded": false
}
```

Los valores son ilustrativos. Los mocks definitivos deben generarse desde el
pipeline y nunca escribirse a mano.

## Configuración objetivo

```text
domain/
├── sensor_profiles.json
├── crop_profiles.json
├── formulation_catalog.json
├── risk_thresholds.json
└── review_policies.json
```

En producción estos recursos pueden vivir en Postgres. Durante la demo pueden ser
JSON versionados, siempre que el código no duplique sus valores.

## Fuentes y degradación

- Open-Meteo: pronóstico y estacional.
- NASA POWER: contexto histórico.
- NOAA CPC: contexto ENSO; hoy se actualiza manualmente.
- Sensor: medición puntual del lote.

El cache actual es de proceso. El objetivo es un cache durable con TTL y último dato
bueno. Una fuente fallida debe marcar `degraded: true`; nunca inventar datos.

## Persistencia objetivo

```text
centers
users
plots
readings
packages
crop_profiles
formulations
proposals
decisions
audit_log
```

Cada entidad mutable necesita centro, versión, timestamps y autor. Propuestas,
decisiones y auditoría conservan historial append-only.

## Migración desde `v0.1`

| Paso | Archivos principales | Criterio de aceptación |
|---|---|---|
| Unidad `%` | `schemas.py`, `soil.py`, `package.py`, mocks | No aparece `ppm` en API ni UI |
| Configuración | nuevo `domain/`, `config.py` | Sin catálogo, perfiles o precios dentro de Python |
| Optimizador | `soil.py` o nuevo `ml/formulations.py` | Solución entera reproducible y cubierta por tests |
| Gobernanza | `proposals.py`, `audit.py` | Revisión por confianza/límites; auditoría registra eventos |
| Persistencia | repositorios y migraciones | Lecturas e idempotencia sobreviven reinicios |
| Contrato | `schemas.py`, `FRONTEND.md` | `contract_version=2.0` y validación de mocks |

## Verificación mínima

- tests de rangos 0–100;
- primera fila del Excel permanece `2,1,1` en la API;
- arrays de grilla tienen igual longitud;
- ninguna recomendación contiene marca, nombre químico o precio;
- el optimizador cumple restricciones con bultos enteros;
- un paquete degradado sigue siendo válido;
- propuestas y decisiones aparecen en `audit_log`;
- OpenAPI solo publica unidades y nombres vigentes.

## Arranque

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Documentación interactiva: <http://localhost:8000/docs>.
