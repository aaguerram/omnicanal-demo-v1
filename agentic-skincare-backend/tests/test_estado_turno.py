from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from core import estado_turno


@pytest.mark.parametrize(
    ("customer_message", "end_conversation"),
    [
        ("eso es todo, puedes cerrar", True),
        ("gracias, cuanto cuesta?", False),
        ("no quiero ese producto, muestrame otro", False),
    ],
)
def test_evaluar_estado_propagates_structured_end_signal(
    monkeypatch, customer_message, end_conversation
):
    structured_llm = MagicMock()
    structured_llm.invoke.return_value = SimpleNamespace(
        status="finalizado",
        end_conversation=end_conversation,
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured_llm
    chat_bedrock = MagicMock(return_value=llm)
    monkeypatch.setattr(estado_turno, "ChatBedrockConverse", chat_bedrock)

    result = estado_turno.evaluar_estado_node(
        {
            "messages": [
                HumanMessage(content=customer_message),
                AIMessage(content="Respuesta de Luna"),
            ],
            "patient_info": {},
        }
    )

    assert result == {
        "turn_status": "finalizado",
        "end_conversation": end_conversation,
    }
    chat_bedrock.assert_called_once()
    assert chat_bedrock.call_args.kwargs["temperature"] == 0.0
    assert chat_bedrock.call_args.kwargs["max_tokens"] == 1470
    llm.with_structured_output.assert_called_once_with(estado_turno.TurnStatusResult)


def test_evaluar_estado_defaults_to_open_when_classifier_fails(monkeypatch):
    structured_llm = MagicMock()
    structured_llm.invoke.side_effect = RuntimeError("bedrock unavailable")
    llm = MagicMock()
    llm.with_structured_output.return_value = structured_llm
    monkeypatch.setattr(estado_turno, "ChatBedrockConverse", MagicMock(return_value=llm))

    result = estado_turno.evaluar_estado_node(
        {
            "messages": [
                HumanMessage(content="eso es todo"),
                AIMessage(content="Hasta luego"),
            ],
            "patient_info": {},
        }
    )

    assert result == {"turn_status": "en_progreso", "end_conversation": False}


def test_prompt_does_not_equate_finalized_with_end_conversation():
    normalized_prompt = " ".join(estado_turno.SYSTEM_PROMPT.split())
    assert "No deduzcas end_conversation=true a partir de status=finalizado" in normalized_prompt
    assert '"gracias, cuanto cuesta?"' in normalized_prompt
    assert '"no quiero ese producto, muestrame otro"' in normalized_prompt
