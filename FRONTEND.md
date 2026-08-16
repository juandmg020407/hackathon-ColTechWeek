# IOmido — contrato y experiencia del frontend

El frontend tiene dos contextos conectados:

1. **Centro de acopio:** identifica lotes que requieren medición o revisión.
2. **Lote:** muestra suelo, incertidumbre, formulación propuesta, clima y decisión.

El productor puede recibir una vista simplificada o una respuesta de voz, pero el
cliente y operador principal es el centro de acopio.

## Estado actual

La demo es una SPA estática sin build ni dependencias. Carga un único package y
funciona con un mock cuando el backend no responde.

```text
frontend/
├── index.html
├── app.js
├── style.css
├── sw.js
├── pitch.html
├── login.html
├── register.html
├── lib/
│   ├── api.js
│   ├── adapt.js
│   ├── assistant.js
│   ├── heatsurface.js
│   ├── plotmap.js
│   └── slippy.js
└── mock/package-nar-001.json
```

La navegación actual entra directamente al lote. La vista de red del centro y el
contrato NPK en porcentajes forman parte de la migración `v0.2`.

## Principios de interfaz

- Una pantalla debe responder una pregunta concreta.
- Porcentajes NPK siempre visibles con `%`.
- Nunca mostrar ppm para los datos de este sensor.
- Nunca mostrar marcas, nombres químicos ni precios.
- Una formulación se presenta como grado: `30-30-40`.
- El rayado siempre significa incertidumbre, no valor bajo.
- Severidad usa forma, texto y color; nunca solo color.
- Toda modificación climática incluye factor y motivo.
- Una propuesta no se presenta como una orden.
- La app debe seguir abriendo si no hay conectividad.

## Personas y pantallas

### 1. Red del centro

Objetivo: decidir qué lote visitar o revisar primero.

```text
Centro de Acopio Nariño
32 productores · 41 lotes

4  requieren revisión
3  necesitan nueva medición
2  tienen riesgo climático alto

[ Lote El Rosal · papa · Pasto ]
[ Lote La Esperanza · papa · Tangua ]
```

La demo puede tener un solo centro y un solo lote, pero la jerarquía debe existir en
el modelo visual.

### 2. Mapa del lote

Debe mostrar:

- cultivo, municipio, área y centro de acopio;
- selector N/P/K;
- escala en porcentaje;
- contorno y mediciones;
- celdas inciertas rayadas;
- siguiente punto de medición;
- última actualización y origen del paquete.

Ejemplo de lectura:

```text
Punto 01 · N 2 % · P 1 % · K 1 %
```

### 3. Formulación propuesta

```text
Zona 1 · 0,43 ha

Formulación NPK sugerida
30-30-40

Cantidad sugerida
2 bultos de 50 kg

Por qué
Es la formulación disponible que cubre mejor el faltante de esta zona
con el menor exceso estimado.

[ ¿Por qué? ] [ Aceptar ] [ Pedir revisión ]
```

No debe aparecer costo ni ahorro. El impacto se comunica como mejor ajuste,
reducción de exceso y capacidad de priorizar asistencia, no como una cifra monetaria
sin validación.

### 4. Lo que viene

Máximo tres alertas, ordenadas por severidad, probabilidad y confianza. Solo la
primera inicia expandida.

Cada tarjeta incluye:

- título en lenguaje llano;
- ventana temporal;
- confianza;
- acciones sugeridas;
- modelo, entradas y fuentes;
- cambios que produjo sobre la recomendación.

### 5. Decisión humana

Estados:

```text
pendiente
aceptada
rechazada
derivada
modificada
pendiente_revision
```

La revisión técnica `v0.2` se activa por incertidumbre, límites agronómicos o una
regla del centro, no por precio.

### 6. Respuesta al productor

La vista o voz simplificada puede decir:

> Para esta zona se sugiere la formulación NPK 30-30-40. El técnico debe confirmar
> la cantidad antes de aplicarla porque todavía hay incertidumbre entre los puntos
> medidos.

La respuesta siempre aparece en texto aunque también se reproduzca en voz.

## Conexión con el backend

La implementación actual no usa Vite. La URL se configura antes de cargar
`app.js`:

```html
<script>
  window.NPK_API_BASE = "https://api.example.com";
</script>
```

No usar `VITE_API_URL` mientras el frontend siga siendo estático y sin build.

`lib/api.js` es la única puerta de red. El objetivo se mantiene en un round-trip
para abrir un lote:

```text
GET /v1/plots/{id}/package
```

## Contrato actual y objetivo

### `v0.1` — implementado

El JSON actual contiene campos como `unidad: ppm`, `promedio_ppm`, productos y
costos. Se mantienen temporalmente para que la demo actual siga cargando, pero no
son el contrato final.

### `v0.2` — contrato objetivo

