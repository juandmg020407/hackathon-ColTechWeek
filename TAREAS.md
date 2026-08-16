# Roadmap de migración `v0.1 → v0.2`

Este archivo sustituye las notas operativas de la hackathon. No contiene llaves,
cuentas ni pasos manuales de proveedores. El objetivo es que cada cambio pueda
subirse como un commit pequeño, verificable y fácil de revisar.

## Decisiones cerradas

- Cliente inicial: centros de acopio.
- Beneficiarios: pequeños productores y comunidad agrícola.
- Demo: cultivo de papa de 0,69 ha en Pasto, Nariño.
- Unidad del sensor: porcentaje NPK.
- Ejemplo: `2,1,1` = N 2 %, P 1 %, K 1 %.
- Formulaciones: grados NPK como `30-30-40`.
- Sin marcas, nombres químicos, precios ni ahorro monetario.
- Parámetros de dominio fuera del código y con versión/fuente.
- Optimización por cobertura nutricional, exceso y bultos; no por precio.
- La IA central es inferencia espacial, incertidumbre y muestreo activo.

## P0 · Congelar el contrato

### Cambio

- Añadir `contract_version`.
- Crear schemas `NpkPct`, `Formulation`, `CropProfile` y package `v0.2`.
- Mantener un adaptador temporal para leer el mock `v0.1`.
- Definir una única convención N/P/K en el límite del dominio.

### Archivos

```text
backend/app/schemas.py
backend/app/ml/package.py
frontend/lib/adapt.js
FRONTEND.md
BACKEND.md
```

### Criterios

- La lectura `2,1,1` sale de la API como `2 %, 1 %, 1 %`.
- OpenAPI documenta `%`.
- Un package declara su versión.
- Tests rechazan porcentajes menores que 0 o mayores que 100.

### Commit

```text
feat(contract): introduce versioned NPK percentage schema
```

## P0 · Eliminar calibración ppm heredada

### Cambio

- Retirar `CAL` y `calibrate()` del camino principal.
- Interpolar directamente `N_pct`, `P_pct` y `K_pct`.
- Renombrar grillas, medias, sigma y tooltips.
- Regenerar ambos mocks desde el mismo pipeline.

### Criterios

- `rg -i "ppm" backend frontend/mock mock` no devuelve campos activos.
- GP recibe y devuelve porcentajes.
- Primera fila y puntos del mock conservan valores originales.

### Commit

```text
refactor(soil): preserve sensor NPK percentages end to end
```

## P0 · Sacar parámetros de dominio del código

### Cambio

Crear configuración versionada:

```text
backend/domain/sensor_profiles.json
backend/domain/crop_profiles.json
backend/domain/formulation_catalog.json
backend/domain/risk_thresholds.json
backend/domain/review_policies.json
```

Mover allí:

- objetivos por cultivo/variedad/etapa;
- respuesta por punto porcentual;
- peso y disponibilidad de bultos;
- formulaciones NPK;
- límites de aplicación;
- umbrales de riesgo y revisión.

Los perfiles de ejemplo deben marcarse `draft` hasta revisión agronómica.

### Criterios

- `soil.py` no contiene catálogo comercial ni perfil de papa literal.
- Cada perfil tiene `id`, `version`, `source`, `valid_from` y `status`.
- El backend falla de forma clara si falta un perfil requerido.

### Commit

```text
refactor(domain): load crop and formulation profiles from versioned data
```

## P0 · Optimización entera sin precios

### Cambio

- Eliminar `cop_bulto`, `costo_cop`, genérico y ahorro del dominio.
- Reemplazar `linprog + ceil` por MILP o búsqueda entera acotada.
- Permitir formulaciones configuradas por centro.
- Optimizar, en orden: faltante, exceso, número de bultos y variedad de grados.

### Casos de prueba

- Una formulación exacta cubre el requerimiento sin exceso innecesario.
- La solución nunca contiene fracciones de bulto.
- Una formulación no disponible no se selecciona.
- Un problema imposible devuelve faltantes explícitos, no una lista vacía.
- Empates generan una salida determinista.

