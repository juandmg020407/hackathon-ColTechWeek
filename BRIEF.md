# IOmido — brief de producto

## En una frase

IOmido permite que un centro de acopio lleve inteligencia de suelo y clima a su
red de pequeños productores usando un sensor compartido, inferencia espacial con
incertidumbre y recomendaciones NPK revisadas por un técnico.

## Encaje con Track 04

El reto pide ayudar a comunidades y pequeños productores a adaptarse al clima,
reducir desperdicio y tomar mejores decisiones. IOmido responde con un canal
operativo concreto:

- el centro de acopio financia y coordina;
- el técnico mueve el sensor entre fincas;
- el productor recibe la recomendación sin comprar software ni hardware;
- la red obtiene alertas tempranas y prioriza dónde intervenir.

El objetivo no es vender un mapa aislado. Es convertir la asistencia técnica de
una finca a la vez en una capacidad compartida por toda la red de proveedores.

## Problema específico

Los centros de acopio dependen de muchos lotes pequeños, pero normalmente no
tienen información comparable y oportuna sobre el suelo de cada proveedor. Una
medición puntual tampoco describe todo el lote y un pronóstico regional no explica
qué significa el clima para una recomendación concreta.

IOmido une tres escalas:

1. **Punto:** lectura NPK del sensor.
2. **Lote:** inferencia espacial e incertidumbre.
3. **Red:** priorización de fincas y riesgo de abastecimiento para el centro.

## Público objetivo

### Cliente inicial

Centros de acopio de papa que trabajan con redes de pequeños productores y cuentan
con una persona técnica o un aliado que pueda recorrer los lotes.

### Usuarios

- Gestor del centro: ve la red y decide qué lotes priorizar.
- Técnico: toma mediciones, revisa la incertidumbre y valida propuestas.
- Productor: recibe una recomendación comprensible y conserva la decisión final.

### Beneficio público

- acceso compartido a agricultura de precisión;
- menos aplicación innecesaria de nutrientes;
- decisiones anticipadas frente a clima adverso;
- mayor continuidad de abastecimiento local;
- construcción responsable de datos de suelo con consentimiento.

## Caso demostrativo

La demo usa un cultivo de papa de 0,69 ha en Pasto, Nariño:

- 19 mediciones georreferenciadas;
- N, P y K reportados como porcentaje;
- primera fila: N 2 %, P 1 %, K 1 %;
- una lectura fuera del lote, detectada por distancia;
- mapa de 5 m por celda;
- incertidumbre visible y siguiente punto sugerido.

La demo debe presentarse desde la perspectiva de un centro de acopio que abre el
lote de uno de sus productores proveedores.

## Propuesta de valor

### Para el centro

- una vista consistente de sus lotes proveedores;
- priorización de visitas y mediciones;
- riesgo de suelo y clima explicable;
- trazabilidad de propuestas y decisiones;
- un sensor que se comparte en vez de uno por finca.

### Para el productor

- recomendación gratuita y comprensible;
- formulación expresada como grado NPK, no como marca o nombre químico;
- explicación de por qué cambió la propuesta;
- derecho a aceptar, rechazar o pedir revisión;
- propiedad y control sobre sus mediciones.

## Semántica NPK

La fuente de demo no está en ppm. Cada lectura es el porcentaje reportado por el
sensor. La `v0.2` usará una convención única:

```text
suelo.N_pct
suelo.P_pct
suelo.K_pct
```

Las formulaciones también se describen únicamente por sus porcentajes:

```text
30-30-40 = 30 % N · 30 % P · 40 % K
```

No se expondrán marcas, nombres químicos, precios nacionales ni supuestos de ahorro.
El centro registra las formulaciones realmente disponibles en su zona.

## La lógica objetivo

1. Validar que cada lectura esté entre 0 % y 100 % y conservar el valor original.
2. Detectar errores geográficos y lecturas atípicas.
3. Interpolar N, P y K por separado con incertidumbre.
4. Consultar un perfil versionado de cultivo, variedad y etapa.
5. Calcular el faltante relativo por zona.
6. Aplicar ajustes climáticos explícitos.
7. Comparar el faltante con las formulaciones disponibles en el centro.
8. Resolver una mezcla entera que minimice faltantes, exceso y cantidad de bultos.
9. Crear una propuesta pendiente de decisión humana.

