"""Application container and write authorization dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from ..agronomy import AgronomicCalculator
from ..config import Settings
from ..governance.service import GovernanceService
from ..ml.spatial import SoilSpatialEngine
from ..optimization import IntegerFormulationOptimizer
from ..repositories import SQLiteRepository
from ..services.anthropic_explainer import AnthropicEvidenceExplainer
from ..services.engine import SoilIntelligenceEngine
from ..services.explainer import AIBudgetPolicy, EvidenceExplainer
from ..services.agent import GroundedAgent
from ..services.importer import ReadingImporter
from ..sources.climate import ClimateFusion

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    settings: Settings
    repository: SQLiteRepository
    engine: SoilIntelligenceEngine
    importer: ReadingImporter
    governance: GovernanceService
    agent: GroundedAgent


def build_container(settings: Settings) -> AppContainer:
    repository = SQLiteRepository(settings.db_path)
    spatial = SoilSpatialEngine(
        cell_size_m=settings.grid_cell_size_m,
        seed=settings.random_seed,
    )
    climate = ClimateFusion(
        repository,
        settings.config_root / "climate" / "pasto-demo-v1.json",
        external_enabled=settings.external_sources_enabled,
        timeout_seconds=settings.external_timeout_seconds,
        max_retries=settings.external_max_retries,
    )
    engine = SoilIntelligenceEngine(
        repository,
        spatial,
        climate,
        AgronomicCalculator(),
        IntegerFormulationOptimizer(),
    )
    return AppContainer(
        settings=settings,
        repository=repository,
        engine=engine,
        importer=ReadingImporter(repository, settings.max_import_bytes),
        governance=GovernanceService(repository),
        agent=GroundedAgent(repository, build_explainer(settings)),
    )


def build_explainer(settings: Settings) -> EvidenceExplainer | None:
    """Explicador solo si esta habilitado y configurado.

    Cualquier fallo aqui (SDK ausente, credencial mala) deja el agente en su
    modo determinista en vez de impedir que el backend arranque.
    """
    if not settings.ai_explainer_enabled or settings.ai_model in ("", "disabled"):
        return None
    policy = AIBudgetPolicy(
        total_budget_usd=settings.ai_total_budget_usd,
        max_input_tokens=settings.ai_max_input_tokens,
        max_output_tokens=settings.ai_max_output_tokens,
        input_price_usd_per_million=settings.ai_input_price_usd_per_million,
        output_price_usd_per_million=settings.ai_output_price_usd_per_million,
    )
    try:
        return AnthropicEvidenceExplainer(
            model=settings.ai_model,
            policy=policy,
            api_key=settings.anthropic_api_key,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    except Exception as error:  # noqa: BLE001 - arrancar sin explicador es valido
        logger.warning("[explainer] deshabilitado, no se pudo construir: %s", error)
        return None


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def authorize_write(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    expected = get_container(request).settings.write_api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing write API key")
