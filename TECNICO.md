# IOmido — documento técnico

Todo lo que hay debajo del mapa: stack, datos, modelos, optimización, uso de IA y
las decisiones de ingeniería que costaron trabajo. Para la narrativa del producto
ver [README.md](README.md); para las métricas y sus límites,
[MODEL_CARD.md](MODEL_CARD.md).

---

## 1. Stack

| Capa | Elección | Por qué |
|---|---|---|
| API | FastAPI 0.115 + Pydantic 2.10 | Tipado del contrato y OpenAPI generado, no escrito a mano |
| ML | scikit-learn 1.6 · NumPy 2.2 · SciPy 1.15 | Proceso gaussiano, KMeans, NearestNeighbors, Isolation Forest |
| Persistencia | SQLite (WAL, claves foráneas, triggers) | Local-first: un centro de acopio con mala conexión no puede depender de una base remota |
| Ingesta | openpyxl + `csv` | El técnico entrega Excel. Sin pandas: pesaba 66 MB en un bundle al límite |
| Transporte | httpx + `brotli-asgi` | Async para las fuentes externas; la grilla es grande y se comprime |
| IA opcional | `anthropic` 0.122 · Claude Sonnet 5 | Redacta la respuesta del asistente. No calcula nada |
| Frontend | HTML + CSS + JS de módulos, **sin build ni dependencias** | 3 459 líneas que se sirven tal cual. Cero `node_modules`, cero cadena de compilación que se rompa a las 3 a. m. |
| Despliegue | Vercel: estático + una función Python ASGI | Sin servidor que mantener y sin costo fijo |

Backend: 5 377 líneas de Python. Frontend: 3 459 de JS/CSS/HTML. Pruebas: 66,
todas offline.

## 2. Arquitectura

`SoilIntelligenceEngine` es el **único** camino que produce un package, una
propuesta o una explicación. No hay una segunda lógica en el frontend ni en un
script de demo: los mocks del repositorio se regeneran llamando a esta misma API
(`tools/build_mock.py`).

```text
lectura porcentual (sensor)
  → validación, idempotencia por client_id y escritura en SQLite
  → GP Matérn por N/P/K + incertidumbre por celda
  → benchmark leave-one-out contra IDW + zonas KMeans + siguiente punto
  → fuentes climáticas resilientes + años análogos
  → balance agronómico con parámetros versionados
  → búsqueda entera exacta sobre el catálogo del centro
  → propuesta `pending`
  → decisión humana
  → auditoría append-only
```

| Directorio | Responsabilidad |
|---|---|
| `app/domain/` | Entidades NPK, perfil, formulación, lote, lectura y errores |
| `app/repositories/` | Migraciones SQL y repositorio SQLite transaccional |
| `app/ml/` | GP, IDW, métricas, anomalías, zonas, aprendizaje activo, análogos |
| `app/agronomy/` | Perfiles YAML, conversión de bases y balance de masa |
| `app/optimization/` | Búsqueda entera acotada y exacta |
| `app/sources/` | Política uniforme de fuentes externas y fusión climática |
| `app/services/` | Casos de uso, motor, agente y explicador |
| `app/api/` | 35 rutas y schemas Pydantic |
| `app/governance/` | Propuestas, explicaciones, decisiones e historial |

### La convención que evita el error más caro

Todo el sistema usa **N, P y K elementales en porcentaje de masa**. Nunca óxidos,
nunca ppm, nunca las dos cosas mezcladas.

```text
suelo:        N_pct, P_pct, K_pct        base = elemental_mass_pct
formulación:  30-30-40 = 30 % N, 30 % P, 40 % K de la masa del bulto
```

Una fuente en base óxido se **rechaza** con `incompatible_npk_basis` salvo que
pase explícitamente por `oxide_grade_to_elemental`. El grado del bulto jamás se
resta del porcentaje medido en suelo: son magnitudes distintas y confundirlas es
exactamente el error que produce una recomendación absurda. La ecuación viaja
visible dentro de la respuesta:

```text
masa de suelo (kg/ha) = 10 000 m²/ha × profundidad (m) × densidad (kg/m³)
disponible (kg/ha)    = masa de suelo × porcentaje/100 × factor de disponibilidad
faltante (kg/ha)      = max(requerimiento por etapa − disponible, 0)
```

Con el perfil de demo y la zona 1: `1 800 000 kg/ha` de suelo muestreado →
`89,9 kg/ha` de N disponible frente a `180 kg/ha` de requerimiento →
`90,1 kg/ha` de faltante. Cada número de esa cadena está en el JSON.

