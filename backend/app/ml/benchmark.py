"""Spatial leave-one-out benchmark: Gaussian Process versus IDW."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np


def idw_predict(
    train_x: np.ndarray,
    train_y: np.ndarray,
    query_x: np.ndarray,
    power: float = 2.0,
) -> np.ndarray:
    train_x = np.asarray(train_x, dtype=float)
    train_y = np.asarray(train_y, dtype=float)
    query_x = np.atleast_2d(np.asarray(query_x, dtype=float))
    if len(train_x) == 1:
        return np.full(len(query_x), float(train_y[0]))
    distances = np.linalg.norm(query_x[:, None, :] - train_x[None, :, :], axis=2)
    predictions: list[float] = []
    for row in distances:
        exact = np.where(row < 1e-12)[0]
        if len(exact):
            predictions.append(float(train_y[exact[0]]))
            continue
        weights = 1.0 / np.power(row, power)
        predictions.append(float(np.sum(weights * train_y) / np.sum(weights)))
    return np.array(predictions)


def _errors(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    residual = np.asarray(predicted) - np.asarray(actual)
    return {
        "mae": round(float(np.mean(np.abs(residual))), 6),
        "rmse": round(float(math.sqrt(np.mean(np.square(residual)))), 6),
    }


def leave_one_out(
    coordinates: np.ndarray,
    values: dict[str, np.ndarray],
    gp_predictor: Callable[[np.ndarray, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]],
) -> dict:
    observation_count = len(coordinates)
    if observation_count < 3:
        return {
            "method": "spatial_leave_one_out",
            "available": False,
            "reason": "Se requieren al menos 3 observaciones para validar el modelo espacial.",
            "observation_count": observation_count,
            "per_nutrient": {},
            "gp_better_than_idw": None,
        }

    per_nutrient: dict[str, dict] = {}
    for nutrient, target in values.items():
        actual: list[float] = []
        gp_mean: list[float] = []
        gp_std: list[float] = []
        idw_mean: list[float] = []
        for held_out in range(observation_count):
            keep = np.arange(observation_count) != held_out
            query = coordinates[held_out:held_out + 1]
            mean, std = gp_predictor(coordinates[keep], target[keep], query)
            actual.append(float(target[held_out]))
            gp_mean.append(float(mean[0]))
            gp_std.append(float(std[0]))
            idw_mean.append(float(idw_predict(coordinates[keep], target[keep], query)[0]))
        actual_array = np.array(actual)
        gp_array = np.array(gp_mean)
        std_array = np.array(gp_std)
        coverage = np.mean(
            (actual_array >= gp_array - 1.96 * std_array)
            & (actual_array <= gp_array + 1.96 * std_array)
        )
        per_nutrient[nutrient] = {
            "unit": "mass_pct",
            "gp": _errors(actual_array, gp_array) | {
                "interval_95_coverage": round(float(coverage), 6)
            },
            "idw": _errors(actual_array, np.array(idw_mean)),
        }

    gp_rmse = float(np.mean([item["gp"]["rmse"] for item in per_nutrient.values()]))
    idw_rmse = float(np.mean([item["idw"]["rmse"] for item in per_nutrient.values()]))
    return {
        "method": "spatial_leave_one_out",
        "available": True,
        "observation_count": observation_count,
        "per_nutrient": per_nutrient,
        "mean_rmse": {"gp": round(gp_rmse, 6), "idw": round(idw_rmse, 6)},
        "gp_better_than_idw": gp_rmse < idw_rmse,
        "claim": (
            "El GP tiene menor RMSE medio que IDW en esta validación cruzada."
            if gp_rmse < idw_rmse
            else "No se afirma que el GP supere a IDW con este conjunto de datos."
        ),
    }
