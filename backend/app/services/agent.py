"""Grounded conversational agent with deterministic fast paths."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..repositories import SQLiteRepository
from .explainer import EvidenceExplainer


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


class GroundedAgent:
    version = "grounded-evidence-agent/2.0.0"

    def __init__(
        self,
        repository: SQLiteRepository,
        explainer: EvidenceExplainer | None = None,
    ):
        self.repository = repository
        # El modelo solo recibe evidencia compacta y no puede introducir cifras
        # nuevas. Las preguntas conocidas conservan sus respuestas deterministas.
        self.explainer = explainer

    def ask(self, plot_id: str, question: str) -> dict[str, Any]:
        package = self.repository.latest_package(plot_id)
        if package is None:
            raise ValueError(
                "no package evidence exists for this plot; import readings and recompute first"
            )
        intent = self._intent(question)
        builders = {
            "plot_status": self._plot_status,
            "formulation_reason": self._formulation_reason,
            "next_measurement": self._next_measurement,
            "climate_risk": self._climate_risk,
            "missing_data": self._missing_data,
            "prediction_confidence": self._prediction_confidence,
        }
        if intent is None:
            fallback = {
                "answered": False,
                "intent": "unsupported",
                "answer": (
                    "No encontré evidencia para responder esa pregunta. Puedo explicar el estado "
                    "del lote, la formulación candidata, el siguiente punto, los riesgos, los "
                    "datos faltantes o la incertidumbre."
                ),
                "evidence_ids": [],
                "sources": [],
                "grounded": True,
                "router_version": self.version,
                "llm_used": False,
            }
            return self._answer_from_evidence(question, package, fallback)
        answer, evidence_ids = builders[intent](package)
        sources = self._source_names(package)
        result = {
            "answered": True,
            "intent": intent,
            "answer": answer,
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "sources": list(dict.fromkeys(sources)),
            "grounded": True,
            "router_version": self.version,
            "llm_used": False,
            "limitations": package.get("warnings", []),
        }
        return self._phrase(question, result)

    def _answer_from_evidence(
        self,
        question: str,
        package: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        """Responde preguntas abiertas sin entregar al modelo grillas enormes."""
        if self.explainer is None:
            return fallback

        evidence_ids = [
            package["id"],
            package["model_run"]["id"],
            package["proposal"]["id"],
        ]
        rendered = self.explainer.render(
            question=question,
            evidence=self._conversation_evidence(package),
            evidence_ids=evidence_ids,
        )
        fallback["explainer"] = rendered
        if not rendered.get("used"):
            return fallback

        fallback.update({
            "answered": True,
            "intent": "grounded_question",
            "answer": rendered["text"],
            "evidence_ids": evidence_ids,
            "sources": self._source_names(package),
            "limitations": package.get("warnings", []),
            "llm_used": True,
        })
        return fallback

    @staticmethod
    def _source_names(package: dict[str, Any]) -> list[str]:
        names = [
            source.get("name")
            for source in package.get("sources", [])
            if source.get("name")
        ]
        return list(dict.fromkeys(names))

    @staticmethod
    def _conversation_evidence(package: dict[str, Any]) -> dict[str, Any]:
        """Resumen conversable del package; excluye matrices y series pesadas."""
        points = package["measurements"].get("points", [])
        proposal = package["proposal"]
        recommendations = []
        for recommendation in proposal.get("recommendations", []):
            plan = recommendation.get("integer_plan", {})
            assessment = recommendation.get("agronomic_assessment") or {}
            recommendations.append({
                "zone_id": recommendation.get("zone_id"),
                "agronomic_assessment": {
                    key: assessment.get(key)
                    for key in (
                        "soil_measurement", "estimated_crop_available", "crop_requirement",
                        "calculated_deficit", "zone_area", "validation_status",
                        "technical_validation_reasons", "warning",
                    )
                },
                "integer_plan": {
                    key: plan.get(key)
                    for key in (
                        "formulations", "total_bags", "total_weight",
                        "nutrient_contribution", "requirement", "shortfall", "excess",
                        "validation_status", "technical_review_required",
                        "why_this_combination_won",
                    )
                },
            })
        seasonal = package["climate"].get("seasonal_context") or {}
        crop_profile = package.get("crop_profile") or {}
        plot = package.get("plot") or {}
        return {
            "answer": "",
            "validation_status": package.get("validation_status"),
            "plot": {
                key: plot.get(key)
                for key in (
                    "id", "center_id", "producer_id", "crop_profile_id",
                    "name", "municipality", "area",
                )
            },
            "measurement_summary": {
                "count": package["measurements"].get("count", len(points)),
                "valid_for_model": package["measurements"].get("valid_for_model"),
                "suspicious": sum(
                    bool(point.get("quality", {}).get("suspicious")) for point in points
                ),
                "outside_plot": sum(
                    point.get("quality", {}).get("valid_for_model") is False for point in points
                ),
                "unit": package["measurements"].get("unit"),
            },
            "zones": [
                {
                    key: zone.get(key)
                    for key in (
                        "id", "area", "centroid_npk", "mean_uncertainty", "cluster_method"
                    )
                }
                for zone in package["spatial"].get("zones", [])
            ],
            "next_sample": package["spatial"].get("next_sample"),
            "climate": {
                "risks": [
                    {
                        key: risk.get(key)
                        for key in (
                            "type", "score", "severity", "confidence", "window", "inputs",
                            "recommended_action", "limitations",
                        )
                    }
                    for risk in package["climate"].get("risks", [])
                ],
                "seasonal_context": {
                    key: seasonal.get(key)
                    for key in ("enso", "analog_years", "analog_model")
                },
                "degraded": package["climate"].get("degraded"),
                "warnings": package["climate"].get("warnings", []),
            },
            "crop_profile": {
                key: crop_profile.get(key)
                for key in (
                    "id", "crop", "variety", "stage", "scope", "requirement_kg_ha",
                    "maximum_application_kg_ha", "maximum_bags_per_zone",
                    "target_yield_t_ha", "version", "validation_status",
                )
            },
            "proposal": {
                "status": proposal.get("status"),
                "validation_status": proposal.get("validation_status"),
                "human_decision_required": proposal.get("human_decision_required"),
                "applied": proposal.get("applied"),
                "recommendations": recommendations,
                "explanation": proposal.get("explanation"),
            },
            "model": {
                key: package["model_run"].get(key)
                for key in (
                    "model_name", "model_version", "observation_count", "metrics", "limitations"
                )
            },
            "warnings": package.get("warnings", []),
            "sources": GroundedAgent._source_names(package),
        }

    def _phrase(self, question: str, result: dict[str, Any]) -> dict[str, Any]:
        """Deja que el explicador reescriba la respuesta, si hay uno activo.

        La respuesta determinista es la que se devuelve mientras el explicador no
        confirme una redaccion valida, asi que un modelo caido, sin presupuesto o
        que inventa una cifra no cambia lo que ve el usuario.
        """
        if self.explainer is None:
            return result
        rendered = self.explainer.render(
            question=question,
            evidence=result,
            evidence_ids=result["evidence_ids"],
        )
        result["explainer"] = rendered
        if rendered.get("used"):
            result["answer_deterministic"] = result["answer"]
            result["answer"] = rendered["text"]
            result["llm_used"] = True
        return result

    @staticmethod
    def _intent(question: str) -> str | None:
        text = _normalise(question)
        patterns = [
            ("formulation_reason", r"por que|formula|formulacion|bulto|recomiend"),
            ("next_measurement", r"donde.*(medir|mido)|siguiente punto|medir ahora|muestre"),
            ("climate_risk", r"riesgo|clima|helada|sequia|gota|tizon|lluvia"),
            ("missing_data", r"falta.*dato|datos faltan|que falta|no sabemos"),
            ("prediction_confidence", r"segur|confianza|incertid|precision|fiable"),
            ("plot_status", r"que tiene|estado.*lote|suelo|nutriente|este lote"),
        ]
        for intent, pattern in patterns:
            if re.search(pattern, text):
                return intent
        return None

    @staticmethod
    def _plot_status(package: dict[str, Any]) -> tuple[str, list[str]]:
        zones = package["spatial"]["zones"]
        summaries = [
            (
                f"{zone['id']}: N {zone['centroid_npk']['N']:.2f} %, "
                f"P {zone['centroid_npk']['P']:.2f} %, K {zone['centroid_npk']['K']:.2f} %"
            )
            for zone in zones
        ]
        suspicious = sum(
            bool(point["quality"]["suspicious"])
            for point in package["measurements"]["points"]
        )
        answer = (
            f"El lote tiene {package['measurements']['valid_for_model']} mediciones válidas "
            f"para el modelo y {len(zones)} zonas: " + "; ".join(summaries) + ". "
            f"Hay {suspicious} lecturas marcadas para revisión; no fueron eliminadas automáticamente."
        )
        return answer, [package["id"], package["model_run"]["id"]]

    @staticmethod
    def _formulation_reason(package: dict[str, Any]) -> tuple[str, list[str]]:
        proposal = package["proposal"]
        zone_text = []
        for recommendation in proposal["recommendations"]:
            plan = recommendation["integer_plan"]
            selected = ", ".join(
                f"{item['bags']} {'bulto' if item['bags'] == 1 else 'bultos'} {item['label']}"
                for item in plan["formulations"]
            ) or "0 bultos"
            zone_text.append(f"{recommendation['zone_id']}: {selected}")
        answer = (
            "La combinación candidata ganó por minimizar, en orden, faltante elemental, "
            "exceso, total de bultos y número de formulaciones: " + "; ".join(zone_text) + ". "
            "Sigue pendiente y requiere validación técnica; no está aplicada."
        )
        return answer, [package["id"], proposal["id"], package["model_run"]["id"]]

    @staticmethod
    def _next_measurement(package: dict[str, Any]) -> tuple[str, list[str]]:
        sample = package["spatial"]["next_sample"]
        point = sample["point"]
        potential = sample["potential_coverage_improvement"]
        answer = (
            f"Mida cerca de {point['latitude']:.6f}, {point['longitude']:.6f}. "
            f"Está a {sample['distance_to_nearest_measurement']['value']:.1f} m de la medición "
            "más cercana y combina incertidumbre alta con separación espacial. "
            f"La mejora potencial tiene un límite superior heurístico de "
            f"{potential['upper_bound_percentage_points']:.1f} puntos porcentuales; no es una promesa."
        )
        return answer, [package["id"], package["model_run"]["id"]]

    @staticmethod
    def _climate_risk(package: dict[str, Any]) -> tuple[str, list[str]]:
        risks = package["climate"]["risks"]
        risk_text = ", ".join(
            f"{risk['type']} {risk['severity']} ({risk['score']['value']:.2f})"
            for risk in risks
        )
        degraded = " Los datos están en modo degradado y no se presentan como actuales." if package["climate"]["degraded"] else ""
        return (
            f"El contexto reporta {risk_text}.{degraded}",
            [package["id"]] + [source["name"] for source in package["climate"]["sources"]],
        )

    @staticmethod
    def _missing_data(package: dict[str, Any]) -> tuple[str, list[str]]:
        unknowns = package["proposal"]["explanation"]["unknowns"]
        return "Falta confirmar: " + " ".join(unknowns), [package["proposal"]["id"]]

    @staticmethod
    def _prediction_confidence(package: dict[str, Any]) -> tuple[str, list[str]]:
        metric = package["model_run"]["metrics"]
        threshold = package["spatial"]["grid"]["combined_uncertainty"]["threshold"]
        if metric.get("available"):
            comparison = metric["claim"]
        else:
            comparison = metric.get("reason", "benchmark unavailable")
        answer = (
            f"El umbral dinámico de incertidumbre es {threshold:.2f} puntos porcentuales. "
            f"La validación espacial dice: {comparison} El conjunto tiene "
            f"{package['model_run']['observation_count']} observaciones válidas, por lo que las "
            "métricas tienen alta variabilidad."
        )
        return answer, [package["model_run"]["id"]]
