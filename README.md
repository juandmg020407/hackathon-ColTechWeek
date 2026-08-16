<p align="center">
  <img width="1400" height="400" alt="IOmido: un sensor de suelo para muchas fincas" src="https://github.com/user-attachments/assets/ce35261d-ab36-4c11-889e-af5a7f35f92c">
</p>

<p align="center">
  <strong>Un sensor de suelo, muchas fincas.</strong><br>
  Convierte mediciones de nitrógeno, fósforo y potasio (NPK) en un mapa del lote,<br>
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

Cada lectura lleva un identificador único. Si el técnico pierde señal y vuelve a
enviarla, el sistema la reconoce y **no la duplica**. También se pueden cargar
varias mediciones a la vez desde un archivo de Excel.

La lectura fuera del polígono no se borra: se **conserva y se anota**. De las 19,
18 entran al modelo y una queda marcada por geometría, con su motivo. Un dato mal
ubicado que desaparece en silencio es un dato que nadie puede auditar después.

### ③ La IA procesa, y cruza seis fuentes externas

<img src="docs/media/3.jpg" alt="Diagrama del procesamiento por IA cruzando las APIs de IDEAM, Open-Meteo, NASA POWER, NOAA CPC y Anthropic" width="100%">

| Fuente | Qué aporta |
|---|---|
| **IDEAM** | La **observación real** de estaciones meteorológicas colombianas. Para El Rosal, la estación *Universidad de Nariño – AUT* está a **2,47 km** y publicó ayer. Es el único dato medido por un instrumento; las demás fuentes climáticas son estimaciones. |
| **Open-Meteo** | Pronóstico de 16 días para la **ubicación exacta del lote**, no para la cabecera municipal. Permite anticipar heladas, sequía y condiciones favorables para la gota tardía. |
| **NASA POWER** | 20 años de historia climática del mismo punto. Es la **memoria**: sin ella, «va a llover poco» no significa nada. Permite comparar la temporada actual con años anteriores. |
| **NOAA** | Informa si hay **El Niño o La Niña**, fenómenos que pueden cambiar la temporada más allá de lo que muestra un pronóstico de 16 días. |
| **Anthropic Claude** | Redacta la respuesta del asistente en español claro. **No calcula, no decide y no puede añadir cifras que no estén en los datos**. |
| **OpenStreetMap** | Proporciona el mapa de fondo. Es **opcional**: si no carga por falta de señal, el mapa de suelo sigue siendo legible. |

Usar los datos del IDEAM exigió una precaución: su conjunto de datos **repite la misma lectura hasta
19 veces**. Sumar sin deduplicar inflaba la lluvia acumulada un **31 %** (45,4 mm
frente a los 34,6 mm reales). El sistema elimina esas copias, informa cuántas
descartó y conserva el valor correcto.

Si una fuente externa tarda o falla, el sistema vuelve a intentarlo y, cuando es
necesario, usa la última copia válida. Si no hay Internet, **sigue funcionando
con datos de respaldo e indica claramente que la información puede no estar
actualizada**.

### ④ La IA convierte los datos en una decisión entendible

Tres modelos estadísticos —uno por nutriente— convierten 18 mediciones en un mapa
de 140 celdas de 10 × 10 m. El mapa no solo estima qué hay en cada celda: también
muestra **dónde tiene dudas**. Las franjas rayadas indican que hace falta medir
más, no que el suelo sea pobre. El sistema también sugiere dónde tomar la
siguiente muestra para reducir esas dudas.

La IA no es una caja negra ni un chatbot que inventa dosis. En el flujo actual
cumple tareas separadas y verificables:

- un modelo estadístico construye el mapa y muestra qué tan segura es cada
  estimación;
- otro método propone dónde conviene tomar la siguiente muestra;
- las celdas parecidas se agrupan en zonas que el técnico sí puede manejar;
- se buscan temporadas pasadas con condiciones climáticas similares;
- Claude Sonnet 5, cuando está habilitado, **traduce la evidencia a español
  claro**, pero no calcula ni decide.

Después, un cálculo tradicional —no el modelo de lenguaje— prueba las 12 341
combinaciones posibles del inventario del centro y devuelve la que mejor cubre
la necesidad nutricional:

```text
Zona 1 · 0,67 ha        8 bultos de 20-10-30  +  1 bulto de 30-30-40
                        faltante 0,0 kg  ·  exceso 48,9 kg
```

Bultos enteros, porque nadie aplica 2,7 bultos. Sin marcas, sin nombres químicos
y **sin precios**: el objetivo es nutricional, no monetario, y no publicamos un
ahorro que no podemos sustentar.

