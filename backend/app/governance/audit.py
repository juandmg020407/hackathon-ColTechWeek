"""
Registro append-only. AI Act art. 12.

Tres tablas y una sola regla: aqui no se corrige nada, se agrega. Una
propuesta modificada es una fila nueva; una decision revocada es una fila
nueva. El pasado del sistema no se puede reescribir.

La regla no es una promesa del codigo: son disparadores de SQLite que
abortan cualquier UPDATE o DELETE. Se puede verificar desde afuera con el
cliente de sqlite3, sin confiar en nosotros. Eso es lo que hace auditable
un sistema, no un parrafo en un README.

    sqlite3 backend/sereno.sqlite3 "UPDATE audit_log SET actor='otro';"
    Error: el registro de auditoria es append-only (AI Act art. 12)

En produccion esto vive en Postgres con la misma forma. Se eligio SQLite
para la demo por una razon operativa: no depende de que la red del recinto
aguante, y el archivo se puede abrir delante del jurado.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from ..config import settings

RUTA = pathlib.Path(settings.db_path)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id           TEXT PRIMARY KEY,
    plot_id      TEXT NOT NULL,
    zona_id      TEXT,
    tipo         TEXT NOT NULL,
    payload      TEXT NOT NULL,
    costo_cop    INTEGER NOT NULL DEFAULT 0,
    creado       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id            TEXT PRIMARY KEY,
    proposal_id   TEXT NOT NULL,
    accion        TEXT NOT NULL,
    estado        TEXT NOT NULL,
    actor_tipo    TEXT NOT NULL,
    actor_id      TEXT NOT NULL,
    modificacion  TEXT,
    nota          TEXT,
    creado        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evento          TEXT NOT NULL,
    entidad         TEXT NOT NULL,
    entidad_id      TEXT NOT NULL,
    modelo_version  TEXT,
    entradas        TEXT,
    fuentes         TEXT,
    actor           TEXT,
    creado          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_decisions_proposal ON decisions(proposal_id);
CREATE INDEX IF NOT EXISTS ix_audit_entidad      ON audit_log(entidad, entidad_id);
"""

# Sin UPDATE y sin DELETE. La restriccion vive en la base, no en el codigo.
CANDADOS = """
CREATE TRIGGER IF NOT EXISTS decisions_sin_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'las decisiones son append-only (AI Act art. 12)'); END;

CREATE TRIGGER IF NOT EXISTS decisions_sin_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'las decisiones son append-only (AI Act art. 12)'); END;

CREATE TRIGGER IF NOT EXISTS audit_sin_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'el registro de auditoria es append-only (AI Act art. 12)'); END;

CREATE TRIGGER IF NOT EXISTS audit_sin_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'el registro de auditoria es append-only (AI Act art. 12)'); END;
"""


@contextmanager
def _conexion() -> Iterator[sqlite3.Connection]:
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(RUTA)
    cx.row_factory = sqlite3.Row
    try:
        with cx:
            yield cx
    finally:
        cx.close()


def preparar() -> None:
    """Crea el esquema y los candados. Idempotente: se llama en cada arranque."""
    with _conexion() as cx:
        cx.executescript(ESQUEMA)
        cx.executescript(CANDADOS)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------- escribir

def registrar(evento: str, entidad: str, entidad_id: str, *,
              modelo_version: str | None = None,
              entradas: dict | None = None,
              fuentes: list | None = None,
              actor: str | None = None) -> None:
    """Una linea en el diario del sistema. Nunca falla hacia afuera: si el
    registro no se puede escribir, se pierde la traza pero no la respuesta
    al agricultor, que esta parado en el potrero esperando."""
    try:
        with _conexion() as cx:
            cx.execute(
                "INSERT INTO audit_log (evento, entidad, entidad_id, modelo_version,"
                " entradas, fuentes, actor, creado) VALUES (?,?,?,?,?,?,?,?)",
                (evento, entidad, entidad_id, modelo_version,
                 json.dumps(entradas, ensure_ascii=False, default=str) if entradas else None,
                 json.dumps(fuentes, ensure_ascii=False, default=str) if fuentes else None,
                 actor, _ahora()),
            )
    except sqlite3.Error:
        pass


