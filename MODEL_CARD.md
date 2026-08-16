# Model card — IOmido Soil Intelligence Engine 2.0.0

Contexto del producto en [README.md](README.md); arquitectura y detalle de cada
modelo en [TECNICO.md](TECNICO.md).

## Propósito

Interpolar mediciones georreferenciadas de N, P y K elementales en porcentaje,
cuantificar incertidumbre, formar zonas de manejo y sugerir el siguiente punto de
muestreo. Es apoyo a decisión para un técnico, no diagnóstico de laboratorio ni
prescripción automática.

## Datos evaluados

- Archivo: `data/data_ejemplo.csv.xlsx`.
- Ubicación declarada: lote demo, Pasto, Nariño.
- 19 filas recibidas.
- 18 filas dentro del polígono usadas por el modelo.
- 1 fila conservada en persistencia pero excluida por geometría.
- Variables: latitud, longitud, N %, P %, K %.
- No existe calibración sensor-laboratorio disponible.

## Modelos

- Tres `GaussianProcessRegressor`, uno por nutriente.
- Kernel: `ConstantKernel × Matern(nu=1.5) + WhiteKernel`.
- Coordenadas normalizadas; semilla 42.
- Línea base: interpolación IDW, potencia 2.
- Validación: leave-one-out espacial.
- Zonas: `StandardScaler + KMeans`, semilla 42.
- Años análogos: `StandardScaler + NearestNeighbors`.

## Métricas reproducidas

Unidad de error: puntos porcentuales de masa.

| Nutriente | GP MAE | GP RMSE | Cobertura GP 95 % | IDW MAE | IDW RMSE |
|---|---:|---:|---:|---:|---:|
| N | 5.515783 | 7.455675 | 0.833333 | 5.629854 | 7.349048 |
| P | 2.074505 | 2.692089 | 0.833333 | 2.244697 | 2.721642 |
| K | 2.868187 | 3.880008 | 0.833333 | 3.129466 | 3.787414 |

RMSE medio GP: `4.675924`. RMSE medio IDW: `4.619368`.

**Conclusión:** GP no demuestra menor RMSE medio que IDW en este conjunto. El
sistema lo reporta como `gp_better_than_idw=false` y no hace una afirmación de
superioridad. El valor adicional de GP aquí es la incertidumbre predictiva y la
selección activa; ambas también necesitan validación con más datos.

## Incertidumbre

Cada celda recibe media, desviación e intervalo del 95 %. El umbral dinámico es
el percentil 75 de incertidumbre combinada dentro del polígono. Con una sola
medición se usa un fallback constante explícito. La cobertura observada de 0.833
está por debajo de 0.95 y no debe interpretarse como calibración perfecta.

## Calidad y anomalías

- Fuera del polígono: no entra al ajuste espacial.
- Mediana/MAD: disponible desde tres observaciones.
- Isolation Forest: solo desde doce observaciones.
- Una lectura sospechosa no se elimina automáticamente.
- Se almacena método, score y motivo.

## Usos permitidos

- visualizar heterogeneidad probable;
- priorizar nuevas mediciones;
- comparar zonas para revisión técnica;
- explicar incertidumbre y procedencia;
- evaluar el modelo contra una línea base.

## Usos prohibidos

- sustituir análisis de laboratorio;
- afirmar que el sensor está calibrado;
- prescribir aplicación sin validación técnica;
- transferir el perfil demo a otro cultivo, etapa o región;
- entrenar o presentar clasificadores con etiquetas sintéticas;
- afirmar que GP supera a IDW con las métricas actuales;
- presentar los riesgos como detección de incendios: se modelan helada, sequía y
  gota tardía, más el contexto ENSO, y nada más.

## Riesgos

- muestra muy pequeña y de un solo lote;
- correlación o señal compartida entre nutrientes del sensor;
- polígono de demo aproximado;
- supuestos agronómicos no validados;
- resolución climática insuficiente para microclimas de montaña;
- fixtures climáticos envejecidos en modo offline;
- KMeans fuerza separación aunque la estructura agronómica pueda ser continua.

## Supervisión humana

Cada plan se guarda como propuesta `pending`, `applied=false` y
`requires_technical_validation`. Las decisiones y modificaciones se registran en
auditoría append-only. Las respuestas cuantitativas del agente parten de rutas
deterministas; las preguntas abiertas generadas no pueden emitir cifras y el
modelo nunca recalcula dosis.

## Pendiente antes de un uso de campo

1. Calibrar el sensor contra muestras de laboratorio.
2. Medir la densidad aparente real del lote y validar la profundidad de muestreo
   contra el protocolo usado.
3. Validar requerimiento por etapa, factor de disponibilidad y máximos con un
   ingeniero agrónomo local, y firmar el perfil.
4. Sustituir los fixtures climáticos por consulta en vivo.
5. Confirmar el inventario real de formulaciones de cada centro.
6. Ejecutar un piloto y reevaluar GP contra IDW con más lotes y más temporadas.

Ninguno de estos pendientes autoriza presentar el perfil de demo como una
prescripción validada.

## Reproducibilidad

```powershell
python -m pytest backend/tests/test_ml.py -q
python backend/scripts/demo_backend.py
```

Cada model run registra versión, parámetros, observaciones, métricas, tiempo,
limitaciones y SHA-256 del conjunto de entrada.