**Ningún umbral agronómico es una constante de código.** Profundidad, densidad,
disponibilidad, requerimiento por etapa, máximos de seguridad y peso del bulto
viven en `backend/config/agronomy/*.yaml` con versión, cita, fecha de vigencia y
`validation_status`.

## 3. Los datos: qué entra y qué aporta cada fuente

Resumen de todo lo que entra al sistema:

| Fuente | Endpoint | Qué aporta | ¿Llave? |
|---|---|---|---|
| Sensor NPK del centro | `data/data_ejemplo.csv.xlsx` | 19 lecturas reales georreferenciadas del lote El Rosal | — |
| IDEAM (Socrata) | `datos.gov.co/resource/{s54a-sgyg, sbwg-7ju4, uext-mhny}.json` | Observación de estaciones físicas colombianas cercanas al lote | No |
| Open-Meteo Forecast | `api.open-meteo.com/v1/forecast` | 16 días de pronóstico horario en la coordenada del lote | No |
| NASA POWER | `power.larc.nasa.gov/api/temporal/daily/point` | 20 años de reanálisis diario del mismo punto | No |
| NOAA CPC ENSO | boletín versionado con fecha y URL | Fase e índice de El Niño / La Niña | n/a |
| Anthropic Claude | Messages API, `claude-sonnet-5` | Redacción en español sobre evidencia | Sí, opt-in |
| OpenStreetMap | `tile.openstreetmap.org/{z}/{x}/{y}.png` | Mapa base opcional del frontend | No |
| Perfil de cultivo | `backend/config/agronomy/*.yaml` | Requerimientos, densidad, disponibilidad, máximos | — |
| Catálogo del centro | `backend/config/formulations/*.yaml` | Formulaciones realmente disponibles en bodega | — |

Solo una necesita credencial, y es la única que se puede apagar sin perder una
función del producto.

### 3.1 El sensor (dato propio, real)

`data/data_ejemplo.csv.xlsx` — 19 mediciones georreferenciadas tomadas en el lote
El Rosal, Pasto (Nariño). Latitud, longitud, N %, P %, K %. La primera fila se
preserva exactamente como `N 2 %, P 1 %, K 1 %` y el importador lo verifica
(`conversion_applied: false`).

18 filas caen dentro del polígono declarado y alimentan el modelo. La 19.ª se
**conserva en la base** pero se excluye del ajuste espacial por geometría: un
dato mal ubicado no se borra, se anota. Es la diferencia entre un pipeline y una
limpieza manual que nadie puede auditar después.

### 3.2 IDEAM — el único dato de instrumento

Open-Meteo y NASA POWER son **productos de modelo**: interpolan y reanalizan. El
IDEAM opera pluviómetros y termómetros físicos, y publica sus lecturas como
datasets Socrata en el portal de datos abiertos de Colombia, sin llave de API:

| Variable | Recurso | Unidad |
|---|---|---|
| Precipitación | `s54a-sgyg` | mm |
| Temperatura del aire a 2 m | `sbwg-7ju4` | °C |
| Humedad relativa a 2 m | `uext-mhny` | % |

**Selección de estación.** Se filtra por caja numérica sobre `latitud`/`longitud`
—no por municipio, porque un lote no tiene por qué compartir municipio con su
estación más cercana— exigiendo dato de los últimos 7 días, y se elige la más
próxima. Para el lote El Rosal salen 11 candidatas y gana **Universidad de
Nariño – AUT `[52045080]` a 2,47 km**, que publicó ayer. Las series se piden por
`codigoestacion` y no por nombre: los nombres del dataset traen espacios
inconsistentes (`'UNIVERSIDAD DE NARINO  - AUT'`) y son mal identificador.

**El dato público no es dato limpio.** El dataset republica la misma lectura
varias veces: se observaron **19 registros idénticos** para un mismo instante,
sensor y estación. Sumar sin deduplicar inflaba la lluvia acumulada un **31 %**
—45,4 mm frente a los 34,6 mm reales— y el 24 de julio traía `n=2736` registros
donde lo correcto son 144 (uno cada 10 minutos). Se deduplica por marca de tiempo
y **se reporta cuántos registros se descartaron**, porque un número que nadie
puede auditar no vale más que una estimación.

**Cobertura parcial, dicha en voz alta.** En la ventana de 30 días la estación
solo reportó **12 días** de precipitación. Los 11,1 mm acumulados no son un total
mensual, y presentarlos como tal sería una lectura falsa: el package devuelve
`days_with_data` junto al acumulado y una limitación explícita.

