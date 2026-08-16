"""Agente conversacional opcional sobre Claude.

El router determinista de `agent.py` decide QUE se responde y con que evidencia.
Para las rutas conocidas este modulo mejora la redaccion; para otras preguntas
puede responder directamente desde un resumen acotado del paquete. No calcula,
no decide y no puede introducir cifras: si la respuesta trae un numero que no
estaba en la evidencia, se descarta. Esa regla permite seguir firmando la
respuesta como fundamentada.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .explainer import AIBudgetPolicy

logger = logging.getLogger(__name__)

# Un numero es cualquier cifra con separadores de miles o decimales, en punto o
# en coma. El guion solo cuenta como signo cuando no viene pegado a algo: en
# este dominio "zone-3" y "20-10-30" llevan guiones que no son negativos, y
# leerlos como signo hacia que "zone 3" pareciera una cifra inventada.
_NUMBER = re.compile(r"(?<![\w.,])-?\d[\d.,]*")

SYSTEM_PROMPT = """Eres el asistente de un tablero agronomico colombiano. Recibes una \
pregunta, evidencia estructurada de un lote y, a veces, una respuesta ya calculada \
por un motor determinista.

Si existe una respuesta calculada, reescribela con claridad. Si esta vacia, \
responde la pregunta usando exclusivamente la evidencia entregada. Usa frases \
cortas y espanol claro de Colombia, sin jerga innecesaria.

