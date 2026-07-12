import boto3
import pytest
from moto import mock_aws

from repositories.session_repository import SessionRepository

TABLE_NAME = "SkincareAgentSessions"


@pytest.fixture
def dynamodb_table():
    with mock_aws():
        client = boto3.resource("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield client.Table(TABLE_NAME)


@pytest.fixture
def session_repository(dynamodb_table):
    return SessionRepository(table=dynamodb_table, max_stored_messages=12)
