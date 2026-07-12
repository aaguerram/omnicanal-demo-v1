from langchain_core.messages import AIMessage, HumanMessage


def test_get_session_returns_none_when_missing(session_repository):
    assert session_repository.get_session("contact-1") is None


def test_load_messages_returns_empty_list_when_missing(session_repository):
    assert session_repository.load_messages("contact-1") == []


def test_save_then_load_round_trip(session_repository):
    messages = [HumanMessage(content="hola"), AIMessage(content="hola, como estas?")]

    session_repository.save_turn(
        conversation_id="contact-1",
        messages=messages,
        patient_info={"skin_type": "grasa"},
        consecutive_unresolved=1,
        turn_status="en_progreso",
        ttl_seconds=3600,
    )

    session = session_repository.get_session("contact-1")
    assert session is not None
    assert session.patient_info == {"skin_type": "grasa"}
    assert session.consecutive_unresolved == 1
    assert session.turn_status == "en_progreso"

    loaded = session_repository.load_messages("contact-1")
    assert [m.content for m in loaded] == ["hola", "hola, como estas?"]


def test_save_turn_trims_to_max_stored_messages(session_repository):
    messages = [HumanMessage(content=str(i)) for i in range(20)]

    session_repository.save_turn(
        conversation_id="contact-1",
        messages=messages,
        patient_info={},
        consecutive_unresolved=0,
        turn_status="en_progreso",
        ttl_seconds=3600,
    )

    loaded = session_repository.load_messages("contact-1")
    assert len(loaded) == 12
    assert loaded[-1].content == "19"


def test_save_turn_handles_floats_in_message_metadata(session_repository):
    # Real LLM responses (Bedrock included) carry response_metadata/
    # usage_metadata with float fields (scores, token costs, ...) --
    # DynamoDB's Table resource raises TypeError on a bare float, only
    # Decimal is accepted.
    message = AIMessage(
        content="listo",
        response_metadata={"avg_logprobs": -0.1234, "safety_ratings": [{"score": 0.02}]},
    )

    session_repository.save_turn(
        conversation_id="contact-1",
        messages=[message],
        patient_info={},
        consecutive_unresolved=0,
        turn_status="en_progreso",
        ttl_seconds=3600,
    )

    loaded = session_repository.load_messages("contact-1")
    assert loaded[0].content == "listo"


def test_expired_session_returns_none(session_repository):
    session_repository.save_turn(
        conversation_id="contact-1",
        messages=[HumanMessage(content="hola")],
        patient_info={},
        consecutive_unresolved=0,
        turn_status="en_progreso",
        ttl_seconds=-10,
    )

    assert session_repository.get_session("contact-1") is None
