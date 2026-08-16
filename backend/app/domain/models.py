"""Version 2 domain entities.

The core convention is elemental N, P and K. Soil observations are mass
percentages of the sampled soil and formulations are mass percentages of the
bag. They deliberately share a unit label but are never subtracted directly.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ElementalBasis = Literal["elemental_mass_pct"]
ValidationStatus = Literal[
    "validated",
    "demo_unvalidated",
    "requires_technical_validation",
]


class Producer(BaseModel):
    """Privacy-conscious producer record owned by a collection center."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    center_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=150)
    municipality: str = Field(min_length=1, max_length=150)
    data_origin: Literal["demonstration", "pilot", "operational"] = "demonstration"
    consent_status: Literal["demonstration", "granted", "withdrawn"] = "demonstration"
    consent_updated_at: datetime | None = None
    created_at: datetime | None = None

    @model_validator(mode="after")
    def validate_consent(self) -> "Producer":
        if self.consent_status == "granted" and self.consent_updated_at is None:
            raise ValueError("granted consent requires consent_updated_at")
        if self.data_origin == "demonstration" and self.consent_status != "demonstration":
            raise ValueError("demonstration records must use demonstration consent status")
        if self.data_origin != "demonstration" and self.consent_status == "demonstration":
            raise ValueError("pilot and operational records require a real consent status")
        return self


class NPKPercent(BaseModel):
    """Elemental NPK concentration in mass percent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    N: float = Field(ge=0, le=100)
    P: float = Field(ge=0, le=100)
    K: float = Field(ge=0, le=100)
    basis: ElementalBasis = "elemental_mass_pct"

    @model_validator(mode="after")
    def plausible_total(self) -> "NPKPercent":
        if self.N + self.P + self.K > 100 + 1e-9:
            raise ValueError("N + P + K cannot exceed 100 mass percent")
        return self

    def as_dict(self) -> dict[str, float]:
        return {"N": self.N, "P": self.P, "K": self.K}


class NPKAmount(BaseModel):
    """Elemental nutrient mass, normally expressed per hectare."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    N: float = Field(ge=0)
    P: float = Field(ge=0)
    K: float = Field(ge=0)
    unit: Literal["kg/ha", "kg"] = "kg/ha"
    basis: Literal["elemental"] = "elemental"

    def as_dict(self) -> dict[str, float]:
        return {"N": self.N, "P": self.P, "K": self.K}


class ParameterSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter: str = Field(min_length=1, max_length=100)
    citation: str = Field(min_length=1, max_length=500)
    url: str | None = None
    note: str | None = Field(default=None, max_length=500)


class CropProfile(BaseModel):
    """Explicit, versioned assumptions used by the agronomic layer."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    crop: str = Field(min_length=1, max_length=100)
    variety: str | None = Field(default=None, max_length=100)
    stage: str = Field(min_length=1, max_length=100)
    scope: str = Field(min_length=1, max_length=200)
    requirement_kg_ha: NPKAmount
    sampling_depth_cm: float = Field(gt=0, le=200)
    bulk_density_g_cm3: float = Field(gt=0, le=3)
    availability_fraction: dict[Literal["N", "P", "K"], float]
    maximum_application_kg_ha: NPKAmount
    maximum_bags_per_zone: int = Field(gt=0, le=500)
    target_yield_t_ha: float | None = Field(default=None, gt=0)
    sources: list[ParameterSource] = Field(min_length=1)
    version: str = Field(min_length=1, max_length=50)
    validation_status: ValidationStatus
    validated_by_role: str | None = Field(default=None, max_length=100)
    effective_from: date

    @model_validator(mode="after")
    def validate_assumptions(self) -> "CropProfile":
        if set(self.availability_fraction) != {"N", "P", "K"}:
            raise ValueError("availability_fraction must define N, P and K")
        if any(not 0 <= value <= 1 for value in self.availability_fraction.values()):
            raise ValueError("availability fractions must be between 0 and 1")
        cited = {source.parameter for source in self.sources}
        required = {
            "requirement_kg_ha",
            "sampling_depth_cm",
            "bulk_density_g_cm3",
            "availability_fraction",
            "maximum_application_kg_ha",
        }
        if not required.issubset(cited):
            missing = ", ".join(sorted(required - cited))
            raise ValueError(f"missing sources for: {missing}")
        if self.validation_status == "validated" and not self.validated_by_role:
            raise ValueError("validated profiles require validated_by_role")
        return self


_GRADE = re.compile(r"^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$")


class Formulation(BaseModel):
    """Brand-independent formulation available at a collection center."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    center_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    label: str = Field(min_length=5, max_length=50)
    npk_pct: NPKPercent
    bag_weight_kg: float = Field(gt=0, le=1000)
    available: bool = True
    valid_from: date
    source: str = Field(min_length=1, max_length=500)
    basis: ElementalBasis = "elemental_mass_pct"

    @model_validator(mode="after")
    def label_matches_composition(self) -> "Formulation":
        match = _GRADE.fullmatch(self.label.strip())
        if not match:
            raise ValueError("label must use the N-P-K grade format, for example 30-30-40")
        grade = tuple(float(value) for value in match.groups())
        actual = (self.npk_pct.N, self.npk_pct.P, self.npk_pct.K)
        if any(abs(left - right) > 1e-6 for left, right in zip(grade, actual)):
            raise ValueError("label does not match npk_pct")
        if self.npk_pct.basis != self.basis:
            raise ValueError("formulation and npk_pct basis must match")
        return self


class Plot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    center_id: str
    producer_id: str | None = None
    crop_profile_id: str
    name: str = Field(min_length=1, max_length=150)
    municipality: str = Field(min_length=1, max_length=150)
    boundary: list[tuple[float, float]] = Field(min_length=3)
    created_at: datetime | None = None


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    plot_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    npk_pct: NPKPercent
    measured_at: datetime
    client_id: str = Field(min_length=1, max_length=200)
    valid_for_model: bool = True
    suspicious: bool = False
    anomaly_method: str | None = None
    anomaly_score: float | None = None
    anomaly_reason: str | None = None
