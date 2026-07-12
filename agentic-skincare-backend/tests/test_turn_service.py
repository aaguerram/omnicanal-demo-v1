import importlib

import boto3
import pytest
from langchain_core.messages import AIMessage
from moto import mock_aws

TABLE_NAME = "SkincareAgentSessions"


class _FakeGraph:
    """Stand-in for core.main_graph.app_graph -- avoids real Bedrock calls
    in tests. Returns a fixed turn_status regardless of input, mirroring the
    shape core.estado_turno.evaluar_estado_node would produce.
    """

    def __init__(self, turn_status: str, reply: str = "respuesta de prueba"):
        self.turn_status = turn_status
        self.reply = reply

    def invoke(self, state):
        messages = list(state["messages"]) + [AIMessage(content=self.reply)]
        return {
            "messages": messages,
            "patient_info": state.get("patient_info", {}),
            "turn_status": self.turn_status,
        }


@pytest.fixture
def turn_service(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-creds-for-tests.json")
    with mock_aws():
        boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        import core.turn_service as module

        importlib.reload(module)
        yield module


def test_empty_message_is_a_noop(turn_service):
    result = turn_service.process_turn("c1", "  ")
    assert result == {"response_text": "", "status": "en_progreso", "escalate": False}


def test_finalizado_stays_with_agentcore(turn_service, monkeypatch):
    monkeypatch.setattr(turn_service, "app_graph", _FakeGraph("finalizado"))

    result = turn_service.process_turn("c1", "quiero el kit hidratante")

    assert result["status"] == "finalizado"
    assert result["escalate"] is False
    assert result["response_text"] == "respuesta de prueba"


def test_en_progreso_never_escalates(turn_service, monkeypatch):
    monkeypatch.setattr(turn_service, "app_graph", _FakeGraph("en_progreso"))

    result = turn_service.process_turn("c1", "tengo piel grasa")

    assert result["status"] == "en_progreso"
    assert result["escalate"] is False


def test_three_consecutive_no_resuelto_escalates(turn_service, monkeypatch):
    monkeypatch.setattr(turn_service, "app_graph", _FakeGraph("no_resuelto"))

    first = turn_service.process_turn("c1", "quiero cancelar mi factura")
    second = turn_service.process_turn("c1", "de nuevo lo mismo")
    third = turn_service.process_turn("c1", "sigo con lo mismo")

    assert [r["escalate"] for r in (first, second)] == [False, False]
    assert third["escalate"] is True


def test_en_progreso_resets_unresolved_counter(turn_service, monkeypatch):
    monkeypatch.setattr(turn_service, "app_graph", _FakeGraph("no_resuelto"))
    turn_service.process_turn("c1", "primero")
    turn_service.process_turn("c1", "segundo")

    monkeypatch.setattr(turn_service, "app_graph", _FakeGraph("en_progreso"))
    reset_turn = turn_service.process_turn("c1", "tercero")
    assert reset_turn["escalate"] is False

    monkeypatch.setattr(turn_service, "app_graph", _FakeGraph("no_resuelto"))
    fourth = turn_service.process_turn("c1", "cuarto")
    fifth = turn_service.process_turn("c1", "quinto")
    assert fourth["escalate"] is False
    assert fifth["escalate"] is False  # counter is 2 here, reset broke the streak


def test_graph_failure_never_raises_and_escalates(turn_service, monkeypatch):
    class _BoomGraph:
        def invoke(self, state):
            raise RuntimeError("boom")

    monkeypatch.setattr(turn_service, "app_graph", _BoomGraph())

    result = turn_service.process_turn("c1", "hola")

    assert result["escalate"] is True
    assert result["status"] == "no_resuelto"
