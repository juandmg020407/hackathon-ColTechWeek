# SERENO — brief del proyecto

> *El sereno es el frío húmedo que cae de noche sobre los cultivos. Los paperos de Nariño le tienen respeto: es lo que quema la mata. El producto avisa del sereno, y deja sereno al que lo usa.*

Hackathon Colombia Tech Week 2026 · Track 04 Planeta y Comunidad · Entrega domingo 09:00

---

## 1. En una frase

**Un asistente de voz en español colombiano que le dice a un papero de menos de una hectárea qué viene, qué significa para su lote y qué puede hacer — usando su propio suelo medido, el pronóstico estacional y las alertas públicas del país.**

---

## 2. El giro respecto a la idea original

La primera versión optimizaba fertilización: sensor → mapa de calor → receta de abono. Útil, pero mira hacia atrás: describe el suelo tal como está hoy.

**El país no está en una situación normal.** El Niño está activo desde el 4 de agosto de 2026, con 63% de probabilidad de convertirse en un evento muy fuerte con pico entre noviembre de 2026 y enero de 2027. Para un cultivo de papa a 2.500 msnm en Nariño eso significa cielos despejados, noches frías y déficit hídrico: **heladas y sequía en la mitad del ciclo del cultivo.**

Un mapa de calor no sirve de nada frente a eso. Lo que sirve es saberlo con meses de anticipación y ajustar.

Entonces la tesis cambia:

> **No le decimos cuánto abono echar. Le decimos cuánto abono echar dado lo que viene.**

Ese "dado lo que viene" no es retórica, es agronomía:

| Lo que viene | Qué cambia en la recomendación |
|---|---|
| Sequía prolongada | **Bajar nitrógeno.** Sin agua no se absorbe, se volatiliza y se pierde la plata |
| Riesgo de helada | **Subir potasio.** El K regula el potencial osmótico y mejora la tolerancia al frío |
| Lluvia fuerte en 48 h | **Aplazar la aplicación.** Se lava y termina en la quebrada |
| Condiciones de gota | Alerta sanitaria antes de que aparezca en la mata |

Las dos mitades del producto se necesitan: el suelo dice *qué tiene*, el pronóstico dice *qué va a pasar*, y la recomendación sale del cruce.

---

## 3. El hardware es la premisa

Nada de esto funciona sin resolver primero cómo se obtienen los datos, y ahí está nuestra ventaja: **un integrante del equipo diseñó el dispositivo.**

Es una sonda que se clava en la tierra y mide NPK, construida cumpliendo la normativa del ICA y el Ministerio de Agricultura. Cuesta una fracción de una sonda comercial —ChrysaLabs se arrienda por unos **USD 10.000 al año**— y no requiere drones, laboratorio ni instalación fija.

Esa diferencia de costo **es** el proyecto. Cultivar una hectárea de papa pastusa cuesta unos $15,6 millones: una sonda comercial sale más cara que el cultivo entero. La agricultura de precisión no llegó al minifundio por precio, no por falta de ganas.

**Y el sensor no es de una finca: rota por la vereda.** Con 30 fincas compartiendo un aparato el costo por finca cae 30 veces, y cada finca medida mejora el modelo de las vecinas porque comparten suelo, altitud y clima. Un sensor fijo por finca nunca genera ese efecto.

---

## 4. Modelo de negocio: B2B2F

**Paga la empresa. Usa el agricultor.**

El agricultor de media hectárea no tiene con qué comprar software ni internet estable para sostener una conversación por voz. Pero hay actores en la cadena que sí tienen ambas cosas — y a quienes les conviene directamente que sus proveedores optimicen gastos y no pierdan cosecha.

| | |
|---|---|
| **Quién paga** | Agroindustria y procesadoras, comercializadoras, cooperativas, bancos agrarios, alcaldías y UMATA |
| **Por qué le conviene** | Sus proveedores son quienes pierden la cosecha cuando llega una helada. Un evento climático en Nariño no es un problema del agricultor: es un problema de **suministro** para quien compra la papa |
| **Qué recibe** | Riesgo agregado de toda su base de proveedores, trazabilidad de origen, optimización del insumo que en muchos casos ellos mismos financian, y reporte de sostenibilidad |
| **Qué recibe el agricultor** | La recomendación completa, gratis, en su idioma y por voz |
| **De quién son los datos** | Del agricultor. El aporte al mapa público es opcional y revocable |

### Por qué esto no es lo mismo que Agrosmart

Agrosmart le vende benchmarking de sostenibilidad a Cargill y Coca-Cola **y además cobra suscripción al agricultor**: el valor fluye hacia arriba y el productor es, en la práctica, el sensor.

