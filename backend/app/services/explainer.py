"""Optional explainer boundary and enforceable AI budget arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AIBudgetPolicy:
    total_budget_usd: float
    max_input_tokens: int
    max_output_tokens: int
    input_price_usd_per_million: float
    output_price_usd_per_million: float

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("el conteo de tokens no puede ser negativo")
        if input_tokens > self.max_input_tokens or output_tokens > self.max_output_tokens:
            raise ValueError("la solicitud supera los límites de tokens configurados por llamada")
        return round(
            input_tokens * self.input_price_usd_per_million / 1_000_000
            + output_tokens * self.output_price_usd_per_million / 1_000_000,
            8,
        )

    def can_spend(self, spent_usd: float, input_tokens: int, output_tokens: int) -> bool:
        return spent_usd + self.estimated_cost(input_tokens, output_tokens) <= self.total_budget_usd


class EvidenceExplainer(Protocol):
    """An optional model may phrase evidence but cannot derive new quantities."""

    def render(
        self,
        *,
        question: str,
        evidence: dict[str, Any],
        evidence_ids: list[str],
    ) -> dict[str, Any]: ...
