"""Exact bounded integer optimization for a small formulation catalog."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ..domain.models import Formulation
from ..agronomy.conversions import require_elemental_basis

NUTRIENTS = ("N", "P", "K")


class OptimizationError(ValueError):
    pass


class IntegerFormulationOptimizer:
    """Enumerate all bounded bag combinations and select a lexicographic optimum.

    This is exact for the configured demo bounds. It avoids the invalid pattern
    of solving a continuous problem and rounding each variable afterward.
    """

    version = "bounded-exact-integer/2.0.0"

    def solve(
        self,
        formulations: list[Formulation],
        *,
        target_kg_ha: dict[str, float],
        zone_area_ha: float,
        maximum_application_kg_ha: dict[str, float],
        maximum_bags: int,
        validation_status: str,
    ) -> dict[str, Any]:
        active = sorted(
            [formulation for formulation in formulations if formulation.available],
            key=lambda formulation: formulation.id,
        )
        if not active:
            raise OptimizationError("the center has no active formulations")
        if zone_area_ha <= 0:
            raise OptimizationError("zone_area_ha must be positive")
        if maximum_bags <= 0:
            raise OptimizationError("maximum_bags must be positive")
        for formulation in active:
            require_elemental_basis(formulation.basis)
        missing_targets = set(NUTRIENTS) - set(target_kg_ha)
        missing_limits = set(NUTRIENTS) - set(maximum_application_kg_ha)
        if missing_targets or missing_limits:
            raise OptimizationError("target and maximum application must define N, P and K")

        requirement = {
            nutrient: max(0.0, float(target_kg_ha[nutrient]) * zone_area_ha)
            for nutrient in NUTRIENTS
        }
        maximum = {
            nutrient: max(0.0, float(maximum_application_kg_ha[nutrient]) * zone_area_ha)
            for nutrient in NUTRIENTS
        }
        per_bag = [self._per_bag(formulation) for formulation in active]

        best_counts: tuple[int, ...] | None = None
        best_contribution: dict[str, float] | None = None
        best_objective: tuple[float, float, int, int, tuple[int, ...]] | None = None
        evaluated = 0
        feasible = 0
        for counts in self._bounded_combinations(len(active), maximum_bags):
            evaluated += 1
            contribution = {
                nutrient: sum(
                    counts[index] * per_bag[index][nutrient]
                    for index in range(len(active))
                )
                for nutrient in NUTRIENTS
            }
            if any(contribution[nutrient] > maximum[nutrient] + 1e-9 for nutrient in NUTRIENTS):
                continue
            feasible += 1
            shortfall = sum(
                max(0.0, requirement[nutrient] - contribution[nutrient])
                for nutrient in NUTRIENTS
            )
            excess = sum(
                max(0.0, contribution[nutrient] - requirement[nutrient])
                for nutrient in NUTRIENTS
            )
            total_bags = sum(counts)
            distinct = sum(count > 0 for count in counts)
            # The counts tuple is a deterministic fifth-order tie breaker only.
            objective = (
                round(shortfall, 9), round(excess, 9), total_bags, distinct, counts
            )
            if best_objective is None or objective < best_objective:
                best_objective = objective
                best_counts = counts
                best_contribution = contribution

        if best_counts is None or best_contribution is None or best_objective is None:
            raise OptimizationError("no combination satisfies the configured maximum application limits")

        shortfall = {
            nutrient: max(0.0, requirement[nutrient] - best_contribution[nutrient])
            for nutrient in NUTRIENTS
        }
        excess = {
            nutrient: max(0.0, best_contribution[nutrient] - requirement[nutrient])
            for nutrient in NUTRIENTS
        }
        selected = []
        total_weight = 0.0
        for formulation, count, bag_contribution in zip(active, best_counts, per_bag):
            if count == 0:
                continue
            weight = count * formulation.bag_weight_kg
            total_weight += weight
            selected.append({
                "formulation_id": formulation.id,
                "label": formulation.label,
                "bags": count,
                "bag_weight": {"value": formulation.bag_weight_kg, "unit": "kg"},
                "total_weight": {"value": round(weight, 6), "unit": "kg"},
                "nutrient_contribution": {
                    nutrient: round(count * bag_contribution[nutrient], 6)
                    for nutrient in NUTRIENTS
                } | {"unit": "kg", "basis": "elemental"},
                "source": formulation.source,
                "basis": formulation.basis,
            })

        active_constraints = [
            {"id": "integer-bags", "value": True},
            {"id": "active-formulations-only", "value": True},
            {"id": "maximum-total-bags", "value": maximum_bags, "unit": "bags"},
            {
                "id": "maximum-application",
                "value": {nutrient: round(value, 6) for nutrient, value in maximum.items()},
                "unit": "kg",
                "basis": "elemental",
            },
        ]
        has_shortfall = any(value > 1e-6 for value in shortfall.values())
        result_validation_status = validation_status
        if has_shortfall:
            result_validation_status = "requires_technical_validation"

        return {
            "optimizer": {
                "name": "exact bounded integer search",
                "version": self.version,
                "optimal_within_bounds": True,
                "evaluated_combinations": evaluated,
                "feasible_combinations": feasible,
                "objective_order": [
                    "total_nutrient_shortfall_kg",
                    "total_nutrient_excess_kg",
                    "total_bags",
                    "distinct_formulations",
                ],
                "objective_value": {
                    "shortfall_kg": best_objective[0],
                    "excess_kg": best_objective[1],
                    "bags": best_objective[2],
                    "distinct_formulations": best_objective[3],
                },
            },
            "formulations": selected,
            "total_bags": sum(best_counts),
            "total_weight": {"value": round(total_weight, 6), "unit": "kg"},
            "nutrient_contribution": {
                nutrient: round(best_contribution[nutrient], 6) for nutrient in NUTRIENTS
            } | {"unit": "kg", "basis": "elemental"},
            "requirement": {
                nutrient: round(requirement[nutrient], 6) for nutrient in NUTRIENTS
            } | {"unit": "kg", "basis": "elemental"},
            "shortfall": {
                nutrient: round(shortfall[nutrient], 6) for nutrient in NUTRIENTS
            } | {"unit": "kg", "basis": "elemental"},
            "excess": {
                nutrient: round(excess[nutrient], 6) for nutrient in NUTRIENTS
            } | {"unit": "kg", "basis": "elemental"},
            "active_constraints": active_constraints,
            "validation_status": result_validation_status,
            "technical_review_required": result_validation_status != "validated",
            "why_this_combination_won": (
                f"It is the lexicographic optimum among {feasible} feasible integer "
                "combinations: first least elemental nutrient shortfall, then least "
                "excess, then fewest bags, then fewest distinct formulations."
            ),
        }

    @staticmethod
    def _per_bag(formulation: Formulation) -> dict[str, float]:
        return {
            nutrient: formulation.bag_weight_kg
            * float(getattr(formulation.npk_pct, nutrient)) / 100
            for nutrient in NUTRIENTS
        }

    @classmethod
    def _bounded_combinations(cls, variables: int, maximum_total: int) -> Iterator[tuple[int, ...]]:
        def generate(prefix: tuple[int, ...], remaining_variables: int, remaining: int):
            if remaining_variables == 1:
                for value in range(remaining + 1):
                    yield prefix + (value,)
                return
            for value in range(remaining + 1):
                yield from generate(prefix + (value,), remaining_variables - 1, remaining - value)

        yield from generate((), variables, maximum_total)
