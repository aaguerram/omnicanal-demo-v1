from unittest.mock import MagicMock

import pytest

from connect_nlu_router_menu import handler


@pytest.fixture(autouse=True)
def stub_graph(monkeypatch):
    stub = MagicMock()
    stub.invoke.return_value = {"message": "hola", "intent": "ventas"}
    # _get_graph (no ChatBedrockConverse real) -- ver la nota en handler.py
    # sobre por que el grafo se arma perezosamente en vez de a nivel de modulo.
    monkeypatch.setattr(handler, "_get_graph", lambda: stub)
    return stub


def test_lambda_handler_returns_classified_intent(stub_graph):
    result = handler.lambda_handler({"message": "quiero contratar algo"}, None)

    assert result == {"intent": "ventas"}
    stub_graph.invoke.assert_called_once_with({"message": "quiero contratar algo", "intent": None})


def test_lambda_handler_handles_missing_message(stub_graph):
    stub_graph.invoke.return_value = {"message": "", "intent": None}

    result = handler.lambda_handler({}, None)

    assert result == {"intent": ""}
    stub_graph.invoke.assert_called_once_with({"message": "", "intent": None})


def test_lambda_handler_handles_none_event(stub_graph):
    stub_graph.invoke.return_value = {"message": "", "intent": None}

    result = handler.lambda_handler(None, None)

    assert result == {"intent": ""}


def test_lambda_handler_extracts_message_from_connect_flow_event(stub_graph):
    # Bloque "Invoke AWS Lambda function" de un contact flow de Connect:
    # LambdaInvocationAttributes llega envuelto en Details.Parameters, no
    # como {"message": ...} en el nivel superior -- ver _extract_message.
    connect_event = {
        "Details": {
            "ContactData": {"ContactId": "abc-123"},
            "Parameters": {"message": "quiero contratar algo"},
        },
        "Name": "ContactFlowEvent",
    }

    result = handler.lambda_handler(connect_event, None)

    assert result == {"intent": "ventas"}
    stub_graph.invoke.assert_called_once_with({"message": "quiero contratar algo", "intent": None})
