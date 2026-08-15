# SERENO — backend

Arquitectura, endpoints y fuentes. Complemento técnico de `BRIEF.md`.
El contrato con el frontend está en `FRONTEND.md` y es la fuente de verdad.

---

## 1. Stack

```
Python 3.11
FastAPI + Uvicorn            API
Pydantic v2                  schemas y OpenAPI automático
scikit-learn                 GP, GradientBoosting, IsolationForest
scipy                        linprog, spatial
httpx                        clientes de APIs externas (async)
Supabase (Postgres+PostGIS)  persistencia, geometrías, Realtime
Azure Speech SDK             TTS es-CO y STT
Anthropic SDK                agente con tool-use
Railway                      deploy
```

**Por qué Supabase:** PostGIS resuelve las geometrías, Realtime da el tiempo real sin montar WebSockets, y sobrevive al hackathon — que son 15 puntos del scoring.

---

## 2. Estructura

```
backend/
├── app/
│   ├── main.py                  FastAPI, CORS, compresión, middleware de auditoría
│   ├── config.py                settings desde entorno
│   ├── db.py                    cliente Supabase
│   │
│   ├── api/v1/
│   │   ├── plots.py             lotes y el paquete
│   │   ├── readings.py          ingesta del sensor
│   │   ├── risk.py              riesgos y contexto estacional
│   │   ├── decisions.py         human-in-the-loop
│   │   ├── agent.py             preguntas
│   │   ├── voice.py             TTS / STT
│   │   └── public.py            bien público
│   │
│   ├── schemas/                 modelos Pydantic (espejo de FRONTEND.md)
│   │
│   ├── ml/
│   │   ├── quality.py           M1  control de calidad
│   │   ├── calibration.py       M2  desagregación NPK
│   │   ├── spatial.py           M3  Proceso Gaussiano + zonas + active learning
│   │   ├── nutrition.py         M4  balance de nutrientes
│   │   └── blend.py             M5  optimización de mezcla
│   │
│   ├── risk/
│   │   ├── frost.py             R1  helada
│   │   ├── drought.py           R2  sequía
│   │   ├── blight.py            R3  gota
│   │   ├── fire.py              R4  incendios
│   │   ├── landslide.py         R5  deslizamiento
│   │   ├── seasonal.py          R6  ENSO
│   │   └── engine.py            orquesta los seis y ordena por severidad
│   │
│   ├── adjust.py                ajusta la receta según los riesgos activos
│   │
│   ├── sources/
│   │   ├── openmeteo.py         forecast, seasonal, archive
│   │   ├── firms.py             NASA FIRMS
│   │   ├── soilgrids.py         ISRIC
│   │   ├── enso.py              NOAA CPC
│   │   └── cache.py             caché en Postgres con TTL
│   │
│   ├── agent/
│   │   ├── tools.py             las herramientas = los endpoints
│   │   └── runner.py            bucle con tool-use
│   │
│   ├── voice/
│   │   ├── tts.py               Azure es-CO-SalomeNeural
│   │   └── phrasing.py          números y unidades a español hablado
│   │
│   └── governance/
│       ├── audit.py             registro append-only (AI Act art. 12)
│       ├── disclosure.py        divulgación de IA (art. 50)
│       └── limits.py            lo que el sistema NO hace
│
├── tools/build_mock.py          prototipo del pipeline, ya funciona
├── data/                        el Excel real
├── mock/                        paquete generado
└── requirements.txt
```

---

## 3. Endpoints

Base `/v1`. Todo JSON, todo con Brotli.

### P0 — sin esto no hay demo

| Ruta | Qué hace |
|---|---|
| `GET /v1/plots` | Lista de lotes |
| `GET /v1/plots/{id}/package` | **El principal.** Suelo + zonas + receta + riesgos + voz, en una llamada |
| `POST /v1/readings` | Ingesta de una medición, con M1 e idempotencia |

### P1 — la demo brilla

| Ruta | Qué hace |
|---|---|
| `GET /v1/plots/{id}/risk` | Los seis riesgos, por separado, para refrescar sin recalcular el suelo |
| `POST /v1/agent/ask` | Pregunta en texto o audio |
| `POST /v1/decisions` | Aceptar, rechazar o derivar una propuesta |
| `GET /v1/decisions/{id}/why` | Explicación completa y trazable |

### P2 — si sobra

