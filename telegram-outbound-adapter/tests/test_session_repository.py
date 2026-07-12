def test_get_channel_and_user_by_contact_returns_none_when_missing(session_repository):
    assert session_repository.get_channel_and_user_by_contact("unknown-contact") is None


def test_get_channel_and_user_by_contact_returns_mapping(dynamodb_table, session_repository):
    dynamodb_table.put_item(
        Item={
            "pk": "contact#contact-1",
            "channel": "telegram",
            "external_user_id": "123",
            "ttl": 9999999999,
        }
    )

    assert session_repository.get_channel_and_user_by_contact("contact-1") == ("telegram", "123")


def test_mark_ended_updates_session_status(dynamodb_table, session_repository):
    dynamodb_table.put_item(
        Item={
            "pk": "telegram#123",
            "channel": "telegram",
            "external_user_id": "123",
            "status": "ACTIVE",
            "connect_contact_id": "contact-1",
            "participant_id": "participant-1",
            "participant_token": "token-1",
            "connection_token": "conn-1",
            "ttl": 9999999999,
        }
    )

    session_repository.mark_ended("telegram", "123")

    item = dynamodb_table.get_item(Key={"pk": "telegram#123"})["Item"]
    assert item["status"] == "ENDED"
