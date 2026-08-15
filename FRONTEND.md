# Frontend — contrato de construcción

Hackathon Colombia Tech Week 2026 · Track 04 Planeta y Comunidad
Entrega: **domingo 16 de agosto, 09:00**

---

## 1. Qué estamos construyendo

Un sensor que se clava en la tierra mide N, P y K. Nosotros lo volvemos inteligente: interpolamos el lote completo con un modelo, calculamos qué fertilizante falta en cada zona y lo traducimos a **bultos y pesos colombianos**.

El usuario es un papero de **Nariño con menos de una hectárea**. No tiene drones, no tiene laboratorio, y **su red es 2G**. Esa última restricción manda sobre todas las decisiones de esta app.

Tenemos 18 mediciones reales de un lote de 0,69 ha cerca de Pasto. Ese lote es el que se ve en la demo.

---

## 2. La restricción: 2G

| | |
|---|---|
| EDGE real en zona rural | **4–9 KB/s** |
| GPRS puro | **1–2 KB/s** |
| Latencia por viaje | **300–1000 ms** |

**La latencia mata más que el ancho de banda.** Seis llamadas encadenadas son ~5 segundos antes de transferir un byte útil.

### Presupuesto

| Cosa | Máximo | Realidad hoy |
|---|---|---|
| Shell de la app (una sola vez) | 150 KB | por medir |
| Paquete de lote | 20 KB | **3,2 KB** ✅ |
| Cada interacción posterior | 5 KB | |
| Round-trips por pantalla | **1** | |

### No entra

- ❌ **MapLibre, Leaflet, Mapbox** — cualquier basemap de tiles. 500+ KB, ~90 s en 2G. El mapa se dibuja como SVG local.
- ❌ **Webfonts** — ni CDN ni self-hosted. Stack del sistema.
- ❌ **PNG / JPG / logos raster** — todo icono es SVG inline, y solo el que se usa.
- ❌ **Polling** — nada de `setInterval` ni refetch on focus.
- ❌ **Analytics, Sentry, scripts de terceros**.
- ❌ **Framer Motion, Lottie, GSAP** — transiciones CSS y nada más.
- ❌ **Fetch en cascada** — si una pantalla necesita dos llamadas, el endpoint está mal. Avísame.

### Obligatorio

- ✅ Service worker cache-first — tras la primera carga la app abre sin red.
- ✅ Outbox en IndexedDB — toda escritura se encola y se reintenta.
- ✅ UI optimista — la acción se ve hecha al instante.
- ✅ Estado de sincronización siempre visible, nunca un spinner bloqueante.
- ✅ Botones de **56 px o más**.
- ✅ Contraste alto de verdad: se lee a mediodía en una loma.

---

## 3. Stack

```
Vite + React 18 + TypeScript      SPA pura, no Next.js
vite-plugin-pwa                   service worker con Workbox
zustand                           estado global, ~1 KB
idb-keyval                        outbox en IndexedDB, ~0.6 KB
Tailwind                          se purga, queda en ~6 KB
Deploy: Vercel
```

**Por qué Vite y no Next.js**, aunque Next sea patrocinador: necesitamos una SPA offline-first pura. El App Router con SSR complica el service worker sin darnos nada aquí, y el baseline de JS es casi el doble. Vercel hostea Vite igual de bien, así que el guiño al sponsor se mantiene.

Si prefieres Next de todos modos, úsalo con `output: 'export'`. **Los contratos JSON de abajo no cambian.**

**Nada de librerías de mapas, gráficas, iconos o UI.** Si crees que necesitas una, hablemos primero.

Optimización opcional al final, si sobra tiempo: alias de `preact/compat` en `vite.config.ts` baja React de ~45 KB a ~12 KB. Una línea, pero pruébalo cuando todo funcione, no antes.

---

## 4. Arranca ya, sin esperarme

En `mock/package-nar-001.json` está el paquete real generado con los datos reales del lote de Nariño. **Cópialo a `public/mock/package-nar-001.json` y trabaja contra eso desde el minuto cero.**

```ts
const API = import.meta.env.VITE_API_URL ?? "";

export async function getPackage(plotId: string): Promise<Package> {
  const url = API
    ? `${API}/v1/plots/${plotId}/package`
    : `/mock/package-${plotId}.json`;
  return (await fetch(url)).json();
}
```