### Commit

```text
feat(optimization): select integer NPK grades without price assumptions
```

## P0 · Actualizar gobernanza

### Cambio

- Corregir el nombre de columna de auditoría y no silenciar errores críticos.
- Versionar IDs de propuesta con revisión o hash del package.
- Retirar revisión basada en costo.
- Activar revisión por confianza, límites, disponibilidad y política del centro.
- Separar identidad declarada de rol autenticado.

### Criterios

- Generar y decidir una propuesta incrementa `audit_log`.
- Un actor no autenticado no puede declararse técnico.
- Recalcular un lote produce una revisión identificable.
- “¿Por qué?” nunca muestra precios ni marcas.

### Commits

```text
fix(governance): persist audit events and surface failures
feat(governance): review proposals by confidence and agronomic limits
```

## P1 · Migrar el frontend

### Cambio

- Mostrar `%` en mapa, tooltips y tarjetas.
- Reemplazar productos/costos por grado, bultos y peso.
- Añadir contexto centro → red → lote.
- Conectar aceptar, rechazar y derivar.
- Mantener explicación e incertidumbre visibles.

### Criterios

- No aparece `ppm`, una marca, un nombre químico ni `$`.
- El centro de acopio es visible antes o dentro del lote.
- El usuario puede completar una decisión real.
- Sin basemap, los datos continúan legibles.

### Commits

```text
feat(frontend): render NPK percentage contract
feat(frontend): show configurable formulation grades
feat(frontend): add collection-center lot context
feat(frontend): wire proposal decisions
```

## P1 · Persistencia y offline real

### Cambio

- Persistir lecturas e idempotencia fuera de memoria.
- Guardar el último package vivo para una API cross-origin.
- Implementar outbox IndexedDB con backoff.
- Añadir cache durable y TTL para fuentes.

### Criterios

- Reiniciar el backend no pierde una lectura aceptada.
- Reintentar el mismo `client_id` devuelve el mismo resultado.
- Tras una carga online, modo avión abre ese package, no solo el mock.
- Las fuentes vencidas muestran antigüedad y degradación.

### Commits

```text
feat(storage): persist readings and idempotency
feat(pwa): add reading outbox and last-live package cache
```

## P1 · Pruebas y CI

### Suite mínima

- calidad geográfica;
- anomalías robustas;
- GP y dimensiones de grilla;
- porcentajes y formulaciones;
- optimización entera;
- riesgos con datos faltantes;
- auditoría append-only;
- contrato OpenAPI;
- adaptador frontend;
- smoke test package → propuesta → decisión → explicación.

### Commit

```text
test: cover NPK package and human decision flow
```

## P2 · Producto y despliegue

- Autenticación y roles por centro.
- Catálogo multi-centro de lotes y formulaciones.
- Base durable y migraciones.
- Configuración runtime del backend en el frontend.
- Deploy reproducible y health checks.
- Observabilidad sin exponer datos del productor.
- Imágenes reales del proceso de medición para el README.
- Video final de máximo un minuto.

Commits sugeridos:

```text
feat(auth): scope users and plots by collection center
chore(deploy): add reproducible backend and frontend configuration
docs(readme): add real sensor capture and demo visuals
```

## Definición de terminado para `v0.2`

- [ ] Datos del sensor en porcentaje de extremo a extremo.
- [ ] Formulaciones configurables por grado NPK.
- [ ] Sin marcas, precios o ahorro monetario.
- [ ] Sin perfiles agronómicos escondidos en Python.
- [ ] Optimizador entero cubierto por tests.
- [ ] Auditoría funcional.
- [ ] Centro de acopio visible como cliente y operador.
- [ ] Lote de Pasto reproducible desde Excel hasta UI.
- [ ] Mocks generados, no editados manualmente.
- [ ] README describe exactamente lo que corre.
- [ ] Working tree revisado y commits granulares publicados.
