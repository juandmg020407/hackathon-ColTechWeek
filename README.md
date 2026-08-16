<h1 align="center">IOmido</h1>

<p align="center">
  <strong>Un sensor de suelo, muchas fincas.</strong><br>
  Convierte una medición puntual de NPK en un mapa del lote con incertidumbre visible,<br>
  una receta de fertilización <em>recomendada</em> y una decisión que siempre firma una persona.
</p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="scikit-learn" src="https://img.shields.io/badge/scikit--learn-1.6-F7931E?style=flat-square&logo=scikitlearn&logoColor=white">
  <img alt="NumPy" src="https://img.shields.io/badge/NumPy-2.2-013243?style=flat-square&logo=numpy&logoColor=white">
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-WAL%20%2B%20triggers-003B57?style=flat-square&logo=sqlite&logoColor=white">
  <img alt="Claude Sonnet 5" src="https://img.shields.io/badge/Claude-Sonnet%205-D97757?style=flat-square&logo=anthropic&logoColor=white">
  <img alt="Vercel" src="https://img.shields.io/badge/Vercel-serverless-000000?style=flat-square&logo=vercel&logoColor=white">
</p>

<p align="center">
  <img alt="66 tests offline" src="https://img.shields.io/badge/tests-66%20offline-2EA043?style=flat-square">
  <img alt="Datos IDEAM" src="https://img.shields.io/badge/datos-IDEAM%20·%20datos.gov.co-DC2626?style=flat-square">
  <img alt="Contrato v2.0" src="https://img.shields.io/badge/contrato-v2.0%20·%2035%20endpoints-1F6FEB?style=flat-square">
  <img alt="Human in the loop" src="https://img.shields.io/badge/decisión-humana%20obligatoria-6E56CF?style=flat-square">
  <img alt="Track 04" src="https://img.shields.io/badge/CTW%202026-Track%2004-EAB308?style=flat-square">
</p>

---

## El problema

Un centro de acopio de papa en Nariño compra a decenas de pequeños productores de
media a dos hectáreas. Ninguno tiene análisis de suelo reciente: el laboratorio
cuesta más de lo que deja una cosecha pequeña y los resultados llegan cuando ya se
sembró. Entonces se fertiliza por costumbre —el mismo bulto, la misma dosis, en
todo el lote y todos los años.

Y un lote no es homogéneo. En las **19 mediciones reales** de esta demo, dos
puntos separados **45 metros** dan potasio de **1 %** y de **13 %**, y el
nitrógeno va de **1 % a 27 %** dentro de la misma hectárea y cuarto. Fertilizar
eso con una dosis única es equivocarse en casi toda la superficie: sobra donde ya
había, falta donde el suelo estaba pobre, y el excedente de N y P termina lavado
en el río.

Comprar un sensor por finca no lo resuelve, porque nadie lo va a comprar.

## A quién está dirigido

IOmido está pensado para **centros de acopio, asociaciones y técnicos
agropecuarios que acompañan a pequeños productores**. El centro comparte un
sensor entre muchas fincas, interpreta las mediciones y entrega al agricultor una
propuesta que puede entender y discutir. El productor no necesita comprar
hardware, aprender un software especializado ni tener conexión permanente.

## Impacto social

El proyecto busca que la agricultura de precisión deje de ser un servicio
reservado para fincas grandes. Compartir el sensor reduce la barrera de entrada;
aplicar por zonas **puede** evitar fertilizante innecesario y busca disminuir el
excedente de N y P que termina en las fuentes de agua; mostrar la incertidumbre
evita disfrazar una estimación como certeza; y traducir el resultado a lenguaje
cotidiano devuelve la decisión a quien conoce el lote.

IOmido no reemplaza al agricultor, al técnico ni al laboratorio. Les da una
evidencia más útil, trazable y oportuna para decidir juntos.

---

## De la tierra a la decisión

### ① La medición en campo

<img src="docs/media/1.jpg" alt="Agricultor insertando el sensor NPK en el suelo de un lote de papa en Pasto, Nariño" width="100%">

El técnico del centro de acopio recorre las fincas con **un solo sensor
compartido por toda la red**. Lo clava en la tierra y anota N, P, K y la
coordenada. Nada más. El productor no compra hardware, no instala software y no
paga suscripción.