| Ruta | Qué hace |
|---|---|
| `POST /v1/readings/import` | Subir el Excel |
| `GET /v1/public/soil-map` | Mapa agregado anonimizado |
| `GET /v1/public/stats` | Mediciones, hectáreas, kg de N no aplicados |
| `POST /v1/vision/leaf` | Foto de hoja |
| `POST /v1/whatsapp/webhook` | Canal B |

---

### `GET /v1/plots/{id}/package`

Al paquete de `FRONTEND.md` se le agregan dos bloques. **Todo lo anterior se mantiene igual.**

```jsonc
{
  // ... plot, grid, contorno, puntos, descartados, zonas, next_sample, receta, voz

  "riesgos": [
    {
      "id": "rk-helada-2026w34",
      "tipo": "helada",                    // helada|sequia|gota|incendio|deslizamiento|estacional
      "severidad": "alta",                 // baja|media|alta|critica
      "probabilidad": 0.72,
      "confianza": "media",                // baja|media|alta
      "ventana": { "desde": "2026-08-22", "hasta": "2026-08-27" },
      "titulo": "Riesgo de helada la próxima semana",
      "resumen": "Cinco noches seguidas con cielo despejado y mínimas cerca de cero.",
      "que_hacer": [
        "Riegue en la tarde: el suelo húmedo suelta calor de noche.",
        "Si tiene con qué, cubra los surcos más bajos del lote.",
        "Aplace la aplicación de nitrógeno hasta que pase."
      ],
      "por_que": {
        "modelo": "frost/v1",
        "entradas": { "t_min_c": [1.2, 0.4, -0.3], "nubosidad_pct": [12, 8, 5],
                      "punto_rocio_c": [-1.1, -1.8], "viento_ms": [0.8, 0.6] },
        "regla": "Mínima bajo 2 °C con nubosidad bajo 30% y viento bajo 2 m/s",
        "fuentes": [
          { "nombre": "Open-Meteo Forecast", "consultado": "2026-08-15T14:00:00Z" }
        ]
      },
      "requiere_confirmacion": true
    }
  ],

  "estacional": {
    "fenomeno": "El Niño",
    "estado": "activo y fortaleciéndose",
    "anomalia_nino34_c": 0.7,
    "prob_muy_fuerte": 0.63,
    "pico_esperado": "noviembre 2026 a enero 2027",
    "implicacion_local": "Menos lluvia y más noches despejadas en el altiplano nariñense. Su papa va a estar llenando tubérculo justo en el pico.",
    "horizonte_meses": 9,
    "fuente": { "nombre": "NOAA CPC", "actualizado": "2026-08-04" }
  }
}
```

`por_que` no es decoración: es el artículo 12 del AI Act. Cada riesgo carga sus entradas, su modelo y sus fuentes con marca de tiempo.

---

### `POST /v1/decisions` — human-in-the-loop

Toda propuesta nace en estado `pendiente` y no pasa nada hasta que alguien decide.

```jsonc
// request
{ "propuesta_id": "rec-nar-001-z1",
  "accion": "aceptar",              // aceptar | rechazar | derivar | modificar
  "actor": { "tipo": "agricultor", "id": "u-882" },
  "modificacion": { "productos": [ { "nombre": "KCl 0-0-60", "bultos": 3 } ] },
  "nota": "No consigo DAP en la vereda esta semana" }

// response
{ "ok": true,
  "decision_id": "dc-4471",
  "estado": "aceptada",
  "requiere_revision_tecnica": false,
  "registrado_en": "2026-08-15T15:22:10Z" }

// cuando supera el umbral de gasto
{ "ok": true,
  "decision_id": "dc-4472",
  "estado": "pendiente_revision",
  "requiere_revision_tecnica": true,
  "motivo": "La propuesta supera $1.500.000. Necesita visto bueno del técnico de la UMATA.",
  "notificado_a": "tec-nar-03" }
```

**`modificar` es la acción más valiosa del sistema.** Cada corrección de un técnico es una etiqueta de entrenamiento. Con 19 mediciones no se entrena nada; con miles de correcciones, sí. La supervisión humana es lo que llena el dataset.

---

### `GET /v1/decisions/{id}/why`

El botón «¿por qué me dice eso?».

