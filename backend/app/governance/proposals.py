"""
Propuestas y el boton «¿por que me dice eso?».

El sistema no recomienda: propone. Cada zona del paquete nace como una
propuesta en estado `pendiente`, con su costo congelado y sus entradas
guardadas. Sin una decision humana no pasa absolutamente nada.

Guardar el payload completo no es redundancia. Si manana el pronostico
cambia y la receta se recalcula, la explicacion de la propuesta de hoy
tiene que seguir diciendo lo que se sabia hoy. Un sistema que reescribe
sus razones a posteriori no es auditable.
"""

from __future__ import annotations

from ..config import settings
from ..ml import soil
from ..schemas import Explicacion, PasoExplicacion, Package
from . import audit

MODELOS = {
    "suelo": "gp/v1",
    "calibracion": "cal/v0-provisional",
    "nutricion": "balance/v1",
    "mezcla": "linprog/v1",
    "riesgo": "engine/v1",
}


def id_de(plot_id: str, zona_id: str) -> str:
    return f"rec-{plot_id}-{zona_id}"


# --------------------------------------------------------------- registrar

def registrar_del_paquete(paquete: Package) -> list[str]:
    """
    Convierte el paquete recien construido en propuestas pendientes, una por
    zona de manejo. Devuelve los identificadores en el mismo orden.
    """
    ids: list[str] = []
    riesgos = [
        {"tipo": r.tipo, "severidad": r.severidad, "titulo": r.titulo,
         "probabilidad": r.probabilidad, "confianza": r.confianza}
        for r in paquete.riesgos
    ]
    ajustes = [a.model_dump() for a in paquete.receta.ajustes]
    fuentes = [f.model_dump() for r in paquete.riesgos for f in r.por_que.fuentes]

    for zona in paquete.zonas:
        celdas = [c for c in zona.celdas if c < len(paquete.grid.sigma)]
        sigma = (
            round(sum(paquete.grid.sigma[c] for c in celdas) / len(celdas), 1)
            if celdas else None
        )
        payload = {
            "plot": paquete.plot.model_dump(),
            "zona": zona.model_dump(exclude={"celdas"}),
            "sigma_medio": sigma,
            "sigma_umbral": paquete.grid.sigma_umbral,
            "puntos_validos": len(paquete.puntos),
            "puntos_sospechosos": sum(1 for p in paquete.puntos if p.sospechoso),
            "puntos_descartados": [d.model_dump() for d in paquete.descartados],
            "riesgos": riesgos,
            "ajustes": ajustes,
            "ventana": paquete.receta.ventana.model_dump(),
            "costo_generico_cop": paquete.receta.costo_generico_cop,
            "generico_detalle": paquete.receta.generico_detalle,
            "degradado": paquete.degradado,
            "generado": paquete.generado.isoformat(),
            "modelos": MODELOS,
        }
        id_ = id_de(paquete.plot.id, zona.id)
        audit.guardar_propuesta(
            id_, paquete.plot.id, zona.id, "fertilizacion", payload, zona.costo_cop,
        )
        audit.registrar(
            "propuesta_generada", "proposal", id_,
            modelo_version=MODELOS["nutricion"],
            entradas={"kg_ha": zona.kg_ha, "nivel": zona.nivel,
                      "promedio_ppm": zona.promedio_ppm, "area_ha": zona.area_ha,
                      "ajustes": ajustes},
            fuentes=fuentes,
            actor="sistema",
        )
        ids.append(id_)
    return ids


# --------------------------------------------------------------- explicar

def _plural(n: int, uno: str, varios: str) -> str:
    return f", {n} {uno if n == 1 else varios}"


def _confianza_del_suelo(payload: dict) -> str:
    sigma, umbral = payload.get("sigma_medio"), payload.get("sigma_umbral") or 8.0
    if sigma is None:
        return "baja"
    if sigma <= umbral:
        return "alta"
    return "media" if sigma <= umbral * 3 else "baja"


def _no_sabemos(payload: dict, confianza: str) -> list[str]:
    """
    Nunca va vacio, y no por formalismo: un sistema que solo declara
    certezas pierde al agricultor la primera vez que se equivoca.
    """
    faltantes = [
        "Cuánto rinde su lote: no tenemos historial de cosecha suyo, así que el "
        "objetivo de 25 toneladas por hectárea es una referencia de la zona, no una predicción.",
        "Si el precio del bulto en su vereda coincide con el de referencia nacional.",
        "Cuánto vale exactamente su suelo en partes por millon: la calibración del "
        "sensor no está validada contra laboratorio todavía.",
    ]
    if confianza != "alta":
        faltantes.append(
            "Qué tan parejo es el suelo entre los puntos que se midieron: en esta zona "
            "el modelo tiene poca certeza y conviene medir mas."
        )
    if payload.get("puntos_sospechosos"):
        faltantes.append(
            f"Si las {payload['puntos_sospechosos']} lecturas marcadas como raras son "
            "suelo de verdad o un punto donde ya habian abonado."
        )
    if payload.get("degradado"):
        faltantes.append(
            "Como esta el clima ahora mismo: alguna fuente externa no respondio y se "
            "uso el último dato bueno que habia guardado."
        )
    return faltantes


def _estado(propuesta_id: str) -> tuple[str, dict | None]:
    """El estado sale del historial, no de un campo mutable. La ultima
    decision manda; las anteriores siguen registradas."""
    decisiones = audit.decisiones_de(propuesta_id)
    if not decisiones:
        return "pendiente", None
    ultima = decisiones[-1]
    return ultima["estado"], ultima