**No alimenta las reglas de riesgo.** Entra como `climate.observed_context` y
como una entrada más de `sources[]`, para contrastar el modelo contra el
instrumento. Convertirlo en entrada del cálculo exige validar primero cuánto
representa una estación a 2,5 km del lote, y eso es trabajo de piloto.
`test_ideam.py` verifica que ningún `risk.inputs` contenga una clave del IDEAM.

Las tres series se piden en paralelo con `asyncio.gather`: en serie costaban
**7,08 s** de reloj y en paralelo **3,08 s**, y la segunda consulta sale de la
caché SQLite en **0,02 s** (TTL de 6 h, porque una estación publica cada diez
minutos pero el package no necesita ese detalle).

### 3.3 Open-Meteo Forecast — `api.open-meteo.com/v1/forecast`

Pronóstico de 16 días para una coordenada arbitraria, sin llave de API y sin
costo. Aporta lo que ninguna otra fuente da: **el futuro cercano en el punto
exacto del lote**, no de la cabecera municipal a 400 m de altitud de diferencia.

Se piden `temperature_2m_min/max`, `precipitation_sum`,
`et0_fao_evapotranspiration` diarios, y `temperature_2m`,
`relative_humidity_2m`, `precipitation` horarios. De ahí salen tres entradas:

- la mínima prevista → riesgo de **helada**;
- `precipitación − evapotranspiración` = balance hídrico → riesgo de **sequía**;
- horas con 10–24 °C y HR ≥ 90 % en las próximas 48 h → riesgo de **gota tardía**
  (*Phytophthora infestans*), que es lo que arruina un cultivo de papa en el alto
  andino.

### 3.4 NASA POWER — `power.larc.nasa.gov/api/temporal/daily/point`

20 años de reanálisis diario (`T2M`, `T2M_MIN`, `PRECTOTCORR`) para el mismo
punto. Aporta la **memoria**: sin ella, «va a llover poco» no significa nada. Con
ella se pregunta *«¿a qué año se parece este?»* y se responde con
`NearestNeighbors` sobre cuatro variables normalizadas (lluvia, mínima, media,
índice ENSO). El resultado son los años análogos que acompañan la propuesta.

### 3.5 Boletín ENSO (NOAA CPC) — versionado, no consultado

Fase e índice de El Niño / La Niña. Modula los riesgos de helada (+0,08) y sequía
(+0,15) cuando la fase es seca. Aporta la **escala estacional**, que ni el
pronóstico de 16 días ni la climatología histórica capturan.

Va como fixture versionado con fecha y URL, y no como llamada en vivo, por una
razón que decimos en voz alta: **NOAA CPC no publica ese aviso como una API JSON
estable**. Fingir un endpoint que no existe habría sido más cómodo y menos
honesto.

### 3.6 Catálogo del centro y perfil de cultivo

Configuración versionada, no datos de mercado. Tres formulaciones (`30-30-40`,
`20-10-30`, `10-20-20`) de 50 kg, declaradas por el centro. **Sin marcas, sin
nombres químicos, sin precios.** El objetivo del optimizador es nutricional, no
monetario: no publicamos una cifra de ahorro que no podemos sustentar.

### 3.7 La política que aplica a toda fuente externa

`ResilientJSONSource` envuelve cada llamada JSON con timeout configurable,
reintentos acotados, backoff exponencial con *jitter*, caché en SQLite con TTL
(3 h el pronóstico, 30 días el histórico), último valor válido, *circuit breaker*
y marcas de `stale`, `failed` y `degraded`.

Por defecto **`EXTERNAL_SOURCES_ENABLED=false`**: el sistema no toca Internet,
carga los fixtures versionados y lo declara en la respuesta:

```json
"warnings": ["Open-Meteo Forecast: el acceso a Internet está desactivado;
              se usa un fixture versionado sin conexión.
              El dato no se presenta como actual."]
```

Una demo que se cae por el wifi del auditorio no es una demo. Una demo que
disimula que está usando datos viejos es peor.

## 4. Los modelos

### 4.1 Inferencia espacial — el núcleo

`GaussianProcessRegressor` con kernel `ConstantKernel × Matérn(ν=1,5) +
WhiteKernel`. **Un modelo independiente por nutriente**, coordenadas proyectadas
a metros locales y normalizadas, semilla 42.

De 18 puntos a 140 celdas de 10 × 10 m dentro del polígono (10 × 14, con máscara
para lo que queda fuera). Cada celda recibe **media, desviación estándar e
intervalo del 95 %** por nutriente.

