# API IOmido para el frontend

Contrato actual: `2.0`. En desarrollo, la documentación interactiva está en
`http://localhost:8000/docs` y el documento máquina en `/openapi.json`.

## Orden recomendado de consumo

1. Portada del centro: `GET /v1/centers/{center_id}/dashboard`.
2. Detalle de productor: usar `dashboard.producers[]` o
   `GET /v1/producers/{producer_id}/plots`.
3. Experiencia del lote: `GET /v1/plots/{plot_id}/package`.
4. Captura: `POST /v1/readings`; después
   `POST /v1/plots/{plot_id}/recompute`.
5. Explicación: `POST /v1/agent/ask`.
6. Decisión humana: `POST /v1/decisions`.

El dashboard cuenta únicamente registros persistidos. `data_scope` indica si
son de demostración, piloto u operación; no se deben presentar como impacto
validado.

## Centro y red

| Método | Ruta | Uso en interfaz |
|---|---|---|
| GET | `/v1/centers` | Selector de centro |
| GET | `/v1/centers/{center_id}` | Cabecera y estado del centro |
| GET | `/v1/centers/{center_id}/dashboard` | KPIs, prioridades, riesgo, productores y lotes |
| GET | `/v1/centers/{center_id}/producers` | Listado simple de productores |
| POST | `/v1/centers/{center_id}/producers` | Crear productor |
| GET | `/v1/producers/{producer_id}` | Ficha del productor |
| PUT | `/v1/producers/{producer_id}` | Reemplazar ficha y consentimiento |
| GET | `/v1/producers/{producer_id}/plots` | Lotes del productor |

El dashboard es el endpoint principal para una portada de alto impacto. Devuelve
`summary`, `priority_queue`, `risk_horizon`, `producers[].plots[]` y
`data_scope`.

Payload para crear o actualizar un productor:

```json
{
  "display_name": "Productor 001",
  "municipality": "Pasto, Nariño",
  "data_origin": "pilot",
  "consent_status": "granted",
  "consent_updated_at": "2026-08-16T10:00:00Z"
}
```

Para una demo se usa `data_origin=demonstration` y
`consent_status=demonstration`. Un consentimiento `granted` exige fecha.

## Lotes, lecturas y cálculo

| Método | Ruta | Uso en interfaz |
|---|---|---|
| GET | `/v1/plots?center_id=&producer_id=` | Buscar lotes; filtros opcionales |
| POST | `/v1/plots` | Crear un lote |
| GET | `/v1/plots/{plot_id}` | Metadatos y polígono |
| GET | `/v1/plots/{plot_id}/readings?valid_only=false` | Tabla y mapa de lecturas |
| GET | `/v1/plots/{plot_id}/package?refresh=false` | Experiencia completa del lote |
| POST | `/v1/plots/{plot_id}/recompute` | Recalcular ML, clima y propuesta |
| GET | `/v1/plots/{plot_id}/risk` | Riesgo sin transferir toda la grilla |
| POST | `/v1/readings` | Registrar una lectura idempotente |
| POST | `/v1/readings/bulk` | Registrar hasta 500 lecturas |
| POST | `/v1/readings/import?plot_id={plot_id}` | Importar CSV/XLS/XLSX multipart |

Lectura individual:

```json
{
  "plot_id": "nar-001",
  "latitude": 1.248,
  "longitude": -77.267,
  "npk_pct": {"N": 2, "P": 1, "K": 1, "basis": "elemental_mass_pct"},
  "measured_at": "2026-08-16T10:00:00Z",
  "client_id": "telefono-01:lectura-0001"
}
```

`client_id` hace la captura idempotente. Si la lectura cambia el modelo, la
respuesta marca `recompute_required=true`; el frontend debe ofrecer el recálculo.

El `package` contiene `plot`, `measurements`, `spatial.grid`, `spatial.zones`,
`spatial.next_sample`, `model_run.metrics`, `climate`, `crop_profile` y
`proposal`. La grilla puede ser grande: el backend aplica Brotli y el frontend
debe evitar `refresh=true` en cada navegación.

