"""Dependency-light geospatial helpers for small agricultural plots."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np


def to_local_meters(
    latitude: float,
    longitude: float,
    origin_latitude: float,
    origin_longitude: float,
) -> tuple[float, float]:
    x = (longitude - origin_longitude) * 111_320.0 * math.cos(math.radians(origin_latitude))
    y = (latitude - origin_latitude) * 110_540.0
    return float(x), float(y)


def to_lat_lon(
    x: float,
    y: float,
    origin_latitude: float,
    origin_longitude: float,
) -> tuple[float, float]:
    longitude = origin_longitude + x / (
        111_320.0 * math.cos(math.radians(origin_latitude))
    )
    latitude = origin_latitude + y / 110_540.0
    return float(latitude), float(longitude)


def point_in_polygon(
    latitude: float,
    longitude: float,
    boundary: Iterable[tuple[float, float]],
) -> bool:
    """Ray casting with boundary points expressed as ``(lat, lon)``."""

    polygon = list(boundary)
    inside = False
    x, y = longitude, latitude
    for index, (lat_a, lon_a) in enumerate(polygon):
        lat_b, lon_b = polygon[(index + 1) % len(polygon)]
        x_a, y_a = lon_a, lat_a
        x_b, y_b = lon_b, lat_b
        cross = (y_a > y) != (y_b > y)
        if cross:
            x_intersection = (x_b - x_a) * (y - y_a) / (y_b - y_a) + x_a
            if x <= x_intersection:
                inside = not inside
    return inside


def polygon_area_ha(boundary: list[tuple[float, float]]) -> float:
    origin_latitude = float(np.mean([point[0] for point in boundary]))
    origin_longitude = float(np.mean([point[1] for point in boundary]))
    local = [
        to_local_meters(lat, lon, origin_latitude, origin_longitude)
        for lat, lon in boundary
    ]
    area_m2 = abs(
        sum(
            x_a * y_b - x_b * y_a
            for (x_a, y_a), (x_b, y_b) in zip(local, local[1:] + local[:1])
        )
    ) / 2
    return area_m2 / 10_000
