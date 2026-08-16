# IOmido

**Inteligencia de suelo y clima para centros de acopio y sus redes de pequeños productores.**

IOmido convierte mediciones NPK dispersas en un mapa del lote con incertidumbre,
indica dónde conviene medir después y propone una formulación NPK ajustada a los
riesgos climáticos. El centro de acopio opera el sistema; el técnico revisa las
propuestas; el productor recibe una recomendación simple y explicable.

Proyecto construido para la Hac[k]athon Colombia Tech Week 2026, Track 04:
**Planeta y Comunidad · Resiliencia**.

> Estado: la demo `v0.1` corre con un lote de papa de Pasto. La migración `v0.2`
> cambia todo el dominio de ppm, marcas y precios hardcodeados a porcentajes NPK
> y formulaciones configurables como `30-30-40`. Los documentos distinguen lo
> implementado de lo que está en migración.

## El problema

Un centro de acopio reúne la producción de muchas fincas, pero no puede enviar un
laboratorio ni instalar una sonda comercial en cada lote. Sin información local,
la asistencia técnica termina usando recetas generales y reacciona tarde a
heladas, falta de agua o condiciones favorables para enfermedades.

El problema tiene tres consecuencias:

- El productor aplica una formulación que puede no corresponder a su suelo.
- El centro descubre el riesgo cuando la calidad o el volumen ya están afectados.
- La comunidad desperdicia insumos y aumenta la presión sobre suelo y agua.

## A quién sirve

| Rol | Qué hace | Qué recibe |
|---|---|---|
| **Centro de acopio** | Comparte el sensor entre sus fincas proveedoras y coordina la asistencia técnica | Estado de su red, lotes prioritarios y trazabilidad |
| **Técnico** | Toma o revisa mediciones y valida recomendaciones | Mapa, incertidumbre, riesgos y siguiente punto de muestreo |
| **Productor** | Decide si aplica o no la recomendación | Una instrucción sencilla, sin marcas comerciales y con explicación |

El centro es el cliente y canal operativo. El pequeño productor y el territorio
son los beneficiarios. Las mediciones siguen perteneciendo al productor; cualquier
uso agregado debe ser explícito, revocable y anonimizado.

## La demo de Pasto

La demostración usa un lote de papa de **0,69 hectáreas en Pasto, Nariño** con 19
lecturas georreferenciadas. Una está aproximadamente a 1,2 km del grupo principal
y el control de calidad la descarta como punto ajeno al lote.

La fuente está en [`data/data_ejemplo.csv.xlsx`](data/data_ejemplo.csv.xlsx). Sus
columnas `N`, `p` y `k` son **porcentajes reportados por el sensor**, no ppm:

| Fila de ejemplo | N | P | K | Lectura correcta |
|---|---:|---:|---:|---|
| Primera medición | 2 | 1 | 1 | N 2 %, P 1 %, K 1 % |

La `v0.2` preservará esa unidad de extremo a extremo. No se convertirá a ppm sin
una calibración externa verificable.

## Qué hace realmente la IA

La IA no mide el suelo: el dispositivo ya resuelve la captura. La IA resuelve qué
hacer con pocos puntos y cómo comunicar lo que todavía no se sabe.

1. **Control de calidad.** Reglas geográficas separan puntos ajenos al lote e
   Isolation Forest marca lecturas atípicas sin borrarlas.
2. **Inferencia espacial.** Un Proceso Gaussiano con kernel Matérn estima N, P y K
   entre los puntos medidos.
3. **Incertidumbre visible.** Cada celda incluye una medida de incertidumbre; las
   zonas poco informadas se muestran rayadas.
4. **Muestreo activo.** La celda con mayor incertidumbre se convierte en la
   siguiente ubicación recomendada para medir.
5. **Zonas de manejo.** El campo interpolado se agrupa para facilitar la revisión
   técnica del lote.
6. **Contexto climático.** Riesgos de corto y mediano plazo modifican o aplazan la
   propuesta, siempre mostrando el motivo.

La voz y un futuro agente conversacional son interfaces. No son el núcleo de IA.

## Recomendaciones NPK sin marcas ni precios