Cuando el backend esté arriba defines `VITE_API_URL` y no tocas una línea más.

---

## 5. Endpoints

Base: `/v1`. Todo JSON, todo con `Content-Encoding: br`.

### P0 — sin esto no hay demo

| Método y ruta | Cuándo | Peso |
|---|---|---|
| `GET /v1/plots` | Al abrir la app | ~2 KB |
| `GET /v1/plots/{id}/package` | Al entrar a un lote y con «Actualizar» | **5,6 KB** medidos |
| `POST /v1/readings` | Al guardar una medición | ~0.3 KB |

### P1 — la demo brilla

| Método y ruta | Cuándo |
|---|---|
| `GET /v1/plots/{id}/risk` | Refrescar solo los riesgos sin recalcular el suelo |
| `POST /v1/decisions` | El agricultor acepta, rechaza o modifica una propuesta |
| `GET /v1/governance` | Ficha de «qué es esto y qué no hace». Se pide una vez y se cachea |
| `POST /v1/agent/ask` | Solo si la pregunta no hace match con el cache de voz local |
| `POST /v1/readings/import` | Subir el Excel (vista escritorio) |

### P2 — si sobra tiempo

| Método y ruta | Cuándo |
|---|---|
| `GET /v1/public/soil-map` | Mapa público del municipio (escritorio) |
| `POST /v1/vision/leaf` | Foto de la hoja |

---

### `GET /v1/plots`

```json
{
  "plots": [
    { "id": "nar-001", "nombre": "Lote El Rosal",
      "municipio": "Pasto, Nariño", "area_ha": 0.69,
      "cultivo": "papa", "mediciones": 18,
      "actualizado": "2026-08-15T14:47:00Z" }
  ]
}
```

---

### `GET /v1/plots/{id}/package` — el que importa

Trae **todo** lo necesario para operar el lote sin red. Guárdalo íntegro en IndexedDB y trabaja siempre contra la copia local.