Nuestra diferencia es explícita: **el agricultor nunca paga y sus datos siguen siendo suyos.** La empresa paga por el agregado, el riesgo de suministro y la trazabilidad — cosas que solo tienen sentido a escala de cartera y que al agricultor individual no le sirven de nada.

### Y resuelve el problema práctico

La empresa tiene internet, capacidad de pago y personal técnico. El agricultor tiene 2G y un teléfono modesto. **Cada uno recibe la interfaz que su realidad permite:**

| | Quién | Canal | Red |
|---|---|---|---|
| **A** | Empresa, cooperativa o UMATA — cartera de proveedores, riesgo agregado | Panel web | Buena |
| **B** | Técnico que carga el sensor y hace la ronda | PWA offline-first | Intermitente |
| **C** | El agricultor | WhatsApp, notas de voz en español colombiano | 2G |
| **D** | Quien tiene teléfono de botones | SMS de 160 caracteres | Sin datos |

---

## 5. Qué hace, concretamente

### 5.1 Lee el suelo
Un sensor que se clava en la tierra entrega N, P y K. Con los 18 puntos válidos del lote de Pasto, un Proceso Gaussiano interpola el lote completo **con su incertidumbre**, lo divide en zonas de manejo y calcula el faltante de nutrientes por zona.

Y algo que descubrimos en los datos y que define el aporte de IA: **el sensor no mide tres cosas, mide una.** La correlación entre P y K es de 0,9917 y P ≈ 0,356·N. El aparato deriva los tres valores de una sola señal de conductividad. Recuperar tres grados de libertad a partir de uno solo es posible inyectando información externa (prior de suelos, contexto, clima) — y eso no lo hace ninguna regla fija.

### 5.2 Mira lo que viene
Seis motores de riesgo, todos sobre datos públicos y gratuitos:

| | Riesgo | Cómo |
|---|---|---|
| R1 | **Helada** | Mínimas, cobertura nubosa, punto de rocío y viento del pronóstico horario. Las heladas de radiación en Nariño ocurren con cielo despejado y aire seco — exactamente lo que trae El Niño |
| R2 | **Sequía / déficit hídrico** | Balance hídrico: precipitación acumulada contra evapotranspiración de referencia, más el pronóstico estacional a 9 meses |
| R3 | **Gota (tizón tardío)** | *Phytophthora infestans* es la enfermedad número uno de la papa en Colombia. El riesgo se calcula solo con clima: horas de humedad relativa sobre 90% y temperatura entre 10 y 24 °C |
| R4 | **Incendios cerca** | Focos activos de NASA FIRMS en un radio alrededor del lote, con dirección del viento |
| R5 | **Deslizamiento** | Lluvia acumulada de 3 y 7 días contra umbrales de intensidad-duración, ponderada por la pendiente del terreno |
| R6 | **Estacional / ENSO** | Estado de El Niño y su implicación local para el ciclo del cultivo |

### 5.3 Lo dice en voz colombiana
Azure Speech con `es-CO-SalomeNeural`. **500.000 caracteres gratis al mes** — unas 2.500 respuestas mensuales, indefinidamente. El agricultor pregunta por nota de voz y recibe una nota de voz.

No es una conversación en vivo: en 2G eso no existe. Es mensajería asíncrona, que es lo que WhatsApp hace mejor que nadie.

### 5.4 Y usa veinte años de historia para dar contexto
NASA POWER entrega **7.305 días de datos agroclimáticos diarios** del punto exacto del lote, sin llave y gratis. Con eso el sistema deja de usar adjetivos y empieza a usar números: no dice "va a estar seco", dice "los próximos meses caen en el percentil 8 de los últimos veinte años".

Y lo más valioso: **años análogos.** En vez de pedirle a un modelo que prediga a nueve meses —donde nadie acierta— se buscan los años con la misma fase de El Niño y se muestra lo que efectivamente ocurrió:

```
ONI actual proyectado: +1.3
  2006  El Niño        →  265 mm,  mínima 7,7 °C
  2009  El Niño fuerte →  314 mm,  mínima 7,3 °C
  2018  El Niño        →  389 mm,  mínima 5,7 °C
Normal histórica de la mínima: 8,9 °C
```

En años de El Niño la mínima cae entre 1,2 y 3,2 grados. Eso es razonamiento por casos: interpretable, verificable y con datos reales, no una caja negra.

