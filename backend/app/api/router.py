"""Contract v2 endpoints."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from ..domain.models import Formulation, NPKPercent, Plot, Producer, Reading
from ..ml.geometry import point_in_polygon
from ..repositories.sqlite import stable_id
from ..services.contracts import contract_metadata
from .dependencies import AppContainer, authorize_write, get_container
from .schemas import (
    AgentAsk,
    BulkReadings,
    DecisionCreate,
    FormulationPayload,
    PackageResponse,
    PlotCreate,
    ProducerPayload,
    ReadingCreate,
)

router = APIRouter()
write_guard = [Depends(authorize_write)]


def _container(request: Request) -> AppContainer:
    return get_container(request)


def _response(
    data: dict | None = None,
    *,
    validation_status: str = "requires_technical_validation",
    warnings: list[str] | None = None,
    degraded: bool = False,
) -> dict:
    return contract_metadata(
        validation_status=validation_status,
        warnings=warnings,
        degraded=degraded,
    ) | (data or {})


@router.get("/health/live")
def live() -> dict:
    return _response(
        {"status": "live", "service": "iomido-backend"},
        validation_status="operational",
    )


@router.get("/health/ready")
def ready(request: Request) -> dict:
    container = _container(request)
    if not container.repository.ready():
        raise HTTPException(status_code=503, detail="SQLite is not ready")
    return _response(
        {
            "status": "ready",
            "database": "sqlite",
            "external_sources_enabled": container.settings.external_sources_enabled,
        },
        validation_status="operational",
    )


@router.get("/v1/governance")
def governance(request: Request) -> dict:
    container = _container(request)
    return _response({
        "governance": {
            "system_role": "decision_support",
            "human_decision_required": True,
            "proposals_default_status": "pending",
            "audit_mode": "append-only SQLite triggers",
            "llm_is_mathematical_core": False,
            "paid_calls_in_tests": False,
            "audit_counts": container.repository.audit_counts(),
        }
    })


@router.get("/v1/models")
def models(request: Request) -> dict:
    runs = _container(request).repository.list_model_runs()
    return contract_metadata(model_versions=model_versions_from_runs(runs)) | {"models": runs}


def model_versions_from_runs(runs: list[dict]) -> dict[str, str]:
    if not runs:
        return {}
    first = runs[0]
    return {"spatial": f"{first['model_name']}/{first['model_version']}"}


@router.get("/v1/models/{model_id}/metrics")
def model_metrics(model_id: str, request: Request) -> dict:
    run = _container(request).repository.get_model_run(model_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"model run {model_id} does not exist")
    return contract_metadata(
        model_versions={"spatial": f"{run['model_name']}/{run['model_version']}"},
        warnings=run["limitations"],
    ) | {"model_run_id": model_id, "metrics": run["metrics"], "limitations": run["limitations"]}


@router.get("/v1/centers")
def centers(request: Request) -> dict:
    return _response({"centers": _container(request).repository.list_centers()})


@router.get("/v1/centers/{center_id}")
def center(center_id: str, request: Request) -> dict:
    item = _container(request).repository.get_center(center_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"center {center_id} does not exist")
    return _response({"center": item}, validation_status=item["validation_status"])


@router.get("/v1/centers/{center_id}/dashboard")
def center_dashboard(center_id: str, request: Request) -> dict:
    container = _container(request)
    center_item = container.repository.get_center(center_id)
    if center_item is None:
        raise HTTPException(status_code=404, detail=f"center {center_id} does not exist")
    dashboard = container.network.dashboard(center_id)
    plot_rows = [
        plot
        for producer in dashboard["producers"]
        for plot in producer["plots"]
    ] + dashboard["unassigned_plots"]
    return contract_metadata(
        validation_status=center_item["validation_status"],
        model_versions={"network": container.network.version},
        degraded=any(plot["degraded"] for plot in plot_rows),
        warnings=(
            ["El dashboard incluye registros identificados como datos de demostración."]
            if dashboard["data_scope"]["contains_demonstration_data"] else []
        ),
    ) | {"dashboard": dashboard}


@router.get("/v1/centers/{center_id}/producers")
def producers(center_id: str, request: Request) -> dict:
    container = _container(request)
    center_item = container.repository.get_center(center_id)
    if center_item is None:
        raise HTTPException(status_code=404, detail=f"center {center_id} does not exist")
    items = [
        producer.model_dump(mode="json")
        for producer in container.repository.list_producers(center_id)
    ]
    return _response({"producers": items}, validation_status=center_item["validation_status"])


@router.post(
    "/v1/centers/{center_id}/producers",
    dependencies=write_guard,
    status_code=201,
)
def create_producer(center_id: str, payload: ProducerPayload, request: Request) -> dict:
    container = _container(request)
    if container.repository.get_center(center_id) is None:
        raise HTTPException(status_code=404, detail=f"center {center_id} does not exist")
    producer_id = payload.id or stable_id(
        "producer", f"{center_id}|{payload.display_name}|{payload.municipality}"
    )
    producer = Producer(
        id=producer_id,
        center_id=center_id,
        **payload.model_dump(exclude={"id"}),
    )
    container.repository.upsert_producer(producer, actor="api")
    return _response({"producer": producer.model_dump(mode="json")})


@router.get("/v1/producers/{producer_id}")
def producer(producer_id: str, request: Request) -> dict:
    item = _container(request).repository.get_producer(producer_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"producer {producer_id} does not exist")
    return _response({"producer": item.model_dump(mode="json")})


@router.put("/v1/producers/{producer_id}", dependencies=write_guard)
def update_producer(
    producer_id: str,
    payload: ProducerPayload,
    request: Request,
) -> dict:
    container = _container(request)
    current = container.repository.get_producer(producer_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"producer {producer_id} does not exist")
    if payload.id and payload.id != producer_id:
        raise HTTPException(status_code=409, detail="payload id does not match path id")
    updated = Producer(
        id=producer_id,
        center_id=current.center_id,
        **payload.model_dump(exclude={"id"}),
    )
    container.repository.upsert_producer(updated, actor="api")
    return _response({"producer": updated.model_dump(mode="json")})


@router.get("/v1/producers/{producer_id}/plots")
def producer_plots(producer_id: str, request: Request) -> dict:
    container = _container(request)
    if container.repository.get_producer(producer_id) is None:
        raise HTTPException(status_code=404, detail=f"producer {producer_id} does not exist")
    return _response({"plots": container.repository.list_plots(producer_id=producer_id)})


@router.get("/v1/centers/{center_id}/formulations")
def formulations(center_id: str, request: Request) -> dict:
    container = _container(request)
    if container.repository.get_center(center_id) is None:
        raise HTTPException(status_code=404, detail=f"center {center_id} does not exist")
    items = [item.model_dump(mode="json") for item in container.repository.list_formulations(center_id)]
    return _response({"formulations": items})


@router.post(
    "/v1/centers/{center_id}/formulations",
    dependencies=write_guard,
    status_code=201,
)
def create_formulation(center_id: str, payload: FormulationPayload, request: Request) -> dict:
    container = _container(request)
    if container.repository.get_center(center_id) is None:
        raise HTTPException(status_code=404, detail=f"center {center_id} does not exist")
    formulation_id = payload.id or stable_id("formulation", f"{center_id}|{payload.label}")
    formulation = Formulation(
        id=formulation_id,
        center_id=center_id,
        **payload.model_dump(exclude={"id"}),
    )
    container.repository.upsert_formulation(formulation, actor="api")
    return _response({"formulation": formulation.model_dump(mode="json")})


@router.put(
    "/v1/centers/{center_id}/formulations/{formulation_id}",
    dependencies=write_guard,
)
def update_formulation(
    center_id: str,
    formulation_id: str,
    payload: FormulationPayload,
    request: Request,
) -> dict:
    container = _container(request)
    if container.repository.get_formulation(center_id, formulation_id) is None:
        raise HTTPException(status_code=404, detail=f"formulation {formulation_id} does not exist")
    if payload.id and payload.id != formulation_id:
        raise HTTPException(status_code=409, detail="payload id does not match path id")
    formulation = Formulation(
        id=formulation_id,
        center_id=center_id,
        **payload.model_dump(exclude={"id"}),
    )
    container.repository.upsert_formulation(formulation, actor="api")
    return _response({"formulation": formulation.model_dump(mode="json")})


@router.get("/v1/crop-profiles")
def crop_profiles(request: Request) -> dict:
    return _response({"crop_profiles": _container(request).repository.list_crop_profiles()})


@router.get("/v1/crop-profiles/{profile_id}")
def crop_profile(profile_id: str, request: Request) -> dict:
    profile = _container(request).repository.get_crop_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"crop profile {profile_id} does not exist")
    return _response(
        {"crop_profile": profile.model_dump(mode="json")},
        validation_status=profile.validation_status,
    )


@router.get("/v1/plots")
def plots(
    request: Request,
    center_id: str | None = None,
    producer_id: str | None = None,
) -> dict:
    return _response({
        "plots": _container(request).repository.list_plots(
            center_id=center_id, producer_id=producer_id
        )
    })


@router.post("/v1/plots", dependencies=write_guard, status_code=201)
def create_plot(payload: PlotCreate, request: Request) -> dict:
    container = _container(request)
    if payload.producer_id:
        producer_item = container.repository.get_producer(payload.producer_id)
        if producer_item is None:
            raise HTTPException(
                status_code=409, detail=f"producer {payload.producer_id} does not exist"
            )
        if producer_item.center_id != payload.center_id:
            raise HTTPException(
                status_code=409, detail="producer and plot must belong to the same center"
            )
    plot = Plot.model_validate(payload.model_dump())
    try:
        container.repository.upsert_plot(plot)
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail=f"invalid center or crop profile: {error}") from error
    return _response({"plot": plot.model_dump(mode="json")})


@router.get("/v1/plots/{plot_id}")
def plot(plot_id: str, request: Request) -> dict:
    item = _container(request).repository.get_plot(plot_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"plot {plot_id} does not exist")
    return _response({"plot": item.model_dump(mode="json")})


@router.get("/v1/plots/{plot_id}/readings")
def plot_readings(plot_id: str, request: Request, valid_only: bool = False) -> dict:
    container = _container(request)
    if container.repository.get_plot(plot_id) is None:
        raise HTTPException(status_code=404, detail=f"plot {plot_id} does not exist")
    readings = [
        item.model_dump(mode="json")
        for item in container.repository.list_readings(plot_id, valid_only=valid_only)
    ]
    return _response({
        "plot_id": plot_id,
        "readings": readings,
        "count": len(readings),
        "valid_only": valid_only,
    })


@router.get("/v1/plots/{plot_id}/package", response_model=PackageResponse)
async def package(plot_id: str, request: Request, refresh: bool = False) -> dict:
    container = _container(request)
    if container.repository.get_plot(plot_id) is None:
        raise HTTPException(status_code=404, detail=f"plot {plot_id} does not exist")
    result = None if refresh else container.repository.latest_package(plot_id)
    if result is None:
        result = await container.engine.recompute(plot_id)
    return result


@router.post(
    "/v1/plots/{plot_id}/recompute",
    dependencies=write_guard,
    response_model=PackageResponse,
)
async def recompute(plot_id: str, request: Request) -> dict:
    return await _container(request).engine.recompute(plot_id)


@router.get("/v1/plots/{plot_id}/risk")
async def risk(plot_id: str, request: Request) -> dict:
    container = _container(request)
    result = container.repository.latest_package(plot_id)
    if result is None:
        result = await container.engine.recompute(plot_id)
    return contract_metadata(
        validation_status=result["validation_status"],
        sources=result["climate"]["sources"],
        model_versions={
            "analog_years": result["climate"]["seasonal_context"]["analog_model"]["version"]
        },
        generated_at=result["generated_at"],
        degraded=result["climate"]["degraded"],
        warnings=result["climate"]["warnings"],
    ) | {"plot_id": plot_id, "climate": result["climate"]}


def _reading(payload: ReadingCreate, plot: Plot) -> Reading:
    return Reading(
        id=stable_id("reading", payload.client_id),
        plot_id=payload.plot_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        npk_pct=payload.npk_pct,
        measured_at=payload.measured_at,
        client_id=payload.client_id,
        valid_for_model=point_in_polygon(payload.latitude, payload.longitude, plot.boundary),
    )


@router.post("/v1/readings", dependencies=write_guard, status_code=201)
def reading(payload: ReadingCreate, request: Request) -> dict:
    container = _container(request)
    plot_item = container.repository.get_plot(payload.plot_id)
    if plot_item is None:
        raise HTTPException(status_code=404, detail=f"plot {payload.plot_id} does not exist")
    stored, created = container.repository.create_reading(_reading(payload, plot_item))
    return _response({
        "reading": stored.model_dump(mode="json"),
        "created": created,
        "idempotent": not created,
        "recompute_required": created and stored.valid_for_model,
    })


@router.post("/v1/readings/bulk", dependencies=write_guard, status_code=201)
def readings_bulk(payload: BulkReadings, request: Request) -> dict:
    container = _container(request)
    plot_ids = {item.plot_id for item in payload.readings}
    if len(plot_ids) != 1:
        raise HTTPException(status_code=400, detail="all bulk readings must belong to one plot")
    plot_item = container.repository.get_plot(next(iter(plot_ids)))
    if plot_item is None:
        raise HTTPException(status_code=404, detail="plot does not exist")
    stored, created = container.repository.create_readings([
        _reading(item, plot_item) for item in payload.readings
    ])
    return _response({
        "readings": [item.model_dump(mode="json") for item in stored],
        "rows_received": len(stored),
        "rows_created": created,
        "rows_idempotent": len(stored) - created,
    })


@router.post("/v1/readings/import", dependencies=write_guard, status_code=201)
async def readings_import(
    request: Request,
    plot_id: str = Query(..., min_length=1),
    file: UploadFile = File(...),
) -> dict:
    container = _container(request)
    plot_item = container.repository.get_plot(plot_id)
    if plot_item is None:
        raise HTTPException(status_code=404, detail=f"plot {plot_id} does not exist")
    content = await file.read(container.settings.max_import_bytes + 1)
    result = container.importer.import_file(
        plot=plot_item,
        filename=file.filename or "",
        content=content,
    )
    return _response({"import": result})


@router.get("/v1/proposals/{proposal_id}")
def proposal(proposal_id: str, request: Request) -> dict:
    item = _container(request).repository.get_proposal(proposal_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id} does not exist")
    return _response({"proposal": item}, validation_status=item["validation_status"])


@router.get("/v1/proposals/{proposal_id}/why")
def proposal_why(proposal_id: str, request: Request) -> dict:
    explanation = _container(request).governance.explanation(proposal_id)
    if explanation is None:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id} does not exist")
    return _response({"proposal_id": proposal_id, "explanation": explanation})


@router.post("/v1/decisions", dependencies=write_guard, status_code=201)
def decision(payload: DecisionCreate, request: Request) -> dict:
    result = _container(request).governance.decide(
        proposal_id=payload.proposal_id,
        action=payload.action,
        actor_type=payload.actor.type,
        actor_id=payload.actor.id,
        modification=payload.modification,
        note=payload.note,
    )
    return _response({"decision": result}, validation_status="human_review_recorded")


@router.get("/v1/decisions/{decision_id}")
def get_decision(decision_id: str, request: Request) -> dict:
    item = _container(request).repository.get_decision(decision_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"decision {decision_id} does not exist")
    return _response({"decision": item}, validation_status="human_review_recorded")


@router.get("/v1/decisions/{identifier}/history")
def decision_history(identifier: str, request: Request) -> dict:
    history = _container(request).governance.history(identifier)
    if history is None:
        raise HTTPException(status_code=404, detail=f"history {identifier} does not exist")
    return _response({"history": history}, validation_status="human_review_recorded")


@router.get("/v1/audit")
def audit(
    request: Request,
    entity_type: str = Query(..., min_length=1),
    entity_id: str = Query(..., min_length=1),
) -> dict:
    events = _container(request).repository.audit_history(entity_type, entity_id)
    return _response({"entity_type": entity_type, "entity_id": entity_id, "events": events})


@router.post("/v1/agent/ask")
def ask_agent(payload: AgentAsk, request: Request) -> dict:
    container = _container(request)
    if container.repository.get_plot(payload.plot_id) is None:
        raise HTTPException(status_code=404, detail=f"plot {payload.plot_id} does not exist")
    result = container.agent.ask(payload.plot_id, payload.question)
    package = container.repository.latest_package(payload.plot_id)
    assert package is not None  # GroundedAgent refuses to answer without this evidence.
    return contract_metadata(
        validation_status=package["validation_status"],
        sources=package["sources"],
        model_versions=package["model_versions"]
        | {"agent": container.agent.version}
        | ({"explainer": result["explainer"]["explainer_version"]} if "explainer" in result else {}),
        generated_at=package["generated_at"],
        degraded=package["degraded"],
        warnings=package["warnings"],
    ) | {"agent": result}