El resultado es siempre una receta **recomendada, no prescrita**. Primero queda
pendiente de validación técnica y marcada como no aplicada. Una persona puede
**aceptarla, rechazarla, modificarla o remitirla** a otro profesional.

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
la explicación generada mediante reglas verificables. Si no hay llave, Internet
o presupuesto, el sistema sigue funcionando.

Esta supervisión humana está alineada con el enfoque del **AI Act** europeo, y no
depende de una promesa:

- el sistema **propone**, una persona **decide** — el esquema de la base no
  permite otra cosa;
- toda salida trae su explicación, su modelo, sus fuentes y una **huella digital
  de los datos de entrada** para comprobar que no cambiaron;
- la incertidumbre es visible, no se esconde detrás de un color bonito;
- lo que el sistema **no sabe** viaja en la misma respuesta que la recomendación;
- las decisiones quedan en un historial que no se puede editar ni borrar;
- se registra de dónde viene cada dato y si existe consentimiento para usarlo;
  no puntuamos agricultores ni evaluamos crédito.

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

Cada riesgo explica su nivel, cuándo podría ocurrir, qué datos y fuentes utilizó
y **qué cambió en la propuesta**. Si alguna fuente falla o está desactualizada,
la confianza baja automáticamente de 0,90 a 0,65 y se informa.

Son **reglas transparentes con límites visibles**, no un modelo entrenado con
ejemplos inventados para presumir una precisión que no existe.

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
6. **Historial** — se acepta o se remite, y queda en un registro que no se puede
   alterar.

## Correrlo (para desarrolladores)

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
python backend/scripts/demo_backend.py   # el proceso entero sin Internet
```

## Lo que afirmamos y lo que no

Un jurado puede verificar esto en el código, no solo leerlo aquí.

**Sí:**

- El proceso completo usa mediciones reales de un lote real.
- Construye el mapa, muestra sus dudas y recomienda la siguiente medición.
- Encuentra la mejor mezcla posible dentro de sus límites y lo demuestra
  (`optimal_within_bounds: true`, 12 341 combinaciones enumeradas).
- Los riesgos modifican la propuesta con explicación y fuente.
- Toda decisión queda en un registro que la base impide reescribir.

**No, y lo decimos en la propia respuesta del sistema:**

- El sensor **todavía no se ha comparado con análisis de laboratorio**. Cada
  respuesta incluye esta advertencia.
- Los valores agronómicos de la demo son supuestos sin validar, no una
  prescripción firmada por un agrónomo.
- **El modelo actual no fue más preciso que el método sencillo usado como
  comparación.** Se mantiene porque permite mostrar la incertidumbre y sugerir
  dónde medir después, no porque haya demostrado mayor precisión.
- Los riesgos modelados son **helada, sequía y gota tardía**, además del contexto
  de El Niño o La Niña. **No modelamos incendios**: la señal de sequía indica
  condiciones propicias, y eso es todo lo que podemos afirmar.
- No estimamos ahorro en pesos, no predecimos rendimiento y no puntuamos
  agricultores.

Preferimos un sistema que sepa lo que no sabe.

## Uso responsable, AI Act y escalabilidad

El [AI Act de la Unión Europea](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)
establece un enfoque basado en el riesgo y, para determinados sistemas de alto
riesgo, exige supervisión humana efectiva. IOmido adopta esos principios como
guía de diseño. Esto **no equivale a afirmar una certificación o clasificación
legal** del proyecto.

- **Una persona decide.** La IA prepara el mapa y recomienda una receta, pero el
  técnico o agrónomo puede aceptarla, modificarla, rechazarla o remitirla. Nada
  se presenta como aplicado sin esa decisión.
- **La responsabilidad se diseña desde el inicio.** El sistema muestra sus dudas,
  explica de dónde sale cada recomendación, limita a Claude a redactar evidencia
  ya calculada y conserva un historial que no se puede reescribir.
- **Escalar no significa quitar a la persona.** Un sensor compartido y el mismo
  motor pueden atender muchas fincas. La validación ocurre por lote, en el punto
  importante: antes de llevar la recomendación al campo.
- **Cada región conserva control local.** Antes de incorporar un cultivo o una
  zona nueva, deben validarse los parámetros con especialistas locales, definirse
  responsables y vigilar si la calidad del sistema cambia con el tiempo.

Así, crecer significa producir más recomendaciones trazables y revisables, no
automatizar más decisiones sin control.

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
4. Consultar clima en vivo en vez de los datos de respaldo incluidos en la demo.
5. Cargar el inventario real de formulaciones de cada centro.
6. Hacer pruebas con más lotes y temporadas, y volver a comparar el modelo con
   métodos más sencillos.

Ninguno de esos pendientes autoriza presentar el perfil de demo como una
prescripción validada. Por eso, el sistema marca toda propuesta como pendiente
de validación técnica.