Reglas que no puedes romper:
1. No inventes, calcules, redondees ni conviertas cifras. Si hay respuesta \
calculada, copia sus numeros exactamente; en una pregunta abierta, copia cada \
numero exactamente como aparece en la evidencia.
2. No agregues hechos, causas, recomendaciones ni contexto que no esten en la \
evidencia. Si no hay evidencia suficiente, dilo directamente.
3. No quites las salvedades. Si la respuesta dice que algo esta pendiente de \
validacion tecnica o que los datos estan degradados, eso se mantiene.
4. No presentes una propuesta pendiente como aprobada y no reemplaces la \
validacion de un tecnico.
5. Responde solo con la respuesta al usuario. Sin encabezados, sin vinetas, sin \
comillas y sin comentarios sobre tu tarea.
6. Si la respuesta calculada esta vacia, no hagas afirmaciones cuantitativas ni \
incluyas cifras; responde de forma cualitativa con la evidencia disponible.
7. Maximo cuatro frases."""


def _numbers(text: str) -> set[str]:
    """Cifras de un texto, normalizadas para comparar entre formatos.

    "1.234,50" y "1234.50" son el mismo numero escrito distinto, y el modelo
    puede cambiar el separador sin cambiar el valor. Lo que no se tolera es un
    valor distinto: ahi es donde estaria la invencion.
    """
    found: set[str] = set()
    for raw in _NUMBER.findall(text):
        cleaned = raw.rstrip(".,")
        if not cleaned:
            continue
        # Se deja un solo separador decimal y se eliminan los de miles.
        if "," in cleaned and "." in cleaned:
            decimal = max(cleaned.rfind(","), cleaned.rfind("."))
            cleaned = cleaned[:decimal].replace(",", "").replace(".", "") + "." + cleaned[decimal + 1 :]
        else:
            cleaned = cleaned.replace(",", ".")
            if cleaned.count(".") > 1:
                head, _, tail = cleaned.rpartition(".")
                cleaned = head.replace(".", "") + "." + tail
        try:
            found.add(f"{float(cleaned):g}")
        except ValueError:
            continue
    return found


class AnthropicEvidenceExplainer:
    """Implementa `EvidenceExplainer` contra la API de Anthropic."""

    version = "anthropic-evidence-agent/2.0.0"

    def __init__(
        self,
        *,
        model: str,
        policy: AIBudgetPolicy,
        api_key: str = "",
        client: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.model = model
        self.policy = policy
        self.spent_usd = 0.0
        if client is not None:
            self._client = client
            return
        import anthropic  # se importa aqui: el backend arranca sin el SDK

        self._client = anthropic.Anthropic(
            **({"api_key": api_key} if api_key else {}),
            timeout=timeout_seconds,
            max_retries=1,
        )

    @property
    def budget_left_usd(self) -> float:
        return round(self.policy.total_budget_usd - self.spent_usd, 8)

    def render(
        self,
        *,
        question: str,
        evidence: dict[str, Any],
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        """Devuelve la redaccion, o el motivo por el que no se uso el modelo.

        Nunca lanza: un fallo del proveedor degrada a la respuesta determinista,
        igual que el backend degrada cuando una fuente externa no responde.
        """
        grounded = evidence.get("answer", "")
        user_prompt = self._prompt(question, evidence)

        # Las rutas con cifras ya vienen calculadas por el motor y solo pueden
        # repetir esas cifras. Las preguntas abiertas deben ser cualitativas:
        # permitir todos los numeros del package hacia casi inutil este guard.
        allowed = _numbers(grounded)

        try:
            input_tokens = self._count_tokens(user_prompt)
        except Exception as error:  # noqa: BLE001 - el conteo no puede tumbar la demo
            return self._skip("token_count_failed", str(error))

        if input_tokens > self.policy.max_input_tokens:
            return self._skip(
                "input_over_limit",
                f"{input_tokens} tokens de entrada superan el limite de {self.policy.max_input_tokens}",
            )
        # El costo se acota por arriba: se asume que la salida agota su tope.
        if not self.policy.can_spend(self.spent_usd, input_tokens, self.policy.max_output_tokens):
            return self._skip(
                "budget_exhausted",
                f"quedan {self.budget_left_usd:.6f} USD del presupuesto",
            )

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.policy.max_output_tokens,
                thinking={"type": "disabled"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as error:  # noqa: BLE001 - proveedor caido o sin credencial
            logger.warning("[explainer] la API no respondio: %s", error)
            return self._skip("provider_error", str(error))

        usage = getattr(response, "usage", None)
        cost = self.policy.estimated_cost(
            min(getattr(usage, "input_tokens", input_tokens), self.policy.max_input_tokens),
            min(getattr(usage, "output_tokens", 0), self.policy.max_output_tokens),
        )
        self.spent_usd = round(self.spent_usd + cost, 8)

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        if not text:
            return self._skip("empty_response", "el modelo no devolvio texto", cost=cost)

        invented = _numbers(text) - allowed
        if invented:
            # No es un error del modelo que se pueda ignorar: una cifra que no
            # esta en la evidencia rompe la trazabilidad de la respuesta.
            logger.warning("[explainer] redaccion descartada, cifras sin evidencia: %s", invented)
            return self._skip(
                "unsupported_numbers",
                "la redaccion introdujo cifras que no estan en la evidencia: "
                + ", ".join(sorted(invented)),
                cost=cost,
            )

        return {
            "used": True,
            "text": text,
            "model": self.model,
            "explainer_version": self.version,
            "cost_usd": cost,
            "spent_usd": self.spent_usd,
            "budget_left_usd": self.budget_left_usd,
            "evidence_ids": list(evidence_ids),
        }

    def _prompt(self, question: str, evidence: dict[str, Any]) -> str:
        calculated = evidence.get("answer", "")
        return (
            f"Pregunta del usuario:\n{question}\n\n"
            f"Respuesta calculada por el motor (puede estar vacia):\n{calculated}\n\n"
            "Evidencia disponible:\n"
            f"{json.dumps(evidence, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}\n\n"
            + (
                "Reescribe la respuesta calculada respetando las reglas."
                if calculated
                else (
                    "Responde la pregunta solo con la evidencia disponible, "
                    "sin afirmaciones cuantitativas ni cifras."
                )
            )
        )

    def _count_tokens(self, user_prompt: str) -> int:
        counted = self._client.messages.count_tokens(
            model=self.model,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return int(counted.input_tokens)

    def _skip(self, reason: str, detail: str, *, cost: float = 0.0) -> dict[str, Any]:
        return {
            "used": False,
            "reason": reason,
            "detail": detail,
            "model": self.model,
            "explainer_version": self.version,
            "cost_usd": cost,
            "spent_usd": self.spent_usd,
            "budget_left_usd": self.budget_left_usd,
        }
