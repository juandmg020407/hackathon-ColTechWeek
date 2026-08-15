<div align="center">

# SERENO

**Inteligencia agroclimática para el minifundio colombiano**

Hackathon Colombia Tech Week 2026 · Track 04 — Planeta y Comunidad

*El sereno es el frío húmedo que cae de noche sobre los cultivos. Los paperos de Nariño le tienen respeto: es lo que quema la mata.*

</div>

---

## El problema

**El 80% de los productores de papa en Colombia siembra menos de una hectárea.** Cultivar una hectárea de papa pastusa cuesta unos **$15,6 millones**, y los fertilizantes son entre el **17% y el 19%** de ese costo. Se aplican **a ciegas**: sin análisis de suelo, con recetas genéricas heredadas, calculando "de más por si acaso".

Ese "por si acaso" tiene tres facturas:

1. **Económica.** Se compra fertilizante que el suelo no necesita, mientras falta el que sí.
2. **Ambiental.** El nitrógeno sobrante se lava a las quebradas y se emite como óxido nitroso.
3. **De riesgo.** Se fertiliza sin saber qué viene. **El Niño está activo desde el 4 de agosto de 2026** con 63% de probabilidad de volverse muy fuerte, con pico entre noviembre y enero — justo cuando la papa sembrada hoy esté llenando tubérculo.

La tecnología para resolverlo existe y funciona: sondas de suelo con IA como ChrysaLabs o Stenon. **Cuestan unos USD 10.000 al año.** El aparato sale más caro que el cultivo entero.

> Los grandes cultivos tienen drones, laboratorios y agrónomos de planta. El minifundio no tiene nada. Y no es un problema de voluntad: Agrosmart cobra R$1 por hectárea, y con media hectárea ese modelo no le sirve *a Agrosmart*. Es un hueco estructural que no se cierra con más capital, sino con otra arquitectura.

---

## Cómo lo resolvemos

### 1. Hardware propio y barato

Nuestro compañero de equipo **diseñó un dispositivo que se clava en la tierra y mide NPK**, cumpliendo la normativa del ICA y el Ministerio de Agricultura. Cuesta una fracción de una sonda comercial y no necesita drones ni laboratorio.

**El sensor no es de una finca: rota por la vereda.** Con 30 fincas compartiendo un aparato, el costo por finca cae 30 veces — y cada finca medida mejora el modelo de las vecinas, porque comparten suelo, altitud y clima.

### 2. Software que paga quien tiene con qué

**Modelo B2B2F: paga la empresa, usa el agricultor.**

| | |
|---|---|
| **Quién paga** | Agroindustria, comercializadoras, cooperativas, bancos agrarios, alcaldías y UMATA |
| **Por qué le conviene** | Sus proveedores son quienes pierden la cosecha cuando llega una helada. Un evento climático en Nariño es un problema de suministro para quien compra la papa |
| **Qué recibe** | Riesgo agregado de su base de proveedores, trazabilidad, optimización del insumo que muchas veces ellos mismos financian, y reporte de sostenibilidad |
| **Quién usa** | El agricultor, gratis, en su idioma y por voz |
| **De quién son los datos** | Del agricultor. El aporte al mapa público es opcional y revocable |

Esto resuelve además el problema práctico: **la empresa tiene internet y capacidad de pago; el agricultor tiene 2G y un teléfono modesto.** Cada uno recibe la interfaz que su realidad permite.

### 3. Lo más importante: anticipar, no solo optimizar

Un mapa de calor describe el suelo tal como está hoy. Eso no sirve frente a lo que viene.

> **No le decimos cuánto abono echar. Le decimos cuánto abono echar dado lo que viene.**

Y eso no es retórica, es agronomía implementada:

| Lo que viene | Qué cambia | Por qué |
|---|---|---|
| Sequía | **N × 0,75** | Sin agua no se absorbe, se volatiliza. Es plata tirada |
| Helada | **K × 1,15** | El potasio regula el potencial osmótico y mejora la tolerancia al frío |
| Lluvia fuerte en 48 h | Aplazar | Se lava y termina en la quebrada |
| Condiciones de gota | Alerta sanitaria | Antes de que aparezca en la mata |

