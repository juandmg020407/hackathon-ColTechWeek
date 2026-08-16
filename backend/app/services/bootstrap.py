"""Load versioned demo configuration into SQLite."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from ..agronomy import load_formulation_catalog, load_profiles
from ..domain.models import Plot, Producer
from ..repositories import SQLiteRepository
from .importer import ImportValidationError, ReadingImporter

logger = logging.getLogger("iomido")


def bootstrap_repository(repository: SQLiteRepository, config_root: str | Path) -> str:
    """Deja la configuración versionada en SQLite y devuelve el id del lote demo."""

    root = Path(config_root)
    repository.migrate()
    demo = yaml.safe_load((root / "demo" / "center-pasto-v1.yaml").read_text(encoding="utf-8"))
    repository.upsert_center(demo["center"])
    repository.upsert_producer(Producer.model_validate(demo["producer"]))
    for profile in load_profiles(root / "agronomy"):
        repository.upsert_crop_profile(profile)
    plot = Plot.model_validate(demo["plot"])
    repository.upsert_plot(plot)
    for catalog in sorted((root / "formulations").glob("*.yaml")):
        for formulation in load_formulation_catalog(catalog):
            existing = repository.get_formulation(formulation.center_id, formulation.id)
            if existing != formulation:
                repository.upsert_formulation(formulation)
    return plot.id


def seed_demo_readings(
    repository: SQLiteRepository,
    importer: ReadingImporter,
    plot_id: str,
    excel_path: Path,
) -> bool:
    """Carga el Excel de demostración solo si el lote todavía no tiene lecturas.

    En serverless la base vive en /tmp y se pierde entre arranques en frío, así
    que sin esto el lote demo queda vacío, el package falla y la aplicación
    desplegada acaba mostrando el mock en vez del backend. Se comprueba que
    esté vacío para no releer el archivo en cada arranque: la importación ya es
    idempotente, pero leer y parsear el Excel no es gratis.
    """

    plot = repository.get_plot(plot_id)
    if plot is None:
        logger.warning("[bootstrap] el lote demo %s no existe; no se siembran lecturas", plot_id)
        return False
    if repository.count_readings(plot_id):
        return False
    if not excel_path.is_file():
        logger.warning("[bootstrap] no se encontró el Excel de demostración en %s", excel_path)
        return False
    try:
        result = importer.import_path(plot=plot, path=excel_path)
    except ImportValidationError as error:
        logger.warning("[bootstrap] no se pudo importar el Excel de demostración: %s", error)
        return False
    logger.info(
        "demo_readings_seeded",
        extra={"source": str(excel_path), "inference_ms": None},
    )
    return bool(result["rows_created"])


async def warm_demo_package(engine, repository: SQLiteRepository, plot_id: str) -> bool:
    """Calcula el primer package si el lote tiene lecturas y ningún cálculo.

    El frontend pide tablero y package en paralelo. Sin esto, en un arranque en
    frío el tablero puede resolverse antes que el cálculo y la portada abre
    diciendo que no hay ningún lote calculado.
    """

    if repository.latest_package(plot_id) is not None:
        return False
    if not repository.count_readings(plot_id):
        return False
    try:
        await engine.recompute(plot_id)
    except Exception as error:  # noqa: BLE001 - arrancar sin package es válido
        logger.warning("[bootstrap] no se pudo precalcular el lote demo: %s", error)
        return False
    logger.info("demo_package_warmed")
    return True
