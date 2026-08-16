"""Pydantic request and principal response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..domain.models import NPKPercent


class ContractResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    contract_version: Literal["2.0"] = "2.0"
    units: dict[str, str]
    npk_convention: dict[str, Any]
    validation_status: str
    sources: list[dict[str, Any]]
    model_versions: dict[str, str]
    generated_at: datetime
    degraded: bool
    warnings: list[str]


class PackageResponse(ContractResponse):
    id: str
    plot: dict[str, Any]
    measurements: dict[str, Any]
    spatial: dict[str, Any]
    model_run: dict[str, Any]
    climate: dict[str, Any]
    crop_profile: dict[str, Any]
    proposal: dict[str, Any]


class PlotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    center_id: str
    producer_id: str | None = None
    crop_profile_id: str
    name: str = Field(min_length=1, max_length=150)
    municipality: str = Field(min_length=1, max_length=150)
    boundary: list[tuple[float, float]] = Field(min_length=3)


class ProducerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=150)
    municipality: str = Field(min_length=1, max_length=150)
    data_origin: Literal["demonstration", "pilot", "operational"] = "operational"
    consent_status: Literal["demonstration", "granted", "withdrawn"] = "withdrawn"
    consent_updated_at: datetime | None = None


class ReadingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plot_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    npk_pct: NPKPercent
    measured_at: datetime
    client_id: str = Field(min_length=1, max_length=200)


class BulkReadings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    readings: list[ReadingCreate] = Field(min_length=1, max_length=500)


class FormulationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    label: str
    npk_pct: NPKPercent
    bag_weight_kg: float = Field(gt=0, le=1000)
    available: bool = True
    valid_from: date
    source: str = Field(min_length=1, max_length=500)
    basis: Literal["elemental_mass_pct"] = "elemental_mass_pct"


class Actor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["farmer", "technician", "system"]
    id: str = Field(min_length=1, max_length=100)


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    action: Literal["accept", "reject", "modify", "refer"]
    actor: Actor
    modification: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=1000)


class AgentAsk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plot_id: str
    question: str = Field(min_length=2, max_length=1000)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    contract_version: Literal["2.0"] = "2.0"
    generated_at: datetime
    error: ErrorDetail
