"""Reproducible small-data spatial intelligence engine."""

from __future__ import annotations

import hashlib
import json
import time
import warnings
from dataclasses import asdict

import numpy as np
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.preprocessing import StandardScaler

from ..domain.models import Plot, Reading
from .benchmark import leave_one_out
from .geometry import point_in_polygon, polygon_area_ha, to_lat_lon, to_local_meters
from .quality import QualityAnnotation, annotate_quality

NUTRIENTS = ("N", "P", "K")


class SpatialInferenceError(ValueError):
    pass


class SoilSpatialEngine:
    model_name = "GaussianProcessRegressor-Matern"
    model_version = "2.0.0"

    def __init__(self, *, cell_size_m: float = 10.0, seed: int = 42, zone_count: int = 3):
        self.cell_size_m = cell_size_m
        self.seed = seed
        self.zone_count = zone_count

    def run(self, plot: Plot, readings: list[Reading]) -> dict:
        started = time.perf_counter()
        if not readings:
            raise SpatialInferenceError("at least one reading is required")

        annotations = annotate_quality(plot, readings, seed=self.seed)
        quality_by_id = {item.reading_id: item for item in annotations}
        valid = [reading for reading in readings if quality_by_id[reading.id].valid_for_model]
        if not valid:
            raise SpatialInferenceError("no readings fall inside the declared plot boundary")

        origin_latitude = float(np.mean([point[0] for point in plot.boundary]))
        origin_longitude = float(np.mean([point[1] for point in plot.boundary]))
        coordinates = np.array([
            to_local_meters(
                reading.latitude, reading.longitude, origin_latitude, origin_longitude
            )
            for reading in valid
        ])
        values = {
            nutrient: np.array([getattr(reading.npk_pct, nutrient) for reading in valid], dtype=float)
            for nutrient in NUTRIENTS
        }
        grid = self._grid(plot, origin_latitude, origin_longitude)
        inside_coordinates = grid.pop("inside_coordinates")
        inside_indices = grid.pop("inside_indices")

        predictions: dict[str, dict[str, np.ndarray]] = {}
        for nutrient in NUTRIENTS:
            mean, std = self._gp_predict(coordinates, values[nutrient], inside_coordinates)
            predictions[nutrient] = {
                "mean": np.clip(mean, 0, 100),
                "std": np.maximum(std, 0),
            }

        combined_uncertainty = np.sqrt(np.mean(np.column_stack([
            predictions[nutrient]["std"] ** 2 for nutrient in NUTRIENTS
        ]), axis=1))
        uncertainty_threshold = self._uncertainty_threshold(combined_uncertainty, len(valid))
        grid_payload = self._grid_payload(
            grid, inside_indices, predictions, combined_uncertainty, uncertainty_threshold
        )
        zones = self._zones(
            predictions, combined_uncertainty, inside_indices, len(valid)
        )
        next_sample = self._next_sample(
            inside_coordinates,
            inside_indices,
            coordinates,
            combined_uncertainty,
            uncertainty_threshold,
            origin_latitude,
            origin_longitude,
        )
        benchmark = leave_one_out(coordinates, values, self._gp_predict)
        input_hash = self._input_hash(plot.id, valid)
        limitations = self._limitations(len(valid), benchmark)
        inference_ms = round((time.perf_counter() - started) * 1000, 3)

        return {
            "quality": [asdict(annotation) for annotation in annotations],
            "valid_reading_ids": [reading.id for reading in valid],
            "plot_area": {"value": round(polygon_area_ha(plot.boundary), 6), "unit": "ha"},
            "grid": grid_payload,
            "zones": zones,
            "next_sample": next_sample,
            "model_run": {
                "model_name": self.model_name,
                "model_version": self.model_version,
                "parameters": {
                    "kernel": "ConstantKernel * Matern(nu=1.5) + WhiteKernel",
                    "one_model_per_nutrient": True,
                    "nutrients": list(NUTRIENTS),
                    "seed": self.seed,
                    "cell_size_m": self.cell_size_m,
                    "zone_clusterer": "KMeans",
                    "zone_count_requested": self.zone_count,
                },
                "observation_count": len(valid),
                "metrics": benchmark,
                "inference_ms": inference_ms,
                "input_hash": input_hash,
                "limitations": limitations,
            },
        }

    def _gp_predict(
        self,
        train_x: np.ndarray,
        train_y: np.ndarray,
        query_x: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        train_x = np.atleast_2d(np.asarray(train_x, dtype=float))
        train_y = np.asarray(train_y, dtype=float)
        query_x = np.atleast_2d(np.asarray(query_x, dtype=float))
        if len(train_y) == 1:
            baseline_std = max(0.1, abs(float(train_y[0])) * 0.25)
            return (
                np.full(len(query_x), float(train_y[0])),
                np.full(len(query_x), baseline_std),
            )

        scaler = StandardScaler().fit(train_x)
        scaled_train = scaler.transform(train_x)
        scaled_query = scaler.transform(query_x)
        target_spread = max(float(np.std(train_y)), 0.05)
        kernel = (
            ConstantKernel(1.0, constant_value_bounds="fixed")
            * Matern(length_scale=1.0, length_scale_bounds="fixed", nu=1.5)
            + WhiteKernel(
                noise_level=max(1e-6, target_spread * 0.03),
                noise_level_bounds="fixed",
            )
        )
        model = GaussianProcessRegressor(
            kernel=kernel,
            alpha=1e-8,
            normalize_y=True,
            optimizer=None,
            random_state=self.seed,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=ConvergenceWarning)
            model.fit(scaled_train, train_y)
        mean, std = model.predict(scaled_query, return_std=True)
        return np.asarray(mean), np.maximum(np.asarray(std), 1e-6)

    def _grid(self, plot: Plot, origin_latitude: float, origin_longitude: float) -> dict:
        local_boundary = np.array([
            to_local_meters(lat, lon, origin_latitude, origin_longitude)
            for lat, lon in plot.boundary
        ])
        minimum = local_boundary.min(axis=0)
        maximum = local_boundary.max(axis=0)
        cols = max(1, int(np.ceil((maximum[0] - minimum[0]) / self.cell_size_m)))
        rows = max(1, int(np.ceil((maximum[1] - minimum[1]) / self.cell_size_m)))
        all_coordinates: list[tuple[float, float]] = []
        inside_coordinates: list[tuple[float, float]] = []
        inside_indices: list[int] = []
        mask: list[int] = []
        for row in range(rows):
            for col in range(cols):
                x = minimum[0] + (col + 0.5) * self.cell_size_m
                y = minimum[1] + (row + 0.5) * self.cell_size_m
                all_coordinates.append((x, y))
                lat, lon = to_lat_lon(x, y, origin_latitude, origin_longitude)
                is_inside = point_in_polygon(lat, lon, plot.boundary)
                mask.append(int(is_inside))
                if is_inside:
                    inside_indices.append(row * cols + col)
                    inside_coordinates.append((x, y))
        if not inside_coordinates:
            raise SpatialInferenceError("plot boundary did not produce any grid cells")
        origin_lat, origin_lon = to_lat_lon(
            minimum[0], minimum[1], origin_latitude, origin_longitude
        )
        return {
            "cell_size": {"value": self.cell_size_m, "unit": "m"},
            "cols": cols,
            "rows": rows,
            "origin": {"latitude": origin_lat, "longitude": origin_lon, "unit": "degrees"},
            "mask": mask,
            "inside_coordinates": np.array(inside_coordinates),
            "inside_indices": inside_indices,
        }

    @staticmethod
    def _uncertainty_threshold(uncertainty: np.ndarray, observation_count: int) -> float:
        if observation_count <= 2:
            return round(float(np.median(uncertainty)), 6)
        return round(float(np.quantile(uncertainty, 0.75)), 6)

    def _grid_payload(
        self,
        grid: dict,
        inside_indices: list[int],
        predictions: dict[str, dict[str, np.ndarray]],
        combined_uncertainty: np.ndarray,
        threshold: float,
    ) -> dict:
        cell_count = grid["rows"] * grid["cols"]

        def expand(values: np.ndarray) -> list[float | None]:
            output: list[float | None] = [None] * cell_count
            for index, value in zip(inside_indices, values):
                output[index] = round(float(value), 6)
            return output

        nutrient_payload = {}
        for nutrient in NUTRIENTS:
            mean = predictions[nutrient]["mean"]
            std = predictions[nutrient]["std"]
            nutrient_payload[nutrient] = {
                "mean": expand(mean),
                "std": expand(std),
                "interval_95_lower": expand(np.clip(mean - 1.96 * std, 0, 100)),
                "interval_95_upper": expand(np.clip(mean + 1.96 * std, 0, 100)),
                "unit": "mass_pct",
                "basis": "elemental_mass_pct",
            }
        return grid | {
            "nutrients": nutrient_payload,
            "combined_uncertainty": {
                "values": expand(combined_uncertainty),
                "threshold": threshold,
                "threshold_method": "75th percentile of in-plot predictive uncertainty",
                "unit": "percentage_points",
            },
        }

    def _zones(
        self,
        predictions: dict[str, dict[str, np.ndarray]],
        combined_uncertainty: np.ndarray,
        inside_indices: list[int],
        observation_count: int,
    ) -> list[dict]:
        features = np.column_stack([
            predictions[nutrient]["mean"] for nutrient in NUTRIENTS
        ])
        unique_features = len(np.unique(np.round(features, 8), axis=0))
        cluster_count = min(self.zone_count, len(features), unique_features)
        if observation_count < 3 or cluster_count < 2:
            labels = np.zeros(len(features), dtype=int)
            cluster_count = 1
            method = "single-zone fallback"
        else:
            standardized = StandardScaler().fit_transform(features)
            labels = KMeans(
                n_clusters=cluster_count,
                random_state=self.seed,
                n_init=20,
            ).fit_predict(standardized)
            method = "StandardScaler + KMeans"

        unsorted: list[dict] = []
        for label in range(cluster_count):
            members = np.where(labels == label)[0]
            centroid = {
                nutrient: round(float(np.mean(predictions[nutrient]["mean"][members])), 6)
                for nutrient in NUTRIENTS
            }
            unsorted.append({
                "member_positions": members,
                "centroid": centroid,
                "score": sum(centroid.values()),
            })
        unsorted.sort(key=lambda item: (item["score"], min(item["member_positions"])))
        output: list[dict] = []
        for zone_index, item in enumerate(unsorted, start=1):
            members = item["member_positions"]
            output.append({
                "id": f"zone-{zone_index}",
                "cells": [inside_indices[position] for position in members],
                "area": {
                    "value": round(len(members) * self.cell_size_m ** 2 / 10_000, 6),
                    "unit": "ha",
                },
                "centroid_npk": item["centroid"] | {
                    "unit": "mass_pct", "basis": "elemental_mass_pct"
                },
                "mean_uncertainty": {
                    "value": round(float(np.mean(combined_uncertainty[members])), 6),
                    "unit": "percentage_points",
                },
                "cluster_method": method,
            })
        return output

    def _next_sample(
        self,
        candidates: np.ndarray,
        inside_indices: list[int],
        observations: np.ndarray,
        uncertainty: np.ndarray,
        threshold: float,
        origin_latitude: float,
        origin_longitude: float,
    ) -> dict:
        distances = np.min(
            np.linalg.norm(candidates[:, None, :] - observations[None, :, :], axis=2), axis=1
        )
        eligible = distances >= max(self.cell_size_m, 5.0)
        if not np.any(eligible):
            eligible = np.ones(len(candidates), dtype=bool)
        uncertainty_range = float(np.ptp(uncertainty))
        distance_range = float(np.ptp(distances))
        uncertainty_score = (
            (uncertainty - float(np.min(uncertainty))) / uncertainty_range
            if uncertainty_range > 1e-12 else np.ones(len(uncertainty))
        )
        distance_score = (
            (distances - float(np.min(distances))) / distance_range
            if distance_range > 1e-12 else np.ones(len(distances))
        )
        score = 0.7 * uncertainty_score + 0.3 * distance_score
        score[~eligible] = -1
        selected = int(np.argmax(score))
        latitude, longitude = to_lat_lon(
            candidates[selected, 0], candidates[selected, 1],
            origin_latitude, origin_longitude,
        )
        radius = max(self.cell_size_m * 2, distances[selected] / 2)
        uncertain = uncertainty >= threshold
        potentially_covered = uncertain & (
            np.linalg.norm(candidates - candidates[selected], axis=1) <= radius
        )
        upper_bound = 100 * float(np.sum(potentially_covered)) / max(len(candidates), 1)
        return {
            "point": {"latitude": latitude, "longitude": longitude, "unit": "degrees"},
            "grid_cell": inside_indices[selected],
            "predictive_uncertainty": {
                "value": round(float(uncertainty[selected]), 6),
                "unit": "percentage_points",
            },
            "distance_to_nearest_measurement": {
                "value": round(float(distances[selected]), 3), "unit": "m"
            },
            "reason": (
                "Selected inside the plot by high predictive uncertainty and distance "
                "from existing measurements."
            ),
            "potential_coverage_improvement": {
                "upper_bound_percentage_points": round(upper_bound, 2),
                "method": "heuristic neighborhood of currently uncertain cells",
                "limitation": "This is an upper bound, not a promised uncertainty reduction.",
            },
        }

    @staticmethod
    def _input_hash(plot_id: str, readings: list[Reading]) -> str:
        payload = [
            {
                "id": reading.id,
                "lat": reading.latitude,
                "lon": reading.longitude,
                "N": reading.npk_pct.N,
                "P": reading.npk_pct.P,
                "K": reading.npk_pct.K,
            }
            for reading in sorted(readings, key=lambda item: item.id)
        ]
        encoded = json.dumps({"plot_id": plot_id, "readings": payload}, sort_keys=True)
        return hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _limitations(observation_count: int, benchmark: dict) -> list[str]:
        limitations = [
            "Sensor percentages have not been calibrated against laboratory samples.",
            "Spatial predictions support sampling and review; they are not laboratory measurements.",
        ]
        if observation_count < 20:
            limitations.append(
                f"Small dataset ({observation_count} in-plot observations); metrics have high variance."
            )
        if not benchmark["available"]:
            limitations.append(benchmark["reason"])
        return limitations
