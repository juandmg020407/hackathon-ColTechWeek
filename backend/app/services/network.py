"""Collection-center portfolio summaries for a frontend-ready network view."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..ml.geometry import polygon_area_ha
from ..repositories import SQLiteRepository

_SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_EMPTY_READINGS = {
    "total": 0, "valid": 0, "suspicious": 0, "outside": 0, "latest_measured_at": None,
}
_RISK_LABELS = {
    "frost": "Helada",
    "drought": "Sequía",
    "late_blight": "Gota tardía",
    "seasonal": "Riesgo estacional",
}


def _score(risk: dict[str, Any]) -> float:
    value = risk.get("score", 0)
    if isinstance(value, dict):
        value = value.get("value", 0)
    return float(value or 0)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _newer_reading_exists(latest_measured_at: str | None, generated_at: str | None) -> bool:
    """¿Hay evidencia posterior al último cálculo del lote?

    Sin lecturas no hay nada que recalcular. Con lecturas y sin package, sí.
    """

    measured = _parse_time(latest_measured_at)
    if measured is None:
        return False
    package_time = _parse_time(generated_at)
    return package_time is None or measured > package_time


class CenterNetworkService:
    """Builds honest aggregates from persisted producers, plots and packages."""

    version = "center-network-summary/1.0.0"

    def __init__(self, repository: SQLiteRepository):
        self.repository = repository

    def dashboard(self, center_id: str) -> dict[str, Any]:
        center = self.repository.get_center(center_id)
        if center is None:
            raise ValueError(f"el centro {center_id} no existe")

        producers = self.repository.list_producers(center_id)
        producer_rows: dict[str, dict[str, Any]] = {
            producer.id: {
                **producer.model_dump(mode="json"),
                "plot_count": 0,
                "total_area": {"value": 0.0, "unit": "ha"},
                "plots_at_risk": 0,
                "highest_risk": {"severity": "none", "score": 0.0, "type": None},
                "latest_measurement_at": None,
                "plots": [],
            }
            for producer in producers
        }
        unassigned_plots: list[dict[str, Any]] = []
        priorities: list[dict[str, Any]] = []
        risk_groups: dict[str, dict[str, Any]] = {}

        total_area = 0.0
        total_readings = 0
        measured_plots = 0
        computed_plots = 0
        at_risk_plots = 0
        pending_proposals = 0
        review_readings = 0

        plot_items = self.repository.list_plots(center_id=center_id)
        plot_ids = [item["id"] for item in plot_items]
        # Dos consultas agregadas en vez de tres por lote. El snapshot completo
        # de un package lleva la grilla entera y aquí solo se necesitan seis
        # campos: leerlo por cada lote hacía el tablero inviable con una red real.
        digests = self.repository.latest_package_digests(plot_ids)
        reading_digests = self.repository.reading_digests(plot_ids)

        for item in plot_items:
            boundary = item["boundary"]
            package = digests.get(item["id"])
            counts = reading_digests.get(item["id"], _EMPTY_READINGS)
            area = float(
                (package or {}).get("area_ha") or polygon_area_ha(boundary)
            )
            risks = (package or {}).get("risks", [])
            top_risk = max(
                risks,
                key=lambda risk: (_SEVERITY_RANK.get(risk.get("severity", "none"), 0), _score(risk)),
                default=None,
            )
            suspicious = counts["suspicious"]
            outside = counts["outside"]
            needs_recompute = _newer_reading_exists(
                counts["latest_measured_at"],
                package.get("generated_at") if package else None,
            )
            latest_measurement = _parse_time(counts["latest_measured_at"])
            pending = bool(package and package.get("proposal_status") == "pending")
            risk_severity = top_risk.get("severity", "none") if top_risk else "none"
            plot_at_risk = _SEVERITY_RANK.get(risk_severity, 0) >= _SEVERITY_RANK["medium"]

            plot_row = {
                "id": item["id"],
                "name": item["name"],
                "municipality": item["municipality"],
                "producer_id": item["producer_id"],
                "location": {
                    "latitude": round(
                        sum(point[0] for point in boundary) / len(boundary), 7
                    ),
                    "longitude": round(
                        sum(point[1] for point in boundary) / len(boundary), 7
                    ),
                },
                "area": {"value": round(area, 6), "unit": "ha"},
                "measurement_count": counts["total"],
                "valid_measurement_count": counts["valid"],
                "measurements_for_review": suspicious + outside,
                "latest_measurement_at": latest_measurement,
                "package_id": package.get("id") if package else None,
                "package_generated_at": package.get("generated_at") if package else None,
                "needs_recompute": needs_recompute,
                "validation_status": (
                    package.get("validation_status") if package else "not_computed"
                ),
                "degraded": package.get("degraded") if package else False,
                "pending_technical_review": pending,
                "highest_risk": {
                    "type": top_risk.get("type") if top_risk else None,
                    "label": _RISK_LABELS.get(top_risk.get("type"), top_risk.get("type"))
                    if top_risk else None,
                    "severity": risk_severity,
                    "score": round(_score(top_risk), 6) if top_risk else 0.0,
                    "window": top_risk.get("window") if top_risk else None,
                },
                "links": {
                    "plot": f"/v1/plots/{item['id']}",
                    "package": f"/v1/plots/{item['id']}/package",
                    "readings": f"/v1/plots/{item['id']}/readings",
                    "risk": f"/v1/plots/{item['id']}/risk",
                    "assistant": "/v1/agent/ask",
                },
            }

            total_area += area
            total_readings += counts["total"]
            measured_plots += bool(counts["total"])
            computed_plots += bool(package)
            at_risk_plots += plot_at_risk
            pending_proposals += pending
            review_readings += suspicious + outside

            if not counts["total"]:
                priorities.append(self._priority(
                    plot_row, "high", "measurement_missing", "Lote sin mediciones",
                    "Registre mediciones para poder estimar suelo, incertidumbre y riesgo.",
                ))
            elif needs_recompute:
                priorities.append(self._priority(
                    plot_row, "high", "recompute_required", "Hay mediciones nuevas",
                    "Recalcule el paquete antes de tomar una decisión.",
                ))
            if top_risk and _SEVERITY_RANK.get(risk_severity, 0) >= _SEVERITY_RANK["medium"]:
                priorities.append(self._priority(
                    plot_row, risk_severity, f"risk_{top_risk['type']}",
                    f"Riesgo de {_RISK_LABELS.get(top_risk['type'], top_risk['type']).lower()}",
                    top_risk.get("recommended_action", "Revise el riesgo con el técnico."),
                ))
            if suspicious + outside:
                priorities.append(self._priority(
                    plot_row, "medium", "measurement_review", "Medición para revisar",
                    "La lectura se conserva en el historial y no se elimina automáticamente.",
                ))
            if pending:
                priorities.append(self._priority(
                    plot_row, "medium", "technical_review", "Propuesta pendiente",
                    "La propuesta requiere revisión técnica y todavía no está aplicada.",
                ))

            for risk in risks:
                risk_type = risk.get("type", "unknown")
                group = risk_groups.setdefault(risk_type, {
                    "type": risk_type,
                    "label": _RISK_LABELS.get(risk_type, risk_type),
                    "severity": "none",
                    "max_score": 0.0,
                    "plot_ids": set(),
                    "window": risk.get("window"),
                })
                group["plot_ids"].add(item["id"])
                if _SEVERITY_RANK.get(risk.get("severity", "none"), 0) > _SEVERITY_RANK.get(
                    group["severity"], 0
                ):
                    group["severity"] = risk.get("severity", "none")
                    group["window"] = risk.get("window")
                group["max_score"] = max(group["max_score"], _score(risk))

            owner = producer_rows.get(item["producer_id"] or "")
            if owner is None:
                unassigned_plots.append(plot_row)
            else:
                owner["plots"].append(plot_row)
                owner["plot_count"] += 1
                owner["total_area"]["value"] = round(
                    owner["total_area"]["value"] + area, 6
                )
                owner["plots_at_risk"] += plot_at_risk
                if latest_measurement and (
                    owner["latest_measurement_at"] is None
                    or latest_measurement > owner["latest_measurement_at"]
                ):
                    owner["latest_measurement_at"] = latest_measurement
                if _SEVERITY_RANK.get(risk_severity, 0) > _SEVERITY_RANK.get(
                    owner["highest_risk"]["severity"], 0
                ):
                    owner["highest_risk"] = plot_row["highest_risk"]

        ordered_priorities = sorted(
            priorities,
            key=lambda item: (-_SEVERITY_RANK.get(item["severity"], 0), item["plot_name"]),
        )
        horizon = sorted(
            (
                group | {
                    "max_score": round(group["max_score"], 6),
                    "plot_ids": sorted(group["plot_ids"]),
                    "plot_count": len(group["plot_ids"]),
                }
                for group in risk_groups.values()
            ),
            key=lambda item: (-_SEVERITY_RANK.get(item["severity"], 0), -item["max_score"]),
        )
        origins = {producer.data_origin for producer in producers}
        return {
            "center": center,
            "data_scope": {
                "contains_demonstration_data": "demonstration" in origins
                or center.get("validation_status") == "demo_unvalidated",
                "contains_pilot_data": "pilot" in origins,
                "contains_operational_data": "operational" in origins,
                "statement": (
                    "Los conteos provienen únicamente de registros persistidos; "
                    "los datos de demostración se identifican explícitamente."
                ),
            },
            "summary": {
                "producer_count": len(producers),
                "plot_count": len(plot_items),
                "total_area": {"value": round(total_area, 6), "unit": "ha"},
                "measurement_count": total_readings,
                "measured_plot_count": measured_plots,
                "computed_plot_count": computed_plots,
                "plots_at_risk": at_risk_plots,
                "pending_proposals": pending_proposals,
                "measurements_for_review": review_readings,
            },
            "priority_queue": ordered_priorities,
            "risk_horizon": horizon,
            "producers": list(producer_rows.values()),
            "unassigned_plots": unassigned_plots,
            "service_version": self.version,
        }

    @staticmethod
    def _priority(
        plot: dict[str, Any], severity: str, kind: str, title: str, detail: str
    ) -> dict[str, Any]:
        return {
            "id": f"{kind}:{plot['id']}",
            "kind": kind,
            "severity": severity,
            "title": title,
            "detail": detail,
            "plot_id": plot["id"],
            "plot_name": plot["name"],
            "producer_id": plot["producer_id"],
            "links": plot["links"],
        }