```jsonc
{
  "plot": {
    "id": "nar-001",
    "nombre": "Lote El Rosal",
    "municipio": "Pasto, Nariño",
    "area_ha": 0.69,
    "cultivo": "papa",
    "variedad": "Diacol Capiro",
    "centro": [1.247918, -77.267205]
  },

  "grid": {
    "celda_m": 5,
    "cols": 20,
    "rows": 28,
    "origen": [1.247519, -77.267658],   // esquina SUROESTE
    "unidad": "ppm",
    "N":     [24, 25, 26, 27, 30, 34, ...],   // cols*rows = 560, row-major
    "P":     [12, 12, 12, 13, 14, 16, ...],
    "K":     [141, 143, 146, 152, 164, 184, ...],
    "sigma": [32, 32, 32, 32, 31, 30, ...],   // incertidumbre relativa, %
    "sigma_umbral": 8,                        // por encima: pintar rayado
    "mask":  [0, 0, 0, 0, 0, 0, 0, 1, ...]    // 1 = dentro del lote
  },

  "contorno": [[1.24756, -77.26761], ...],  // polígono del lote, cerrado

  "puntos": [                                // dónde midió el sensor
    { "lat": 1.247822, "lon": -77.267613,
      "N": 2, "P": 1, "K": 1,                // lectura CRUDA del sensor
      "sospechoso": false }
  ],

  "descartados": [
    { "lat": 1.2367, "lon": -77.2676,
      "motivo": "Este punto queda a 1.2 km del lote. ¿Se equivocó de finca?" }
  ],

  "zonas": [                                 // ordenadas de mayor a menor área
    { "id": "z1",
      "area_ha": 0.432,
      "celdas": [63, 71, 82, 83, 84, 85, ...],   // índices en la grilla
      "promedio_ppm": { "N": 18.3, "P": 8.7, "K": 110.4 },
      "nivel": { "N": "critico", "P": "critico", "K": "bajo" },
      "kg_ha": { "N": 132, "P2O5": 121, "K2O": 110 },
      "productos": [
        { "nombre": "DAP 18-46-0", "bultos": 3, "costo_cop": 540000 },
        { "nombre": "KCl 0-0-60",  "bultos": 2, "costo_cop": 260000 },
        { "nombre": "Urea 46-0-0", "bultos": 2, "costo_cop": 240000 }
      ],
      "costo_cop": 1040000 }
  ],

  "next_sample": {
    "punto": [1.248378, -77.266849],
    "razon": "Es el punto del lote donde el modelo tiene menos certeza.",
    "sigma": 31.4
  },

  "receta": {
    "costo_total_cop": 1770000,
    "costo_generico_cop": 2160000,
    "ahorro_cop": 390000,
    "generico_detalle": "12 bultos de 13-26-6 + 3 bultos de Urea 46-0-0",
    "ventana": {
      "desde": "2026-08-20", "hasta": "2026-08-22",
      "motivo": "Llueve fuerte el sábado. Si aplica antes, se lava."
    }
  },

  "voz": [
    { "id": "v1",
      "claves": ["cuanto", "abono", "echo", "fertilizante"],
      "texto": "A su lote le faltan 3 bultos de DAP, 2 bultos de KCl y 2 bultos de Urea.",
      "audio": "/audio/v1.opus" }
  ],

  // ─── NUEVO: lo que viene ────────────────────────────────────────
  "riesgos": [                               // máximo 3, ya ordenados
    { "id": "rk-estacional-2026-08-04",
      "tipo": "estacional",                  // helada|sequia|gota|incendio|deslizamiento|estacional
      "severidad": "alta",                   // baja|media|alta|critica
      "probabilidad": 0.97,
      "confianza": "media",                  // baja|media|alta
      "ventana": { "desde": "2026-08-04", "hasta": "2027-01-31" },
      "titulo": "Viene El Niño y va a pegar duro",
      "resumen": "El Niño ya está activo. Hay 63 por ciento de probabilidad de que sea muy fuerte...",
      "que_hacer": [
        "Piense la siembra para que el llenado de tubérculo no caiga en lo más seco.",
        "Suba el potasio: ayuda a la mata a aguantar frío y falta de agua."
      ],
      "por_que": {                           // trazabilidad, AI Act art. 12
        "modelo": "seasonal/v1",
        "entradas": { "anomalia_nino34_c": 0.7, "prob_muy_fuerte": 0.63,
                      "deficit_lluvia_proyectado_pct": 11.4,
                      "dispersion_ensemble_pct": 12.4 },
        "regla": "Estado ENSO de NOAA CPC cruzado con ECMWF SEAS5 a 9 meses...",
        "fuentes": [ { "nombre": "NOAA CPC", "consultado": "2026-08-04T00:00:00Z",
                       "url": "https://..." } ]
      },
      "requiere_confirmacion": true }
  ],

  "estacional": {
    "fenomeno": "El Niño",
    "estado": "activo y fortaleciéndose",
    "anomalia_nino34_c": 0.7,
    "prob_muy_fuerte": 0.63,
    "pico_esperado": "noviembre 2026 a enero 2027",
    "implicacion_local": "En el altiplano nariñense El Niño trae menos lluvia...",
    "horizonte_meses": 9,
    "fuente": { "nombre": "NOAA Climate Prediction Center", "consultado": "..." }
  },

  "generado": "2026-08-15T14:47:00Z",
  "ttl_horas": 72,
  "degradado": false,                        // true = alguna fuente externa falló
  "aviso": "La calibración del sensor a ppm es provisional..."
}
```

`nivel` solo toma tres valores: `"critico" | "bajo" | "adecuado"`.

**Y `receta` ahora trae `ajustes`** — los cambios de dosis que causaron los riesgos:

```jsonc
"receta": {
  "costo_total_cop": 1650000,
  "ahorro_cop": 510000,
  "ajustes": [
    { "nutriente": "N",   "factor": 0.75, "riesgo": "estacional",
      "motivo": "Se baja el nitrógeno porque sin agua no se alcanza a absorber." },
    { "nutriente": "K2O", "factor": 1.10, "riesgo": "estacional",
      "motivo": "Se sube el potasio: ayuda a la mata a manejar la falta de agua." }
  ]
}
```

**Muéstralos siempre.** Un ajuste silencioso es exactamente lo que el AI Act prohíbe: el agricultor tiene que ver que le cambiamos la receta y por qué.

---

### `POST /v1/readings`