**Fusión multi-escala:** veinte años de satélite a 0,5° para saber qué es normal, pronóstico a escala de kilómetros para lo que viene, y la medición puntual del sensor para lo que hay. Ninguna sola alcanza — y es justo lo que un dron no da.

### 5.5 Y nunca decide solo
Ver la sección 7.

---

## 6. La demo

**Un lote real de 0,69 hectáreas en Pasto, Nariño. Coordenadas 1,2478 / −77,2672. Dieciocho mediciones reales de un sensor NPK. Variedad Diacol Capiro.**

No es un caso hipotético. El recorrido de la demo:

1. **El lote.** Mapa de zonas con la incertidumbre visible. Un punto de los datos está a 1,2 km del resto: el sistema lo rechaza en vivo y explica por qué.
2. **La pregunta.** El agricultor manda una nota de voz: *«¿le echo abono este fin de semana?»*
3. **La respuesta, en voz colombiana.** No es un número: *«Todavía no. El jueves llueve fuerte y se le lava. Pero hay algo más importante: viene El Niño y va a pegar duro entre noviembre y enero, justo cuando su papa esté llenando tubérculo. Le conviene subir el potasio ahora para que aguante el frío.»*
4. **El porqué.** Un botón muestra de dónde salió cada pieza: qué dato, qué modelo, qué tan seguro está.
5. **La decisión es del agricultor.** El sistema propone. El agricultor confirma, rechaza o pide que lo revise el técnico. Nada se ejecuta solo.
6. **El bien público.** Cada medición, anonimizada, alimenta el primer mapa abierto de fertilidad de suelos del país.

---

## 7. IA responsable — cómo está construido

### 7.1 El marco

**AI Act de la Unión Europea:** los artículos 14 (supervisión humana) y 50 (transparencia) entraron en vigor el **2 de agosto de 2026**, hace menos de dos semanas.

**Seamos precisos: hoy este sistema no es de alto riesgo.** El apoyo a decisiones agrícolas no está en el Anexo III. Pero la ruta natural de escala sí lo vuelve alto riesgo: en el momento en que un banco lo use para evaluar crédito agrícola, o el Estado para asignar subsidios de fertilizante, cae de lleno en el Anexo III (acceso a servicios esenciales y evaluación de solvencia).

**Por eso lo construimos con ese estándar desde ahora, voluntariamente.** No porque estemos obligados, sino porque rehacerlo después no es viable.

En Colombia el marco es el **CONPES 4144 de 2025**, la Política Nacional de Inteligencia Artificial, con sus ejes de ética y gobernanza y de mitigación de riesgos.

### 7.2 Las nueve reglas

1. **Propone, nunca ejecuta.** Toda recomendación es una propuesta con estado `pendiente`. Alguien la acepta, la rechaza o la deriva. Sin confirmación no pasa nada.
2. **Doble firma para lo caro.** Si la recomendación implica un gasto sobre el umbral configurado, requiere revisión de un técnico agrónomo antes de mostrarse como aceptable.
3. **Incertidumbre obligatoria.** Ninguna cifra sale sin rango ni nivel de confianza. Si el modelo no sabe, el mapa lo pinta rayado y la voz lo dice.
4. **Derecho a explicación.** «¿Por qué me dice eso?» es un botón, no un párrafo de términos y condiciones. Devuelve los datos de entrada, la versión del modelo y las fuentes.
5. **Trazabilidad completa.** Cada recomendación guarda entradas, versión de modelo, fuentes con su marca de tiempo y quién decidió qué. Registro append-only, en línea con el artículo 12.
6. **Divulgación.** La voz se identifica como asistente automático en el primer contacto de cada sesión. Artículo 50.
7. **Límites declarados.** El sistema tiene una lista explícita de lo que no sabe hacer: no diagnostica plagas por descripción verbal, no recomienda dosis de plaguicidas, no reemplaza un análisis de laboratorio. Ante esos casos remite a la UMATA.
8. **Cero decisiones automáticas sobre personas.** No puntúa agricultores, no evalúa solvencia, no ordena listas de beneficiarios.
9. **Los datos son del agricultor.** El aporte al mapa público es opt-in explícito, revocable, y el agregado se publica anonimizado y con grilla gruesa para que no se pueda reidentificar una finca.

### 7.3 Por qué esto también es buena ingeniería

El human-in-the-loop no es un costo de cumplimiento: **es el mecanismo de aprendizaje del sistema.** Cada vez que un técnico corrige una propuesta, esa corrección es una etiqueta. Con 19 mediciones no se entrena nada; con 5.000 propuestas revisadas por técnicos, sí.

La supervisión humana es lo que llena el conjunto de entrenamiento.