Así se levantaron las 19 lecturas del lote **El Rosal** (papa Diacol Capiro,
1,28 ha, Pasto, Nariño) sobre las que corre todo lo que sigue. No son datos
generados.

### ② Recolección y envío a la nube

<img src="docs/media/2.jpg" alt="La lectura del sensor viajando del teléfono del técnico a la nube" width="100%">

Cada lectura se registra con un `client_id` que la hace **idempotente**: si el
técnico pierde señal a mitad de un lote y reintenta, no se duplica nada. También
puede llegar en lote desde un Excel (`POST /v1/readings/import`).

La lectura fuera del polígono no se borra: se **conserva y se anota**. De las 19,
18 entran al modelo y una queda marcada por geometría, con su motivo. Un dato mal
ubicado que desaparece en silencio es un dato que nadie puede auditar después.

### ③ La IA procesa, y cruza seis fuentes externas

<img src="docs/media/3.jpg" alt="Diagrama del procesamiento por IA cruzando las APIs de IDEAM, Open-Meteo, NASA POWER, NOAA CPC y Anthropic" width="100%">

| API | Qué aporta |
|---|---|
| **IDEAM**<br>`datos.gov.co` · Socrata | La **observación real**: estaciones físicas de la autoridad meteorológica colombiana. Para el lote El Rosal, la estación *Universidad de Nariño – AUT* está a **2,47 km** y publicó ayer. Es el único dato de instrumento; los demás productos climáticos son modelos. Abierta y sin llave |
| **Open-Meteo Forecast**<br>`api.open-meteo.com/v1/forecast` | 16 días de pronóstico horario **en la coordenada exacta del lote**, no de la cabecera municipal. De aquí salen la mínima prevista (helada), el balance lluvia − evapotranspiración (sequía) y las horas a 10–24 °C con HR ≥ 90 % (gota tardía). Abierta y sin llave |
| **NASA POWER**<br>`power.larc.nasa.gov/api/temporal/daily/point` | 20 años de reanálisis diario del mismo punto. Es la **memoria**: sin ella «va a llover poco» no significa nada. Con ella se responde a qué año histórico se parece esta temporada |
| **NOAA CPC — ENSO advisory** | Fase e índice de **El Niño / La Niña**: la escala estacional que ni el pronóstico de 16 días ni la climatología capturan. Va versionado con fecha y URL porque NOAA no publica ese aviso como API JSON estable, y preferimos decirlo a fingir un endpoint |
| **Anthropic Claude** `claude-sonnet-5` | Redacta la respuesta del asistente en español claro sobre evidencia estructurada. **No calcula, no decide y no puede emitir una cifra que no esté en los datos** |
| **OpenStreetMap tiles** | Mapa base **opcional**. Si no carga —lo normal en una finca sin señal— el mapa de suelo sigue siendo legible |

Traer al IDEAM tuvo un costo real: su dataset **republica la misma lectura hasta
19 veces**. Sumar sin deduplicar inflaba la lluvia acumulada un **31 %** (45,4 mm
frente a los 34,6 mm reales). El sistema deduplica por marca de tiempo y reporta
cuántos registros descartó, porque un dato público no es lo mismo que un dato
limpio.

Toda fuente externa pasa por la misma política: timeout, reintentos con backoff,
caché en SQLite, *circuit breaker* y último valor válido. Y si no hay Internet, el
sistema **sigue funcionando con fixtures versionados y lo declara degradado en la
propia respuesta**. Una demo que se cae por el wifi del auditorio no es una demo;
una que disimula que usa datos viejos es peor.

### ④ La IA convierte los datos en una decisión entendible

<img src="docs/media/4.jpg" alt="Mapa de nutrientes, receta recomendada y acta humanizada accesible mediante un código QR" width="100%">

Tres **procesos gaussianos Matérn** —uno por nutriente— llevan 18 puntos a 140
celdas de 10 × 10 m. Cada celda recibe media, desviación e intervalo del 95 %, así
que el mapa dice también **dónde no sabe**: lo rayado es lo incierto, nunca lo
pobre. Y sugiere la **siguiente** medición, a 54 m de la más cercana, para
aprender lo máximo con un solo punto más.

La IA no es una caja negra ni un chatbot que inventa dosis. En el flujo actual
cumple tareas separadas y verificables:

- el proceso gaussiano construye el mapa y cuantifica su incertidumbre;
- el aprendizaje activo propone dónde conviene tomar la siguiente muestra;
- KMeans agrupa las celdas en zonas que el técnico sí puede manejar;
- NearestNeighbors busca temporadas climáticas parecidas;
- Claude Sonnet 5, cuando está habilitado, **traduce la evidencia a español
  claro**, pero no calcula ni decide.

Después, una **búsqueda entera exacta y determinista** —no el modelo de lenguaje—
enumera 12 341 combinaciones del catálogo que el centro tiene en bodega y
devuelve la mejor:

```text
Zona 1 · 0,67 ha        8 bultos de 20-10-30  +  1 bulto de 30-30-40
                        faltante 0,0 kg  ·  exceso 48,9 kg
```

Bultos enteros, porque nadie aplica 2,7 bultos. Sin marcas, sin nombres químicos
y **sin precios**: el objetivo es nutricional, no monetario, y no publicamos un
ahorro que no podemos sustentar.

El resultado es siempre una receta **recomendada, no prescrita**. Toda propuesta
nace en la base de datos como `pending`, `applied = false` y
`requires_technical_validation`, y una persona puede **aceptar, rechazar,
modificar o remitir** la propuesta.

Cuando el técnico la acepta, el tablero genera un **QR humanizado** que abre el
acta de campo en el celular. El documento conserva las cifras calculadas por el
motor, reparte los bultos por zona y pone cada tecnicismo al lado de su traducción
cotidiana: por ejemplo, «incertidumbre predictiva sobre el umbral» se convierte
en «las franjas rayadas son lugares donde hace falta medir». El QR se genera
dentro de la aplicación, apunta al PDF del mismo proyecto y no envía información
a un servicio externo.

Claude puede mejorar la redacción del asistente sobre evidencia ya estructurada,
pero un verificador compara todas sus cifras con las permitidas. Si introduce un
número que no estaba en la evidencia, se descarta la respuesta completa y se usa
la explicación determinista. Si no hay llave, Internet o presupuesto, el sistema
sigue funcionando.

Es supervisión humana significativa en el sentido del **AI Act**, y no está
sostenida por una promesa en un slide:

- el sistema **propone**, una persona **decide** — el esquema de la base no
  permite otra cosa;
- toda salida trae su explicación paso a paso, su modelo, sus fuentes y el
  **SHA-256 de los datos de entrada**;
- la incertidumbre es visible, no se esconde detrás de un color bonito;
- lo que el sistema **no sabe** viaja en la misma respuesta que la recomendación;
- las decisiones quedan en una auditoría **append-only**: triggers de SQLite
  rechazan `UPDATE` y `DELETE`, así que el pasado no se reescribe;
- los datos son del productor: cada uno lleva `data_origin` y `consent_status`
  explícitos, y no puntuamos agricultores ni evaluamos crédito.

### ⑤ Aplicación precisa y anticipación al clima

<img src="docs/media/5.jpg" alt="Aplicación precisa por zona y alerta anticipada de riesgo climático estacional" width="100%">

La receta llega a la zona que la necesita, en la cantidad que le corresponde, y
**en el momento en que tiene sentido aplicarla**. Tres motores de riesgo
explicables acompañan cada propuesta:

- **Helada** — mínima prevista por Open-Meteo, agravada por fase ENSO seca.
- **Sequía** — balance hídrico lluvia − evapotranspiración, más la anomalía
  estacional y El Niño. Es la misma señal que precede a una temporada seca
  crítica en el altiplano nariñense.
- **Gota tardía** (*Phytophthora infestans*) — horas favorables en las próximas
  48 h. Es lo que arruina un cultivo de papa en el alto andino.

Cada riesgo entrega score, severidad, ventana temporal, entradas exactas,
fuentes, versión de la regla y **qué le cambió a la propuesta**. Si las fuentes
están degradadas, la confianza baja automáticamente de 0,90 a 0,65 y se dice.

Son **reglas transparentes con umbrales visibles, no un clasificador entrenado**.
Podríamos haber generado etiquetas sintéticas y presentar un modelo con 94 % de
accuracy sobre datos inventados por nosotros mismos. Eso no es machine learning,
es saber llamar a `.fit()`.

---

## La demo en un minuto