Que haga falta interpolar no es una suposición: en las lecturas reales, N va de
1 % a 27 %, K de 0 % a 13 %, y dos puntos separados 45 m marcan K de 1 % y de
13 %. Las tres zonas que salen del clustering tienen centroides de N `4,99 %`,
`9,58 %` y `16,37 %`. El lote no es homogéneo, y una dosis única se equivoca en
casi toda su superficie.

¿Por qué GP y no una red neuronal? Porque con 18 observaciones una red no
aprende: memoriza. El GP es el modelo correcto para *pocos datos densos en el
espacio*, y sobre todo devuelve una **distribución**, no un número. Ese es el
punto: el técnico necesita saber dónde el mapa se lo está inventando.

**Umbral de incertidumbre dinámico:** percentil 75 de la incertidumbre combinada
dentro del lote (`4,515022` puntos porcentuales en la corrida de referencia). No
es una constante mágica: se mueve con los datos. Lo que supera el umbral se
dibuja rayado en el mapa, y rayado significa *incierto*, nunca *bajo*.

Con una sola medición hay un *fallback* constante explícito, porque un lote nuevo
con un punto es el caso normal, no un error.

### 4.2 Benchmark contra IDW — y el resultado que no nos gustó

Validación **leave-one-out espacial** contra interpolación por distancia inversa
(potencia 2), disponible desde tres mediciones.

| Nutriente | GP MAE | GP RMSE | Cobertura 95 % | IDW MAE | IDW RMSE |
|---|---:|---:|---:|---:|---:|
| N | 5,515783 | 7,455675 | 0,833333 | 5,629854 | 7,349048 |
| P | 2,074505 | 2,692089 | 0,833333 | 2,244697 | 2,721642 |
| K | 2,868187 | 3,880008 | 0,833333 | 3,129466 | 3,787414 |

RMSE medio GP `4,675924` · IDW `4,619368` puntos porcentuales.

**GP no le gana a IDW en este dataset.** El sistema lo reporta como
`gp_better_than_idw: false` y no afirma lo contrario en ninguna pantalla.

Podríamos haber quitado el benchmark y nadie se habría enterado. Lo dejamos
porque un modelo sin línea base no es un modelo, es una decoración. GP se queda
por lo que IDW no puede dar —incertidumbre predictiva y muestreo activo— y eso,
con 18 puntos, todavía necesita validación. La cobertura observada de 0,833 está
por debajo de 0,95: los intervalos no están perfectamente calibrados y lo
decimos.

### 4.3 Aprendizaje activo — la parte que ahorra caminatas

Un técnico no puede medir 140 celdas. Puede medir una más. El sistema elige cuál
combinando **incertidumbre predictiva alta** y **distancia a las mediciones
existentes**, siempre dentro del polígono:

```json
"next_sample": {
  "predictive_uncertainty": { "value": 5.645817, "unit": "percentage_points" },
  "distance_to_nearest_measurement": { "value": 54.027, "unit": "m" },
  "potential_coverage_improvement": {
    "upper_bound_percentage_points": 6.84,
    "limitation": "Es una cota superior, no una reducción de incertidumbre prometida."
  }
}
```

Esa última línea es deliberada. Es una cota superior heurística, no una promesa.

### 4.4 Calidad y anomalías, escaladas al tamaño de la muestra

- **Geometría:** fuera del polígono → `valid_for_model = false`. Es el único
  criterio que excluye del ajuste.
- **Mediana / MAD:** disponible desde 3 observaciones.
- **Isolation Forest:** solo desde 12 observaciones. Por debajo de eso, un
  detector de anomalías entrenado sobre 5 puntos marca ruido y llama a eso
  aprendizaje.
- Una lectura sospechosa por **valor** conserva `valid_for_model = true`: se
  anota con método, score y motivo, y la decide una persona. El sistema no borra
  datos del productor por su cuenta.

### 4.5 Zonas de manejo

`StandardScaler + KMeans`, semilla 42, tres zonas pedidas. Si no hay estructura
suficiente devuelve una sola zona en vez de fabricar tres.

Limitación declarada en la model card: KMeans **fuerza** separación aunque la
variación agronómica real pueda ser continua. Las zonas son una herramienta
operativa —el técnico aplica por parcela, no por celda— no un descubrimiento.

### 4.6 Riesgos climáticos: reglas transparentes, no un clasificador falso

Helada, sequía y gota tardía son **reglas explícitas con umbrales visibles**, no
modelos entrenados. La razón está escrita en el propio código:

> «No se usaron etiquetas sintéticas: la probabilidad es el puntaje transparente
> de la regla.»

