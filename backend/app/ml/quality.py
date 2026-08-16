"""Conservative quality and anomaly annotations.

Suspicious measurements remain available to the model. Geometry is the only
hard exclusion rule because it establishes that a point belongs to another
place, not that its nutrient value is unusual.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from ..domain.models import Plot, Reading
from .geometry import point_in_polygon

NUTRIENTS = ("N", "P", "K")


@dataclass(frozen=True)
class QualityAnnotation:
    reading_id: str
    valid_for_model: bool
    suspicious: bool
    method: str | None
    score: float | None
    reason: str | None


def annotate_quality(
    plot: Plot,
    readings: list[Reading],
    *,
    seed: int = 42,
    isolation_minimum: int = 12,
) -> list[QualityAnnotation]:
    inside = [
        point_in_polygon(reading.latitude, reading.longitude, plot.boundary)
        for reading in readings
    ]
    valid_indices = [index for index, is_inside in enumerate(inside) if is_inside]
    values = np.array(
        [
            [readings[index].npk_pct.N, readings[index].npk_pct.P, readings[index].npk_pct.K]
            for index in valid_indices
        ],
        dtype=float,
    )

    mad_scores: dict[int, float] = {}
    if len(values) >= 3:
        median = np.median(values, axis=0)
        mad = np.median(np.abs(values - median), axis=0)
        scale = np.where(mad > 1e-12, mad, 1.0)
        robust = np.abs(0.6745 * (values - median) / scale)
        for local_index, original_index in enumerate(valid_indices):
            mad_scores[original_index] = float(np.max(robust[local_index]))

    isolation_scores: dict[int, float] = {}
    if len(values) >= isolation_minimum:
        standardized = StandardScaler().fit_transform(values)
        detector = IsolationForest(
            n_estimators=100,
            contamination="auto",
            random_state=seed,
        )
        detector.fit(standardized)
        raw_scores = -detector.score_samples(standardized)
        cutoff = float(np.quantile(raw_scores, 0.90))
        for local_index, original_index in enumerate(valid_indices):
            if raw_scores[local_index] >= cutoff:
                isolation_scores[original_index] = float(raw_scores[local_index])

    annotations: list[QualityAnnotation] = []
    for index, reading in enumerate(readings):
        if not inside[index]:
            annotations.append(QualityAnnotation(
                reading_id=reading.id,
                valid_for_model=False,
                suspicious=False,
                method="geometry/polygon-v1",
                score=None,
                reason="measurement is outside the declared plot boundary",
            ))
            continue

        mad_score = mad_scores.get(index, 0.0)
        isolation_score = isolation_scores.get(index)
        mad_suspicious = mad_score > 3.5
        isolation_suspicious = isolation_score is not None
        methods: list[str] = []
        reasons: list[str] = []
        if mad_suspicious:
            methods.append("median-mad/v1")
            reasons.append(f"robust MAD score {mad_score:.2f} exceeds 3.50")
        if isolation_suspicious:
            methods.append("isolation-forest/v1")
            reasons.append("Isolation Forest score is in the most unusual 10%")
        score = max(mad_score, isolation_score or 0.0) if methods else mad_score
        annotations.append(QualityAnnotation(
            reading_id=reading.id,
            valid_for_model=True,
            suspicious=mad_suspicious or isolation_suspicious,
            method=" + ".join(methods) if methods else "median-mad/v1",
            score=round(score, 6),
            reason="; ".join(reasons) if reasons else None,
        ))
    return annotations