Centro de acopio demo con tres formulaciones en bodega: `30-30-40`, `20-10-30` y
`10-20-20`. La aplicación abre en un centro de control con barra lateral y nueve
secciones; el recorrido de la demo toca seis:

1. **Resumen** — qué lotes necesitan medición o revisión, hoy.
2. **Mapas** — N, P y K en porcentaje; lo rayado es lo incierto, no lo pobre.
3. **Recomendaciones** — `20-10-30 × 8 + 30-30-40 × 1` por zona, con su faltante
   y su exceso.
4. **¿Por qué?** — modelo, entradas, fuentes, hash de los datos y lo que **no**
   se sabe.
5. **Alertas** — el riesgo climático con su ventana, su confianza y su efecto
   sobre la propuesta.
6. **Historial** — se acepta o se remite, y queda en la auditoría append-only.

## Correrlo

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --reload --port 8000    # desde backend/
```

En otra terminal:

```powershell
cd frontend
python -m http.server 5173
```

Abrir <http://localhost:5173>. El primer arranque crea la base, carga la
configuración versionada e importa las 19 mediciones solo: no hay paso manual.
Sin backend la aplicación abre igual contra el mock; sin Internet el backend
funciona igual y lo declara.

```powershell
python -m pytest backend/tests -q        # 66 pruebas, ninguna toca la red
python backend/scripts/demo_backend.py   # el pipeline entero sin Internet
```

## Lo que afirmamos y lo que no

Un jurado puede verificar esto en el código, no solo leerlo aquí.

**Sí:**

- El pipeline completo corre sobre datos reales de un lote real.
- Interpola, cuantifica su propia incertidumbre y pide la siguiente medición.
- Resuelve la mezcla entera óptima dentro de sus límites y lo demuestra
  (`optimal_within_bounds: true`, 12 341 combinaciones enumeradas).
- Los riesgos modifican la propuesta con explicación y fuente.
- Toda decisión queda en un registro que la base impide reescribir.

**No, y lo decimos en la propia respuesta de la API:**

- El sensor **no está calibrado** contra laboratorio. Va en `warnings` en cada
  llamada.
- El perfil agronómico es `demo_unvalidated`: requerimientos, densidad aparente y
  factor de disponibilidad son supuestos de demostración, no una prescripción
  firmada por un agrónomo.
- **El proceso gaussiano no le gana a IDW en este dataset.** RMSE medio GP
  `4,675924` contra IDW `4,619368` puntos porcentuales. El backend lo reporta
  como `gp_better_than_idw: false`. Elegimos GP por su distribución predictiva y
  su muestreo activo, no por precisión demostrada.
- Los riesgos modelados son **helada, sequía y gota tardía**, más el contexto
  ENSO. **No modelamos incendios**: la señal de sequía indica condiciones
  propicias, y eso es todo lo que podemos afirmar.
- No estimamos ahorro en pesos, no predecimos rendimiento y no puntuamos
  agricultores.

Preferimos un sistema que sepa lo que no sabe.

## Documentación

| Documento | Qué encontrarás |
|---|---|
| [TECNICO.md](TECNICO.md) | Stack, arquitectura, cada modelo, cada API externa, **cómo se usa la IA** y por qué esto no se podía construir hace dos años |
| [MODEL_CARD.md](MODEL_CARD.md) | Métricas reproducibles, usos permitidos y prohibidos, riesgos |
| [docs/API.md](docs/API.md) | Catálogo de los 35 endpoints y códigos de error |
| [backend/README.md](backend/README.md) | Operar el backend |
| [frontend/README.md](frontend/README.md) | Operar el frontend |

## Antes de que esto llegue a un lote de verdad

1. Calibrar el sensor contra muestras de laboratorio.
2. Medir la densidad aparente real y validar la profundidad de muestreo.
3. Que un ingeniero agrónomo local firme requerimientos, disponibilidad y
   máximos por cultivo, variedad y etapa.
4. Consultar clima en vivo en vez de los fixtures versionados.
5. Cargar el inventario real de formulaciones de cada centro.
6. Pilotear y reevaluar GP contra IDW con más lotes y más temporadas.

Ninguno de esos pendientes autoriza presentar el perfil de demo como una
prescripción validada, y el código no lo permite: toda propuesta sale marcada
`requires_technical_validation`.