Entrenar un clasificador de heladas requiere heladas etiquetadas en este lote. No
las tenemos. Habríamos podido generar etiquetas sintéticas y presentar un
`RandomForest` con 94 % de accuracy sobre datos que nos inventamos. Eso no es
machine learning, es una demostración de que sabemos llamar a `.fit()`.

Cada riesgo entrega score, severidad, confianza, ventana temporal, entradas
exactas, fuentes, versión de la regla (`frost-rule/2.0.0`), acción sugerida y
limitaciones. El factor de confianza baja de 0,90 a **0,65** automáticamente
cuando las fuentes están degradadas.

Los riesgos implementados son **exactamente tres**, más la modulación estacional
por ENSO. No hay motor de incendios: el balance hídrico negativo indica
condiciones propicias para una temporada seca, y eso es todo lo que el sistema
puede afirmar.

### 4.7 Años análogos

`StandardScaler + NearestNeighbors` sobre los 20 años de NASA POWER, con lluvia,
temperatura mínima, temperatura media e índice ENSO.

## 5. Optimización entera

Las variables son **bultos**, y un bulto es un entero. Optimizar en continuo y
redondear después es lo que produce «aplique 2,7 bultos» o, peor, una solución
redondeada que viola el máximo de seguridad.

Para el catálogo pequeño de un centro se **enumeran exhaustivamente** todas las
combinaciones dentro de los límites configurados y se minimiza en orden
lexicográfico:

1. faltante elemental total (kg);
2. exceso elemental total (kg);
3. número total de bultos;
4. número de formulaciones distintas.

El orden importa: primero que no falte, después que no sobre, después que el
productor cargue menos peso, y al final que el técnico no tenga que mezclar
cuatro productos distintos en el lote.

Restricciones activas: solo formulaciones disponibles, máximo de bultos por zona
(40), y máximos de aplicación por nutriente derivados del perfil.

Resultado real de la zona 1:

```json
"optimizer": {
  "optimal_within_bounds": true,
  "evaluated_combinations": 12341,
  "feasible_combinations": 225,
  "objective_value": { "shortfall_kg": 0.0, "excess_kg": 48.896, "bags": 9,
                       "distinct_formulations": 2 }
}
```

Ocho bultos de `20-10-30` más uno de `30-30-40`. Faltante cero. No hay objetivo
monetario y no se publica una cifra de ahorro.

## 6. Cómo se usa la IA

Esta es la sección que importa, y la respuesta corta es: **la IA aporta seis
capacidades distintas y ninguna de ellas decide.**

| # | Dónde | Técnica | Qué aporta | Qué decide |
|---|---|---|---|---|
| 1 | Mapa del lote | Proceso gaussiano Matérn ×3 | 140 celdas desde 18 puntos, con incertidumbre por celda | Nada |
| 2 | Rayado del mapa | Umbral dinámico (P75) | Separa «lo sabemos» de «no lo sabemos» | Nada |
| 3 | Siguiente medición | Aprendizaje activo | A dónde ir mañana para aprender más con un solo punto | Nada |
| 4 | Zonas de manejo | KMeans normalizado | Unidades operables por el técnico | Nada |
| 5 | Años análogos | NearestNeighbors | A qué año se parece esta temporada | Nada |
| 6 | Asistente | Claude Sonnet 5 | Redacta en español claro sobre evidencia estructurada | Nada |

### 6.1 El asistente: cómo se le quita al modelo la posibilidad de mentir

`POST /v1/agent/ask` tiene **dos caminos y el modelo nunca es el primero**.

**Camino determinista.** Un enrutador de intenciones clasifica la pregunta en
seis rutas conocidas —estado del lote, razón de la formulación, siguiente
medición, riesgo climático, datos faltantes, confianza de la predicción— y
construye la respuesta **leyendo el package persistido**. Las cifras salen de la
base. Ese camino existe siempre, funciona sin llave de API y sin Internet, y es
lo que responde si todo lo demás falla.

**Camino de redacción.** Si `AI_EXPLAINER_ENABLED=true` y hay
`ANTHROPIC_API_KEY`, Claude Sonnet 5 recibe la pregunta, un resumen **compacto y
auditable** del package —sin grillas, sin series pesadas, sin el polígono— y la
respuesta ya calculada. Su trabajo es reescribirla con claridad. Para preguntas
abiertas fuera de las seis rutas puede responder desde la evidencia, pero **sin
emitir cifras**.

El *system prompt* tiene siete reglas duras. La que hace el trabajo:

