# IOmido

IOmido es un backend local-first de apoyo a decisiones para centros de acopio,
técnicos y redes de pequeños productores. Esta rama entrega el núcleo `v0.2`
antes de continuar el frontend: porcentajes NPK elementales, inferencia espacial
para pocos datos, incertidumbre, clima, optimización entera y decisión humana.

La demostración oficial usa papa, un lote en Pasto y 19 mediciones del archivo
`data/data_ejemplo.csv.xlsx`. La primera fila se conserva exactamente como:

```text
N 2 %, P 1 %, K 1 %
```

Una formulación `30-30-40` significa 30 % N, 30 % P y 40 % K de la masa del
bulto, bajo convención elemental. El backend nunca resta ese grado al porcentaje
medido en suelo. Primero aplica el perfil agronómico explícito y versionado.

## Estado de la entrega

- Contrato API `2.0` y OpenAPI comprobable.
- SQLite como fuente de verdad para configuración, lecturas, modelos, packages,
  propuestas, decisiones, auditoría y caché externo.
- Un GP Matern por N, P y K, con media, desviación, intervalo del 95 % y umbral
  dinámico de incertidumbre.
- Benchmark espacial leave-one-out contra IDW.
- KMeans reproducible para zonas y selección activa de la siguiente medición.
- Open-Meteo, NASA POWER y contexto ENSO con caché, timeout, reintentos,
  circuit breaker y modo degradado.
- Perfil de papa/Pasto en YAML marcado `demo_unvalidated`.
- Catálogo elemental por centro sin marcas ni precios.
- Búsqueda entera exacta con objetivo lexicográfico.
- Propuestas pendientes y auditoría append-only; nada se aplica sin decisión.
- Agente conversacional determinista, anclado al último package.
- 26 pruebas offline; ninguna llama APIs pagadas.

## Arranque

```powershell
python -m pip install -r backend/requirements.txt
Set-Location backend
python -m uvicorn app.main:app --reload --port 8000
```

Documentación interactiva: <http://localhost:8000/docs>.

## Verificación

Desde la raíz:

```powershell
python -m pytest backend/tests -q
```

Demo completa sin Internet:

```powershell
python backend/scripts/demo_backend.py
```

La demo ejecuta health, importación, package, predicciones, incertidumbre,
siguiente punto, riesgos, formulaciones, explicación, decisión y auditoría.

## Evidencia ML actual

Sobre 18 observaciones dentro del polígono (una de las 19 queda fuera), el
benchmark LOO da RMSE medio GP `4.675924` e IDW `4.619368`, en puntos
porcentuales. Por tanto IOmido **no afirma que GP sea más preciso** en este
dataset. GP sigue siendo el núcleo del package porque aporta una distribución
predictiva y aprendizaje activo, pero requiere más datos y calibración de
laboratorio. Ver [MODEL_CARD.md](MODEL_CARD.md).

## Documentación

- [BACKEND.md](BACKEND.md): arquitectura y contrato.
- [backend/README.md](backend/README.md): operación local.
- [backend/openapi-v2.json](backend/openapi-v2.json): snapshot OpenAPI.
- [MODEL_CARD.md](MODEL_CARD.md): métricas, límites y gobernanza del modelo.
- [TAREAS.md](TAREAS.md): alcance terminado y validaciones externas pendientes.

## Límite científico

El perfil `potato-pasto-demo-v1` contiene supuestos de demostración, no una
prescripción validada. Todas sus propuestas devuelven
`requires_technical_validation`. Antes de uso de campo se necesitan análisis de
laboratorio, densidad aparente del lote, validación del protocolo de muestreo y
firma de un profesional agronómico local.