La recomendación objetivo usa grados NPK, como se compran localmente:

```text
Lectura del suelo:        N 2 % · P 1 % · K 1 %
Formulación disponible:  30-30-40
Salida para el usuario:  "Formulación NPK 30-30-40 · cantidad sugerida · motivo"
```

La formulación `30-30-40` significa 30 % de N, 30 % de P y 40 % de K bajo el
contrato simplificado de IOmido. Si una fuente externa usa P₂O₅ o K₂O, un adaptador
debe convertirla en el límite del sistema y dejar registrada la convención.

No se mostrarán marcas, nombres químicos ni precios. El centro configura:

- formulaciones disponibles;
- peso del bulto;
- cultivo, variedad y etapa;
- perfil agronómico versionado;
- límites de aplicación y reglas de revisión técnica.

El optimizador `v0.2` tendrá un objetivo lexicográfico: minimizar faltantes,
minimizar exceso de nutrientes y, una vez cubierto lo necesario, minimizar el
número de bultos. Todos los coeficientes de dominio estarán fuera del código y
tendrán fuente, versión y fecha.

## Arquitectura

```text
Sensor / Excel (% NPK)
        │
        ▼
Calidad ──► GP + incertidumbre ──► zonas + siguiente medición
                                      │
Clima + perfiles versionados ─────────┤
                                      ▼
                         optimizador de formulaciones
                                      │
                                      ▼
                    propuesta ──► revisión humana ──► productor
```

- **Backend:** FastAPI, Pydantic, NumPy, SciPy y scikit-learn.
- **Frontend:** HTML, CSS y módulos ES; instalable y usable con conectividad
  limitada.
- **Datos de demo:** Excel como fuente y JSON como paquete offline.
- **Gobernanza local:** SQLite para propuestas y decisiones. La persistencia de
  producción sigue pendiente.

## Estado comprobable

### Implementado en `v0.1`

- `GET /health`
- `GET /v1/plots`
- `GET /v1/plots/{id}/package`
- `GET /v1/plots/{id}/risk`
- `POST /v1/readings`
- `POST /v1/decisions`
- `GET /v1/decisions/{id}/why`
- `GET /v1/decisions/{id}/history`
- `GET /v1/governance`
- mapa, incertidumbre, siguiente medición, riesgos y respuestas locales de voz

### En migración a `v0.2`

- renombrar y validar todos los valores como porcentajes NPK;
- retirar `ppm`, marcas, productos y costos del contrato;
- cargar perfiles agronómicos y formulaciones desde configuración versionada;
- reemplazar la optimización continua heredada por optimización entera sin precio;
- orientar la navegación al centro de acopio y su red de lotes;
- persistir lecturas, paquetes y decisiones;
- completar pruebas y despliegue reproducible.

El detalle y los criterios de aceptación están en [`TAREAS.md`](TAREAS.md).

## Límites declarados

- Los porcentajes son los valores reportados por el sensor; todavía no están
  validados contra laboratorio.
- El lote de Pasto es un caso demostrativo, no una validación agronómica.
- IOmido no predice rendimiento ni diagnostica enfermedades a partir de voz.
- Ninguna propuesta se ejecuta automáticamente.
- Una recomendación con baja confianza o fuera de los límites configurados debe
  pasar a un técnico.

## Arrancar

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

En otra terminal:

```bash
cd frontend
python -m http.server 5173
```

Abrir <http://localhost:5173>. En local el frontend intenta usar
`http://127.0.0.1:8000`; si no responde, carga el paquete de demo.

## Documentación

| Documento | Contenido |
|---|---|
| [`BRIEF.md`](BRIEF.md) | Problema, usuarios, valor, demo y encaje con Track 4 |
| [`BACKEND.md`](BACKEND.md) | Arquitectura, semántica NPK y plan técnico `v0.2` |
| [`FRONTEND.md`](FRONTEND.md) | Experiencia, contratos y estados de interfaz |
| [`TAREAS.md`](TAREAS.md) | Roadmap y commits granulares |
| [`backend/README.md`](backend/README.md) | Guía rápida del backend y estado real |
| [`frontend/README.md`](frontend/README.md) | Guía rápida del frontend y estado real |
