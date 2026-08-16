"""Environment-driven backend configuration."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = BACKEND_ROOT.parent


def _default_db_path() -> str:
    """SQLite junto al backend, salvo en serverless.

    En Vercel el sistema de archivos del bundle es de solo lectura y /tmp es
    lo unico escribible. La base se reconstruye desde backend/config en cada
    arranque en frio, asi que perderla entre invocaciones no pierde nada.
    """
    if os.getenv("VERCEL"):
        return "/tmp/iomido.sqlite3"
    return str(BACKEND_ROOT / "iomido.sqlite3")


class Settings(BaseSettings):
    # Se leen los dos .env por ruta absoluta y no el relativo al directorio de
    # trabajo: el backend se lanza tanto desde la raiz como desde backend/, y
    # con una ruta relativa la credencial aparecia o no segun desde donde se
    # arrancara. El de la raiz gana por ir de ultimo.
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", REPOSITORY_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "IOmido Soil Intelligence API"
    app_version: str = "2.0.0"
    db_path: str = Field(default_factory=_default_db_path)
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    write_api_key: str = ""
    demo_mode: bool = True
    demo_auto_import: bool = False
    external_sources_enabled: bool = False
    external_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    external_max_retries: int = Field(default=2, ge=0, le=5)
    max_import_bytes: int = Field(default=5_000_000, gt=0)
    grid_cell_size_m: float = Field(default=10.0, gt=0, le=100)
    random_seed: int = 42
    log_level: str = "INFO"

    ai_explainer_enabled: bool = True
    ai_total_budget_usd: float = Field(default=2.0, ge=0, le=4)
    ai_max_input_tokens: int = Field(default=8_000, gt=0)
    ai_max_output_tokens: int = Field(default=800, gt=0)
    ai_model: str = "claude-sonnet-5"
    # Se usan los precios estandar de Sonnet 5, no la tarifa promocional
    # temporal, para que el control siga siendo conservador despues de agosto.
    ai_input_price_usd_per_million: float = Field(default=3.0, ge=0)
    ai_output_price_usd_per_million: float = Field(default=15.0, ge=0)
    ai_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    # El SDK tambien lee ANTHROPIC_API_KEY del entorno; declararla aqui permite
    # tomarla del .env local sin exportarla a mano.
    anthropic_api_key: str = ""

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def config_root(self) -> Path:
        return BACKEND_ROOT / "config"

    @property
    def demo_excel_path(self) -> Path:
        return REPOSITORY_ROOT / "data" / "data_ejemplo.csv.xlsx"


settings = Settings()