Ningún umbral agronómico, formulación o peso de bulto debe quedar escondido como
una constante de código. Cada parámetro debe tener versión, fuente y fecha.

## Por qué la IA es necesaria

- Hay muchos menos puntos que celdas en el lote.
- La interpolación debe devolver incertidumbre, no solo color.
- El sistema debe escoger dónde medir para aprender más con menos recorridos.
- Los riesgos deben cruzarse con el estado del lote y no mostrarse como alertas
  genéricas.
- Las correcciones del técnico pueden convertirse, con suficiente volumen, en
  etiquetas para mejorar el sistema.

La calibración contra laboratorio es un trabajo futuro. Hasta entonces IOmido no
afirma precisión de laboratorio ni recuperación de nutrientes ocultos.

## Demo de un minuto

1. **Problema:** un centro atiende muchos paperos con poca información por lote.
2. **Captura:** el técnico inserta el sensor y registra NPK más ubicación.
3. **IA:** el mapa completa las zonas no medidas, raya lo incierto y sugiere el
   siguiente punto.
4. **Clima:** una alerta modifica o aplaza la propuesta y explica el motivo.
5. **Acción:** el centro revisa una formulación como `30-30-40`; el productor
   decide.
6. **Escala:** un sensor, muchas fincas, una red más resiliente.

## Modelo de sostenibilidad

- Suscripción o servicio por centro de acopio.
- Sensor compartido dentro de la red de proveedores.
- Incorporación de nuevos lotes con el mismo flujo.
- Expansión desde papa en Pasto a otros municipios, centros y cultivos.

No se fija un precio comercial en la demo. La validación de disposición a pagar y
el costo operativo forman parte del piloto.

## IA responsable

1. El sistema propone; una persona decide.
2. La incertidumbre es visible.
3. Las fuentes y versiones acompañan cada salida.
4. Las recomendaciones fuera de límites pasan a revisión técnica.
5. Las decisiones se registran sin reescribir el pasado.
6. No se puntúan agricultores ni se evalúa crédito.
7. Los datos pertenecen al productor.
8. El uso agregado requiere consentimiento.
9. Las limitaciones se muestran junto a la recomendación.

## Estado actual y objetivo

| Área | `v0.1` actual | `v0.2` objetivo |
|---|---|---|
| Unidad de suelo | El código todavía etiqueta parte de la salida como ppm | Porcentaje NPK de extremo a extremo |
| Fertilizantes | Catálogo, nombres y precios heredados en código | Grados NPK configurados por el centro, sin precio |
| Optimización | Modelo continuo con redondeo posterior | Optimización entera y objetivo nutricional |
| Usuario principal | Tablero de un lote | Centro de acopio → red → lote |
| Persistencia | Excel, memoria y SQLite local | Base durable y multiusuario |
| Voz | Respuestas locales del navegador | Canal opcional para el productor |
| Riesgos | Helada, sequía, gota y estacional | Motores calibrados y activados según disponibilidad |

## Qué afirmamos y qué no

### Sí

- Existe un pipeline funcional sobre el lote de Pasto.
- El sistema interpola, muestra incertidumbre y recomienda una nueva medición.
- Los riesgos modifican la propuesta con una explicación.
- Hay un flujo local de propuestas y decisiones.

### Todavía no

- Precisión de laboratorio.
- Ahorro económico validado.
- Predicción de rendimiento.
- Despliegue multi-centro listo para producción.
- Validación agronómica o piloto en campo.

## Criterios de la hackathon

| Criterio | Evidencia que debe ver el jurado |
|---|---|
| Impacto público · 25 | El centro habilita asistencia de precisión para pequeños productores |
| Uso real de IA · 25 | GP, incertidumbre, muestreo activo, anomalías y riesgo contextual |
| Demo funcional · 20 | Flujo completo del lote de Pasto en el video de un minuto |
| Viabilidad y escala · 15 | Un sensor compartido y crecimiento centro por centro |
| Ejecución técnica y UX · 15 | Paquete ligero, modo degradado, explicación y decisión humana |