> «No inventes, calcules, redondees ni conviertas cifras. Si hay respuesta
> calculada, copia sus números exactamente.»

Un prompt no es una garantía, así que hay un **verificador**. Después de recibir
la respuesta se extraen todos los números del texto, se normalizan formatos
(`1.234,50` y `1234.50` son el mismo valor) y se comparan contra los números que
había en la evidencia. Si aparece uno que no estaba:

```python
invented = _numbers(text) - allowed
if invented:
    logger.warning("[explainer] redacción descartada, cifras sin evidencia: %s", invented)
    return self._skip("unsupported_numbers", ...)
```

Se **descarta la redacción entera** y se devuelve la respuesta determinista. El
detalle que costó depurar: el guion solo cuenta como signo negativo cuando no
viene pegado a algo. En este dominio `zone-3` y `20-10-30` llevan guiones que no
son negativos, y leerlos como signo hacía que «zona 3» pareciera una cifra
inventada.

El mismo mecanismo degrada ante cualquier fallo —proveedor caído, timeout,
respuesta vacía, presupuesto agotado, entrada sobre el límite— y siempre hay
respuesta.

### 6.2 Presupuesto: el costo se conoce antes de gastarlo

Antes de cada llamada se cuenta la entrada con `messages.count_tokens`, se asume
que la salida agota su tope y se verifica contra el presupuesto. Si no cabe, no
se llama.

- `AI_MAX_INPUT_TOKENS = 8 000` · `AI_MAX_OUTPUT_TOKENS = 800`
- `AI_TOTAL_BUDGET_USD = 2,00` (máximo permitido por la configuración: 4)
- Precios estándar conservadores de Sonnet 5, no la tarifa promocional temporal
- **Techo por llamada: 0,036 USD**, y el costo real viaja en la respuesta

`thinking` va **desactivado**: aquí el modelo redacta evidencia, y el tope de
salida debe reservarse para texto visible.

Decimos también lo que este control **no** es: un contador en memoria no impone
un límite entre procesos serverless y se reinicia en cada arranque en frío. Por
eso el explicador está desactivado por defecto y el `.env.example` obliga a fijar
un límite de gasto en el *workspace* de Anthropic antes de habilitarlo.

### 6.3 Lo que la IA no hace, por diseño

- No calcula dosis. Eso es la ecuación de balance y el optimizador entero.
- No decide. Toda propuesta nace `pending`, `applied=false`,
  `human_decision_required=true`.
- No aprende de los datos del productor sin consentimiento explícito: los
  productores llevan `data_origin` y `consent_status` en la base.
- No puntúa agricultores ni evalúa crédito.
- No entra en las pruebas: los 66 tests corren contra un cliente falso, sin red y
  sin llave.

## 7. Por qué esto no se podía construir hace dos años

Empecemos por lo honesto: **casi nada de la matemática es nueva.** El kriging es
de 1951, IDW de 1968, KMeans de 1957, el balance de masa agronómico es más viejo
que todos nosotros. Si alguien dice que su innovación es usar un proceso
gaussiano, está vendiendo un libro de texto.

Lo que cambió es lo que se puede **componer**, y ahí sí hay cuatro cosas que en
2024 no estaban al alcance de dos personas en 24 horas:

### 7.1 Un modelo de lenguaje puede ser una capa opcional en vez del sistema

Este es el cambio de fondo. Hace dos años, «IA para el agro» significaba una de
dos cosas: un pipeline clásico sin capa de explicación —que el técnico no
entiende y no adopta— o un chatbot que respondía con confianza y se inventaba las
dosis.

Que Claude Sonnet 5 pueda **redactar sin calcular** requiere tres capacidades que
maduraron juntas:

1. **Seguimiento de instrucciones fiable en español bajo restricciones duras.**
   Siete reglas simultáneas, incluida «no emitas cifras» en una respuesta
   cualitativa. En 2024 eso era un *fine-tune*, no un *system prompt*.
2. **Conocer el costo antes de pagarlo.** `messages.count_tokens` permite
   verificar el presupuesto *antes* de la llamada. Sin eso, un tope de gasto es
   una esperanza.
3. **Precio y latencia que hacen la llamada desechable.** Con un techo de
   0,036 USD y 10 s de timeout, podemos permitirnos **tirar a la basura** la
   respuesta del modelo cada vez que introduce una cifra sin evidencia. Esa es la
   clave arquitectónica completa: el guard solo es viable porque el camino
   determinista siempre existe y el modelo cuesta lo que cuesta.

