"""Versioned YAML loaders validated by Pydantic domain models."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..domain.models import CropProfile, Formulation


def _yaml(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} debe contener un objeto YAML")
    return payload


def load_profile(path: str | Path) -> CropProfile:
    return CropProfile.model_validate(_yaml(path))


def load_profiles(directory: str | Path) -> list[CropProfile]:
    return [load_profile(path) for path in sorted(Path(directory).glob("*.yaml"))]


def load_formulation_catalog(path: str | Path) -> list[Formulation]:
    payload = _yaml(path)
    center_id = payload.get("center_id")
    raw = payload.get("formulations")
    if not isinstance(raw, list) or not raw:
        raise ValueError("el catálogo debe traer una lista de formulaciones no vacía")
    formulations = [Formulation.model_validate(item) for item in raw]
    if any(formulation.center_id != center_id for formulation in formulations):
        raise ValueError("toda formulación debe pertenecer al center_id del catálogo")
    return formulations
