"""
Divulgacion y limites del sistema.

AI Act art. 50: quien interactua con un sistema de IA tiene derecho a
saberlo. Esta ficha se sirve en /v1/governance, se muestra en la app y la
voz la resume en el primer contacto de cada sesion.

Sobre la clasificacion, siendo precisos: el apoyo a decisiones agricolas
NO esta en el Anexo III, asi que hoy este sistema no es de alto riesgo.
Pero la ruta natural de escala si lo vuelve alto riesgo: en el momento en
que un banco lo use para evaluar credito agricola o el Estado para asignar
subsidios, cae de lleno en el Anexo III. Por eso se construye con ese
estandar desde ahora, de forma voluntaria.
"""

from __future__ import annotations

FRASE_VOZ = (
    "Le habla un asistente automático. Lo que le digo son sugerencias "
    "calculadas con datos, no órdenes. La decisión es suya."
)

NO_HACEMOS = [
    "No diagnosticamos plagas ni enfermedades por descripcion hablada.",
    "No recomendamos dosis de plaguicidas ni fungicidas.",
    "No reemplazamos un análisis de laboratorio de suelos.",
    "No decidimos nada sobre personas: ni crédito, ni subsidios, ni listas de beneficiarios.",
    "No ejecutamos ninguna accion. Solo proponemos.",
]

LIMITES_DATOS = [
    "La calibración del sensor a partes por millon es provisional y no está "
    "validada contra laboratorio.",
    "Los precios de fertilizante son de referencia nacional, no de su vereda.",
    "El pronóstico a mas de siete días pierde precision, y a nueve meses "
    "indica tendencia, no certeza.",
    "No tenemos historial de cosecha de su lote, así que no predecimos rendimiento.",
]

DERIVAR_A_HUMANO = [
    "Síntomas raros en la mata que no coinciden con lo que dicen los sensores.",
    "Cualquier decisión de aplicar plaguicidas.",
    "Propuestas que superen el umbral de gasto configurado.",
    "Cuando el modelo reporta confianza baja en la zona consultada.",
]


def ficha() -> dict:
    return {
        "que_es": (
            "Sereno es un sistema de apoyo a la decisión para pequenos "
            "productores de papa. Combina mediciones de suelo con datos "
            "publicos de clima y riesgo."
        ),
        "es_ia": True,
        "divulgacion_hablada": FRASE_VOZ,
        "decide_solo": False,
        "supervision_humana": (
            "Toda propuesta nace pendiente. Alguien la acepta, la rechaza, la "
            "modifica o la deriva a un técnico. Sin decisión humana no pasa nada."
        ),
        "no_hacemos": NO_HACEMOS,
        "limites_de_los_datos": LIMITES_DATOS,
        "cuando_derivamos_a_un_humano": DERIVAR_A_HUMANO,
        "trazabilidad": (
            "Cada propuesta guarda sus entradas, la versión del modelo, las "
            "fuentes con su fecha y quien decidio que. Registro append-only."
        ),
        "datos_del_agricultor": (
            "Las mediciones son del agricultor. El aporte al mapa público es "
            "opcional, explicito y revocable, y se pública agregado y "
            "anonimizado."
        ),
        "marco": {
            "eu_ai_act": (
                "Articulos 14 y 50 vigentes desde el 2 de agosto de 2026. Este "
                "sistema no es de alto riesgo según el Anexo III, pero adopta "
                "el estandar de forma voluntaria porque su ruta de escala "
                "(crédito o subsidios) si lo sería."
            ),
            "colombia": "CONPES 4144 de 2025, Política Nacional de Inteligencia Artificial.",
        },
    }