El resultado son ~230 líneas —`app/services/anthropic_explainer.py`— que se
pueden apagar con una variable de entorno sin que el producto pierda una función.
Un sistema donde el LLM es el cerebro no se puede apagar.

### 7.2 Datos climáticos punto a punto, abiertos y sin llave

Open-Meteo devuelve 16 días de pronóstico horario para una coordenada arbitraria
de los Andes, sin registro y sin costo. NASA POWER devuelve 20 años de reanálisis
diario para el mismo punto. Y el IDEAM publica las lecturas crudas de sus
estaciones como datasets consultables por API, lo que hace veinte años vivía en
un archivo institucional y hace diez se pedía por oficio. Hace pocos años,
contexto climático a resolución de lote significaba un contrato con un proveedor
meteorológico — un gasto que un centro de acopio de papa nunca va a aprobar para
40 proveedores pequeños.

Que estas APIs existan, sean gratuitas y respondan por coordenada es lo que
convierte «alerta de helada por lote» en una función de producto y no en una
línea de presupuesto. Y la política de datos abiertos del Estado colombiano es
parte de esa infraestructura: sin ella, contrastar un modelo global contra un
pluviómetro real a 2,5 km del lote no sería posible para nadie fuera de una
institución.

### 7.3 El stack científico completo dentro de una función efímera

`numpy 2.2 + scikit-learn 1.6 + scipy 1.15` corriendo dentro de una función
serverless de Vercel, con el GP y su validación leave-one-out en **300–400 ms**
sobre el lote demo (`model_run.inference_ms`; `397,023 ms` en la corrida
publicada en el mock).

Y no fue gratis: el límite del bundle son 250 MB descomprimidos y el primer
intento reportó **284,60 MB**. Quitamos pandas —solo abría el Excel y recorría
filas, lo hacen `openpyxl` y el módulo `csv`— y con eso entró. Ese detalle está
comentado en `requirements.txt`, porque es el tipo de cosa que el siguiente que
toque el archivo necesita saber.

Por qué importa: **sin costo fijo no hay producto**. Un sistema para pequeños
productores no puede arrancar con una factura mensual de servidor. Que el
cómputo científico corra en una función que solo cobra cuando alguien abre un
lote es lo que hace que el modelo de negocio cierre.

### 7.4 Que un equipo de tres escriba esto en 24 horas

5 377 líneas de backend, 3 459 de frontend, 66 pruebas offline, 35 endpoints con
OpenAPI, un esquema con triggers de auditoría y un model card con métricas
reproducidas. Con asistencia de IA en el desarrollo, dentro de la ventana de 24
horas de la hackathon.

Lo decimos porque es la parte que importa: el diferencial no fue escribir
código más rápido, fue tener tiempo sobrante para hacer el benchmark contra IDW
—y para dejarlo publicado cuando salió en contra.

### 7.5 Lo que seguiría sin poderse hacer hoy

Para mantener la simetría: no podemos afirmar precisión de laboratorio, no
podemos predecir rendimiento y no podemos entrenar un clasificador de heladas
para este lote. Faltan datos etiquetados y calibración, y ningún modelo por
grande que sea sustituye una muestra de suelo.

## 8. Ingeniería

### 8.1 Rendimiento medido

- **`spatial.run` corre en el pool de hilos.** El GP y su LOO son CPU pura
  (~700 ms) y dentro del event loop el proceso no atendía ni el *health check*.
  Medido después del cambio: `/health/live` responde en **1,9 ms** mientras un
  recálculo de 704 ms está en curso.
- **El tablero del centro lee dos proyecciones agregadas** —
  `latest_package_digests` y `reading_digests`— en vez de abrir el snapshot
  completo de cada lote. Con 61 lotes: **23 ms frente a 455 ms**.
- Las anotaciones de calidad de un recálculo se persisten en **una sola
  transacción**, no una por lectura.
- La grilla se comprime con Brotli en el transporte.

### 8.2 Persistencia y gobernanza

`001_initial.sql` crea `centers`, `plots`, `readings`, `crop_profiles`,
`formulations`, `model_runs`, `packages`, `proposals`, `decisions`, `audit_log`,
`external_api_cache`. `002_producers.sql` añade productores con `data_origin` y
`consent_status` explícitos.

Claves foráneas activas, WAL, transacciones, índices, `client_id` único para
idempotencia y UTC en todo. **Triggers de SQLite impiden `UPDATE` y `DELETE`
sobre `audit_log`** y registran automáticamente la creación de propuestas y
decisiones. La auditoría no depende de que el código se acuerde de escribirla.

