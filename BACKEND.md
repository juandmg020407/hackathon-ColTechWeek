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

## Persistencia y gobernanza

La migración `001_initial.sql` crea:

`centers`, `plots`, `readings`, `crop_profiles`, `formulations`, `model_runs`,
`packages`, `proposals`, `decisions`, `audit_log`, `external_api_cache`.

SQLite activa claves foráneas, WAL, transacciones e índices. `client_id` es único.
Triggers impiden `UPDATE` y `DELETE` sobre `audit_log`, y registran creación de
propuestas y decisiones. Toda propuesta nace `pending` y `applied=false`.

## API

Rutas principales:

- Operación: `/health/live`, `/health/ready`, `/v1/governance`.
- Modelos: `/v1/models`, `/v1/models/{id}/metrics`.
- Configuración: `/v1/centers`, formulaciones y perfiles.
- Lotes: CRUD, package, recompute y risk.
- Lecturas: individual, bulk e importación Excel/CSV.
- Gobernanza: proposals, why, decisions, history y audit.
- Conversación: `POST /v1/agent/ask`.

Las respuestas principales incluyen `contract_version`, unidades, convención,
validación, fuentes, versiones, tiempo, degradación y advertencias. Los errores
incluyen `request_id` y el middleware emite logs JSON con duración.

## Seguridad y presupuesto

- CORS configurable.
- `WRITE_API_KEY` opcional para endpoints mutables.
- tamaño máximo de archivo configurable;
- validación de nombres, extensiones, tipos y porcentajes;
- no se registran secretos;
- LLM desactivado por defecto;
- precios de tokens solo por variables de entorno;
- presupuesto opcional máximo por defecto: 1 USD;
- las pruebas no habilitan red ni proveedor pagado.

## Verificación

```powershell
python -m pytest backend/tests -q
python backend/scripts/demo_backend.py
python tools/build_mock.py
```

El snapshot OpenAPI está en `backend/openapi-v2.json`; la aplicación sirve el
documento vivo en `/openapi.json`.