```jsonc
// request
{ "plot_id": "nar-001",
  "lat": 1.24798, "lon": -77.26709,
  "N_raw": 12, "P_raw": 4, "K_raw": 6,
  "medido_en": "2026-08-15T09:14:00Z",
  "client_id": "a3f9-uuid-local" }   // idempotencia: reintenta sin duplicar

// 200 — punto bueno
{ "ok": true, "id": "rd-8821",
  "calidad": { "valida": true, "sospechoso": false, "confianza": 0.94 },
  "recalcular": true }               // true → vuelve a pedir el package

// 200 — punto fuera del lote
{ "ok": true, "id": "rd-8822",
  "calidad": { "valida": false, "sospechoso": false, "confianza": 0.11,
               "motivo": "Este punto queda a 1.2 km del lote. ¿Se equivocó de finca?" },
  "recalcular": false }

// 200 — lectura rara pero dentro del lote (NO es error)
{ "ok": true, "id": "rd-8823",
  "calidad": { "valida": true, "sospechoso": true, "confianza": 0.55,
               "motivo": "Lectura mucho más alta que el resto del lote. ¿Midió sobre abono?" },
  "recalcular": true }
```

**Ese caso de `valida: false` está en los datos reales.** Preséntalo como tarjeta **ámbar** con dos botones — «Corregir ubicación» y «Guardar de todos modos» — nunca como error rojo bloqueante. El técnico está parado en un potrero y tiene que poder seguir.

`sospechoso: true` es solo una nota informativa. No bloquea nada.

---

### `POST /v1/agent/ask`

```jsonc
// request
{ "plot_id": "nar-001",
  "texto": "¿cuánto abono le echo?",
  "quiere_audio": true }

// response
{ "texto": "A su lote le faltan 6 bultos de DAP y 3 de KCl. Le cuesta 1.510.000 pesos.",
  "audio_url": "https://.../r-8821.opus",
  "fuentes": ["zona z1", "precios SIPSA agosto 2026"] }
```

**Llama esto solo si no hubo match en el array `voz` local.** Ver §7.

---

## 6. Tipos

```ts
export type Nivel = "critico" | "bajo" | "adecuado";
export type Nutriente = "N" | "P" | "K";

export interface Plot {
  id: string; nombre: string; municipio: string;
  area_ha: number; cultivo: string; variedad?: string;
  centro: [number, number];
}

export interface Grid {
  celda_m: number; cols: number; rows: number;
  origen: [number, number];
  unidad: "ppm";
  N: number[]; P: number[]; K: number[];
  sigma: number[]; sigma_umbral: number;
  mask: (0 | 1)[];
}

export interface Punto {
  lat: number; lon: number;
  N: number; P: number; K: number;
  sospechoso: boolean;
}

export interface Producto { nombre: string; bultos: number; costo_cop: number; }

export interface Zona {
  id: string; area_ha: number; celdas: number[];
  promedio_ppm: Record<Nutriente, number>;
  nivel: Record<Nutriente, Nivel>;
  kg_ha: { N: number; P2O5: number; K2O: number };
  productos: Producto[];
  costo_cop: number;
}

export interface Ajuste {
  nutriente: "N" | "P2O5" | "K2O";
  factor: number;              // 0.75 = se bajó 25%
  motivo: string;
  riesgo: TipoRiesgo;
}

export interface Receta {
  costo_total_cop: number;
  costo_generico_cop: number;
  ahorro_cop: number;
  generico_detalle: string;
  ventana: { desde: string; hasta: string; motivo: string };
  ajustes: Ajuste[];
}

export type TipoRiesgo =
  | "helada" | "sequia" | "gota" | "incendio" | "deslizamiento" | "estacional";
export type Severidad = "baja" | "media" | "alta" | "critica";
export type Confianza = "baja" | "media" | "alta";

export interface Fuente { nombre: string; consultado?: string; url?: string; }

export interface PorQue {
  modelo: string;
  entradas: Record<string, unknown>;
  regla: string;
  fuentes: Fuente[];
}

export interface Riesgo {
  id: string;
  tipo: TipoRiesgo;
  severidad: Severidad;
  probabilidad: number;
  confianza: Confianza;
  ventana: { desde: string; hasta: string };
  titulo: string;
  resumen: string;
  que_hacer: string[];
  por_que: PorQue;
  requiere_confirmacion: boolean;
}

export interface Estacional {
  fenomeno: string;
  estado: string;
  anomalia_nino34_c?: number;
  prob_muy_fuerte?: number;
  pico_esperado?: string;
  implicacion_local: string;
  horizonte_meses: number;
  fuente: Fuente;
}

export interface RespuestaVoz {
  id: string; claves: string[]; texto: string; audio: string;
}

export interface Package {
  plot: Plot;
  grid: Grid;
  contorno: [number, number][];
  puntos: Punto[];
  descartados: { lat: number; lon: number; motivo: string }[];
  zonas: Zona[];
  next_sample: { punto: [number, number]; razon: string; sigma: number };
  receta: Receta;
  riesgos: Riesgo[];          // máximo 3, ya ordenados por prioridad
  estacional: Estacional | null;
  voz: RespuestaVoz[];
  generado: string;
  ttl_horas: number;
  degradado: boolean;         // true = alguna fuente externa falló
  aviso: string | null;
}

export interface NuevaLectura {
  plot_id: string; lat: number; lon: number;
  N_raw: number; P_raw: number; K_raw: number;
  medido_en: string; client_id: string;
}

export interface Calidad {
  valida: boolean; sospechoso: boolean;
  confianza: number; motivo?: string;
}
```

