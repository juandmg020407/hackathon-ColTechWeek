"""IOmido backend application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .api.dependencies import build_container
from .config import REPOSITORY_ROOT, Settings, settings as default_settings
from .observability import configure_logging, request_context_middleware
from .services.bootstrap import bootstrap_repository
from .services.contracts import utc_now


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or default_settings
    configure_logging(active_settings.log_level)
    container = build_container(active_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        bootstrap_repository(container.repository, active_settings.config_root)
        if active_settings.demo_auto_import:
            plot = container.repository.get_plot("nar-001")
            if plot is not None:
                container.importer.import_path(plot=plot, path=active_settings.demo_excel_path)
        yield

    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        description=(
            "Local-first soil and climate decision support. Elemental NPK percentages, "
            "small-data spatial ML, explicit uncertainty and mandatory human decisions."
        ),
        lifespan=lifespan,
    )
    app.state.container = container
    app.middleware("http")(request_context_middleware)
    app.add_middleware(BrotliMiddleware, quality=5, minimum_size=500)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return _error_response(request, error.status_code, "http_error", str(error.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return _error_response(
            request, 422, "validation_error", "request did not match the contract", error.errors()
        )

    @app.exception_handler(ValueError)
    async def domain_error(request: Request, error: ValueError):
        return _error_response(request, 400, "domain_error", str(error))

    app.include_router(router)

    # El frontend se sirve desde la misma app: una sola URL en el despliegue y
    # ningún CORS que configurar. Va montado después del router para que
    # /health y /v1 conserven precedencia sobre este catch-all.
    frontend_root = REPOSITORY_ROOT / "frontend"
    if frontend_root.is_dir():
        app.mount("/", StaticFiles(directory=frontend_root, html=True), name="frontend")

    return app


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details=None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unavailable")
    return JSONResponse(
        status_code=status_code,
        content={
            "contract_version": "2.0",
            "generated_at": utc_now(),
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details,
            },
        },
    )


app = create_app()
