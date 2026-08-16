"""Excel/CSV ingestion that preserves the sensor's percentage readings."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from ..domain.models import NPKPercent, Plot, Reading
from ..ml.geometry import point_in_polygon
from ..repositories import SQLiteRepository
from ..repositories.sqlite import stable_id


class ImportValidationError(ValueError):
    pass


class ReadingImporter:
    def __init__(self, repository: SQLiteRepository, max_bytes: int):
        self.repository = repository
        self.max_bytes = max_bytes

    def import_file(
        self,
        *,
        plot: Plot,
        filename: str,
        content: bytes,
        measured_at: datetime | None = None,
    ) -> dict[str, Any]:
        if not content:
            raise ImportValidationError("uploaded file is empty")
        if len(content) > self.max_bytes:
            raise ImportValidationError(
                f"uploaded file exceeds the {self.max_bytes} byte limit"
            )
        suffix = Path(filename or "").suffix.lower()
        try:
            if suffix in {".xlsx", ".xls"}:
                frame = pd.read_excel(BytesIO(content))
            elif suffix == ".csv":
                frame = pd.read_csv(StringIO(content.decode("utf-8-sig")))
            else:
                raise ImportValidationError("only .xlsx, .xls and .csv files are accepted")
        except ImportValidationError:
            raise
        except (ValueError, UnicodeDecodeError, OSError) as error:
            raise ImportValidationError(f"could not parse tabular file: {error}") from error
        return self.import_frame(
            plot=plot,
            frame=frame,
            import_hash=hashlib.sha256(content).hexdigest(),
            measured_at=measured_at,
        )

    def import_path(self, *, plot: Plot, path: str | Path) -> dict[str, Any]:
        file_path = Path(path)
        return self.import_file(
            plot=plot,
            filename=file_path.name,
            content=file_path.read_bytes(),
            measured_at=datetime.fromtimestamp(file_path.stat().st_mtime, timezone.utc),
        )

    def import_frame(
        self,
        *,
        plot: Plot,
        frame: pd.DataFrame,
        import_hash: str,
        measured_at: datetime | None = None,
    ) -> dict[str, Any]:
        normalised = {str(column).strip().lower(): column for column in frame.columns}
        required = {"latitud", "longitud", "n", "p", "k"}
        if not required.issubset(normalised):
            missing = ", ".join(sorted(required - set(normalised)))
            raise ImportValidationError(f"missing columns: {missing}")
        timestamp = measured_at or datetime.now(timezone.utc)
        readings: list[Reading] = []
        for position, (_, row) in enumerate(frame.iterrows(), start=1):
            try:
                latitude = float(row[normalised["latitud"]])
                longitude = float(row[normalised["longitud"]])
                npk = NPKPercent(
                    N=float(row[normalised["n"]]),
                    P=float(row[normalised["p"]]),
                    K=float(row[normalised["k"]]),
                )
            except (TypeError, ValueError) as error:
                raise ImportValidationError(f"invalid row {position}: {error}") from error
            client_id = f"import:{plot.id}:{import_hash}:{position}"
            readings.append(Reading(
                id=stable_id("reading", client_id),
                plot_id=plot.id,
                latitude=latitude,
                longitude=longitude,
                npk_pct=npk,
                measured_at=timestamp,
                client_id=client_id,
                valid_for_model=point_in_polygon(latitude, longitude, plot.boundary),
            ))
        if not readings:
            raise ImportValidationError("file contains no readings")
        stored, created = self.repository.create_readings(readings)
        first = stored[0]
        return {
            "plot_id": plot.id,
            "rows_received": len(readings),
            "rows_created": created,
            "rows_idempotent": len(readings) - created,
            "first_reading": {
                "id": first.id,
                "N": first.npk_pct.N,
                "P": first.npk_pct.P,
                "K": first.npk_pct.K,
                "unit": "mass_pct",
                "basis": "elemental_mass_pct",
            },
            "conversion_applied": False,
            "warning": "Sensor values were persisted as percentages; no unit conversion was applied.",
        }