def guardar_propuesta(id_: str, plot_id: str, zona_id: str | None, tipo: str,
                      payload: dict, costo_cop: int) -> None:
    """
    Congela lo que se propuso, con su costo. Es lo que permite que el
    `por que` de manana explique la propuesta de hoy y no una recalculada
    con datos nuevos.

    Mientras nadie haya decidido, la propuesta se refresca con cada paquete
    nuevo: es solo una sugerencia vigente. En cuanto alguien decide sobre
    ella queda sellada, porque a partir de ahi es la prueba de sobre que
    exactamente decidio esa persona. Cada version que pasa por aqui queda
    igual en audit_log, que si es intocable.
    """
    with _conexion() as cx:
        decidida = cx.execute(
            "SELECT 1 FROM decisions WHERE proposal_id = ? LIMIT 1", (id_,)
        ).fetchone()
        if decidida:
            return
        cx.execute(
            "INSERT OR REPLACE INTO proposals (id, plot_id, zona_id, tipo, payload,"
            " costo_cop, creado) VALUES (?,?,?,?,?,?,?)",
            (id_, plot_id, zona_id, tipo,
             json.dumps(payload, ensure_ascii=False, default=str), costo_cop, _ahora()),
        )


def guardar_decision(id_: str, proposal_id: str, accion: str, estado: str,
                     actor_tipo: str, actor_id: str,
                     modificacion: dict | None, nota: str | None) -> None:
    with _conexion() as cx:
        cx.execute(
            "INSERT INTO decisions (id, proposal_id, accion, estado, actor_tipo,"
            " actor_id, modificacion, nota, creado) VALUES (?,?,?,?,?,?,?,?,?)",
            (id_, proposal_id, accion, estado, actor_tipo, actor_id,
             json.dumps(modificacion, ensure_ascii=False, default=str) if modificacion else None,
             nota, _ahora()),
        )


# --------------------------------------------------------------- leer

def propuesta(id_: str) -> dict | None:
    with _conexion() as cx:
        fila = cx.execute("SELECT * FROM proposals WHERE id = ?", (id_,)).fetchone()
    if fila is None:
        return None
    d = dict(fila)
    d["payload"] = json.loads(d["payload"])
    return d


def propuestas_del_lote(plot_id: str) -> list[dict]:
    with _conexion() as cx:
        filas = cx.execute(
            "SELECT id, zona_id, costo_cop FROM proposals WHERE plot_id = ?", (plot_id,)
        ).fetchall()
    return [dict(f) for f in filas]


def decision(id_: str) -> dict | None:
    with _conexion() as cx:
        fila = cx.execute("SELECT * FROM decisions WHERE id = ?", (id_,)).fetchone()
    return _decision(fila) if fila else None


def decisiones_de(proposal_id: str) -> list[dict]:
    """Todas las decisiones sobre una propuesta, de la mas vieja a la mas
    nueva. La ultima es la que manda; las anteriores siguen ahi."""
    with _conexion() as cx:
        filas = cx.execute(
            "SELECT * FROM decisions WHERE proposal_id = ? ORDER BY creado, rowid",
            (proposal_id,),
        ).fetchall()
    return [_decision(f) for f in filas]


def _decision(fila: sqlite3.Row) -> dict:
    d = dict(fila)
    if d.get("modificacion"):
        d["modificacion"] = json.loads(d["modificacion"])
    return d


def historial(entidad: str, entidad_id: str, limite: int = 50) -> list[dict]:
    with _conexion() as cx:
        filas = cx.execute(
            "SELECT * FROM audit_log WHERE entidad = ? AND entidad_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (entidad, entidad_id, limite),
        ).fetchall()
    salida = []
    for f in filas:
        d = dict(f)
        for campo in ("entradas", "fuentes"):
            if d.get(campo):
                d[campo] = json.loads(d[campo])
        salida.append(d)
    return salida


def conteos() -> dict:
    """Cuanto lleva registrado el sistema. Sirve para /v1/public/stats y para
    mostrar en vivo que el diario no esta vacio."""
    with _conexion() as cx:
        return {
            t: cx.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("proposals", "decisions", "audit_log")
        }