```jsonc
{ "propuesta": "rec-nar-001-z1",
  "que_recomendamos": "3 bultos de DAP, 2 de KCl y 2 de Urea en la zona 1",
  "porque": [
    { "paso": "medición", "detalle": "18 puntos válidos del 15 de agosto. Uno descartado por estar a 1,2 km." },
    { "paso": "suelo",    "detalle": "Zona 1: nitrógeno crítico, fósforo crítico, potasio bajo.",
      "confianza": "media", "nota": "La calibración del sensor a ppm es provisional, sin validar contra laboratorio." },
    { "paso": "clima",    "detalle": "El Niño activo. Se subió el potasio un 15% por riesgo de helada." },
    { "paso": "costo",    "detalle": "Mezcla más barata que cubre el faltante. Precios de referencia, no de su vereda." }
  ],
  "no_sabemos": [
    "Cuánto rinde su lote: no tenemos historial de cosecha.",
    "Si el precio del bulto en su vereda coincide con el nacional."
  ],
  "modelo": { "suelo": "gp/v1", "nutricion": "balance/v1", "riesgo": "engine/v1" },
  "decidido_por": null,
  "estado": "pendiente" }
```

`no_sabemos` es obligatorio y nunca va vacío. Un sistema que solo declara certezas es el que pierde la confianza del agricultor la primera vez que se equivoca.

---

## 4. Los seis motores de riesgo

Todos exponen la misma firma: `evaluar(lote, clima, contexto) -> Riesgo | None`, y siempre devuelven `por_que`.

### R1 · Helada — `risk/frost.py`
El riesgo real para papa a 2.500 msnm, y el que trae El Niño.
Heladas de radiación: cielo despejado, aire seco, viento calmo, la noche irradia al espacio.

```
señal = f(t_min, nubosidad, punto_rocio, viento)
alerta si  t_min < 2 °C  y  nubosidad < 30 %  y  viento < 2 m/s
severidad por cuántas noches seguidas y qué tan por debajo de cero
```
Entradas: Open-Meteo horario, `temperature_2m_min`, `cloud_cover`, `dew_point_2m`, `wind_speed_10m`.

### R2 · Sequía — `risk/drought.py`
Balance hídrico simple contra el pronóstico estacional.

```
balance = precipitación acumulada − evapotranspiración de referencia
compara contra la normal climática de ERA5 para el mismo período
proyecta a 9 meses con SEAS5 y su índice de eventos extremos
```

### R3 · Gota (tizón tardío) — `risk/blight.py`
*Phytophthora infestans*, la enfermedad número uno de la papa en Colombia. El riesgo se calcula **solo con clima**, sin necesidad de ver la planta.

```
hora favorable: humedad relativa > 90 % y temperatura entre 10 y 24 °C
acumula horas favorables en ventanas de 48 h
umbral de severidad sobre las horas acumuladas
```
Es un modelo agronómico clásico, barato de implementar y de altísimo valor práctico.

### R4 · Incendios — `risk/fire.py`
Focos activos de NASA FIRMS en un radio configurable, ponderados por distancia y dirección del viento respecto al lote.

### R5 · Deslizamiento — `risk/landslide.py`
Umbrales de intensidad-duración sobre lluvia acumulada de 3 y 7 días, ponderados por la pendiente del terreno (derivada de la elevación de Open-Meteo).

No dependemos de una API de terceros que se pueda caer en la demo. El dataset de alertas del IDEAM queda como validación cruzada, no como dependencia.

### R6 · Estacional — `risk/seasonal.py`
Estado de ENSO y su traducción a una implicación local para el ciclo del cultivo. Es el que da la visión de meses, no de días.

### Orquestador — `risk/engine.py`
Corre los seis en paralelo con `asyncio.gather`, ordena por severidad × probabilidad, y **se queda con los tres primeros**. Más de tres alertas es ruido y el agricultor deja de leerlas.

---

## 5. El ajuste de la receta — `adjust.py`

Donde las dos mitades del producto se encuentran.

| Riesgo activo | Ajuste | Razón |
|---|---|---|
| Sequía alta o crítica | N × 0,75 | Sin agua no se absorbe y se volatiliza |
| Helada alta o crítica | K × 1,15 | El potasio mejora la tolerancia osmótica al frío |
| Lluvia fuerte en 48 h | Aplazar la ventana | Se lava y termina en la quebrada |
| Gota alta | Alerta sanitaria, sin cambio de dosis | Es un problema de fungicida, no de nutrición |

