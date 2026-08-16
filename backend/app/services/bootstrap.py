"""Load versioned demo configuration into SQLite."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..agronomy import load_formulation_catalog, load_profiles
from ..domain.models import Plot
from ..repositories import SQLiteRepository


def bootstrap_repository(repository: SQLiteRepository, config_root: str | Path) -> None:
    root = Path(config_root)
    repository.migrate()
    demo = yaml.safe_load((root / "demo" / "center-pasto-v1.yaml").read_text(encoding="utf-8"))
    repository.upsert_center(demo["center"])
    for profile in load_profiles(root / "agronomy"):
        repository.upsert_crop_profile(profile)
    repository.upsert_plot(Plot.model_validate(demo["plot"]))
    for catalog in sorted((root / "formulations").glob("*.yaml")):
        for formulation in load_formulation_catalog(catalog):
            existing = repository.get_formulation(formulation.center_id, formulation.id)
            if existing != formulation:
                repository.upsert_formulation(formulation)
