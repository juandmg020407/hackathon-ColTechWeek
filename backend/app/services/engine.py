"""The single package, proposal and explanation computation path."""

from __future__ import annotations

from typing import Any

from ..agronomy import AgronomicCalculator
from ..domain.models import NPKPercent
from ..ml.spatial import SoilSpatialEngine
from ..optimization import IntegerFormulationOptimizer
from ..repositories import SQLiteRepository
from ..repositories.sqlite import stable_id
from ..sources.climate import ClimateFusion
from .contracts import contract_metadata, utc_now


class EngineError(ValueError):
    pass


class SoilIntelligenceEngine:
    """Canonical orchestration from persisted readings to governed proposal."""

    def __init__(
        self,
        repository: SQLiteRepository,
        spatial: SoilSpatialEngine,
        climate: ClimateFusion,
        agronomy: AgronomicCalculator | None = None,
        optimizer: IntegerFormulationOptimizer | None = None,
    ):
        self.repository = repository
        self.spatial = spatial
        self.climate = climate
        self.agronomy = agronomy or AgronomicCalculator()
        self.optimizer = optimizer or IntegerFormulationOptimizer()

    async def recompute(self, plot_id: str) -> dict[str, Any]:
        plot = self.repository.get_plot(plot_id)
        if plot is None:
            raise EngineError(f"plot {plot_id} does not exist")
        readings = self.repository.list_readings(plot_id)
        if not readings:
            raise EngineError("plot has no readings; import or submit readings first")

        spatial_result = self.spatial.run(plot, readings)
        for annotation in spatial_result["quality"]:
            self.repository.update_reading_quality(
                annotation["reading_id"],
                valid_for_model=annotation["valid_for_model"],
                suspicious=annotation["suspicious"],
                method=annotation["method"],
                score=annotation["score"],
                reason=annotation["reason"],
            )
        generated_at = utc_now()
        model_run = spatial_result["model_run"] | {
            "id": stable_id(
                "model-run", f"{spatial_result['model_run']['input_hash']}|{generated_at}"
            ),
            "plot_id": plot.id,
            "created_at": generated_at,
        }
        self.repository.save_model_run(model_run)

        latitude = sum(point[0] for point in plot.boundary) / len(plot.boundary)
        longitude = sum(point[1] for point in plot.boundary) / len(plot.boundary)
        climate_context = await self.climate.evaluate(latitude, longitude)
        profile = self.repository.get_crop_profile(plot.crop_profile_id)
        if profile is None:
            raise EngineError(f"crop profile {plot.crop_profile_id} does not exist")
        formulations = self.repository.list_formulations(plot.center_id, active_only=True)
        if not formulations:
            raise EngineError(f"center {plot.center_id} has no active formulations")

        recommendations: list[dict[str, Any]] = []
        for zone in spatial_result["zones"]:
            centroid = zone["centroid_npk"]
            assessment = self.agronomy.assess(
                NPKPercent(N=centroid["N"], P=centroid["P"], K=centroid["K"]),
                profile,
                zone_area_ha=zone["area"]["value"],
                climate_risks=climate_context["risks"],
            )
            plan = self.optimizer.solve(
                formulations,
                target_kg_ha={
                    nutrient: assessment["optimization_target"][nutrient]
                    for nutrient in ("N", "P", "K")
                },
                zone_area_ha=zone["area"]["value"],
                maximum_application_kg_ha=profile.maximum_application_kg_ha.as_dict(),
                maximum_bags=profile.maximum_bags_per_zone,
                validation_status=assessment["validation_status"],
            )
            recommendations.append({
                "zone_id": zone["id"],
                "agronomic_assessment": assessment,
                "integer_plan": plan,
            })

        package_id = stable_id(
            "package", f"{plot.id}|{model_run['id']}|{generated_at}"
        )
        proposal_id = stable_id("proposal", f"{package_id}|pending")
        profile_sources = [
            {
                "name": source.citation,
                "url": source.url,
                "parameter": source.parameter,
                "degraded": profile.validation_status != "validated",
            }
            for source in profile.sources
        ]
        warnings = list(climate_context["warnings"]) + list(model_run["limitations"])
        warnings.append(
            "The crop profile is demo_unvalidated; no candidate plan is an applied prescription."
        )
        metadata = contract_metadata(
            validation_status="requires_technical_validation",
            sources=climate_context["sources"] + profile_sources,
            model_versions={
                "spatial": f"{model_run['model_name']}/{model_run['model_version']}",
                "analog_years": climate_context["seasonal_context"]["analog_model"]["version"],
                "agronomy": self.agronomy.version,
                "optimizer": self.optimizer.version,
            },
            degraded=climate_context["degraded"],
            warnings=warnings,
            generated_at=generated_at,
        )
        proposal = self._proposal(
            proposal_id,
            package_id,
            plot.id,
            recommendations,
            model_run,
            climate_context,
            generated_at,
        )
        quality_by_id = {
            annotation["reading_id"]: annotation for annotation in spatial_result["quality"]
        }
        package = metadata | {
            "id": package_id,
            "plot": {
                "id": plot.id,
                "center_id": plot.center_id,
                "crop_profile_id": plot.crop_profile_id,
                "name": plot.name,
                "municipality": plot.municipality,
                "boundary": plot.boundary,
                "area": spatial_result["plot_area"],
            },
            "measurements": {
                "count": len(readings),
                "valid_for_model": len(spatial_result["valid_reading_ids"]),
                "unit": "mass_pct",
                "basis": "elemental_mass_pct",
                "points": [
                    {
                        "id": reading.id,
                        "latitude": reading.latitude,
                        "longitude": reading.longitude,
                        "N": reading.npk_pct.N,
                        "P": reading.npk_pct.P,
                        "K": reading.npk_pct.K,
                        "quality": quality_by_id[reading.id],
                    }
                    for reading in readings
                ],
            },
            "spatial": {
                "grid": spatial_result["grid"],
                "zones": spatial_result["zones"],
                "next_sample": spatial_result["next_sample"],
            },
            "model_run": model_run,
            "climate": climate_context,
            "crop_profile": profile.model_dump(mode="json"),
            "proposal": proposal,
        }
        self.repository.save_package(package)
        self.repository.save_proposal(proposal)
        self.repository.append_audit(
            "package_generated", "plot", plot.id, "system",
            {"package_id": package_id, "model_run_id": model_run["id"], "proposal_id": proposal_id},
        )
        return package

    def _proposal(
        self,
        proposal_id: str,
        package_id: str,
        plot_id: str,
        recommendations: list[dict[str, Any]],
        model_run: dict[str, Any],
        climate_context: dict[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        explanation = {
            "summary": (
                "Candidate integer formulation plans were derived from spatial estimates, "
                "explicit demo agronomy assumptions and the center's active catalog."
            ),
            "steps": [
                {
                    "step": "spatial inference",
                    "evidence_id": model_run["id"],
                    "detail": "Three Matern Gaussian Processes produced means and uncertainty.",
                },
                {
                    "step": "agronomic accounting",
                    "detail": (
                        "Soil percentage was converted to sampled-layer mass and availability; "
                        "it was not subtracted from bag percentage."
                    ),
                },
                {
                    "step": "integer optimization",
                    "detail": (
                        "Each zone used exact bounded integer search with shortfall, excess, "
                        "bag count and formulation count in that order."
                    ),
                },
                {
                    "step": "climate context",
                    "detail": "Risk rules used the fused sources and can block application timing.",
                },
            ],
            "evidence": {
                "model_run_id": model_run["id"],
                "source_names": [source["name"] for source in climate_context["sources"]],
                "input_hash": model_run["input_hash"],
            },
            "unknowns": [
                "The sensor has not been calibrated against laboratory samples.",
                "The crop profile has not been validated by a local agronomist.",
                "Offline or stale climate data must be refreshed before field action.",
            ],
        }
        return {
            "id": proposal_id,
            "plot_id": plot_id,
            "package_id": package_id,
            "status": "pending",
            "validation_status": "requires_technical_validation",
            "human_decision_required": True,
            "applied": False,
            "recommendations": recommendations,
            "explanation": explanation,
            "created_at": created_at,
        }
