# Backend IOmido v0.2

## Principio central

`SoilIntelligenceEngine` es el único camino que produce packages, propuestas y
explicaciones:

```text
lectura porcentual
→ validación, idempotencia y SQLite
→ GP Matern por N/P/K + incertidumbre
→ benchmark IDW y zonas
→ fuentes climáticas resilientes + años análogos
→ balance agronómico configurado
→ búsqueda entera exacta
→ propuesta pendiente
→ decisión humana
→ auditoría append-only
```

Los mocks se regeneran llamando esta misma API mediante `tools/build_mock.py`.
No existe una segunda lógica para fabricar recomendaciones.

## Capas

| Directorio | Responsabilidad |
|---|---|
| `app/domain/` | Entidades NPK, perfil, formulación, lote y lectura |
| `app/repositories/` | Migraciones y repositorio SQLite transaccional |
| `app/ml/` | GP, IDW, métricas, anomalías, zonas, aprendizaje activo y análogos |
| `app/agronomy/` | Perfiles YAML, adaptadores de convención y balance explícito |
| `app/optimization/` | Búsqueda entera acotada y exacta |
| `app/sources/` | Política uniforme de fuentes y fusión climática |
| `app/services/` | Casos de uso y `SoilIntelligenceEngine` |
| `app/api/` | Rutas y schemas Pydantic |
| `app/governance/` | Propuestas, explicaciones, decisiones e historial |

## Idioma del contrato

El sistema tiene un solo público: un centro de acopio colombiano. Por eso la
regla es explícita y verificable:

- **En español** todo el texto que una persona lee tal cual: acciones
  recomendadas, limitaciones, motivos de una anotación de calidad, explicación
  de la propuesta, avisos y mensajes de error.
- **En inglés** todo lo que es identificador de máquina: claves JSON, valores de
  enumeración (`pending`, `high`, `elemental_mass_pct`), nombres y versiones de
  modelo (`GaussianProcessRegressor-Matern`, `frost-rule/2.0.0`) y códigos de
  error.

`tests/test_operations.py` recorre el package y el tablero buscando prosa
inglesa en los campos que se renderizan, así que la regla no depende de que
alguien se acuerde.

## Errores distinguibles

Cada excepción de dominio tiene su propio código y estado; el cliente puede
reaccionar en vez de mostrar un error genérico.

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

Un lote sin mediciones no es un fallo: es el estado inicial de todo lote nuevo,
y el frontend debe ofrecer la importación en lugar de una pantalla de error.

## Contrato NPK

El núcleo usa N, P y K elementales.

- Lectura de suelo: `mass_pct`, base `elemental_mass_pct`.
- Formulación: `mass_pct`, base `elemental_mass_pct`.
- Aportes y requerimientos: `kg` o `kg/ha`, siempre etiquetados.
- Una fuente en base óxido se rechaza, salvo paso explícito por
  `oxide_grade_to_elemental`.

La ecuación agronómica es visible en la respuesta:

```text
masa de suelo kg/ha
= 10 000 m²/ha × profundidad m × densidad kg/m³

nutriente estimado disponible
= masa de suelo × porcentaje/100 × factor de disponibilidad

faltante
= max(requerimiento por etapa − disponible, 0)
```

Profundidad, densidad, disponibilidad, requerimiento, máximos, fuentes, versión y
estado viven en `backend/config/agronomy/`. El perfil de demo no está validado.

## Inteligencia espacial

- `GaussianProcessRegressor` con Matern `nu=1.5`.
- Un modelo independiente por nutriente.
- Semilla 42 y parámetros registrados.
- Grilla dentro del polígono, media, desviación e intervalo del 95 %.
- Umbral de incertidumbre: percentil 75 de celdas interiores.
- Fallback constante seguro con una medición.
- LOO contra IDW desde tres mediciones.
- Mediana/MAD; Isolation Forest solo desde 12 puntos.
- Una anomalía de valor conserva `valid_for_model=true`; solo geometría excluye.
- KMeans normalizado y reproducible; una zona si faltan datos.
- Siguiente muestra por incertidumbre y distancia, siempre dentro del lote.

Cada ejecución persiste nombre, versión, parámetros, observaciones, métricas,
duración, hash de entrada y limitaciones.

## Clima

`ResilientJSONSource` aplica a fuentes JSON externas:

- timeout configurable;
- reintentos acotados;
- backoff exponencial con jitter;
- caché SQLite con TTL;
- último valor válido;
- circuit breaker;
- marca temporal, URL, stale, failed y degraded.

El modo por defecto no usa Internet. Carga fixtures versionados y marca el
resultado como degradado/no actual. NASA POWER alimenta el modelo de años
análogos `StandardScaler + NearestNeighbors`. ENSO es un boletín local versionado
con fecha y URL porque NOAA CPC no ofrece ese aviso como API JSON estable.

Helada, sequía y gota tardía son reglas transparentes, no clasificadores
entrenados con etiquetas fabricadas. Cada riesgo entrega score, severidad,
confianza, ventana, entradas, fuentes, versión, acción y limitaciones.

## Optimizador

Las variables son números enteros de bultos. Para el catálogo pequeño se enumeran
todas las combinaciones dentro del máximo configurado y se minimiza:

1. faltante elemental total;
2. exceso elemental total;
3. bultos totales;
4. formulaciones distintas.