Cada ajuste se registra en `por_que` con su factor. Nunca se aplica en silencio.

---

## 6. Fuentes externas

### Open-Meteo — sin llave, CC-BY

```
Pronóstico    https://api.open-meteo.com/v1/forecast
              &hourly=temperature_2m,relative_humidity_2m,dew_point_2m,
                      cloud_cover,wind_speed_10m,precipitation,
                      soil_moisture_0_to_7cm,soil_temperature_0cm
              &daily=temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration
              &forecast_days=16&timezone=America/Bogota

Estacional    https://seasonal-api.open-meteo.com/v1/seasonal
              &monthly=temperature_2m_max,precipitation_sum
              &forecast_months=9
              ECMWF SEAS5, 51 miembros de ensemble

Histórico     https://archive-api.open-meteo.com/v1/archive
              ERA5 desde 1940, para las normales climáticas
```

### NASA FIRMS — llave gratis por correo
```
https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/{bbox}/{días}
Límite 5.000 peticiones por cada 10 minutos.
```

### SoilGrids (ISRIC)
pH, carbono orgánico, textura, nitrógeno total, CEC a 250 m.
⚠️ **Su REST API está pausada.** Descargar el raster de la zona por adelantado. Nada en la demo puede depender de que responda.

### NOAA CPC — estado de ENSO
Se actualiza mensualmente. **Cachear el valor y no consultarlo en vivo durante la demo.**

### SIPSA (DANE) y UPRA
Precios de insumos, vía `datos.gov.co` (Socrata). Reemplazan los precios de referencia del catálogo.

### Regla general de caché
Nada de red en el camino crítico de una petición. Todo lo externo se cachea en Postgres con TTL: clima 3 h, estacional 24 h, ENSO 7 días, precios 24 h, SoilGrids indefinido. **Si una fuente externa falla, el paquete se sirve igual con lo cacheado y marca `degradado: true`.**

---

## 7. Datos

```sql
plots        (id, nombre, municipio, geom, cultivo, variedad, area_ha, owner_id, creado)
readings     (id, plot_id, geom, n_raw, p_raw, k_raw, medido_en, client_id UNIQUE,
              valida, sospechoso, confianza, motivo, creado)
packages     (plot_id, payload JSONB, generado, ttl_horas)
risks        (id, plot_id, tipo, severidad, probabilidad, ventana, payload JSONB, generado)
proposals    (id, plot_id, tipo, payload JSONB, costo_cop, estado, creado)
decisions    (id, proposal_id, accion, actor_tipo, actor_id, modificacion JSONB,
              nota, creado)                                    -- append-only
audit_log    (id, evento, entidad, entidad_id, modelo_version, entradas JSONB,
              fuentes JSONB, actor, creado)                    -- append-only
consents     (id, owner_id, alcance, otorgado, revocado)       -- opt-in del mapa público
```

`decisions` y `audit_log` son **append-only**: sin UPDATE, sin DELETE. Una corrección es una fila nueva. Eso es lo que hace auditable el sistema.

---

## 8. Entorno

```bash
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=eastus
AZURE_TTS_VOICE=es-CO-SalomeNeural
ANTHROPIC_API_KEY=
FIRMS_MAP_KEY=
UMBRAL_REVISION_COP=1500000        # sobre esto, doble firma
CORS_ORIGINS=http://localhost:5173,https://sereno.vercel.app
```

---

## 9. Orden de implementación

| | Qué | Por qué primero |
|---|---|---|
| 1 | Portar `build_mock.py` a `ml/` y servir `/package` desde memoria | Desbloquea al frontend. **Ya funciona.** |
| 2 | `sources/openmeteo.py` con caché | Alimenta cuatro de los seis riesgos |
| 3 | R1 helada + R6 estacional | Son el corazón del giro del producto |
| 4 | `adjust.py` | Une las dos mitades |
| 5 | Supabase + `POST /readings` | Persistencia |
| 6 | `voice/tts.py` | La escena del video |
| 7 | R2 sequía + R3 gota | Profundidad |
| 8 | `agent/` con tool-use | La conversación |
| 9 | `decisions` + `why` | La gobernanza, demostrable |
| 10 | R4 incendios, R5 deslizamiento, `/public` | Si sobra tiempo |

**Regla:** a las 19:00 tiene que existir un corte end-to-end feo pero completo. Congelar funcionalidad a las 22:00.