def explicar(propuesta_id: str) -> Explicacion | None:
    fila = audit.propuesta(propuesta_id)
    if fila is None:
        return None

    p = fila["payload"]
    zona = p["zona"]
    confianza = _confianza_del_suelo(p)
    estado, ultima = _estado(propuesta_id)

    productos = zona.get("productos") or []
    que = (
        f"{soil.frase_bultos(productos)} en la zona {zona['id'][-1]} "
        f"({zona['area_ha']} hectáreas)"
        if productos else "por ahora no hace falta aplicar nada en esta zona"
    )

    criticos = [n for n, nivel in (zona.get("nivel") or {}).items() if nivel == "critico"]
    bajos = [n for n, nivel in (zona.get("nivel") or {}).items() if nivel == "bajo"]
    detalle_suelo = ", ".join(
        [f"{n} critico" for n in criticos] + [f"{n} bajo" for n in bajos]
    ) or "todos los nutrientes en nivel adecuado"

    pasos = [
        PasoExplicacion(
            paso="medicion",
            detalle=(
                f"{p['puntos_validos']} puntos validos del sensor"
                + (_plural(len(p["puntos_descartados"]),
                           "descartado por estar fuera del lote",
                           "descartados por estar fuera del lote")
                   if p.get("puntos_descartados") else "")
                + (_plural(p["puntos_sospechosos"],
                           "marcado como lectura rara, pero incluido",
                           "marcados como lecturas raras, pero incluidos")
                   if p.get("puntos_sospechosos") else "")
                + "."
            ),
        ),
        PasoExplicacion(
            paso="suelo",
            detalle=f"Zona {zona['id']}: {detalle_suelo}.",
            confianza=confianza,
            nota=(
                "La calibración del sensor a partes por millon es provisional y no "
                "esta validada contra laboratorio."
            ),
        ),
    ]

    if p.get("riesgos"):
        r = p["riesgos"][0]
        cambios = ", ".join(
            f"{a['nutriente']} por {a['factor']}" for a in (p.get("ajustes") or [])
        )
        pasos.append(PasoExplicacion(
            paso="clima",
            detalle=(
                f"{r['titulo']} ({r['severidad']}). "
                + (f"Por eso se movio la dosis: {cambios}." if cambios
                   else "No cambio la dosis, pero si la ventana de aplicación.")
            ),
            confianza=r.get("confianza"),
        ))

    pasos.append(PasoExplicacion(
        paso="costo",
        detalle=(
            f"Es la mezcla más barata que cubre el faltante: {zona.get('costo_cop', 0):,} pesos "
            f"frente a {p.get('costo_generico_cop', 0):,} de la fórmula genérica "
            f"({p.get('generico_detalle', 'sin detalle')})."
        ).replace(",", "."),
        nota="Precios de referencia nacional, no de su vereda.",
    ))

    pasos.append(PasoExplicacion(
        paso="cuando",
        detalle=f"{p['ventana']['desde']}: {p['ventana']['motivo']}",
    ))

    return Explicacion(
        propuesta=propuesta_id,
        que_recomendamos=que,
        porque=pasos,
        no_sabemos=_no_sabemos(p, confianza),
        modelo=p.get("modelos") or MODELOS,
        decidido_por=(
            {"tipo": ultima["actor_tipo"], "id": ultima["actor_id"]} if ultima else None
        ),
        estado=estado,
    )


# --------------------------------------------------------------- decidir

ESTADO_DE = {
    "aceptar": "aceptada",
    "rechazar": "rechazada",
    "derivar": "derivada",
    "modificar": "modificada",
}


def comprometido(plot_id: str, excepto: str | None = None) -> int:
    """
    Lo que el agricultor ya lleva aceptado en este lote.

    Existe para cerrar un hueco concreto: el lote tiene tres zonas y cada
    una es una propuesta suelta. Si el umbral se midiera propuesta por
    propuesta, aceptar las tres por separado se salta la doble firma sin
    que nadie tenga que hacer trampa a proposito. El control tiene que
    mirar el gasto del lote, no el de la linea.
    """
    total = 0
    for p in audit.propuestas_del_lote(plot_id):
        if p["id"] == excepto:
            continue
        estado, _ = _estado(p["id"])
        if estado in ("aceptada", "modificada"):
            total += int(p["costo_cop"] or 0)
    return total


def evaluar_decision(propuesta: dict, accion: str, actor_tipo: str) -> tuple[str, bool, str | None]:
    """
    Devuelve (estado, requiere_revision_tecnica, motivo).

    La doble firma solo aplica a aceptar y a modificar: rechazar o derivar
    nunca gastan plata, y ponerle friccion a un «no» empuja al agricultor a
    aceptar por inercia, que es justo lo contrario de la supervision humana.
    """
    estado = ESTADO_DE[accion]
    if accion in ("rechazar", "derivar"):
        return estado, False, None

    costo = int(propuesta.get("costo_cop") or 0)
    previo = comprometido(propuesta["plot_id"], excepto=propuesta["id"])
    acumulado = costo + previo

    if acumulado <= settings.umbral_revision_cop or actor_tipo == "tecnico":
        return estado, False, None

    plata = lambda v: "$" + f"{v:,}".replace(",", ".")     # noqa: E731
    detalle = (
        f"Esta propuesta cuesta {plata(costo)} y ya lleva {plata(previo)} aceptados "
        f"en el lote: {plata(acumulado)} en total."
        if previo else f"La propuesta cuesta {plata(costo)}."
    )
    return "pendiente_revision", True, (
        f"{detalle} Supera el umbral de {plata(settings.umbral_revision_cop)}, "
        f"así que necesita el visto bueno del técnico antes de aplicarse."
    )
