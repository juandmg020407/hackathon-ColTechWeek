"""The single package, proposal and explanation computation path."""

from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool

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


class PlotHasNoReadingsError(EngineError):
    """El lote existe pero todavía no tiene evidencia sobre la que calcular.

    Se separa de `EngineError` porque no es un fallo: es el estado inicial de
    todo lote nuevo, y el cliente debe poder distinguirlo para ofrecer la
    importación en vez de mostrar un error genérico.
    """


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
            raise EngineError(f"el lote {plot_id} no existe")
        readings = self.repository.list_readings(plot_id)
        if not readings:
            raise PlotHasNoReadingsError(
                f"el lote {plot_id} no tiene mediciones: importe un archivo o "
                "registre una lectura antes de calcular"
            )

        # El GP y el benchmark leave-one-out son CPU pura y tardan cientos de
        # milisegundos: dentro del event loop dejarían al proceso sin atender
        # ni siquiera el health check mientras corren.
        spatial_result = await run_in_threadpool(self.spatial.run, plot, readings)
        self.repository.update_reading_qualities(spatial_result["quality"])
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
            raise EngineError(f"el perfil de cultivo {plot.crop_profile_id} no existe")
        formulations = self.repository.list_formulations(plot.center_id, active_only=True)
        if not formulations:
            raise EngineError(
                f"el centro {plot.center_id} no tiene formulaciones activas en su catálogo"
            )

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
            "El perfil de cultivo está sin validar: ningún plan candidato es una "
            "prescripción aplicada."
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
                "producer_id": plot.producer_id,
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
                "Los planes candidatos de formulación entera salen de las estimaciones "
                "espaciales, de los supuestos agronómicos explícitos de la demo y del "
                "catálogo activo del centro de acopio."
            ),
            "steps": [
                {
                    "step": "Inferencia espacial",
                    "evidence_id": model_run["id"],
                    "detail": (
                        "Tres procesos gaussianos Matérn, uno por nutriente, produjeron "
                        "la media y la incertidumbre de cada celda."
                    ),
                },
                {
                    "step": "Balance agronómico",
                    "detail": (
                        "El porcentaje del suelo se convirtió a masa de la capa muestreada "
                        "y se aplicó un factor de disponibilidad explícito. Nunca se restó "
                        "del porcentaje del bulto."
                    ),
                },
                {
                    "step": "Optimización entera",
                    "detail": (
                        "Cada zona resolvió una búsqueda entera exacta y acotada que "
                        "minimiza, en ese orden, faltante, exceso, número de bultos y "
                        "número de formulaciones distintas."
                    ),
                },
                {
                    "step": "Contexto climático",
                    "detail": (
                        "Las reglas de riesgo usaron las fuentes fusionadas y pueden "
                        "aplazar el momento de aplicación."
                    ),
                },
            ],
            "evidence": {
                "model_run_id": model_run["id"],
                "source_names": [source["name"] for source in climate_context["sources"]],
                "input_hash": model_run["input_hash"],
            },
            "unknowns": [
                "El sensor no está calibrado contra muestras de laboratorio.",
                "El perfil de cultivo no ha sido validado por un agrónomo local.",
                "El clima está en modo degradado o no actual: hay que refrescarlo antes de ir a campo.",
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
