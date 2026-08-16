# IOmido — frontend

SPA ligera para centros de acopio, técnicos y pequeños productores. La interfaz
abre en el centro de acopio y baja al lote: **centro → productores → lotes →
mediciones**.

## Correr

```bash
cd frontend
python -m http.server 5173
```

Abrir <http://localhost:5173>.

## Conectar el backend

Este frontend no usa Vite. Configurar la URL antes de `app.js`:

```html
<script>window.NPK_API_BASE = "https://api.example.com";</script>
```

En localhost, `index.html` intenta `http://127.0.0.1:8000`. Si falla, carga
`mock/package-nar-001.json`.

## Pantallas

| Archivo | Contenido |
|---|---|
| `index.html` | Centro de control del acopio. Cuatro vistas sin scroll, una por hash |
| `pitch.html` | Solo el demo en vivo y el audio narrado; no sustituye el video final |
| `login.html` y `register.html` | Prototipos sin backend de identidad |

### Vistas del centro de control

| Hash | Vista | Qué responde |
|---|---|---|
| `#resumen` | Resumen | Estado del centro, lotes que requieren atención y prioridades |
| `#mapa` | Mapa | Red del centro o N/P/K del lote en porcentaje, con incertidumbre |
| `#productores` | Productores | Productores del centro con sus lotes y su última medición |
| `#lote` | Lote El Rosal | Suelo, incertidumbre, propuesta por zona, clima y decisión |

Cada vista tiene su hash, así que el botón Atrás funciona y las vistas se pueden
enlazar. Un hash desconocido cae en `#resumen`. `pitch.html` embebe
`index.html#lote`.

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `lib/api.js` | Única puerta de red: package, lecturas, propuestas, decisiones, agente y gobernanza |
| `lib/adapt.js` | Contrato v2 → modelo de vista. No modifica el JSON de origen |
| `lib/network.js` | Dashboard persistido del centro; `network.json` solo como fallback offline |
| `lib/heatsurface.js` | Superficie e incertidumbre |
| `lib/slippy.js` | Basemap opcional |
| `lib/plotmap.js` | Render local sin tiles |
| `lib/assistant.js` | Respuesta del agente y Web Speech |
| `lib/auth.js` | Sesión simulada mientras no exista `/v1/auth` |

## Datos: qué es real y qué no

El único lote con datos reales es **El Rosal**, y sus valores salen siempre del
package v2 del backend o de su mock. Con conexión, la red consume
`/v1/centers/{center_id}/dashboard`, cuyos conteos son persistidos y declaran su
origen. `mock/network.json` queda exclusivamente como contexto sintético para el
fallback offline.

No se publica exposición en pesos: no existe un modelo de producción validado.

## Contrato

El frontend consume `contract_version` **2.0** y solo estas raíces:

```text
pkg.plot · pkg.measurements · pkg.spatial.{grid, zones, next_sample}
pkg.climate · pkg.crop_profile · pkg.proposal
```

El dato del sensor **no está en ppm**: `2,1,1` significa N 2 %, P 1 %, K 1 %.
Una formulación `30-30-40` es 30 % N, 30 % P y 40 % K de la masa del bulto, en
convención elemental.

No se muestran marcas, nombres químicos, precios ni ahorro monetario.

## Criterios de aceptación

- No aparece la cadena `ppm`.
- No aparecen marcas, nombres químicos, precios o costos.
- `30-30-40` coincide con 30 % N, 30 % P y 40 % K.
- La primera medición aparece como `2 % · 1 % · 1 %`.
- El mapa es legible sin OpenStreetMap.
- La app identifica centro, productor, lote, municipio y cultivo.
- Una decisión se persiste contra el backend y la UI respeta su `resulting_status`.
- La app sigue abriendo con el mock offline.

## Trabajo pendiente

1. Outbox de lecturas en IndexedDB con `client_id`.
2. Último package vivo para uso offline entre dominios.
3. Manifest con iconos y pruebas de accesibilidad.

Detalles en [`../FRONTEND.md`](../FRONTEND.md) y roadmap en
[`../TAREAS.md`](../TAREAS.md).