## Configuración agronómica

| Método | Ruta | Uso |
|---|---|---|
| GET | `/v1/crop-profiles` | Perfiles disponibles |
| GET | `/v1/crop-profiles/{profile_id}` | Parámetros, fuentes y validación |
| GET | `/v1/centers/{center_id}/formulations` | Catálogo N-P-K del centro |
| POST | `/v1/centers/{center_id}/formulations` | Crear formulación |
| PUT | `/v1/centers/{center_id}/formulations/{formulation_id}` | Actualizar formulación |

## Propuesta, decisión y auditoría

| Método | Ruta | Uso |
|---|---|---|
| GET | `/v1/proposals/{proposal_id}` | Propuesta pendiente |
| GET | `/v1/proposals/{proposal_id}/why` | Explicación paso a paso |
| POST | `/v1/decisions` | Aceptar, rechazar, modificar o remitir |
| GET | `/v1/decisions/{decision_id}` | Resultado de una decisión |
| GET | `/v1/decisions/{identifier}/history` | Historial por decisión o propuesta |
| GET | `/v1/audit?entity_type=&entity_id=` | Eventos append-only |
| GET | `/v1/governance` | Reglas y conteos de gobernanza |

Payload de decisión:

```json
{
  "proposal_id": "proposal-...",
  "action": "refer",
  "actor": {"type": "farmer", "id": "producer-001"},
  "note": "Solicitar revisión del técnico"
}
```

Una aceptación no aplica automáticamente la formulación: conserva la revisión
técnica obligatoria.

## Modelos y asistente

| Método | Ruta | Uso |
|---|---|---|
| GET | `/v1/models` | Ejecuciones espaciales disponibles |
| GET | `/v1/models/{model_id}/metrics` | GP vs. IDW, cobertura y límites |
| POST | `/v1/agent/ask` | Preguntas ancladas al último package |

```json
{"plot_id": "nar-001", "question": "¿Qué debería priorizar hoy?"}
```

Las preguntas operativas numéricas usan respuestas deterministas. Claude es
opcional y de activación explícita; las preguntas abiertas generadas por el
modelo no pueden introducir cifras. El cliente debe distinguir `llm_used`,
`answered`, `intent`, `degraded` y `warnings`.

## Operación y errores

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health/live` | Proceso vivo |
| GET | `/health/ready` | SQLite listo |

Todos los endpoints devuelven `contract_version`, `units`, `npk_convention`,
`validation_status`, `sources`, `model_versions`, `generated_at`, `degraded` y
`warnings`.

```json
{
  "contract_version": "2.0",
  "generated_at": "...",
  "error": {
    "code": "plot_has_no_readings",
    "message": "el lote nar-002 no tiene mediciones: importe un archivo o registre una lectura antes de calcular",
    "request_id": "...",
    "details": null
  }
}
```

`error.code` distingue la situación y la interfaz debe reaccionar a él:

| `code` | HTTP | Qué debe hacer la interfaz |
|---|---|---|
| `plot_has_no_readings` | 409 | Ofrecer importar o capturar una medición, no mostrar un error |
| `no_package_evidence` | 409 | Ofrecer recalcular antes de preguntar al asistente |
| `import_validation_error` | 422 | Mostrar el motivo y dejar reintentar con otro archivo |
| `spatial_inference_error` | 422 | Indicar que las mediciones no permiten inferir todavía |
| `optimization_error` | 422 | Revisar catálogo y límites del perfil |
| `validation_error` | 422 | Corregir el formulario; `details` trae los campos |
| `http_error` | 4xx | Recurso inexistente o sin autorización |

`error.message` viene en español y se puede mostrar tal cual.

Los endpoints de escritura aceptan `X-API-Key` cuando `WRITE_API_KEY` está
configurada. No existe todavía autenticación de usuarios: `login.html` y
`register.html` son prototipos y no deben presentarse como seguridad real.
