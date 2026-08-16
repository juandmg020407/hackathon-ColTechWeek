# Frontend — IOmido

SPA sin build ni dependencias: HTML, CSS y módulos ES nativos. Implementa el contrato de [`../FRONTEND.md`](../FRONTEND.md).

## Correr

```bash
cd frontend && python -m http.server 5173
```

Abrir <http://localhost:5173>. Cualquier servidor estático sirve; el directorio tiene que ser la raíz del sitio.

## Conectar el backend

```html
<script>window.NPK_API_BASE = 'https://mi-backend';</script>
```

Antes de cargar los módulos. Sin esa variable, el frontend lee `mock/package-nar-001.json` y funciona completo sin red.

## Pantallas

| Archivo | Qué es |
|---|---|
| `index.html` | Centro de control del acopio. Cuatro vistas sin scroll, una por hash |
| `pitch.html` | Pitch de un minuto: solo el demo en vivo y el audio narrado |
| `login.html`, `register.html` | Fuera del flujo por ahora. Se conservan; la raíz no pide sesión |

### Vistas del centro de control

La jerarquía es **acopio → productores → lotes → mediciones**: la pregunta de entrada es «¿qué puede afectar mi abastecimiento?», y la receta de fertilizante queda como drill-down.

| Hash | Vista | Qué responde |
|---|---|---|
| `#resumen` | Resumen | Estado, 4 KPIs, mapa de la red, «Prioridad hoy», salud de abastecimiento |
| `#mapa` | Mapa | Red del acopio (por defecto) o nutrientes del lote, con filtro por nivel de riesgo |
| `#productores` | Productores | Cards por productor, con sus lotes y su última medición |
| `#lote` | Lote El Rosal | Tablero del lote: mapa, receta, riesgos y preguntas |

Cada vista tiene su hash, así que el botón Atrás del navegador funciona y las vistas se pueden enlazar. Un hash desconocido cae en `#resumen`. `pitch.html` usa esto: embebe `index.html#lote`, que es de lo que habla la narración de un minuto.

**La red es demostrativa.** Los productores de `mock/network.json` son sintéticos y la interfaz lo declara con un chip; el único lote con datos reales es El Rosal, de María López. No se publica exposición en pesos: no hay modelo de producción validado.

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `lib/api.js` | Paquete del lote: `GET /v1/plots/{id}/package` |
| `lib/network.js` | Red del acopio: `GET /v1/acopios/{id}/network`. Mismo patrón y mismo interruptor `NPK_API_BASE` |
| `lib/adapt.js` | Paquete → modelo de vista. No modifica el JSON de origen |
| `lib/plotmap.js` | Renderizador conforme al contrato: grilla SVG de un solo tono |
| `lib/heatsurface.js` | Renderizador alterno en uso: superficie plasma sobre basemap |
| `lib/slippy.js` | Capa de tiles Web Mercator, sin librería de mapas |
| `lib/assistant.js` | Voz: primero el cache local `voz[]`, la red solo si no hay match |
| `lib/auth.js` | Sesión simulada mientras no exista `/v1/auth` |

## Desviaciones del contrato, pendientes de aprobación

**Dos peticiones de datos en el arranque, no una.** `FRONTEND.md` §11 pide un round-trip por pantalla; el centro de control necesita el paquete del lote **y** la red del acopio: `mock/package-nar-001.json` (18,6 KB) + `mock/network.json` (4,7 KB). Son dos pantallas de datos servidas de una, no fetch en cascada. Si el backend prefiere una sola, la salida natural es que `network` traiga el paquete del lote piloto embebido.

`FRONTEND.md` §2 prohíbe los basemaps de tiles y §7 exige una escala de un solo tono. El mapa en uso (`heatsurface.js` + `slippy.js`) usa **tiles de OpenStreetMap y colormap plasma**, por decisión de producto.

`plotmap.js` mantiene el renderizador conforme al contrato, con sus tests. Volver a él es cambiar la llamada en `app.js`.

Lo que sí cumple el mapa actual: los datos salen de `package.grid` en ppm, las celdas con `sigma > sigma_umbral` van rayadas, están la cruz de `next_sample`, el contorno, los puntos de muestreo y los botones de 56 px.

## Dos cosas para el backend

1. **`sigma_umbral` deja el mapa ilegible.** En el mock, `sigma` tiene mediana 22 contra un umbral de 8: se rayan 262 de 275 celdas (95 %). Con umbral 25 quedarían 83 (30 %), honesto y legible. No se tocó: es campo del contrato.

2. **El snippet de `buscarLocal` de `FRONTEND.md` §9 parte por espacios**, así que la puntuación rompe el match: «¿cuánto abono le echo?» da un acierto en vez de dos y se va a la red sin necesidad. Aquí se parte por caracteres no alfanuméricos.

## Falta

`pitch-audio.mp3` (narración de un minuto). Sin él el botón se desactiva y lo dice; no rompe la presentación.

Outbox en IndexedDB y `POST /v1/readings` — pendientes, requieren el backend arriba.
