"""El explicador redacta, pero no puede introducir cifras ni gastar de mas."""

from __future__ import annotations

import pytest

from app.services.agent import GroundedAgent
from app.services.anthropic_explainer import AnthropicEvidenceExplainer, _numbers
from app.services.explainer import AIBudgetPolicy

EVIDENCE = {
    "answer": "El lote tiene 18 mediciones validas y 3 zonas: zone-a: N 0.12 %, K 0.21 %.",
    "intent": "plot_status",
    "sources": ["Open-Meteo Forecast"],
}

POLICY = AIBudgetPolicy(
    total_budget_usd=0.01,
    max_input_tokens=2_000,
    max_output_tokens=500,
    input_price_usd_per_million=1.00,
    output_price_usd_per_million=5.00,
)


class FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class FakeResponse:
    def __init__(self, text: str, input_tokens: int = 400, output_tokens: int = 80):
        self.content = [FakeBlock(text)]
        self.usage = FakeUsage(input_tokens, output_tokens)


class FakeMessages:
    def __init__(self, reply: str | Exception, input_tokens: int = 400):
        self.reply = reply
        self.input_tokens = input_tokens
        self.calls = 0

    def count_tokens(self, **_kwargs):
        return type("Counted", (), {"input_tokens": self.input_tokens})()

    def create(self, **_kwargs):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return FakeResponse(self.reply, input_tokens=self.input_tokens)


class FakeClient:
    def __init__(self, reply: str | Exception, input_tokens: int = 400):
        self.messages = FakeMessages(reply, input_tokens)


def build(reply: str | Exception, *, policy: AIBudgetPolicy = POLICY, input_tokens: int = 400):
    client = FakeClient(reply, input_tokens)
    explainer = AnthropicEvidenceExplainer(
        model="claude-haiku-4-5", policy=policy, client=client
    )
    return explainer, client


def render(explainer: AnthropicEvidenceExplainer):
    return explainer.render(question="que tiene el lote?", evidence=EVIDENCE, evidence_ids=["pkg-1"])


def test_numbers_ignores_format_but_not_value():
    # El mismo valor escrito distinto no es una cifra nueva; un valor distinto si.
    assert _numbers("1.234,50") == _numbers("1234.50")
    assert _numbers("0,12 %") == _numbers("0.12 %")
    assert _numbers("0.1") != _numbers("0.12")


def test_numbers_reads_domain_hyphens_as_separators_not_signs():
    # Los guiones de un identificador de zona o de una formulacion no son signos.
    assert _numbers("zone-3") == _numbers("zone 3") == {"3"}
    assert _numbers("20-10-30") == {"20", "10", "30"}
    # Un negativo de verdad si conserva el signo.
    assert _numbers("cayo -8 puntos") == {"-8"}


def test_rewrite_that_keeps_the_numbers_is_used():
    explainer, _ = build("Hay 18 mediciones validas en 3 zonas. En zone-a: N 0.12 %, K 0.21 %.")
    result = render(explainer)
    assert result["used"] is True
    assert "18 mediciones" in result["text"]
    assert result["cost_usd"] == pytest.approx(400 / 1e6 + 80 * 5 / 1e6)


def test_invented_number_is_rejected():
    # Redondear 0.12 a 0.1 ya es derivar una cantidad, y eso rompe la evidencia.
    explainer, _ = build("Hay 18 mediciones en 3 zonas y el nitrogeno ronda 0.1 %.")
    result = render(explainer)
    assert result["used"] is False
    assert result["reason"] == "unsupported_numbers"
    # El costo de la llamada descartada se sigue contabilizando.
    assert result["spent_usd"] > 0


def test_provider_failure_degrades_instead_of_raising():
    explainer, _ = build(RuntimeError("401 authentication_error"))
    result = render(explainer)
    assert result["used"] is False
    assert result["reason"] == "provider_error"


def test_budget_stops_the_call_before_spending():
    tight = AIBudgetPolicy(
        total_budget_usd=0.0000001,
        max_input_tokens=2_000,
        max_output_tokens=500,
        input_price_usd_per_million=1.00,
        output_price_usd_per_million=5.00,
    )
    explainer, client = build("da igual, no deberia llamarse", policy=tight)
    result = render(explainer)
    assert result["used"] is False
    assert result["reason"] == "budget_exhausted"
    assert client.messages.calls == 0


def test_oversized_input_is_not_sent():
    explainer, client = build("da igual", input_tokens=5_000)
    result = render(explainer)
    assert result["used"] is False
    assert result["reason"] == "input_over_limit"
    assert client.messages.calls == 0


def ask(client):
    response = client.post(
        "/v1/agent/ask", json={"plot_id": "nar-001", "question": "que tiene este lote?"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_agent_without_explainer_stays_deterministic(prepared_client):
    client, _, _ = prepared_client
    agent = ask(client)["agent"]
    assert agent["llm_used"] is False
    assert "explainer" not in agent


def test_agent_keeps_the_deterministic_answer_when_the_model_invents(prepared_client, monkeypatch):
    # El fixture es de sesion: monkeypatch devuelve el agente original al salir.
    client, _, _ = prepared_client
    container = client.app.state.container
    explainer, _ = build("El lote tiene 999 mediciones validas.")
    monkeypatch.setattr(container, "agent", GroundedAgent(container.repository, explainer))

    agent = ask(client)["agent"]
    assert agent["llm_used"] is False
    assert "999" not in agent["answer"]
    assert agent["explainer"]["reason"] == "unsupported_numbers"


def test_agent_uses_the_rewrite_and_publishes_the_explainer_version(prepared_client, monkeypatch):
    client, _, _ = prepared_client
    container = client.app.state.container
    deterministic = GroundedAgent(container.repository).ask("nar-001", "que tiene este lote?")
    # Una redaccion valida repite las cifras del router, asi que se acepta.
    explainer, _ = build(deterministic["answer"])
    monkeypatch.setattr(container, "agent", GroundedAgent(container.repository, explainer))

    body = ask(client)
    agent = body["agent"]
    assert agent["llm_used"] is True
    assert agent["answer_deterministic"] == deterministic["answer"]
    assert agent["evidence_ids"] == deterministic["evidence_ids"]
    assert body["model_versions"]["explainer"] == AnthropicEvidenceExplainer.version
