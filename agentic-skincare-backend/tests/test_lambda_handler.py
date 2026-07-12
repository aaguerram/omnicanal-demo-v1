import importlib
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "SkincareAgentSessions"


@pytest.fixture
def handler(monkeypatch):
    # Mismo patron defensivo que tests/test_turn_service.py: entrypoints.lambda_handler
    # importa core.turn_service, cuyo codigo de modulo (carga de credenciales
    # GCP + wiring de DynamoDB) necesita correr con AWS mockeado la primera
    # vez que se importa en el proceso de test -- reload de ambos modulos
    # adentro de mock_aws() para no depender del orden de ejecucion de los
    # otros archivos de test.
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

        import entrypoints.lambda_handler as module

        importlib.reload(module)
        yield module


def test_extract_contact_id_and_message_direct_invocation(handler):
    contact_id, message = handler._extract_contact_id_and_message(
        {"contact_id": "abc-123", "message": "hola"}
    )
    assert contact_id == "abc-123"
    assert message == "hola"


def test_extract_prefers_conversation_id_direct_invocation(handler):
    conversation_id, message = handler._extract_conversation_id_and_message(
        {"conversation_id": "stable-id", "contact_id": "contact-id", "message": "hola"}
    )
    assert conversation_id == "stable-id"
    assert message == "hola"


def test_extract_contact_id_and_message_connect_invocation(handler):
    event = {
        "Details": {
            "Parameters": {"message": "quiero un producto"},
            "ContactData": {"ContactId": "connect-contact-1"},
        }
    }
    contact_id, message = handler._extract_contact_id_and_message(event)
    assert contact_id == "connect-contact-1"
    assert message == "quiero un producto"


def test_extract_prefers_connect_parameter_conversation_id(handler):
    event = {
        "Details": {
            "Parameters": {
                "conversation_id": "stable-id",
                "contact_id": "parameter-contact-id",
                "message": "quiero un producto",
            },
            "ContactData": {"ContactId": "connect-contact-1"},
        }
    }

    conversation_id, message = handler._extract_conversation_id_and_message(event)

    assert conversation_id == "stable-id"
    assert message == "quiero un producto"


def test_lambda_handler_delegates_to_process_turn_and_maps_escalate(handler, monkeypatch):
    stub = MagicMock(
        return_value={"response_text": "hola, soy Luna", "status": "en_progreso", "escalate": False}
    )
    monkeypatch.setattr(handler, "process_turn", stub)

    result = handler.lambda_handler({"contact_id": "c1", "message": "hola"}, None)

    assert result == {
        "response_text": "hola, soy Luna",
        "status": "en_progreso",
        "escalate": "false",
    }
    stub.assert_called_once_with("c1", "hola")


def test_lambda_handler_maps_escalate_true(handler, monkeypatch):
    stub = MagicMock(
        return_value={"response_text": "listo", "status": "finalizado", "escalate": True}
    )
    monkeypatch.setattr(handler, "process_turn", stub)

    result = handler.lambda_handler({"contact_id": "c1", "message": "gracias"}, None)

    assert result["escalate"] == "true"