---

## 7. Cómo dibujar el mapa

Esto es lo menos obvio del proyecto, así que va explícito.

**La grilla es row-major desde la esquina suroeste.** La celda en fila `r`, columna `c` está en el índice `r * cols + c`. La fila 0 es la más al sur, así que en SVG hay que voltear la Y.

```tsx
const RANGOS: Record<Nutriente, [number, number]> = {
  N: [10, 50],    // ppm: crítico <20, bajo 20-40, adecuado >40
  P: [4, 28],     // crítico <10, bajo 10-20, adecuado >20
  K: [60, 300],   // crítico <100, bajo 100-200, adecuado >200
};

function color(v: number, [min, max]: [number, number]) {
  const t = Math.max(0, Math.min(1, (v - min) / (max - min)));
  // escala secuencial de un solo tono: pobre = pálido, rico = intenso
  const l = 94 - t * 56;      // 94% → 38%
  const s = 22 + t * 42;
  return `hsl(96 ${s}% ${l}%)`;
}

export function MapaLote({ grid, nutriente, nextSample, onCelda }: Props) {
  const vals = grid[nutriente];
  const rango = RANGOS[nutriente];

  return (
    <svg viewBox={`0 0 ${grid.cols} ${grid.rows}`} className="w-full h-auto"
         shapeRendering="crispEdges" role="img"
         aria-label={`Mapa de ${nutriente} del lote`}>
      <defs>
        <pattern id="nose" width="2" height="2" patternUnits="userSpaceOnUse"
                 patternTransform="rotate(45)">
          <rect width="2" height="2" fill="hsl(96 8% 88%)" />
          <line x1="0" y1="0" x2="0" y2="2" stroke="hsl(96 10% 62%)" strokeWidth="0.7" />
        </pattern>
      </defs>

      {vals.map((v, i) => {
        if (!grid.mask[i]) return null;              // fuera del lote
        const c = i % grid.cols;
        const r = grid.rows - 1 - Math.floor(i / grid.cols);   // voltear Y
        const incierto = grid.sigma[i] > grid.sigma_umbral;
        return (
          <rect key={i} x={c} y={r} width={1} height={1}
                fill={incierto ? "url(#nose)" : color(v, rango)}
                onClick={() => onCelda?.(i)} />
        );
      })}

      {/* la cruz de "mide aquí" — el diferenciador de la demo */}
      {nextSample && (
        <g className="pulso">
          <circle cx={nextSample.c + 0.5} cy={grid.rows - 0.5 - nextSample.r}
                  r={1.6} fill="none" stroke="#1b1d1a" strokeWidth={0.35} />
          <path d={`M${nextSample.c - 0.3} ${grid.rows - 0.5 - nextSample.r}h1.6
                    M${nextSample.c + 0.5} ${grid.rows - 1.3 - nextSample.r}v1.6`}
                stroke="#1b1d1a" strokeWidth={0.35} />
        </g>
      )}
    </svg>
  );
}
```

```css
@media (prefers-reduced-motion: no-preference) {
  .pulso { animation: pulso 2.2s ease-in-out infinite; transform-origin: center; }
  @keyframes pulso { 0%,100% { opacity: 1 } 50% { opacity: .45 } }
}
```

**Tres reglas de color:**

