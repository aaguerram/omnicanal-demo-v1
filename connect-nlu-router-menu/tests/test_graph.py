from unittest.mock import MagicMock

from connect_nlu_router_menu.graph import build_graph


def make_llm(content: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=content)
    return llm


def test_classifies_valid_intent():
    graph = build_graph(make_llm("ventas"))

    result = graph.invoke({"message": "quiero contratar facturacion electronica", "intent": None})

    assert result["intent"] == "ventas"


def test_strips_punctuation_and_case():
    graph = build_graph(make_llm(" Cobranza.\n"))

    result = graph.invoke({"message": "tengo una factura pendiente", "intent": None})

    assert result["intent"] == "cobranza"


def test_returns_none_for_unrecognized_label():
    graph = build_graph(make_llm("no se"))

    result = graph.invoke({"message": "mensaje ambiguo", "intent": None})

    assert result["intent"] is None


def test_returns_none_when_llm_raises():
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("throttled")
    graph = build_graph(llm)

    result = graph.invoke({"message": "hola", "intent": None})

    assert result["intent"] is None


def test_returns_none_for_empty_message():
    llm = MagicMock()
    graph = build_graph(llm)

    result = graph.invoke({"message": "   ", "intent": None})

    assert result["intent"] is None
    llm.invoke.assert_not_called()


def test_classifies_each_valid_intent():
    for label in ("soporte", "ventas", "cobranza"):
        graph = build_graph(make_llm(label))
        result = graph.invoke({"message": f"mensaje de {label}", "intent": None})
        assert result["intent"] == label


def test_returns_none_for_ninguna():
    # "ninguna" es la respuesta explicita del modelo para saludos/consultas
    # ambiguas (ver SYSTEM_PROMPT) -- no es una intencion valida, mismo
    # tratamiento que cualquier clasificacion inconclusa.
    graph = build_graph(make_llm("ninguna"))

    result = graph.invoke({"message": "hola", "intent": None})

    assert result["intent"] is None
