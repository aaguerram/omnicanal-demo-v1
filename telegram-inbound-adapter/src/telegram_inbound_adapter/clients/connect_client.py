from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatContact:
    contact_id: str
    participant_id: str
    participant_token: str


class ConnectClient:
    def __init__(
        self,
        connect_boto_client: Any,
        connect_participant_boto_client: Any,
        instance_id: str,
        contact_flow_id: str,
        streaming_topic_arn: str,
    ) -> None:
        self._connect = connect_boto_client
        self._participant = connect_participant_boto_client
        self._instance_id = instance_id
        self._contact_flow_id = contact_flow_id
        self._streaming_topic_arn = streaming_topic_arn

    def start_chat_contact(self, display_name: str, attributes: dict[str, str]) -> ChatContact:
        # Deliberately NOT using StartChatContact's InitialMessage param here.
        # It was tried (2026-07-11) to avoid a separate SendMessage racing
        # with F_Menu_Router's GetParticipantInput -- but InitialMessage
        # leaves a real, unconsumed customer message sitting in the chat
        # participant channel from the very start of the contact. F_Menu_Router
        # itself doesn't use GetParticipantInput anymore (it reads
        # $.Attributes.initialMessage instead, see chat_service.py's
        # _create_session), so nothing ever "claims" that leftover message --
        # and the FIRST GetParticipantInput that runs anywhere in the contact
        # (F_Menu_Reintento's, when intent isn't detected) hit it instead,
        # erroring out (NoMatchingError) almost immediately rather than
        # waiting for real new input, sending the customer straight to
        # TECHNICAL_FALLBACK_INTENT. See ../context.md (gotcha #7) for the
        # full incident. Fix: the triggering message travels ONLY as the
        # `initialMessage` contact attribute (used solely by F_Menu_Router's
        # classification) -- never as an actual chat message -- so no
        # GetParticipantInput downstream ever finds anything pending.
        # Known tradeoff: the very first message a customer sends no longer
        # shows up as its own bubble in the Connect chat transcript/CCP.
        response = self._connect.start_chat_contact(
            InstanceId=self._instance_id,
            ContactFlowId=self._contact_flow_id,
            Attributes=attributes,
            ParticipantDetails={"DisplayName": display_name},
        )
        return ChatContact(
            contact_id=response["ContactId"],
            participant_id=response["ParticipantId"],
            participant_token=response["ParticipantToken"],
        )

    def create_participant_connection(self, participant_token: str) -> str:
        response = self._participant.create_participant_connection(
            Type=["CONNECTION_CREDENTIALS"],
            ParticipantToken=participant_token,
            # Required for real-time contact streaming to actually deliver
            # events to the SNS topic -- per AWS's docs, ConnectParticipant
            # must be true and the caller must be the Customer participant.
            ConnectParticipant=True,
        )
        return response["ConnectionCredentials"]["ConnectionToken"]

    def send_message(self, connection_token: str, text: str) -> None:
        self._participant.send_message(
            ContentType="text/plain",
            Content=text,
            ConnectionToken=connection_token,
        )

    def start_contact_streaming(self, contact_id: str) -> str:
        response = self._connect.start_contact_streaming(
            InstanceId=self._instance_id,
            ContactId=contact_id,
            ChatStreamingConfiguration={"StreamingEndpointArn": self._streaming_topic_arn},
        )
        return response["StreamingId"]