Se respetan disponibilidad, límites por nutriente, zona y máximo de bultos. El
resultado informa combinaciones evaluadas y óptimo dentro de los límites. No hay
objetivo monetario.

## Rendimiento y arranque

- `spatial.run` corre en el pool de hilos. El GP y su validación leave-one-out
  son CPU pura (~700 ms); dentro del event loop el proceso no atendía ni el
  health check. Medido: `/health/live` responde en 1,9 ms mientras un recálculo
  de 704 ms está en curso.
- El tablero del centro lee dos proyecciones agregadas —`latest_package_digests`
  y `reading_digests`— en vez de abrir el snapshot completo de cada lote. Con
  61 lotes: 23 ms frente a 455 ms leyendo package por package.
- Las anotaciones de calidad de un recálculo se persisten en una sola
  transacción, no en una por lectura.
- `DEMO_AUTO_IMPORT=true` siembra el Excel de demostración solo si el lote está
  vacío. En serverless la base vive en `/tmp` y se pierde en cada arranque en
  frío: sin esta siembra el despliegue servía el mock del frontend en vez del
  backend.
- `/health/ready` reporta centros, lotes, lotes con mediciones y total de
  lecturas, para poder diagnosticar un despliegue desde fuera.

## Persistencia y gobernanza

La migración `001_initial.sql` crea:

`centers`, `plots`, `readings`, `crop_profiles`, `formulations`, `model_runs`,
`packages`, `proposals`, `decisions`, `audit_log`, `external_api_cache`.

La migración `002_producers.sql` añade productores con origen de datos y estado
de consentimiento explícitos, y vincula cada lote con su productor cuando se
dispone de esa relación.

SQLite activa claves foráneas, WAL, transacciones e índices. `client_id` es único.
Triggers impiden `UPDATE` y `DELETE` sobre `audit_log`, y registran creación de
propuestas y decisiones. Toda propuesta nace `pending` y `applied=false`.

## API

Rutas principales:

- Operación: `/health/live`, `/health/ready`, `/v1/governance`.
- Modelos: `/v1/models`, `/v1/models/{id}/metrics`.
- Configuración: `/v1/centers`, formulaciones y perfiles.
- Red: dashboard por centro, productores y lotes por productor.
- Lotes: CRUD, package, recompute y risk.
- Lecturas: consulta por lote, individual, bulk e importación Excel/CSV.
- Gobernanza: proposals, why, decisions, history y audit.
- Conversación: `POST /v1/agent/ask`.

Las respuestas principales incluyen `contract_version`, unidades, convención,
validación, fuentes, versiones, tiempo, degradación y advertencias. Los errores
incluyen `request_id` y el middleware emite logs JSON con duración.

## Agente conversacional sobre evidencia

`POST /v1/agent/ask` conserva rutas deterministas para las preguntas operativas
más frecuentes. Para preguntas abiertas entrega a Claude un resumen compacto y
auditable del package, sin grillas, series pesadas ni el polígono del lote.

El modelo configurado es `claude-sonnet-5`. No decide ni aplica propuestas:

- las rutas cuantitativas solo pueden repetir cifras de la respuesta
  determinista; las preguntas abiertas generadas no pueden emitir cifras;
- Sonnet 5 se llama con `thinking=disabled`, porque aquí redacta evidencia y el
  tope de salida debe reservarse para texto visible;
- si el modelo falla, tarda o se queda sin presupuesto, se devuelve el texto
  determinista o un rechazo explícito y la demo no se cae;
- el costo real de cada llamada se acumula contra `AI_TOTAL_BUDGET_USD` y viaja
  en la respuesta. Las rutas conocidas incluyen `answer_deterministic` para
  poder comparar.

`llm_used` dice si la redacción se usó, y `model_versions.explainer` identifica
la versión del agente. Con los topes actuales, una llamada no puede estimarse en
más de 0,036 USD usando el precio estándar conservador de Sonnet 5.

## Seguridad y presupuesto

- CORS configurable.
- `WRITE_API_KEY` opcional para endpoints mutables, comparada con
  `secrets.compare_digest`.
- tamaño máximo de archivo configurable;
- validación de nombres, extensiones, tipos y porcentajes;
- no se registran secretos;
- el agente pagado está desactivado por defecto y requiere
  `AI_EXPLAINER_ENABLED=true` además de `ANTHROPIC_API_KEY`;
- precios de tokens solo por variables de entorno;
- presupuesto máximo por defecto: 2 USD, verificado antes de cada llamada y
  acumulado con el consumo real que reporta la API dentro de cada proceso;
- ese contador en memoria no sustituye un límite de gasto del proveedor y se
  reinicia en un nuevo proceso o arranque en frío;
- antes de habilitarlo en serverless se debe fijar un límite de gasto en el
  workspace de Anthropic;
- `ANTHROPIC_API_KEY` vive en el `.env` local, que `.gitignore` excluye;
- las pruebas no habilitan red ni proveedor pagado: el explicador se prueba
  contra un cliente falso.

## Verificación

```powershell
python -m pytest backend/tests -q      # 57 pruebas offline
python backend/scripts/demo_backend.py
python tools/build_mock.py
```

El snapshot OpenAPI está en `backend/openapi-v2.json`; la aplicación sirve el
documento vivo en `/openapi.json`.
