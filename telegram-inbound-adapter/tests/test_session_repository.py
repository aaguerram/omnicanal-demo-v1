from telegram_inbound_adapter.models import SessionRecord


def make_record(external_user_id: str = "123") -> SessionRecord:
    return SessionRecord(
        pk=SessionRecord.build_pk("telegram", external_user_id),
        channel="telegram",
        external_user_id=external_user_id,
        connect_contact_id="contact-1",
        participant_id="participant-1",
        participant_token="token-1",
        connection_token="conn-1",
        ttl=0,
    )


def test_get_active_session_returns_none_when_missing(session_repository):
    assert session_repository.get_active_session("telegram", "123") is None


def test_put_then_get_active_session(session_repository):
    record = make_record()
    session_repository.put_session(record, ttl_seconds=3600)

    fetched = session_repository.get_active_session("telegram", "123")

    assert fetched is not None
    assert fetched.connect_contact_id == "contact-1"
    assert fetched.connection_token == "conn-1"


def test_get_active_session_expired_returns_none(session_repository):
    record = make_record()
    session_repository.put_session(record, ttl_seconds=-10)

    assert session_repository.get_active_session("telegram", "123") is None