1. **Escala secuencial de un solo tono**, nunca arcoíris ni rojo-verde. Hay daltonismo en el campo también.
2. **Las celdas inciertas van con patrón, no con color.** Mostrar que no sabemos es parte del producto — ningún competidor lo hace y el jurado lo va a notar.
3. La leyenda dice **«poco / mucho»** en palabras, no solo números.

Para convertir lat/lon a celda (por ejemplo el `next_sample`):

```ts
export function aCelda(lat: number, lon: number, g: Grid) {
  const [lat0, lon0] = g.origen;
  const x = (lon - lon0) * 111320 * Math.cos((lat0 * Math.PI) / 180);
  const y = (lat - lat0) * 110540;
  return { c: Math.floor(x / g.celda_m), r: Math.floor(y / g.celda_m) };
}
```

---

## 8. Estados de sincronización

Una barra fija, siempre visible, siempre con texto. **Nunca bloquees la interfaz esperando la red.**

| Estado | Qué se ve | Comportamiento |
|---|---|---|
| `al_dia` | Todo guardado · hace 4 min | Sin acción |
| `pendiente` | 3 mediciones por enviar | Reintenta con backoff. App 100% usable |
| `sin_red` | Sin señal · trabajando en el teléfono | Todo contra IndexedDB, cero degradación |
| `enviando` | Enviando 3 de 7 | Progreso por ítem, no barra indeterminada |
| `vencido` | Datos de hace 4 días · toca actualizar | Al pasar `ttl_horas`. Sugiere, no obliga |

### Outbox

```ts
import { get, set } from "idb-keyval";

export async function guardarMedicion(m: NuevaLectura) {
  const cola = (await get<NuevaLectura[]>("outbox")) ?? [];
  await set("outbox", [...cola, m]);
  pintarOptimista(m);          // se ve hecho YA
  vaciarCola();                // sin await
}

export async function vaciarCola() {
  if (!navigator.onLine) return;
  const cola = (await get<NuevaLectura[]>("outbox")) ?? [];
  const quedan: NuevaLectura[] = [];
  for (const m of cola) {
    try {
      const r = await fetch(`${API}/v1/readings`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(m),
      });
      if (!r.ok) quedan.push(m);
    } catch { quedan.push(m); }
  }
  await set("outbox", quedan);
}

window.addEventListener("online", vaciarCola);
```

El `client_id` es un UUID que generas en el cliente. Garantiza que reintentar no duplica.

---

## 9. Las pantallas

### 1 · Mapa del lote

```
┌──────────────────────────────┐
│ ● Sin señal · guardado local │
├──────────────────────────────┤
│  Lote El Rosal      0.69 ha  │
│  [ N ] [ P ] [ K ]           │
│                              │
│    ▓▓▒▒░░░░                  │
│    ▓▓▒▒░░▨▨   ▨ = no sé      │
│    ██▓▓▒▒░░   ✛ = mide aquí  │
│    ██▓▓✛▒░░                  │
│                              │
│  poco ░▒▓█ mucho             │
│                              │
│  Zona 1  0.43 ha   K bajo    │
│  Zona 2  0.08 ha   todo bien │
├──────────────────────────────┤
│  [      MEDIR AQUÍ      ]    │
└──────────────────────────────┘
```

### 2 · La receta

```
┌──────────────────────────────┐
│  LO QUE NECESITA SU LOTE     │
│                              │
│   ▬▬▬  3 bultos DAP          │
│   ▬▬   2 bultos KCl          │
│   ▬▬   2 bultos Urea         │
│                              │
│      $ 1.770.000             │
│  antes: $2.160.000  −$390.000│
│                              │
│  N ●○○○   P ●○○○   K ●●○○    │
│                              │
│  Aplique el jueves 20.       │
│  El sábado llueve fuerte.    │
├──────────────────────────────┤
│  [ 🔊 ESCUCHAR ] [ ENVIAR ]  │
└──────────────────────────────┘
```

- **El precio en pesos es el elemento más grande de toda la app.** Es lo que gana el criterio de impacto público.
- Bultos dibujados, no una tabla de kg/ha. El agricultor compra bultos.
- Semáforo por nutriente, legible sin leer números.
- «Enviar» manda la receta por WhatsApp al dueño de la finca.

### 3 · Lo que viene ← **pantalla nueva, y la más importante**

