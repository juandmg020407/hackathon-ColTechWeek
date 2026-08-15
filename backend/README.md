# Sereno — backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Documentación interactiva en http://localhost:8000/docs

No hace falta `.env` para arrancar: todas las claves son opcionales y el
sistema degrada en vez de caerse. Open-Meteo no pide llave, así que los
riesgos climáticos funcionan de una.

## Qué corre hoy

| | Estado |
|---|---|
| `GET /health` | ✅ |
| `GET /v1/plots` | ✅ |
| `GET /v1/plots/{id}/package` | ✅ suelo + riesgos + receta ajustada, **5,6 KB** con Brotli |
| `GET /v1/plots/{id}/risk` | ✅ |
| `POST /v1/readings` | ✅ con control de calidad e idempotencia |
| `GET /v1/governance` | ✅ |
| `POST /v1/decisions` | ⬜ pendiente |
| `POST /v1/agent/ask` | ⬜ pendiente |
| Voz Azure `es-CO` | ⬜ pendiente |
| Persistencia Supabase | ⬜ hoy es memoria; el Excel es la fuente |

## Estructura

```
app/
├── main.py            API y router v1
├── config.py          settings; todo tiene default
├── schemas.py         espejo de los tipos de FRONTEND.md
├── adjust.py          ajusta la receta según los riesgos activos
├── ml/
│   ├── soil.py        M1 calidad · M2 calibración · M3 GP · M4 balance · M5 mezcla
│   └── package.py     ensambla el paquete completo
├── risk/
│   ├── frost.py       R1 helada
│   ├── drought.py     R2 déficit hídrico
│   ├── blight.py      R3 gota (tizón tardío)
│   ├── seasonal.py    R4 ENSO + SEAS5
│   └── engine.py      orquesta y recorta a 3
├── sources/
│   ├── openmeteo.py   forecast, seasonal, archive; caché con degradación
│   └── enso.py        boletín NOAA CPC vigente
└── governance/
    └── disclosure.py  qué es, qué no hace, bajo qué marco
```

## Notas de diseño

**Nada de red en el camino crítico.** Todo lo externo pasa por caché con TTL.
Si una fuente falla, el paquete se sirve igual con lo último bueno y marca
`degradado: true`. En el Wi-Fi de un hackathon esto no es opcional.

**Los ajustes nunca son silenciosos.** Cuando un riesgo cambia la dosis, el
cambio viaja en `receta.ajustes` con su factor y su motivo. El agricultor ve
que le movimos la receta y por qué.

**El semáforo se deriva del faltante**, no de umbrales de ppm sueltos, para
que la tarjeta y la receta no puedan contradecirse.

**Calidad de datos: dos cosas distintas.** `descartado` es geometría (regla
dura, se excluye). `sospechoso` es estadística (solo se marca). Con 19
muestras, un valor alto es información, no un error.

## Pendiente antes de la entrega

- `POST /v1/decisions` con el umbral de doble firma
- Voz Azure `es-CO-SalomeNeural` y los `.opus` precomputados del paquete
- Agente con tool-use sobre los endpoints
- Reemplazar precios de referencia por SIPSA
- Persistir en Supabase
