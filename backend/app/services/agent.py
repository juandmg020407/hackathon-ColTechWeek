"""Deterministic, grounded conversational intent router."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..repositories import SQLiteRepository


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


class GroundedAgent:
    version = "deterministic-grounded-router/1.0.0"

    def __init__(self, repository: SQLiteRepository):
        self.repository = repository

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
            return {
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
        answer, evidence_ids = builders[intent](package)
        sources = [
            source.get("name") for source in package.get("sources", []) if source.get("name")
        ]
        return {
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
                f"{item['bags']} bultos {item['label']}" for item in plan["formulations"]
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
