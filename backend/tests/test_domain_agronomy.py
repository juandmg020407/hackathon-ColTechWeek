from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.agronomy import (
    AgronomicCalculator,
    load_formulation_catalog,
    load_profile,
    oxide_grade_to_elemental,
)
from app.agronomy.conversions import require_elemental_basis
from app.domain.errors import IncompatibleNPKBasis
from app.domain.models import Formulation, NPKPercent
from app.config import BACKEND_ROOT


def test_sensor_percentage_is_not_relabelled_or_converted():
    reading = NPKPercent(N=2, P=1, K=1)
    assert reading.as_dict() == {"N": 2.0, "P": 1.0, "K": 1.0}
    assert reading.basis == "elemental_mass_pct"


def test_grade_30_30_40_parses_as_elemental_percentages():
    formulations = load_formulation_catalog(
        BACKEND_ROOT / "config" / "formulations" / "center-pasto-demo-v1.yaml"
    )
    grade = next(item for item in formulations if item.label == "30-30-40")
    assert grade.npk_pct.as_dict() == {"N": 30.0, "P": 30.0, "K": 40.0}
    assert grade.basis == "elemental_mass_pct"


@pytest.mark.parametrize(
    "values",
    [
        {"N": -1, "P": 1, "K": 1},
        {"N": 101, "P": 0, "K": 0},
        {"N": 60, "P": 30, "K": 20},
    ],
)
def test_invalid_percentages_are_rejected(values):
    with pytest.raises(ValidationError):
        NPKPercent(**values)


def test_formulation_label_must_match_composition():
    with pytest.raises(ValidationError):
        Formulation(
            id="bad-formulation",
            center_id="center-pasto-demo",
            label="30-30-40",
            npk_pct=NPKPercent(N=20, P=20, K=20),
            bag_weight_kg=50,
            valid_from=date.today(),
            source="test",
        )


def test_incompatible_basis_requires_explicit_adapter():
    with pytest.raises(IncompatibleNPKBasis):
        require_elemental_basis("fertilizer_oxide_mass_pct")
    converted = oxide_grade_to_elemental(
        N_pct=10,
        P2O5_pct=10,
        K2O_pct=10,
        basis="fertilizer_oxide_mass_pct",
    )
    assert converted.N == 10
    assert converted.P == pytest.approx(4.364)
    assert converted.K == pytest.approx(8.301)


def test_configurable_profile_drives_explicit_soil_mass_balance():
    profile = load_profile(
        BACKEND_ROOT / "config" / "agronomy" / "potato-pasto-demo-v1.yaml"
    )
    result = AgronomicCalculator().assess(
        NPKPercent(N=2, P=1, K=1), profile, zone_area_ha=0.5
    )
    assert profile.validation_status == "demo_unvalidated"
    assert result["sampling_layer"]["depth"] == {"value": 20.0, "unit": "cm"}
    assert result["calculated_deficit"]["N"] == 144
    assert result["validation_status"] == "requires_technical_validation"
    assert "not subtracted" in result["warning"]