Cada corrida del modelo persiste nombre, versión, parámetros, número de
observaciones, métricas, duración, limitaciones y **SHA-256 del conjunto de
entrada**. Se puede saber exactamente con qué datos se produjo una propuesta de
hace un mes.

### 8.3 Errores que el frontend puede usar

Cada excepción de dominio tiene su propio código y estado, para que la interfaz
reaccione en vez de mostrar «algo salió mal».

| Excepción | HTTP | `error.code` |
|---|---|---|
| `PlotHasNoReadingsError` | 409 | `plot_has_no_readings` |
| `NoPackageEvidenceError` | 409 | `no_package_evidence` |
| `SpatialInferenceError` | 422 | `spatial_inference_error` |
| `ImportValidationError` | 422 | `import_validation_error` |
| `OptimizationError` | 422 | `optimization_error` |
| `IncompatibleNPKBasis` | 422 | `incompatible_npk_basis` |
| `GovernanceError` | 404 | `governance_error` |
| `EngineError` | 400 | `engine_error` |

Un lote sin mediciones **no es un fallo**: es el estado inicial de todo lote
nuevo. El frontend ofrece importar, no una pantalla de error.

### 8.4 Idioma del contrato

Un solo público: un centro de acopio colombiano. La regla es explícita y
**verificable**:

- **En español** todo lo que una persona lee tal cual: acciones recomendadas,
  limitaciones, motivos de una anotación, explicación de la propuesta y mensajes
  de error.
- **En inglés** todo lo que es identificador de máquina: claves JSON, valores de
  enumeración (`pending`, `high`, `elemental_mass_pct`), nombres y versiones de
  modelo (`GaussianProcessRegressor-Matern`, `frost-rule/2.0.0`) y códigos de
  error.

`tests/test_operations.py` recorre el package y el tablero buscando prosa inglesa
en los campos que se renderizan. La regla no depende de que alguien se acuerde.

### 8.5 Seguridad

CORS configurable · `WRITE_API_KEY` opcional para endpoints mutables, comparada
con `secrets.compare_digest` · tamaño máximo de archivo · validación de nombres,
extensiones, tipos y rangos de porcentaje · no se registran secretos ·
`ANTHROPIC_API_KEY` vive en un `.env` que `.gitignore` excluye · logs JSON con
`request_id` y duración.

`login.html` y `register.html` son **prototipos visuales**. No hay autenticación
de usuarios y no la presentamos como si la hubiera.

## 9. Frontend

SPA estática sin build ni `node_modules`. Un shell con barra lateral y **nueve
secciones** —`resumen`, `lotes`, `mediciones`, `mapa`, `alertas`,
`recomendaciones`, `historial`, `reportes`, `configuracion`— más las vistas
`lote` y `productores`, que enrutan sin entrada propia en el menú.

Cada vista tiene su hash, así que el botón Atrás funciona y las vistas se pueden
enlazar; un hash desconocido cae en `#resumen`. Los iconos del menú van inline
como paths SVG: el shell debe pintar **sin una sola petición de red**.

`lib/api.js` es la **única** puerta de red. `lib/adapt.js` traduce el contrato v2
al modelo de vista sin modificar el JSON de origen. `lib/plotmap.js` renderiza el
mapa **sin tiles**: si OpenStreetMap no carga, el mapa de suelo sigue siendo
legible, que es el caso normal en una finca sin señal.

Reglas de interfaz que se verifican en la demo: nunca aparece `ppm`; nunca
aparece una marca, un nombre químico o un precio; el rayado siempre significa
incertidumbre; la severidad usa forma, texto **y** color, nunca solo color; y una
propuesta nunca se presenta como una orden.

## 10. Verificación

```powershell
python -m pytest backend/tests -q       # 66 pruebas, ninguna toca la red
python backend/scripts/demo_backend.py  # pipeline completo sin Internet
python tools/build_mock.py              # regenera el mock desde el motor real
```

| Archivo de pruebas | Cubre |
|---|---:|
| `test_operations.py` | 16 |
| `test_explainer.py` | 14 |
| `test_ideam.py` | 8 |
| `test_domain_agronomy.py` | 8 |
| `test_api_integration.py` | 7 |
| `test_ml.py` | 7 |
| `test_storage_sources.py` | 4 |
| `test_optimizer.py` | 2 |

Snapshot OpenAPI en `backend/openapi-v2.json`; el documento vivo en
`/openapi.json` y la documentación interactiva en `/docs`.

El catálogo completo de endpoints, sus payloads y el manejo de errores está en
[docs/API.md](docs/API.md).