Cada ajuste viaja al agricultor **con su factor y su motivo**. Nunca en silencio.

---

## Cómo usamos la IA

La IA no es un chatbot pegado encima. Es el núcleo, y resuelve tres problemas que ninguna regla fija puede.

### Problema 1 — El sensor miente, y lo demostramos

Analizando los 19 puntos reales del lote encontramos esto:

```
correlación   N–P = 0.970    N–K = 0.981    P–K = 0.9917
regresión     P ≈ 0.356·N  (R² = 0.94)     K ≈ 0.506·N  (R² = 0.96)
```

Una correlación P–K de **0,9917 no existe en suelos reales**. El nitrógeno (móvil, ligado a materia orgánica) y el potasio (catión intercambiable, ligado a arcillas) no se comportan igual dentro de un lote.

**El sensor no mide tres cosas: mide una** — conductividad eléctrica — y la reparte con coeficientes fijos. Tiene **un grado de libertad, no tres**.

Recuperar los tres exige inyectar información externa: prior espacial de suelos, textura, altitud, clima. **Eso es exactamente lo que un modelo hace y un `if` no.** Es el aporte central de IA del proyecto, y nació de mirar los datos, no de un catálogo de técnicas.

### Problema 2 — Ocho puntos no son un lote

**M3 · Proceso Gaussiano con kernel Matérn** interpola el lote completo a partir de mediciones dispersas y **devuelve la incertidumbre de cada celda**. De ahí salen tres cosas:

- El mapa continuo por nutriente.
- Las zonas de manejo (KMeans sobre el campo interpolado).
- **Dónde medir la próxima vez**: la celda de máxima varianza posterior. Es *active learning* — el sistema dirige su propia recolección de datos. Un sensor fijo no puede hacer esto; nace de que el aparato sea portátil.

Las celdas inciertas se pintan **rayadas, no coloreadas**. Mostrar que no sabemos es parte del producto.

### Problema 3 — Predecir sin fingir que se predice

Nadie acierta un pronóstico a nueve meses. Entonces no lo intentamos. Usamos **razonamiento por casos sobre 20 años de datos satelitales**:

```
ONI actual proyectado: +1.3  (El Niño fuerte)

Años análogos encontrados en NASA POWER:
  2006  El Niño        →  265 mm de lluvia, mínima 7.7 °C
  2009  El Niño fuerte →  314 mm de lluvia, mínima 7.3 °C
  2018  El Niño        →  389 mm de lluvia, mínima 5.7 °C

Normal histórica de la mínima: 8.9 °C
```

En años de El Niño la mínima cae entre **1,2 y 3,2 grados** respecto a la normal. Eso no es una predicción de caja negra: es el registro de lo que pasó las últimas veces que el océano estuvo así. **Interpretable, verificable y con datos reales.**

### El catálogo completo

| | Módulo | Técnica | Qué resuelve |
|---|---|---|---|
| **M1** | Control de calidad | Reglas geométricas + Isolation Forest | Separa "no pertenece al lote" de "lectura rara". Un valor alto es información, no un error |
| **M2** | Desagregación NPK | Gradient Boosting con regresión cuantílica | Recupera 3 grados de libertad de 1, con intervalos de confianza |
| **M3** | Mapa del lote | Proceso Gaussiano (Matérn ν=1.5) | Interpola con incertidumbre + active learning |
| **M4** | Balance de nutrientes | Modelo híbrido tipo QUEFTS + corrección ML | Física agronómica primero, datos después |
| **M5** | Mezcla óptima | Programación lineal | De kg/ha a **bultos y pesos colombianos** |
| **R1–R6** | Motores de riesgo | Modelos agroclimáticos | Helada, sequía, gota, incendio, deslizamiento, ENSO |
| **CLIM** | Climatología | Percentiles + análogos ENSO sobre 7.305 días | Contexto histórico, no adjetivos |
| **AGENT** | Conversación | LLM con *tool-use* | Las herramientas son nuestros endpoints, no conocimiento general |
| **VOZ** | Interfaz | Azure Speech `es-CO` | Español colombiano, 500k caracteres gratis al mes |

