# Estado backend IOmido v0.2

## Terminado en esta entrega

- [x] Convención canónica N/P/K elemental en porcentaje.
- [x] Primera fila del Excel preservada como `2,1,1` porcentual.
- [x] Rechazo de bases incompatibles y adaptador explícito de óxidos.
- [x] Perfil agronómico YAML versionado y `demo_unvalidated`.
- [x] Catálogo por centro con `30-30-40`, sin marcas ni precios.
- [x] SQLite para centros, lotes, lecturas, perfiles, formulaciones, modelos,
  snapshots, propuestas, decisiones, auditoría y caché.
- [x] Claves foráneas, índices, transacciones, idempotencia y UTC.
- [x] Auditoría append-only mediante triggers.
- [x] GP Matern por nutriente como núcleo real del package.
- [x] Media, desviación, intervalos, umbral dinámico y hash de entrada.
- [x] Benchmark leave-one-out GP contra IDW.
- [x] Calidad geométrica, MAD e Isolation Forest condicionado por tamaño.
- [x] Zonas KMeans normalizadas y reproducibles.
- [x] Siguiente punto por incertidumbre, distancia y polígono.
- [x] Años análogos con NearestNeighbors.
- [x] Riesgos climáticos explicables y fusión ENSO.
- [x] Política común de timeout, caché, retries, backoff y circuito.
- [x] Modo offline/degradado sin caída del endpoint.
- [x] Optimizador entero exacto, lexicográfico y sin objetivo monetario.
- [x] Propuestas pendientes, explicación y decisión humana.
- [x] `/v1/agent/ask` local, determinista y anclado a evidencia.
- [x] Productores, consentimiento y dashboard persistido del centro.
- [x] Logs JSON, request ID, errores consistentes, CORS y API key opcional.
- [x] OpenAPI v2 y script de demo sin Internet.
- [x] 42 pruebas unitarias, ML, contrato e integración offline.

## Resultado ML que debe conservarse

- Observaciones del modelo: 18 dentro del lote, 1 fuera.
- RMSE medio GP: `4.675924` puntos porcentuales.
- RMSE medio IDW: `4.619368` puntos porcentuales.
- Conclusión: no afirmar que GP supera a IDW con este conjunto.

## Pendiente fuera del alcance de implementación de backend

- [ ] Calibrar el sensor contra muestras de laboratorio.
- [ ] Medir densidad aparente y validar profundidad real por protocolo.
- [ ] Validar requerimientos, disponibilidad y máximos con agrónomo local.
- [ ] Sustituir fixtures climáticos por consulta actual antes de uso de campo.
- [ ] Validar inventario real de formulaciones en cada centro.
- [ ] Continuar la adaptación visual del frontend al contrato v2 en una tarea
  posterior; esta entrega no modifica su interfaz.
- [ ] Ejecutar un piloto y reevaluar GP contra IDW con más lotes y temporadas.

Ningún pendiente autoriza presentar el perfil demo como prescripción validada.
