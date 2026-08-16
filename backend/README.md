# IOmido — backend

Backend de la demo de inteligencia de suelo y clima para centros de acopio.

## Arrancar

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Abrir <http://localhost:8000/docs>.

No hace falta `.env` para ejecutar la demo. Las fuentes externas degradan cuando
no responden, aunque el primer package puede tardar mientras vencen sus timeouts.

## Estado real

| Capacidad | Estado |
|---|---|
| Lote demo desde Excel | Implementado |
| Calidad geográfica y anomalías | Implementado |
| GP, incertidumbre y siguiente medición | Implementado |
| Zonas de manejo | Implementado |
| Riesgos de helada, sequía, gota y estacional | Implementado |
| Package único comprimido | Implementado |
| Ingesta idempotente | Implementada en memoria |
| Propuestas, decisiones y explicación | Implementadas con SQLite local |
| Unidad NPK porcentual de extremo a extremo | En migración `v0.2` |
| Formulaciones configurables `30-30-40` | En migración `v0.2` |
| Optimización entera sin precios | En migración `v0.2` |
| Persistencia durable y autenticación | Pendiente |
| Agente conversacional y TTS externo | Pendiente; no son ruta crítica |

## Advertencia de contrato

El Excel almacena porcentajes NPK. La primera fila es `2,1,1`, es decir N 2 %, P
1 %, K 1 %. El contrato `v0.1` todavía etiqueta el campo interpolado como ppm y
produce marcas, productos y precios heredados. Esa salida permite ejecutar la demo
actual, pero está obsoleta y no debe presentarse como diseño final.

El contrato objetivo `v0.2`:

- conserva porcentajes;
- usa formulaciones por grado, por ejemplo `30-30-40`;
- elimina marcas y precios;
- carga perfiles y formulaciones desde datos versionados;
- resuelve bultos enteros por ajuste nutricional;
- activa revisión por incertidumbre y límites, no por costo.

Ver [`../BACKEND.md`](../BACKEND.md) para el diseño completo y
[`../TAREAS.md`](../TAREAS.md) para el orden de migración.

## Módulos

| Ruta | Responsabilidad |
|---|---|
| `app/main.py` | API y caches demo |
| `app/schemas.py` | Contrato `v0.1`; punto de entrada de la migración |
| `app/ml/soil.py` | Calidad, GP, zonas y optimizador heredado |
| `app/ml/package.py` | Ensamble suelo + clima + recomendaciones |
| `app/risk/` | Motores climáticos activos |
| `app/sources/` | Clientes y cache en memoria |
| `app/governance/` | Propuestas, decisiones y auditoría local |

## Antes de afirmar que `v0.2` está lista

- No aparece `ppm` en OpenAPI ni en mocks.
- La primera fila sigue siendo `2,1,1` después del pipeline.
- No hay marcas, nombres químicos, precios ni costos en la respuesta.
- Los bultos son enteros y la solución pasa tests de cobertura/exceso.
- Ningún perfil agronómico activo carece de fuente y versión.
- La auditoría registra generación y decisión.
- Las lecturas sobreviven un reinicio.
