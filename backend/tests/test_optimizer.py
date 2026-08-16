from __future__ import annotations

import itertools

from app.agronomy import load_formulation_catalog
from app.config import BACKEND_ROOT
from app.optimization import IntegerFormulationOptimizer


def _reference_objective(formulations, counts, requirement, maximum):
    contribution = {
        nutrient: sum(
            count * formulation.bag_weight_kg
            * getattr(formulation.npk_pct, nutrient) / 100
            for count, formulation in zip(counts, formulations)
        )
        for nutrient in "NPK"
    }
    if any(contribution[nutrient] > maximum[nutrient] + 1e-9 for nutrient in "NPK"):
        return None
    shortfall = sum(max(0, requirement[n] - contribution[n]) for n in "NPK")
    excess = sum(max(0, contribution[n] - requirement[n]) for n in "NPK")
    return (round(shortfall, 9), round(excess, 9), sum(counts), sum(x > 0 for x in counts), counts)


def test_integer_optimizer_matches_independent_brute_force():
    formulations = sorted(load_formulation_catalog(
        BACKEND_ROOT / "config" / "formulations" / "center-pasto-demo-v1.yaml"
    ), key=lambda item: item.id)
    target = {"N": 45.0, "P": 30.0, "K": 55.0}
    maximum = {"N": 100.0, "P": 100.0, "K": 100.0}
    max_bags = 6
    result = IntegerFormulationOptimizer().solve(
        formulations,
        target_kg_ha=target,
        zone_area_ha=1.0,
        maximum_application_kg_ha=maximum,
        maximum_bags=max_bags,
        validation_status="requires_technical_validation",
    )
    candidates = []
    for counts in itertools.product(range(max_bags + 1), repeat=len(formulations)):
        if sum(counts) > max_bags:
            continue
        objective = _reference_objective(formulations, counts, target, maximum)
        if objective is not None:
            candidates.append(objective)
    expected = min(candidates)
    actual_counts = tuple(
        next((item["bags"] for item in result["formulations"] if item["formulation_id"] == f.id), 0)
        for f in formulations
    )
    assert actual_counts == expected[-1]
    assert all(isinstance(count, int) for count in actual_counts)
    assert result["optimizer"]["optimal_within_bounds"] is True
    assert result["optimizer"]["objective_value"]["shortfall_kg"] == expected[0]


def test_optimizer_never_uses_price_as_an_objective():
    formulations = load_formulation_catalog(
        BACKEND_ROOT / "config" / "formulations" / "center-pasto-demo-v1.yaml"
    )
    result = IntegerFormulationOptimizer().solve(
        formulations,
        target_kg_ha={"N": 10, "P": 10, "K": 10},
        zone_area_ha=0.25,
        maximum_application_kg_ha={"N": 100, "P": 100, "K": 100},
        maximum_bags=4,
        validation_status="requires_technical_validation",
    )
    assert result["optimizer"]["objective_order"] == [
        "total_nutrient_shortfall_kg",
        "total_nutrient_excess_kg",
        "total_bags",
        "distinct_formulations",
    ]