**El human-in-the-loop no es un costo de cumplimiento: es el mecanismo de aprendizaje.** Cada vez que un técnico corrige una propuesta, esa corrección es una etiqueta. Con 19 mediciones no se entrena nada; con miles de correcciones revisadas, sí. La supervisión humana es lo que llena el dataset.

---

## Datos: todos públicos, todos verificables

| Fuente | Qué aporta | Volumen | Llave |
|---|---|---|---|
| **NASA POWER** | 20 años de datos agroclimáticos diarios del punto exacto | **7.305 días × 8 parámetros** | No |
| **NASA FIRMS** | Focos de incendio activos casi en tiempo real | VIIRS/MODIS | Gratis |
| **Open-Meteo Forecast** | Pronóstico horario, humedad y temperatura de suelo | 16 días | No |
| **Open-Meteo Seasonal** | ECMWF SEAS5 | 180 días, **51 miembros de ensemble** | No |
| **NOAA CPC** | Estado y pronóstico de ENSO | Mensual | No |
| **SoilGrids (ISRIC)** | pH, carbono orgánico, textura, N total | 250 m | No |
| **SIPSA (DANE)** | Precios de agroinsumos | Mensual | No |
| **El sensor** | Verdad de terreno puntual | 19 mediciones reales | — |

**Fusión multi-escala:** 20 años de satélite a 0,5° para saber qué es normal, pronóstico a escala de kilómetros para lo que viene, y la medición puntual del sensor para lo que hay. Ninguna de las tres sola alcanza. **Eso es lo que un dron no da.**

Usamos cada fuente para lo que sirve y lo decimos: el píxel de NASA POWER promedia valles y montañas, así que sirve para climatología, **nunca** para predecir la helada de mañana.

---

## IA responsable

**Los artículos 14 y 50 del AI Act entraron en vigor el 2 de agosto de 2026.** En Colombia el marco es el **CONPES 4144 de 2025**.

Siendo precisos: **hoy este sistema no es de alto riesgo** — el apoyo a decisiones agrícolas no está en el Anexo III. Pero la ruta natural de escala sí lo vuelve alto riesgo: el día que un banco lo use para crédito agrícola o el Estado para asignar subsidios, cae de lleno en el Anexo III. **Por eso lo construimos con ese estándar desde ahora, voluntariamente.** Rehacerlo después no es viable.

1. **Propone, nunca ejecuta.** Toda recomendación nace `pendiente`. Sin decisión humana no pasa nada.
2. **Doble firma para lo caro.** Sobre el umbral configurado, requiere visto bueno de un técnico.
3. **Incertidumbre obligatoria.** Ninguna cifra sale sin rango. Si el modelo no sabe, el mapa lo pinta rayado.
4. **Derecho a explicación.** `¿Por qué me dice eso?` es un botón que devuelve entradas, modelo y fuentes fechadas.
5. **Trazabilidad completa.** Registro *append-only*: sin UPDATE, sin DELETE. Artículo 12.
6. **Divulgación.** La voz se identifica como asistente automático en el primer contacto.
7. **Límites declarados.** No diagnostica plagas por voz, no recomienda plaguicidas, no reemplaza un laboratorio.
8. **Cero decisiones automáticas sobre personas.** No puntúa agricultores ni evalúa solvencia.
9. **Los datos son del agricultor.** El mapa público es *opt-in*, revocable y anonimizado.

Consultable en vivo: `GET /v1/governance`

---

## Qué corre hoy

```
GET  /health                        ✅
GET  /v1/plots                      ✅
GET  /v1/plots/{id}/package         ✅  suelo + clima + riesgos + receta ajustada
GET  /v1/plots/{id}/risk            ✅  los seis motores
POST /v1/readings                   ✅  con control de calidad e idempotencia
GET  /v1/governance                 ✅  la ficha de IA responsable
```

Salida real con los datos reales del lote de Pasto:

```
[ALTA ] estacional  p=0.97   Viene El Niño y va a pegar duro
[ALTA ] gota        p=0.70   Condiciones para que aparezca la gota
[MEDIA] sequía      p=0.50   Le va a faltar agua

ajustes: N ×0.75 · K₂O ×1.10
receta $1.650.000  vs  genérico $2.160.000  →  ahorro $510.000
climatología: 20 años, 7.305 días · 3 años análogos
paquete: 5,6 KB con Brotli · degradado: false
```

