# IOmido backend 2.0

Backend FastAPI local-first. Requiere Python 3.11 o superior.

Arquitectura, modelos y uso de IA en [`../TECNICO.md`](../TECNICO.md); catálogo
de endpoints en [`../docs/API.md`](../docs/API.md).

## Instalar y arrancar

Desde la raíz del repositorio:

```powershell
python -m pip install -r backend/requirements.txt
Set-Location backend
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

No se necesita `.env` para la demo. Por defecto no se consulta Internet y los
fixtures climáticos se declaran degradados.

## Tests

```powershell
python -m pytest backend/tests -q
```

Resultado de referencia: `58 passed`. Todos los tests usan SQLite temporal,
fixtures o clientes falsos. Ninguno habilita APIs externas o un LLM.

## Demo sin red

```powershell
python backend/scripts/demo_backend.py
```

El script crea una base temporal y ejecuta el pipeline entero. Para regenerar los
mocks contractuales desde el mismo motor:

```powershell
python tools/build_mock.py
```

## Variables principales

Ver `.env.example`. Las de mayor impacto son:

- `DB_PATH`;
- `EXTERNAL_SOURCES_ENABLED=false`;
- `WRITE_API_KEY`;
- `MAX_IMPORT_BYTES`;
- `CORS_ORIGINS`;
- `AI_EXPLAINER_ENABLED=true`;
- `AI_MODEL=claude-sonnet-5`;
- `AI_TOTAL_BUDGET_USD=2.00`.

## Importar el Excel

Con el servidor activo:

```powershell
curl.exe -X POST "http://localhost:8000/v1/readings/import?plot_id=nar-001" `
  -F "file=@../data/data_ejemplo.csv.xlsx"
curl.exe -X POST "http://localhost:8000/v1/plots/nar-001/recompute"
curl.exe "http://localhost:8000/v1/plots/nar-001/package"
```

El primer response de importación debe mostrar N 2 %, P 1 %, K 1 %, con
`conversion_applied=false`.

## Base de datos

El archivo local por defecto es `backend/iomido.sqlite3` y está ignorado por Git.
Las migraciones viven en `app/repositories/migrations/`. No edite `audit_log`:
triggers de SQLite rechazan cambios y borrados.

## Limitación de uso

El perfil demo está `demo_unvalidated`. Los planes son candidatos pendientes y
requieren un técnico; no son una receta lista para aplicar.