---

## 8. Qué es honesto decir y qué no

Un jurado técnico premia el rigor y castiga el exceso. Lo que decimos:

- ✅ Tenemos 18 mediciones reales de un lote real en Pasto.
- ✅ Detectamos y probamos que el sensor tiene un grado de libertad, no tres.
- ✅ El pipeline completo corre y entrega un paquete de 3,2 KB.
- ✅ Los seis motores de riesgo usan fuentes públicas verificables.
- ⚠️ **La calibración de sensor a ppm es provisional.** No está validada contra laboratorio. Lo decimos en la app, en el pitch y en el código.
- ⚠️ **Los precios de fertilizante son de referencia** hasta conectar SIPSA.
- ⚠️ **No hay validación en campo.** Lo que hay es un pipeline correcto y un diseño defendible. La validación es el siguiente paso, y sabemos exactamente cuál es: conseguir pares sensor ↔ laboratorio.

Nunca decimos «precisión de laboratorio», ni «predecimos su cosecha», ni un porcentaje de acierto que no hayamos medido.

---

## 9. Contra qué competimos

| | Agrosmart | Agranimo | ChrysaLabs / Stenon | **Sereno** |
|---|---|---|---|---|
| Qué mide | Clima, agua | Micro-clima | Nutrientes | **Nutrientes + riesgo** |
| Desde dónde | Satélite + sensores | Satélite + drones | Sonda | **Sonda + datos públicos** |
| Para quién | Medianos, Cargill, Coca-Cola | Exportadores de fruta | Agricultura de precisión | **Menos de 1 hectárea** |
| Costo | R$1 por hectárea al mes | Sensores propios | ~USD 10.000 al año | **Un aparato por vereda** |
| Interfaz | App con dashboard | Dashboard | Dashboard | **Voz, en 2G** |
| Los datos van a | La cadena corporativa | El productor | El productor | **El productor y el país** |

Agrosmart cobra por hectárea: con media hectárea, ese modelo no le sirve *a Agrosmart*. No es un descuido suyo, es un hueco estructural que no se cierra con más capital.

Y el análisis de suelo con IA en tiempo real ya existe — cuesta diez mil dólares al año. Cultivar una hectárea de papa pastusa cuesta unos 15,6 millones de pesos. El aparato costaría más que el cultivo entero.

---

## 10. Cómo se puntúa

| Criterio | Pts | Cómo lo atacamos |
|---|---|---|
| Impacto público | 25 | Usuario real y específico, ahorro en pesos, y un bien público de datos abiertos |
| Uso real de IA | 25 | La IA es el núcleo: recuperar 3 grados de libertad de 1, GP con incertidumbre, seis motores de riesgo y un agente con herramientas |
| Demo funcional | 20 | Corre con datos reales, offline, y se ve en el video de 1 minuto |
| Viabilidad + escala | 15 | Sensor compartido por vereda, voz gratis hasta 2.500 respuestas al mes, flywheel de datos |
| Ejecución técnica + UX | 15 | Presupuesto de 20 KB, arquitectura documentada, gobernanza desde el día uno |

---

## 11. Fuentes de datos

Todas públicas, todas gratuitas, todas citables.

| Fuente | Qué aporta | Volumen | Llave |
|---|---|---|---|
| **NASA POWER** | Datos agroclimáticos diarios del punto exacto: temperatura, lluvia, humedad, radiación, punto de rocío, viento | **7.305 días × 8 parámetros** | No |
| **Open-Meteo Forecast** | Pronóstico horario, humedad y temperatura del suelo | 16 días | No |
| **Open-Meteo Seasonal** | ECMWF SEAS5, con Índice de Eventos Extremos | 180 días, 51 miembros | No |
| **Open-Meteo Archive** | ERA5 histórico desde 1940 | — | No |
| **NASA FIRMS** | Focos de incendio activos casi en tiempo real | VIIRS/MODIS | Gratis por correo |
| **SoilGrids (ISRIC)** | pH, carbono orgánico, textura, nitrógeno total a 250 m | No |
| **NOAA CPC** | Estado y pronóstico de ENSO | No |
| **SIPSA (DANE)** | Precios de insumos agropecuarios | No |
| **ICA** | Fertilizantes con registro vigente | No |

Licencias CC-BY en la mayoría — y como nosotros consumimos datos abiertos, publicamos abierto. Coherencia, no marketing.

---

## 12. Equipo y reparto

Dos personas. Uno en backend y modelos, otro en frontend. El contrato de API está congelado en `FRONTEND.md` para que nadie espere al otro.