**Y algo que importa: el sistema no exageró.** SEAS5 proyecta +11,4% de lluvia con solo 12,4% de dispersión entre los 51 miembros del ensemble, así que el motor **no** escaló a "crítica" aunque ENSO diga El Niño. Un sistema que sabe cuándo *no* alarmar es el que se gana la confianza.

---

## La demo

**Un lote real de 0,69 hectáreas en Pasto, Nariño.** Coordenadas 1,2478 / −77,2672, a 2.553 m. Dieciocho mediciones válidas de un sensor real. Variedad Diacol Capiro.

1. **El lote.** Zonas con la incertidumbre visible. Un punto de los datos está a 1,2 km del resto: el sistema lo rechaza en vivo y explica por qué.
2. **La pregunta**, por nota de voz: *«¿le echo abono este fin de semana?»*
3. **La respuesta, en voz colombiana:** *«Todavía no. Pero hay algo más importante: viene El Niño y va a pegar duro entre noviembre y enero, justo cuando su papa esté llenando. La última vez que el clima estuvo así fue en 2009, y la temperatura bajó hasta 7,3 grados. Le conviene subir el potasio ahora.»*
4. **El porqué.** Qué dato, qué modelo, qué tan seguro está.
5. **La decisión es del agricultor.** El sistema propone; el humano decide.
6. **El bien público.** Cada medición anonimizada alimenta el primer mapa abierto de fertilidad de suelos del país.

---

## Criterios de evaluación

| Criterio | Pts | Cómo lo atacamos |
|---|---|---|
| **Impacto público** | **25** | Usuario real y específico (80% siembra <1 ha), ahorro medido en pesos ($510.000 en 0,69 ha), y un bien público de datos abiertos. El track pide "al servicio de lo público" y devolvemos los datos al país |
| **Uso real de IA** | **25** | La IA es el núcleo: recuperar 3 grados de libertad de 1, GP con incertidumbre y active learning, 6 motores de riesgo, análogos ENSO sobre 7.305 días, agente con tool-use |
| **Demo funcional** | **20** | Corre con datos reales, offline en 2G, paquete de 5,6 KB, y se ve en el video de 1 minuto |
| **Viabilidad + escala** | **15** | B2B2F: paga quien puede. Sensor compartido por vereda. Voz gratis hasta 2.500 respuestas/mes. Flywheel de datos vía human-in-the-loop |
| **Ejecución técnica + UX** | **15** | Presupuesto de bytes documentado, arquitectura por capas, gobernanza desde el día uno, contratos de API congelados |

---

## Honestidad

Un jurado técnico premia el rigor y castiga el exceso.

**Lo que afirmamos:**
- 19 mediciones reales de un lote real en Pasto.
- Demostramos con los datos que el sensor tiene un grado de libertad, no tres.
- El pipeline corre end-to-end y entrega 5,6 KB.
- Los seis motores usan fuentes públicas verificables y citadas.

**Lo que NO afirmamos:**
- ⚠️ La calibración de sensor a ppm es **provisional**, sin validar contra laboratorio.
- ⚠️ Los precios de fertilizante son **de referencia** hasta conectar SIPSA.
- ⚠️ **No hay validación en campo.** Hay un pipeline correcto y un diseño defendible. El siguiente paso está identificado: conseguir pares sensor ↔ laboratorio.

Nunca decimos "precisión de laboratorio", ni "predecimos su cosecha", ni un porcentaje de acierto que no hayamos medido.

---

## Arrancar

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

http://localhost:8000/docs · No hace falta `.env`: todas las claves son opcionales y el sistema degrada en vez de caerse.

## Documentos

| | |
|---|---|
| [`BRIEF.md`](BRIEF.md) | El proyecto completo: problema, modelo de negocio, competencia |
| [`BACKEND.md`](BACKEND.md) | Arquitectura, endpoints, fuentes, modelo de datos |
| [`FRONTEND.md`](FRONTEND.md) | Contrato de API, tipos, presupuesto de bytes en 2G |
| [`backend/README.md`](backend/README.md) | Cómo levantar y qué falta |

---

<div align="center">

**Equipo de dos.** Backend y modelos · Frontend · Hardware por un tercero del equipo extendido.

</div>
