"""Transactional SQLite persistence for the zero-cost demo."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from ..domain.models import CropProfile, Formulation, NPKPercent, Plot, Producer, Reading


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _loads(value: str | None, default: Any = None) -> Any:
    return default if value is None else json.loads(value)


def stable_id(prefix: str, value: str, length: int = 16) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]}"


class _ClosingConnection(sqlite3.Connection):
    """Make ``with connection`` commit/rollback and release the file handle."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class SQLiteRepository:
    def __init__(self, db_path: str | Path, migrations_path: str | Path | None = None):
        self.db_path = str(db_path)
        self.migrations_path = Path(migrations_path or Path(__file__).with_name("migrations"))
        if self.db_path != ":memory:":
            Path(self.db_path).resolve().parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path, timeout=30, isolation_level=None, factory=_ClosingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        if self.db_path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for migration in sorted(self.migrations_path.glob("*.sql")):
                if migration.name in applied:
                    continue
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (migration.name, utc_now()),
                )

    def ready(self) -> bool:
        try:
            with self.connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    # -- configuration -------------------------------------------------

    def upsert_center(self, center: dict[str, Any]) -> None:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO centers(id, name, municipality, version, validation_status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                     municipality=excluded.municipality, version=excluded.version,
                     validation_status=excluded.validation_status, updated_at=excluded.updated_at""",
                (
                    center["id"], center["name"], center["municipality"], center["version"],
                    center["validation_status"], now, now,
                ),
            )

    def list_centers(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM centers ORDER BY name")]

    def get_center(self, center_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM centers WHERE id = ?", (center_id,)).fetchone()
            return dict(row) if row else None

    def upsert_producer(self, producer: Producer, actor: str = "system") -> None:
        now = utc_now()
        consent_updated_at = (
            producer.consent_updated_at.isoformat() if producer.consent_updated_at else None
        )
        with self.transaction() as connection:
            existing = connection.execute(
                """SELECT center_id, display_name, municipality, data_origin,
                          consent_status, consent_updated_at
                   FROM producers WHERE id = ?""",
                (producer.id,),
            ).fetchone()
            incoming = (
                producer.center_id, producer.display_name, producer.municipality,
                producer.data_origin, producer.consent_status, consent_updated_at,
            )
            changed = existing is None or tuple(existing) != incoming
            connection.execute(
                """INSERT INTO producers(id, center_id, display_name, municipality, data_origin,
                                         consent_status, consent_updated_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET center_id=excluded.center_id,
                     display_name=excluded.display_name, municipality=excluded.municipality,
                     data_origin=excluded.data_origin, consent_status=excluded.consent_status,
                     consent_updated_at=excluded.consent_updated_at,
                     updated_at=excluded.updated_at""",
                (
                    producer.id, producer.center_id, producer.display_name,
                    producer.municipality, producer.data_origin, producer.consent_status,
                    consent_updated_at, now, now,
                ),
            )
            if changed:
                self._append_audit(
                    connection,
                    "producer_created" if existing is None else "producer_updated",
                    "producer",
                    producer.id,
                    actor,
                    {
                        "center_id": producer.center_id,
                        "data_origin": producer.data_origin,
                        "consent_status": producer.consent_status,
                    },
                    now,
                )

    def list_producers(self, center_id: str) -> list[Producer]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM producers WHERE center_id = ? ORDER BY display_name",
                (center_id,),
            ).fetchall()
            return [self._producer_row(row) for row in rows]

    def get_producer(self, producer_id: str) -> Producer | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM producers WHERE id = ?", (producer_id,)
            ).fetchone()
            return self._producer_row(row) if row else None

    @staticmethod
    def _producer_row(row: sqlite3.Row) -> Producer:
        return Producer(
            id=row["id"], center_id=row["center_id"], display_name=row["display_name"],
            municipality=row["municipality"], data_origin=row["data_origin"],
            consent_status=row["consent_status"],
            consent_updated_at=row["consent_updated_at"], created_at=row["created_at"],
        )

    def upsert_crop_profile(self, profile: CropProfile) -> None:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO crop_profiles(id, profile_json, version, validation_status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET profile_json=excluded.profile_json,
                     version=excluded.version, validation_status=excluded.validation_status,
                     updated_at=excluded.updated_at""",
                (profile.id, _json(profile), profile.version, profile.validation_status, now, now),
            )

    def list_crop_profiles(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT profile_json FROM crop_profiles ORDER BY id").fetchall()
            return [_loads(row["profile_json"]) for row in rows]

    def get_crop_profile(self, profile_id: str) -> CropProfile | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT profile_json FROM crop_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            return CropProfile.model_validate_json(row["profile_json"]) if row else None

    def upsert_plot(self, plot: Plot) -> None:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO plots(id, center_id, producer_id, crop_profile_id, name,
                                      municipality, boundary_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET center_id=excluded.center_id,
                     producer_id=excluded.producer_id,
                     crop_profile_id=excluded.crop_profile_id, name=excluded.name,
                     municipality=excluded.municipality, boundary_json=excluded.boundary_json,
                     updated_at=excluded.updated_at""",
                (
                    plot.id, plot.center_id, plot.producer_id, plot.crop_profile_id, plot.name,
                    plot.municipality, _json(plot.boundary), now, now,
                ),
            )

    def list_plots(
        self,
        *,
        center_id: str | None = None,
        producer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if center_id:
            where.append("p.center_id = ?")
            params.append(center_id)
        if producer_id:
            where.append("p.producer_id = ?")
            params.append(producer_id)
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT p.*, COUNT(r.id) AS reading_count
                    FROM plots p LEFT JOIN readings r ON r.plot_id = p.id
                    {clause}
                    GROUP BY p.id ORDER BY p.name""",
                params,
            ).fetchall()
            return [self._plot_row(row) | {"reading_count": row["reading_count"]} for row in rows]

    def get_plot(self, plot_id: str) -> Plot | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM plots WHERE id = ?", (plot_id,)).fetchone()
            return Plot.model_validate(self._plot_row(row)) if row else None

    @staticmethod
    def _plot_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "center_id": row["center_id"],
            "producer_id": row["producer_id"],
            "crop_profile_id": row["crop_profile_id"], "name": row["name"],
            "municipality": row["municipality"], "boundary": _loads(row["boundary_json"]),
            "created_at": row["created_at"],
        }

    def upsert_formulation(self, formulation: Formulation, actor: str = "system") -> None:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO formulations(id, center_id, label, formulation_json, available,
                                             valid_from, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET label=excluded.label,
                     formulation_json=excluded.formulation_json, available=excluded.available,
                     valid_from=excluded.valid_from, updated_at=excluded.updated_at""",
                (
                    formulation.id, formulation.center_id, formulation.label, _json(formulation),
                    int(formulation.available), formulation.valid_from.isoformat(), now, now,
                ),
            )
            self._append_audit(
                connection, "formulation_saved", "formulation", formulation.id,
                actor, {"center_id": formulation.center_id, "label": formulation.label}, now,
            )

    def list_formulations(self, center_id: str, active_only: bool = False) -> list[Formulation]:
        sql = "SELECT formulation_json FROM formulations WHERE center_id = ?"
        params: list[Any] = [center_id]
        if active_only:
            sql += " AND available = 1"
        sql += " ORDER BY label"
        with self.connect() as connection:
            return [
                Formulation.model_validate_json(row["formulation_json"])
                for row in connection.execute(sql, params).fetchall()
            ]

    def get_formulation(self, center_id: str, formulation_id: str) -> Formulation | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT formulation_json FROM formulations WHERE center_id = ? AND id = ?",
                (center_id, formulation_id),
            ).fetchone()
            return Formulation.model_validate_json(row["formulation_json"]) if row else None

    # -- readings ------------------------------------------------------

    def create_reading(self, reading: Reading) -> tuple[Reading, bool]:
        now = utc_now()
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM readings WHERE client_id = ?", (reading.client_id,)
            ).fetchone()
            if existing:
                return self._reading_row(existing), False
            connection.execute(
                """INSERT INTO readings(id, plot_id, latitude, longitude, n_pct, p_pct, k_pct,
                                        basis, measured_at, client_id, valid_for_model, suspicious,
                                        anomaly_method, anomaly_score, anomaly_reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    reading.id, reading.plot_id, reading.latitude, reading.longitude,
                    reading.npk_pct.N, reading.npk_pct.P, reading.npk_pct.K,
                    reading.npk_pct.basis, reading.measured_at.isoformat(), reading.client_id,
                    int(reading.valid_for_model), int(reading.suspicious), reading.anomaly_method,
                    reading.anomaly_score, reading.anomaly_reason, now,
                ),
            )
            self._append_audit(
                connection, "reading_recorded", "reading", reading.id, "system",
                {"plot_id": reading.plot_id, "client_id": reading.client_id}, now,
            )
            return reading, True

    def create_readings(self, readings: Sequence[Reading]) -> tuple[list[Reading], int]:
        stored: list[Reading] = []
        created = 0
        with self.transaction() as connection:
            for reading in readings:
                existing = connection.execute(
                    "SELECT * FROM readings WHERE client_id = ?", (reading.client_id,)
                ).fetchone()
                if existing:
                    stored.append(self._reading_row(existing))
                    continue
                now = utc_now()
                connection.execute(
                    """INSERT INTO readings(id, plot_id, latitude, longitude, n_pct, p_pct, k_pct,
                                            basis, measured_at, client_id, valid_for_model, suspicious,
                                            anomaly_method, anomaly_score, anomaly_reason, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        reading.id, reading.plot_id, reading.latitude, reading.longitude,
                        reading.npk_pct.N, reading.npk_pct.P, reading.npk_pct.K,
                        reading.npk_pct.basis, reading.measured_at.isoformat(), reading.client_id,
                        int(reading.valid_for_model), int(reading.suspicious), reading.anomaly_method,
                        reading.anomaly_score, reading.anomaly_reason, now,
                    ),
                )
                self._append_audit(
                    connection, "reading_recorded", "reading", reading.id, "system",
                    {"plot_id": reading.plot_id, "client_id": reading.client_id}, now,
                )
                stored.append(reading)
                created += 1
        return stored, created

    def count_readings(self, plot_id: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM readings WHERE plot_id = ?", (plot_id,)
            ).fetchone()
            return int(row["total"])

    def list_readings(self, plot_id: str, valid_only: bool = False) -> list[Reading]:
        sql = "SELECT * FROM readings WHERE plot_id = ?"
        if valid_only:
            sql += " AND valid_for_model = 1"
        sql += " ORDER BY measured_at, rowid"
        with self.connect() as connection:
            return [self._reading_row(row) for row in connection.execute(sql, (plot_id,))]

    def update_reading_qualities(self, annotations: Sequence[dict[str, Any]]) -> int:
        """Persiste las anotaciones de calidad de un recálculo en una sola transacción.

        Antes cada lectura abría su propia conexión y su propio BEGIN IMMEDIATE:
        19 transacciones por recálculo en la ruta caliente de la demo.
        """

        if not annotations:
            return 0
        rows = [
            (
                int(item["valid_for_model"]), int(item["suspicious"]), item["method"],
                item["score"], item["reason"], item["reading_id"],
            )
            for item in annotations
        ]
        with self.transaction() as connection:
            connection.executemany(
                """UPDATE readings SET valid_for_model=?, suspicious=?, anomaly_method=?,
                                      anomaly_score=?, anomaly_reason=? WHERE id=?""",
                rows,
            )
        return len(rows)

    @staticmethod
    def _reading_row(row: sqlite3.Row) -> Reading:
        return Reading(
            id=row["id"], plot_id=row["plot_id"], latitude=row["latitude"],
            longitude=row["longitude"],
            npk_pct=NPKPercent(N=row["n_pct"], P=row["p_pct"], K=row["k_pct"]),
            measured_at=row["measured_at"], client_id=row["client_id"],
            valid_for_model=bool(row["valid_for_model"]), suspicious=bool(row["suspicious"]),
            anomaly_method=row["anomaly_method"], anomaly_score=row["anomaly_score"],
            anomaly_reason=row["anomaly_reason"],
        )

    # -- model, package and governance --------------------------------

    def save_model_run(self, run: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO model_runs(id, plot_id, model_name, model_version, parameters_json,
                                          observation_count, metrics_json, inference_ms, input_hash,
                                          limitations_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run["id"], run["plot_id"], run["model_name"], run["model_version"],
                    _json(run["parameters"]), run["observation_count"], _json(run["metrics"]),
                    run["inference_ms"], run["input_hash"], _json(run["limitations"]),
                    run.get("created_at", utc_now()),
                ),
            )

    def list_model_runs(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM model_runs ORDER BY created_at DESC").fetchall()
            return [self._model_run_row(row) for row in rows]

    def get_model_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM model_runs WHERE id = ?", (run_id,)).fetchone()
            return self._model_run_row(row) if row else None

    @staticmethod
    def _model_run_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for source, target in (
            ("parameters_json", "parameters"), ("metrics_json", "metrics"),
            ("limitations_json", "limitations"),
        ):
            data[target] = _loads(data.pop(source))
        return data

    def save_package(self, package: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO packages(id, plot_id, model_run_id, contract_version,
                                        snapshot_json, degraded, generated_at)
                   VALUES (?, ?, ?, '2.0', ?, ?, ?)""",
                (
                    package["id"], package["plot"]["id"], package["model_run"]["id"],
                    _json(package), int(package["degraded"]), package["generated_at"],
                ),
            )

    def latest_package(self, plot_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT snapshot_json FROM packages WHERE plot_id = ?
                   ORDER BY generated_at DESC, rowid DESC LIMIT 1""", (plot_id,)
            ).fetchone()
            return _loads(row["snapshot_json"]) if row else None

    # Proyección del último package por lote para vistas de lista. Un snapshot
    # completo lleva la grilla entera; el tablero del centro solo necesita seis
    # campos y no puede pagar ese parseo una vez por lote de la red.
    _PACKAGE_DIGEST_SQL = """
        SELECT p.plot_id,
               p.id                                            AS package_id,
               p.generated_at,
               p.degraded,
               json_extract(p.snapshot_json, '$.plot.area.value')        AS area_ha,
               json_extract(p.snapshot_json, '$.validation_status')      AS validation_status,
               json_extract(p.snapshot_json, '$.proposal.status')        AS proposal_status,
               json_extract(p.snapshot_json, '$.climate.risks')          AS risks_json
        FROM packages p
        JOIN (
            SELECT plot_id, MAX(generated_at) AS generated_at, MAX(rowid) AS rowid
            FROM packages GROUP BY plot_id
        ) latest
          ON latest.plot_id = p.plot_id AND latest.rowid = p.rowid
    """

    def latest_package_digests(self, plot_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        if not plot_ids:
            return {}
        placeholders = ",".join("?" for _ in plot_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"{self._PACKAGE_DIGEST_SQL} WHERE p.plot_id IN ({placeholders})",
                list(plot_ids),
            ).fetchall()
        return {
            row["plot_id"]: {
                "id": row["package_id"],
                "generated_at": row["generated_at"],
                "degraded": bool(row["degraded"]),
                "area_ha": row["area_ha"],
                "validation_status": row["validation_status"],
                "proposal_status": row["proposal_status"],
                "risks": _loads(row["risks_json"], []),
            }
            for row in rows
        }

    def reading_digests(self, plot_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Conteos y última fecha por lote sin traer las lecturas a memoria."""

        if not plot_ids:
            return {}
        placeholders = ",".join("?" for _ in plot_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT plot_id,
                           COUNT(*)                                   AS total,
                           SUM(valid_for_model)                       AS valid,
                           SUM(suspicious)                            AS suspicious,
                           SUM(CASE WHEN valid_for_model = 0 THEN 1 ELSE 0 END) AS outside,
                           MAX(measured_at)                           AS latest_measured_at
                    FROM readings WHERE plot_id IN ({placeholders})
                    GROUP BY plot_id""",
                list(plot_ids),
            ).fetchall()
        return {
            row["plot_id"]: {
                "total": int(row["total"]),
                "valid": int(row["valid"] or 0),
                "suspicious": int(row["suspicious"] or 0),
                "outside": int(row["outside"] or 0),
                "latest_measured_at": row["latest_measured_at"],
            }
            for row in rows
        }

    def save_proposal(self, proposal: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO proposals(id, plot_id, package_id, proposal_json, status,
                                         validation_status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    proposal["id"], proposal["plot_id"], proposal["package_id"],
                    _json(proposal), proposal["validation_status"], proposal["created_at"],
                ),
            )

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT proposal_json FROM proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            return _loads(row["proposal_json"]) if row else None

    def latest_proposal_for_plot(self, plot_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT proposal_json FROM proposals WHERE plot_id = ?
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""", (plot_id,)
            ).fetchone()
            return _loads(row["proposal_json"]) if row else None

    def save_decision(self, decision: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO decisions(id, proposal_id, action, resulting_status,
                                         actor_type, actor_id, modification_json, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision["id"], decision["proposal_id"], decision["action"],
                    decision["resulting_status"], decision["actor_type"], decision["actor_id"],
                    _json(decision.get("modification")) if decision.get("modification") else None,
                    decision.get("note"), decision["created_at"],
                ),
            )

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
            return self._decision_row(row) if row else None

    def list_decisions(self, proposal_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM decisions WHERE proposal_id = ? ORDER BY created_at, rowid",
                (proposal_id,),
            ).fetchall()
            return [self._decision_row(row) for row in rows]

    @staticmethod
    def _decision_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["modification"] = _loads(data.pop("modification_json"))
        return data

    def append_audit(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor: str,
        payload: dict[str, Any],
    ) -> str:
        with self.transaction() as connection:
            return self._append_audit(
                connection, event_type, entity_type, entity_id, actor, payload, utc_now()
            )

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> str:
        event_id = stable_id("evt", f"{event_type}|{entity_type}|{entity_id}|{created_at}|{_json(payload)}")
        connection.execute(
            """INSERT INTO audit_log(event_id, event_type, entity_type, entity_id,
                                     actor, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id, event_type, entity_type, entity_id, actor, _json(payload), created_at),
        )
        return event_id

    def audit_history(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM audit_log WHERE entity_type = ? AND entity_id = ?
                   ORDER BY sequence""", (entity_type, entity_id),
            ).fetchall()
            output = []
            for row in rows:
                item = dict(row)
                item["payload"] = _loads(item.pop("payload_json"))
                output.append(item)
            return output

    def audit_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            return {
                row["event_type"]: row["total"]
                for row in connection.execute(
                    "SELECT event_type, COUNT(*) AS total FROM audit_log GROUP BY event_type"
                )
            }

    # -- durable external cache ---------------------------------------

    def get_external_cache(self, source: str, cache_key: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM external_api_cache WHERE source = ? AND cache_key = ?",
                (source, cache_key),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["payload"] = _loads(data.pop("payload_json"))
            return data

    def put_external_cache(
        self,
        source: str,
        cache_key: str,
        payload: dict[str, Any],
        fetched_at: str,
        expires_at: str,
        source_url: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO external_api_cache(source, cache_key, payload_json, fetched_at,
                                                  expires_at, source_url, failure_count, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                   ON CONFLICT(source, cache_key) DO UPDATE SET payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at, expires_at=excluded.expires_at,
                     source_url=excluded.source_url, last_failure_at=NULL, last_error=NULL,
                     failure_count=0, circuit_open_until=NULL, updated_at=excluded.updated_at""",
                (source, cache_key, _json(payload), fetched_at, expires_at, source_url, utc_now()),
            )

    def record_external_failure(
        self,
        source: str,
        cache_key: str,
        failed_at: str,
        error: str,
        circuit_open_until: str | None,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO external_api_cache(source, cache_key, last_failure_at, last_error,
                                                  failure_count, circuit_open_until, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?)
                   ON CONFLICT(source, cache_key) DO UPDATE SET last_failure_at=excluded.last_failure_at,
                     last_error=excluded.last_error, failure_count=external_api_cache.failure_count + 1,
                     circuit_open_until=excluded.circuit_open_until, updated_at=excluded.updated_at""",
                (source, cache_key, failed_at, error[:500], circuit_open_until, utc_now()),
            )