```ts
export type Nutrient = "N" | "P" | "K";

export interface NpkPct {
  N: number;
  P: number;
  K: number;
}

export interface FormulationRecommendation {
  grade: string;              // "30-30-40"
  npk_pct: NpkPct;
  bags: number;
  bag_weight_kg: number;
  reason: string;
}

export interface GridV2 {
  unit: "pct";
  cols: number;
  rows: number;
  cell_m: number;
  origin: [number, number];
  N_pct: number[];
  P_pct: number[];
  K_pct: number[];
  sigma_pct: number[];
  sigma_threshold_pct: number;
  mask: number[];
}

export interface ZoneV2 {
  id: string;
  area_ha: number;
  cells: number[];
  mean_npk_pct: NpkPct;
  recommendation: FormulationRecommendation | null;
  proposal_id: string;
}
```

Reglas de validación:

- todos los porcentajes están entre 0 y 100;
- arrays de grilla tienen longitud `cols × rows`;
- `grade` coincide con `npk_pct`;
- `bags` es entero no negativo;
- no existen `price`, `cost`, `brand` ni `product_name`;
- `contract_version` es obligatorio.

## Ejemplo de package `v0.2`

```json
{
  "contract_version": "2.0",
  "center": {
    "id": "acopio-demo",
    "name": "Centro de acopio demo"
  },
  "plot": {
    "id": "nar-001",
    "name": "Lote El Rosal",
    "municipality": "Pasto, Nariño",
    "crop": "papa",
    "area_ha": 0.69
  },
  "grid": {
    "unit": "pct",
    "cols": 20,
    "rows": 28,
    "cell_m": 5,
    "N_pct": [],
    "P_pct": [],
    "K_pct": [],
    "sigma_pct": [],
    "sigma_threshold_pct": 0.9,
    "mask": []
  },
  "zones": [
    {
      "id": "z1",
      "area_ha": 0.43,
      "cells": [],
      "mean_npk_pct": { "N": 2.4, "P": 1.2, "K": 1.6 },
      "recommendation": {
        "grade": "30-30-40",
        "npk_pct": { "N": 30, "P": 30, "K": 40 },
        "bags": 2,
        "bag_weight_kg": 50,
        "reason": "Mejor cobertura del faltante con menor exceso entre las formulaciones disponibles."
      },
      "proposal_id": "rec-nar-001-z1-rev-001"
    }
  ],
  "risks": [],
  "generated_at": "2026-08-15T20:00:00-05:00",
  "degraded": false
}
```

Los números de recomendación son ilustrativos hasta que el backend `v0.2` genere
el mock desde perfiles validados.

## Ingesta y outbox

Flujo objetivo:

1. El técnico captura coordenadas y NPK porcentual.
2. La lectura se guarda inmediatamente en IndexedDB.
3. La UI marca `pendiente` sin bloquear el mapa.
4. Un worker intenta `POST /v1/readings` con backoff.
5. `client_id` evita duplicados.
6. Al confirmar, la lectura cambia a `sincronizada`.
7. Si se rechaza por ubicación, la app conserva el borrador y pide corregir.

## Offline y degradación

- App shell: cache-first.
- Package de backend: network-first con último paquete vivo en IndexedDB o Cache
  Storage.
- Mock de Pasto: fallback de demostración, no “último dato bueno”.
- Tiles externos: opcionales; el mapa de suelo debe seguir siendo legible sin ellos.
- Riesgos vencidos: mostrar antigüedad y `degraded`.

El service worker actual no puede cachear automáticamente una API en otro dominio
con su estrategia de mismo origen. La migración debe guardar explícitamente el
último package recibido.

## Accesibilidad y campo

- controles táctiles de al menos 44 px;
- texto legible bajo sol;
- contrastes AA;
- `aria-expanded` y `aria-selected` correctos;
- severidad con símbolo y palabra;
- alternativa a voz;
- respeto a `prefers-reduced-motion`;
- modo usable sin basemap.

## Migración del frontend

1. Añadir `contract_version` y adaptador temporal `v0.1 → v0.2`.
2. Cambiar escalas y etiquetas de ppm a porcentaje.
3. Sustituir productos/precios por `grade`, `bags` y `bag_weight_kg`.
4. Añadir contexto del centro de acopio.
5. Conectar decisiones de propuestas.
6. Implementar outbox y último package vivo.
7. Retirar código de compatibilidad cuando mocks y API sean `v0.2`.

## Verificación antes de grabar

- La primera lectura aparece como N 2 %, P 1 %, K 1 %.
- No aparece `ppm`, una marca, un nombre químico o un precio.
- Se ve el centro de acopio y el lote de Pasto.
- Cambiar N/P/K actualiza mapa y escala.
- El rayado sigue visible sin tiles.
- “¿Por qué?” muestra entradas, modelo y límites.
- Aceptar o derivar crea una decisión real.
- La app abre sin backend usando el mock.
- El video completo dura como máximo un minuto.
