# IOmido — frontend

SPA ligera para centros de acopio, técnicos y pequeños productores. La demo actual
abre directamente el lote de papa de Pasto; la migración `v0.2` añadirá el contexto
centro → red → lote.

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

## Pantallas actuales

| Archivo | Contenido |
|---|---|
| `index.html` | Tablero del lote: mapa, recomendación, riesgos y preguntas |
| `pitch.html` | Herramienta visual para grabar; no sustituye el video final |
| `login.html` y `register.html` | Prototipos sin backend de identidad |

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `lib/api.js` | Package y llamadas remotas |
| `lib/adapt.js` | Contrato → modelo de vista |
| `lib/heatsurface.js` | Superficie e incertidumbre |
| `lib/slippy.js` | Basemap opcional |
| `lib/plotmap.js` | Render local sin tiles |
| `lib/assistant.js` | Respuesta local y Web Speech |

## Advertencia de contrato

La UI `v0.1` todavía muestra ppm, nombres de fertilizantes y costos porque consume
el package heredado. El dato original no está en ppm: `2,1,1` significa N 2 %, P
1 %, K 1 %.

La UI `v0.2` mostrará:

```text
N 2 % · P 1 % · K 1 %
Formulación sugerida: 30-30-40
Cantidad: 2 bultos de 50 kg
```

No mostrará marca, nombre químico, precio ni ahorro monetario.

## Trabajo pendiente

1. Adaptador temporal para contratos `v0.1` y `v0.2`.
2. Escalas, labels y tooltips en porcentaje.
3. Panel de formulación por grado NPK.
4. Contexto del centro de acopio y lista de lotes.
5. Botones reales de aceptar, rechazar y derivar.
6. Outbox de lecturas en IndexedDB.
7. Último package vivo para uso offline entre dominios.
8. Manifest con iconos y pruebas de accesibilidad.

Detalles en [`../FRONTEND.md`](../FRONTEND.md) y roadmap en
[`../TAREAS.md`](../TAREAS.md).

## Criterios de aceptación `v0.2`

- No aparece la cadena `ppm`.
- No aparecen marcas, nombres químicos, precios o costos.
- `30-30-40` coincide con 30 % N, 30 % P y 40 % K.
- La primera medición aparece como `2 % · 1 % · 1 %`.
- El mapa es legible sin OpenStreetMap.
- La app identifica centro, productor, lote, municipio y cultivo.
- Una decisión se persiste contra el backend.
- La app sigue abriendo con el mock offline.