Es el giro del producto. Un mapa de calor describe el pasado; esta pantalla anticipa.

```
┌──────────────────────────────┐
│  LO QUE VIENE                │
│                              │
│ ┌──────────────────────────┐ │
│ │ ▲ ALTA                   │ │
│ │ Viene El Niño y va a     │ │
│ │ pegar duro               │ │
│ │                          │ │
│ │ Lo peor entre noviembre  │ │
│ │ y enero, justo cuando su │ │
│ │ papa esté llenando.      │ │
│ │                          │ │
│ │ • Suba el potasio        │ │
│ │ • Guarde agua ahora      │ │
│ │                          │ │
│ │ [🔊] [¿Por qué?] [✓ Ya]  │ │
│ └──────────────────────────┘ │
│ ┌──────────────────────────┐ │
│ │ ▲ ALTA · Gota            │ │
│ └──────────────────────────┘ │
│ ┌──────────────────────────┐ │
│ │ ● MEDIA · Le falta agua  │ │
│ └──────────────────────────┘ │
└──────────────────────────────┘
```

- **Máximo tres tarjetas.** El backend ya recorta: más de tres y el agricultor deja de leerlas.
- Solo la primera va expandida. Las otras dos, colapsadas.
- Severidad por **forma y color**: `critica` ▲ relleno, `alta` ▲, `media` ●, `baja` ○. Nunca solo color.
- **`confianza: "baja"` se muestra literalmente**: «esto todavía puede cambiar». Es lo que nos separa de un horóscopo.
- **`[¿Por qué?]` abre `por_que`** en lenguaje llano: qué dato, qué regla, qué fuente y de cuándo. No lo escondas en un acordeón diminuto — es la pieza de IA responsable y el jurado la va a buscar.
- **`[✓ Ya]` registra la decisión** vía `POST /v1/decisions`. El sistema propone; el agricultor decide. Nada se ejecuta solo.
- Si `degradado: true`, un aviso discreto arriba: «Datos de hace unas horas, no pude conectarme».

### 4 · Preguntar

```
┌──────────────────────────────┐
│          ╭────────╮          │
│          │   🎤   │  120px   │
│          ╰────────╯          │
│      Mantenga y hable        │
│                              │
│  «¿Cuánto abono le echo?»    │
│  ▶ ▬▬▬▬▬▬▬▬  0:12            │
│                              │
│  [ 📷 Foto de la hoja ]      │
└──────────────────────────────┘
```

**Primero busca en el cache local antes de tocar la red:**

```ts
function buscarLocal(pregunta: string, voz: RespuestaVoz[]) {
  const palabras = pregunta.toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .split(/\s+/);
  let mejor: RespuestaVoz | null = null, max = 0;
  for (const r of voz) {
    const hits = r.claves.filter((k) => palabras.includes(k)).length;
    if (hits > max) { max = hits; mejor = r; }
  }
  return max >= 2 ? mejor : null;   // 2 claves o más: responde offline
}
```

Reconocimiento de voz con la **Web Speech API** del navegador (gratis, sin key, funciona en Chrome Android). La respuesta llega en audio **y** en texto grande — nunca solo audio.

---

## 10. Antes de entregar

1. **DevTools en «Slow 3G», después throttling manual a 50 kbps.** Si es usable ahí, es usable en Nariño.
2. **Modo avión tras la primera carga.** Abrir, entrar al lote, guardar una medición, ver el mapa, escuchar una respuesta. Todo debe funcionar.
3. **Volver a conectar.** Las mediciones encoladas se envían solas y sin duplicarse.
4. **Pesar el bundle.** `npm run build` y mirar el tamaño. Si pasa de 150 KB, cortamos.
5. **Contar round-trips.** Pestaña Network al entrar a un lote: **una sola petición**.
6. **Salir al patio del Claustro con el teléfono y el brillo al máximo.** Literalmente.
7. **Grabar el video con la red limitada.** Si la demo se ve fluida en 2G simulado, el jurado entiende el logro sin que se lo expliquen.

---

## 11. Avisos

- La calibración sensor → ppm es **provisional**, sin validar contra laboratorio. No la presentes como precisión de laboratorio.
- Los precios de fertilizante son **placeholder**; los reemplazo con SIPSA (DANE) durante la noche.
- Los contratos de arriba son definitivos. Si algo tiene que cambiar, te aviso antes de que toques código.
