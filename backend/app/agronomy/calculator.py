"""Transparent soil-to-crop nutrient accounting."""

from __future__ import annotations

from typing import Any

from ..domain.models import CropProfile, NPKPercent
from .conversions import require_elemental_basis

NUTRIENTS = ("N", "P", "K")


class AgronomicCalculator:
    version = "soil-mass-balance/2.0.0"

    def assess(
        self,
        soil_npk_pct: NPKPercent,
        profile: CropProfile,
        *,
        zone_area_ha: float,
        climate_risks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        require_elemental_basis(soil_npk_pct.basis)
        depth_m = profile.sampling_depth_cm / 100
        bulk_density_kg_m3 = profile.bulk_density_g_cm3 * 1000
        soil_mass_kg_ha = 10_000 * depth_m * bulk_density_kg_m3

        total_in_sample: dict[str, float] = {}
        estimated_available: dict[str, float] = {}
        requirement = profile.requirement_kg_ha.as_dict()
        maximum = profile.maximum_application_kg_ha.as_dict()
        deficit: dict[str, float] = {}
        optimization_target: dict[str, float] = {}
        limits_exceeded: list[str] = []
        for nutrient in NUTRIENTS:
            measured_pct = float(getattr(soil_npk_pct, nutrient))
            total = soil_mass_kg_ha * measured_pct / 100
            available = total * profile.availability_fraction[nutrient]
            missing = max(0.0, requirement[nutrient] - available)
            target = min(missing, maximum[nutrient])
            total_in_sample[nutrient] = round(total, 6)
            estimated_available[nutrient] = round(available, 6)
            deficit[nutrient] = round(missing, 6)
            optimization_target[nutrient] = round(target, 6)
            if missing > maximum[nutrient] + 1e-9:
                limits_exceeded.append(nutrient)

        risks = climate_risks or []
        active_constraints = self._climate_constraints(risks)
        reasons: list[str] = []
        if profile.validation_status != "validated":
            reasons.append(
                f"El perfil de cultivo {profile.id}@{profile.version} está "
                f"'{profile.validation_status}' y no es una prescripción validada."
            )
        if limits_exceeded:
            reasons.append(
                "El faltante calculado supera el máximo configurado para "
                + ", ".join(limits_exceeded)
                + "."
            )
        if active_constraints:
            reasons.append(
                "El contexto climático obliga a revisar el momento o la dosis de aplicación."
            )
        validation_status = "validated" if not reasons else "requires_technical_validation"

        return {
            "calculation_version": self.version,
            "soil_measurement": soil_npk_pct.model_dump(mode="json") | {"unit": "mass_pct"},
            "sampling_layer": {
                "depth": {"value": profile.sampling_depth_cm, "unit": "cm"},
                "bulk_density": {"value": profile.bulk_density_g_cm3, "unit": "g/cm3"},
                "estimated_soil_mass": {"value": round(soil_mass_kg_ha, 3), "unit": "kg/ha"},
            },
            "total_nutrient_in_sampled_layer": total_in_sample | {
                "unit": "kg/ha", "basis": "elemental"
            },
            "availability_fraction": profile.availability_fraction,
            "estimated_crop_available": estimated_available | {
                "unit": "kg/ha", "basis": "elemental"
            },
            "crop_requirement": requirement | {"unit": "kg/ha", "basis": "elemental"},
            "calculated_deficit": deficit | {"unit": "kg/ha", "basis": "elemental"},
            "optimization_target": optimization_target | {
                "unit": "kg/ha", "basis": "elemental"
            },
            "maximum_application": maximum | {"unit": "kg/ha", "basis": "elemental"},
            "zone_area": {"value": round(zone_area_ha, 6), "unit": "ha"},
            "active_constraints": active_constraints,
            "profile": {
                "id": profile.id,
                "version": profile.version,
                "validation_status": profile.validation_status,
                "effective_from": profile.effective_from.isoformat(),
                "sources": [source.model_dump(mode="json") for source in profile.sources],
            },
            "validation_status": validation_status,
            "technical_validation_reasons": reasons,
            "warning": (
                "El porcentaje del suelo se convirtió a través de la masa de suelo "
                "muestreada y de un factor de disponibilidad explícito. No se restó "
                "del porcentaje de la formulación."
            ),
        }

    @staticmethod
    def _climate_constraints(risks: list[dict[str, Any]]) -> list[dict[str, str]]:
        constraints: list[dict[str, str]] = []
        for risk in risks:
            if risk.get("severity") not in {"high", "critical"}:
                continue
            risk_type = str(risk.get("type"))
            if risk_type == "drought":
                constraints.append({
                    "id": "verify-water-before-application",
                    "risk": risk_type,
                    "effect": (
                        "No presentar el candidato como listo para aplicar hasta "
                        "verificar la disponibilidad de agua."
                    ),
                })
            elif risk_type == "frost":
                constraints.append({
                    "id": "technician-review-before-frost-window",
                    "risk": risk_type,
                    "effect": (
                        "Revisar el momento de aplicación contra la ventana de "
                        "helada pronosticada."
                    ),
                })
            elif risk_type == "late_blight":
                constraints.append({
                    "id": "avoid-leaf-wetting-window",
                    "risk": risk_type,
                    "effect": (
                        "Coordinar el trabajo en campo con la ventana de inspección "
                        "de gota tardía."
                    ),
                })
        return constraints
