"""Application container and write authorization dependency."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from ..agronomy import AgronomicCalculator
from ..config import Settings
from ..governance.service import GovernanceService
from ..ml.spatial import SoilSpatialEngine
from ..optimization import IntegerFormulationOptimizer
from ..repositories import SQLiteRepository
from ..services.engine import SoilIntelligenceEngine
from ..services.agent import GroundedAgent
from ..services.importer import ReadingImporter
from ..sources.climate import ClimateFusion


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
        agent=GroundedAgent(repository),
    )


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def authorize_write(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    expected = get_container(request).settings.write_api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing write API key")
