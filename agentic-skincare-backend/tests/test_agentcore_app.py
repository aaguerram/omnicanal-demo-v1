import importlib
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "SkincareAgentSessions"


@pytest.fixture
def agentcore_app(monkeypatch):
    # Mismo patron defensivo que tests/test_lambda_handler.py -- ver ahi el
    # porque del reload de core.turn_service antes de reload del entrypoint.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-creds-for-tests.json")
    with mock_aws():
        boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        import core.turn_service as turn_service_module

        importlib.reload(turn_service_module)

        import entrypoints.agentcore_app as module

        importlib.reload(module)
        yield module


def test_invoke_delegates_to_process_turn(agentcore_app, monkeypatch):
    stub = MagicMock(
        return_value={
            "response_text": "hola, soy Luna",
            "status": "en_progreso",
            "escalate": False,
            "end_conversation": False,
        }
    )
    monkeypatch.setattr(agentcore_app, "process_turn", stub)

    result = agentcore_app.invoke({"contact_id": "c1", "message": "hola"})

    assert result == {
        "response_text": "hola, soy Luna",
        "status": "en_progreso",
        "escalate": False,
        "end_conversation": False,
    }
    stub.assert_called_once_with("c1", "hola")


def test_invoke_prefers_stable_conversation_id(agentcore_app, monkeypatch):
    stub = MagicMock(
        return_value={
            "response_text": "hola",
            "status": "en_progreso",
            "escalate": False,
            "end_conversation": False,
        }
    )
    monkeypatch.setattr(agentcore_app, "process_turn", stub)

    agentcore_app.invoke(
        {"conversation_id": "stable-session", "contact_id": "new-contact", "message": "hola"}
    )

    stub.assert_called_once_with("stable-session", "hola")


def test_invoke_handles_missing_fields(agentcore_app, monkeypatch):
    stub = MagicMock(
        return_value={
            "response_text": "",
            "status": "en_progreso",
            "escalate": False,
            "end_conversation": False,
        }
    )
    monkeypatch.setattr(agentcore_app, "process_turn", stub)

    agentcore_app.invoke({})

    stub.assert_called_once_with(None, "")
