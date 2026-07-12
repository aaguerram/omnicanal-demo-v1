"""Provisions the 8 Amazon Connect contact flows for the Telegram queue/flow
architecture: F_Entrada_Omnicanal, F_Menu_Router, F_Menu_Reintento,
F_IA_Soporte/Ventas/Cobranza (stubs, no IA yet), F_Handoff_Humano,
F_Espera_Cola.

Run AFTER scripts/provision_queues_routing.ps1 -- the 3 queues (Q_Soporte,
Q_Ventas, Q_Cobranza) must already exist; this script looks them up by name
via the Connect API instead of needing their IDs copy-pasted in.

There used to be a 4th intent/queue, "Atencion" (general inquiries), used by
the NLU classifier (connect-nlu-router-menu) as a catch-all for greetings
and anything unclear. It was removed 2026-07-11 (Q_Atencion queue and
F_IA_Atencion flow deleted from the real account) because that catch-all
defeated the whole point of F_Menu_Reintento below: a plain "Hola" always
classified as "atencion", which is a real match, so it never reached the
retry loop and went straight to a human queue. See ../context.md (Historial,
2026-07-11 entries) for the full incident this fixed and
connect-nlu-router-menu/README.md for the NLU side of the change (the model
now answers "ninguna", not "atencion", for anything that doesn't clearly fit
soporte/ventas/cobranza).

F_Menu_Router only handles the customer's first message. When the NLU
classifier doesn't match a valid intent, F_Menu_Router hands off to
F_Menu_Reintento, which re-prompts the customer, explains what it *can* help
with, and re-classifies -- looping (by transferring to itself) for as many
rounds as it takes, with no cap and no fallback to a human queue at this
point; the customer only leaves this loop once a valid intent is detected.
See build_menu_reintento's docstring for why this loop is implemented as a
TransferToFlow between two flows instead of a Transitions.NextAction
back-edge inside a single flow -- the latter is exactly what caused the
runaway-loop incident described in ../context.md (gotcha #7).

Technical failures (Lambda invocation error, GetParticipantInput timeout --
i.e. the customer went silent, not "wrong topic") are NOT part of this
retry loop; they still fall straight to a fixed queue (TECHNICAL_FALLBACK_INTENT
below, Q_Soporte today) in both F_Menu_Router and F_Menu_Reintento, same as
before this change (just renamed from Atencion to Soporte).

The flow-language JSON schema was cross-checked against AWS's docs
(docs.aws.amazon.com/connect/latest/adminguide/flow-language*.html and
search-indexed APIReference pages) for the envelope, MessageParticipant,
DisconnectParticipant, EndFlowExecution, UpdateContactAttributes,
UpdateContactTargetQueue, TransferContactToQueue, TransferToFlow, and
Compare. The one block NOT independently confirmed is GetParticipantInput's
exact InputValidation requirement for chat/text input (used in
F_Menu_Router) -- if create-contact-flow rejects that specific flow, the
error message will name the exact field to fix; every other flow does not
use this block.

This script is a plain, top-to-bottom AWS CLI-equivalent script (via boto3)
matching the project's other provision_*.ps1 scripts in spirit: it doesn't
try to be idempotent -- create_contact_flow raises DuplicateResourceException
loudly if a flow with that name already exists.

Run from the project root:
    .venv\\Scripts\\python.exe scripts\\provision_connect_flows.py
    .venv\\Scripts\\python.exe scripts\\provision_connect_flows.py --update
        (applies the current F_Handoff_Humano / F_Menu_Router logic to the
        already-deployed flows in place, instead of creating new ones)
"""

from __future__ import annotations

import json
import sys
import uuid

import boto3

REGION = "us-east-1"
ACCOUNT_ID = "042278586355"
INSTANCE_ID = "1029ff15-e0f3-4b9c-bab2-377c17509765"

QUEUE_NAMES = ["Q_Soporte", "Q_Ventas", "Q_Cobranza"]
INTENTS = ["Soporte", "Ventas", "Cobranza"]  # matches queue name suffixes

# Donde caen los timeouts de GetParticipantInput y las fallas del Lambda de
# NLU -- fallas tecnicas/silencio del cliente, no "intencion no detectada"
# (eso ahora es F_Menu_Reintento). Ya no existe una cola "general" separada
# (Atencion se elimino, ver docstring del modulo), asi que se necesita
# igual una de las 3 reales como red de contencion; Soporte es la eleccion
# arbitraria pero razonable dado que un solo pool de asesores atiende las 3
# colas (RP_Asesores_Mensajeria_Omnicanal) -- cambiar aca si se prefiere otra.
TECHNICAL_FALLBACK_INTENT = "Soporte"

# Lambda de NLU (connect-nlu-router-menu/) invocado desde F_Menu_Router --
# debe estar asociado a la instancia de Connect (permiso lambda:InvokeFunction
# para connect.amazonaws.com) antes de aplicar este flow, si no
# create/update-contact-flow-content falla al validar el ARN.
NLU_LAMBDA_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:connect-nlu-router-menu"

# Sent by F_IA_Ventas before handing off to a human -- see build_ia_stub's
# `greeting` param. TODO: reemplazar "etc" por el listado real y completo de
# servicios cuando se confirme (ver context.md).
VENTAS_SERVICES_MESSAGE = (
    "En la empresa tenemos los siguientes servicios: Facturacion electronica, "
    "TaxFlash, etc."
)

# Sent by F_Menu_Reintento every time the NLU classifier doesn't match a
# valid intent -- tells the customer their request is out of scope and what
# this menu *can* route to, then re-asks. See build_menu_reintento.
REINTENTO_MESSAGE = (
    "No pude identificar tu consulta. Por ahora solo puedo ayudarte con: "
    "Soporte tecnico, Ventas o Cobranza/facturacion. "
    "Contame de nuevo, con tus palabras, que necesitas."
)

connect = boto3.client("connect", region_name=REGION)


def uid() -> str:
    return str(uuid.uuid4())


def queue_arn(queue_id: str) -> str:
    return f"arn:aws:connect:{REGION}:{ACCOUNT_ID}:instance/{INSTANCE_ID}/queue/{queue_id}"


def flow_arn(flow_id: str) -> str:
    return f"arn:aws:connect:{REGION}:{ACCOUNT_ID}:instance/{INSTANCE_ID}/contact-flow/{flow_id}"


def get_queue_ids() -> dict[str, str]:
    found: dict[str, str] = {}
    paginator = connect.get_paginator("list_queues")
    for page in paginator.paginate(InstanceId=INSTANCE_ID, QueueTypes=["STANDARD"]):
        for q in page["QueueSummaryList"]:
            if q["Name"] in QUEUE_NAMES:
                found[q["Name"]] = q["Id"]
    missing = set(QUEUE_NAMES) - found.keys()
    if missing:
        raise SystemExit(
            f"Missing queues {sorted(missing)} -- run "
            "scripts/provision_queues_routing.ps1 first."
        )
    return found


def flow_content(actions: list[dict], start_action: str) -> str:
    return json.dumps(
        {
            "Version": "2019-10-30",
            "StartAction": start_action,
            "Metadata": {
                "EntryPointPosition": {"x": 88, "y": 100},
                "ActionMetadata": {
                    a["Identifier"]: {"Position": {"x": 88, "y": 100}} for a in actions
                },
            },
            "Actions": actions,
        }
    )


def create_flow(
    name: str, description: str, flow_type: str, actions: list[dict], start_action: str
) -> str:
    response = connect.create_contact_flow(
        InstanceId=INSTANCE_ID,
        Name=name,
        Type=flow_type,
        Description=description,
        Content=flow_content(actions, start_action),
    )
    flow_id = response["ContactFlowId"]
    print(f"Created {flow_type} flow {name}: {flow_id}")
    return flow_id


def get_flow_id(name: str) -> str:
    flow_id = get_flow_id_optional(name)
    if flow_id is None:
        raise SystemExit(f"Flow '{name}' not found -- run without --update first to create it.")
    return flow_id


def get_flow_id_optional(name: str) -> str | None:
    paginator = connect.get_paginator("list_contact_flows")
    for page in paginator.paginate(InstanceId=INSTANCE_ID):
        for f in page["ContactFlowSummaryList"]:
            if f["Name"] == name:
                return f["Id"]
    return None


def update_flow(name: str, actions: list[dict], start_action: str) -> str:
    flow_id = get_flow_id(name)
    connect.update_contact_flow_content(
        InstanceId=INSTANCE_ID,
        ContactFlowId=flow_id,
        Content=flow_content(actions, start_action),
    )
    print(f"Updated flow {name}: {flow_id}")
    return flow_id


# --- Flow builders -----------------------------------------------------


def build_espera_cola() -> tuple[list[dict], str]:
    msg_id, end_id = uid(), uid()
    actions = [
        {
            "Identifier": msg_id,
            "Type": "MessageParticipant",
            "Parameters": {
                "Text": "Gracias por tu paciencia. Un asesor te atendera en breve."
            },
            "Transitions": {
                "NextAction": end_id,
                "Errors": [{"NextAction": end_id, "ErrorType": "NoMatchingError"}],
                "Conditions": [],
            },
        },
        {"Identifier": end_id, "Type": "EndFlowExecution", "Parameters": {}, "Transitions": {}},
    ]
    return actions, msg_id


def build_handoff_humano(queue_ids: dict[str, str]) -> tuple[list[dict], str]:
    end_id = uid()
    msg_id = uid()
    transfer_id = uid()
    set_queue_action_ids = {name: uid() for name in QUEUE_NAMES}
    compare_id = uid()

    actions = [
        {"Identifier": end_id, "Type": "EndFlowExecution", "Parameters": {}, "Transitions": {}},
        {
            # Sent once, right before the contact actually joins the queue --
            # there's no live agent staffing this pilot yet, so without this
            # the customer gets total silence after landing in a queue (only
            # F_Espera_Cola plays anything while *waiting*, and that's not
            # wired up as a queue's hold flow).
            "Identifier": msg_id,
            "Type": "MessageParticipant",
            "Parameters": {"Text": "Gracias, un asesor te atendera en breve."},
            "Transitions": {
                "NextAction": transfer_id,
                "Errors": [{"NextAction": transfer_id, "ErrorType": "NoMatchingError"}],
                "Conditions": [],
            },
        },
        {
            "Identifier": transfer_id,
            "Type": "TransferContactToQueue",
            "Parameters": {},
            "Transitions": {
                "NextAction": end_id,
                "Errors": [
                    {"NextAction": end_id, "ErrorType": "QueueAtCapacity"},
                    {"NextAction": end_id, "ErrorType": "NoMatchingError"},
                ],
                "Conditions": [],
            },
        },
    ]
    for name, set_id in set_queue_action_ids.items():
        actions.append(
            {
                "Identifier": set_id,
                "Type": "UpdateContactTargetQueue",
                "Parameters": {"QueueId": queue_arn(queue_ids[name])},
                "Transitions": {
                    "NextAction": msg_id,
                    "Errors": [{"NextAction": msg_id, "ErrorType": "NoMatchingError"}],
                    "Conditions": [],
                },
            }
        )

    # Defensive fallback only -- F_Menu_Router/F_Menu_Reintento always
    # transfer here with a valid activeQueue already set, so this path
    # should be unreachable in practice.
    fallback_id = set_queue_action_ids[f"Q_{TECHNICAL_FALLBACK_INTENT}"]
    actions.append(
        {
            "Identifier": compare_id,
            "Type": "Compare",
            "Parameters": {"ComparisonValue": "$.Attributes.activeQueue"},
            "Transitions": {
                "NextAction": fallback_id,
                "Errors": [{"NextAction": fallback_id, "ErrorType": "NoMatchingCondition"}],
                "Conditions": [
                    {
                        "NextAction": set_queue_action_ids[name],
                        "Condition": {"Operator": "Equals", "Operands": [name]},
                    }
                    for name in QUEUE_NAMES
                ],
            },
        }
    )
    return actions, compare_id


def build_ia_stub(
    intent: str, handoff_flow_id: str, greeting: str | None = None
) -> tuple[list[dict], str]:
    """Stub F_IA_<Intent>: no IA resolution yet -- just seeds the plan's
    attribute schema and hands off straight to the matching human queue via
    F_Handoff_Humano. Real IA (Lex/Bedrock) attaches here in a later phase.

    `greeting`, when set, sends a fixed MessageParticipant to the customer
    before the handoff -- used by F_IA_Ventas so every contact routed here
    sees the company's service list before still being transferred to a
    human agent.
    """
    set_attrs_id, transfer_id, end_id = uid(), uid(), uid()
    queue_name = f"Q_{intent}"
    actions = [
        {
            "Identifier": set_attrs_id,
            "Type": "UpdateContactAttributes",
            "Parameters": {
                "Attributes": {
                    "activeIntent": intent.lower(),
                    "activeQueue": queue_name,
                    "activeFlow": f"F_IA_{intent}",
                }
            },
            "Transitions": {
                "NextAction": transfer_id,
                "Errors": [{"NextAction": end_id, "ErrorType": "NoMatchingError"}],
                "Conditions": [],
            },
        },
        {
            "Identifier": transfer_id,
            "Type": "TransferToFlow",
            "Parameters": {"ContactFlowId": flow_arn(handoff_flow_id)},
            "Transitions": {
                "NextAction": end_id,
                "Errors": [{"NextAction": end_id, "ErrorType": "NoMatchingError"}],
                "Conditions": [],
            },
        },
        {"Identifier": end_id, "Type": "EndFlowExecution", "Parameters": {}, "Transitions": {}},
    ]

    if greeting is None:
        return actions, set_attrs_id

    greeting_id = uid()
    actions.append(
        {
            "Identifier": greeting_id,
            "Type": "MessageParticipant",
            "Parameters": {"Text": greeting},
            "Transitions": {
                "NextAction": set_attrs_id,
                "Errors": [{"NextAction": set_attrs_id, "ErrorType": "NoMatchingError"}],
                "Conditions": [],
            },
        }
    )
    return actions, greeting_id


def build_menu_router(
    ia_flow_ids: dict[str, str], reintento_flow_id: str
) -> tuple[list[dict], str]:
    """F_Menu_Router handles ONLY the message that triggered this contact --
    it never prompts or waits for input. telegram-inbound-adapter's
    chat_service.py seeds $.Attributes.initialMessage with that exact
    message at StartChatContact time, so this flow can classify it directly.

    This used to send "Contanos brevemente en que podemos ayudarte." and
    wait on GetParticipantInput first -- but the customer had *already* said
    something to trigger the contact, and that message kept racing with (and
    winning against) this prompt: GetParticipantInput doesn't discard
    messages that existed before it started waiting, so the customer's
    original message answered its own prompt before they ever saw it,
    producing "Contanos brevemente..." and the handoff message back-to-back
    with no real pause. See ../context.md (gotcha #7, 2026-07-11 entry in
    Historial) for the full incident. Classifying $.Attributes.initialMessage
    directly instead of re-prompting sidesteps that race entirely: there is
    no GetParticipantInput here to race against. If it doesn't match, the
    customer lands in F_Menu_Reintento, which prompts and waits properly
    (nothing pending to be consumed early at that point).
    """
    end_id = uid()
    invoke_nlu_id = uid()
    compare_intent_id = uid()
    transfer_reintento_id = uid()
    transfer_ids = {intent: uid() for intent in INTENTS}

    actions = [
        {"Identifier": end_id, "Type": "EndFlowExecution", "Parameters": {}, "Transitions": {}},
        {
            # Clasifica $.Attributes.initialMessage con connect-nlu-router-menu.
            # ResponseValidation=STRING_MAP porque el handler siempre
            # devuelve un dict plano de strings (nunca null -- ver su
            # README.md, "" reemplaza a la clasificacion inconclusa/fallo).
            # Synchronous, 8s es el maximo que permite Connect para este
            # modo -- si Bedrock no responde a tiempo, cae a
            # TECHNICAL_FALLBACK_INTENT igual que cualquier otra falla del
            # clasificador.
            "Identifier": invoke_nlu_id,
            "Type": "InvokeLambdaFunction",
            "Parameters": {
                "LambdaFunctionARN": NLU_LAMBDA_ARN,
                "InvocationTimeLimitSeconds": "8",
                "InvocationType": "SYNCHRONOUS",
                "ResponseValidation": {"ResponseType": "STRING_MAP"},
                "LambdaInvocationAttributes": {"message": "$.Attributes.initialMessage"},
            },
            "Transitions": {
                "NextAction": compare_intent_id,
                "Errors": [
                    {
                        "NextAction": transfer_ids[TECHNICAL_FALLBACK_INTENT],
                        "ErrorType": "NoMatchingError",
                    }
                ],
                "Conditions": [],
            },
        },
        {
            # Sin match -> no cae a una cola directo: pasa a F_Menu_Reintento,
            # que pregunta y re-clasifica en loop (ver su docstring) hasta
            # detectar una intencion valida. Solo la falla tecnica del bloque
            # de arriba (error del Lambda) sigue cayendo directo a
            # TECHNICAL_FALLBACK_INTENT -- eso no es "no entendi tu pedido",
            # es un problema nuestro.
            "Identifier": compare_intent_id,
            "Type": "Compare",
            "Parameters": {"ComparisonValue": "$.External.intent"},
            "Transitions": {
                "NextAction": transfer_reintento_id,
                "Errors": [
                    {"NextAction": transfer_reintento_id, "ErrorType": "NoMatchingCondition"}
                ],
                "Conditions": [
                    {
                        "NextAction": transfer_ids[intent],
                        "Condition": {"Operator": "Equals", "Operands": [intent.lower()]},
                    }
                    for intent in INTENTS
                ],
            },
        },
        {
            "Identifier": transfer_reintento_id,
            "Type": "TransferToFlow",
            "Parameters": {"ContactFlowId": flow_arn(reintento_flow_id)},
            "Transitions": {
                "NextAction": end_id,
                "Errors": [{"NextAction": end_id, "ErrorType": "NoMatchingError"}],
                "Conditions": [],
            },
        },
    ]
    for intent in INTENTS:
        actions.append(
            {
                "Identifier": transfer_ids[intent],
                "Type": "TransferToFlow",
                "Parameters": {"ContactFlowId": flow_arn(ia_flow_ids[intent])},
                "Transitions": {
                    "NextAction": end_id,
                    "Errors": [{"NextAction": end_id, "ErrorType": "NoMatchingError"}],
                    "Conditions": [],
                },
            }
        )
    return actions, invoke_nlu_id



def build_menu_reintento() -> tuple[list[dict], str]:
    """
    Este flujo solo envia el mensaje de reintento y desconecta al cliente.
    Al escribir su siguiente mensaje en Telegram, el inbound adapter generara 
    un nuevo contacto que volvera a evaluar su intencion desde cero.
    """
    msg_id = uid()
    disconnect_id = uid()

    actions = [
        {
            "Identifier": disconnect_id,
            "Type": "DisconnectParticipant",
            "Parameters": {},
            "Transitions": {},
        },
        {
            "Identifier": msg_id,
            "Type": "MessageParticipant",
            "Parameters": {"Text": REINTENTO_MESSAGE},
            "Transitions": {
                "NextAction": disconnect_id,
                "Errors": [{"NextAction": disconnect_id, "ErrorType": "NoMatchingError"}],
                "Conditions": [],
            },
        },
    ]
    return actions, msg_id


def build_entrada_omnicanal(
    menu_flow_id: str, ia_flow_ids: dict[str, str]
) -> tuple[list[dict], str]:
    end_id = uid()
    compare_id = uid()
    transfer_menu_id = uid()
    transfer_ids = {intent: uid() for intent in INTENTS}

    actions = [
        {"Identifier": end_id, "Type": "EndFlowExecution", "Parameters": {}, "Transitions": {}},
        {
            "Identifier": transfer_menu_id,
            "Type": "TransferToFlow",
            "Parameters": {"ContactFlowId": flow_arn(menu_flow_id)},
            "Transitions": {
                "NextAction": end_id,
                "Errors": [{"NextAction": end_id, "ErrorType": "NoMatchingError"}],
                "Conditions": [],
            },
        },
        {
            "Identifier": compare_id,
            "Type": "Compare",
            "Parameters": {"ComparisonValue": "$.Attributes.activeIntent"},
            "Transitions": {
                # Empty/unset activeIntent (first message in the conversation)
                # falls through here -> present the menu.
                "NextAction": transfer_menu_id,
                "Errors": [{"NextAction": transfer_menu_id, "ErrorType": "NoMatchingCondition"}],
                "Conditions": [
                    {
                        "NextAction": transfer_ids[intent],
                        "Condition": {"Operator": "Equals", "Operands": [intent.lower()]},
                    }
                    for intent in INTENTS
                ],
            },
        },
    ]
    for intent in INTENTS:
        actions.append(
            {
                "Identifier": transfer_ids[intent],
                "Type": "TransferToFlow",
                "Parameters": {"ContactFlowId": flow_arn(ia_flow_ids[intent])},
                "Transitions": {
                    "NextAction": end_id,
                    "Errors": [{"NextAction": end_id, "ErrorType": "NoMatchingError"}],
                    "Conditions": [],
                },
            }
        )
    return actions, compare_id


def create_or_update_reintento_flow(ia_flow_ids: dict[str, str] = None) -> str:
    """Ensures F_Menu_Reintento exists with its disconnect content applied."""
    flow_id = get_flow_id_optional("F_Menu_Reintento")
    if flow_id is None:
        placeholder_end = uid()
        flow_id = create_flow(
            "F_Menu_Reintento",
            "Pregunta la intencion de nuevo si el NLU fallo y termina",
            "CONTACT_FLOW",
            [
                {
                    "Identifier": placeholder_end,
                    "Type": "EndFlowExecution",
                    "Parameters": {},
                    "Transitions": {},
                }
            ],
            placeholder_end,
        )
    reintento_actions, reintento_start = build_menu_reintento()
    update_flow("F_Menu_Reintento", reintento_actions, reintento_start)
    return flow_id


def update_existing_flows() -> None:
    # Applies the current flows logic to the already-deployed flows.

    queue_ids = get_queue_ids()
    ia_flow_ids = {intent: get_flow_id(f"F_IA_{intent}") for intent in INTENTS}
    handoff_id = get_flow_id("F_Handoff_Humano")

    handoff_actions, handoff_start = build_handoff_humano(queue_ids)
    update_flow("F_Handoff_Humano", handoff_actions, handoff_start)

    reintento_id = create_or_update_reintento_flow(ia_flow_ids)

    menu_actions, menu_start = build_menu_router(ia_flow_ids, reintento_id)
    menu_id = update_flow("F_Menu_Router", menu_actions, menu_start)

    entrada_actions, entrada_start = build_entrada_omnicanal(menu_id, ia_flow_ids)
    update_flow("F_Entrada_Omnicanal", entrada_actions, entrada_start)

    ventas_actions, ventas_start = build_ia_stub(
        "Ventas", handoff_id, greeting=VENTAS_SERVICES_MESSAGE
    )
    update_flow("F_IA_Ventas", ventas_actions, ventas_start)


def main() -> None:
    if "--update" in sys.argv:
        update_existing_flows()
        return

    queue_ids = get_queue_ids()

    espera_actions, espera_start = build_espera_cola()
    create_flow(
        "F_Espera_Cola",
        "Mensaje de espera mientras el contacto esta en cola",
        "CUSTOMER_QUEUE",
        espera_actions,
        espera_start,
    )

    handoff_actions, handoff_start = build_handoff_humano(queue_ids)
    handoff_id = create_flow(
        "F_Handoff_Humano",
        "Setea la working queue desde activeQueue y transfiere al asesor",
        "CONTACT_FLOW",
        handoff_actions,
        handoff_start,
    )

    ia_flow_ids: dict[str, str] = {}
    for intent in INTENTS:
        greeting = VENTAS_SERVICES_MESSAGE if intent == "Ventas" else None
        actions, start = build_ia_stub(intent, handoff_id, greeting=greeting)
        ia_flow_ids[intent] = create_flow(
            f"F_IA_{intent}",
            f"Stub sin IA -- enruta directo a Q_{intent} via F_Handoff_Humano",
            "CONTACT_FLOW",
            actions,
            start,
        )

    reintento_id = create_or_update_reintento_flow(ia_flow_ids)

    menu_actions, menu_start = build_menu_router(ia_flow_ids, reintento_id)
    menu_id = create_flow(
        "F_Menu_Router",
        "Presenta el menu y clasifica la intencion inicial (sin IA)",
        "CONTACT_FLOW",
        menu_actions,
        menu_start,
    )

    entrada_actions, entrada_start = build_entrada_omnicanal(menu_id, ia_flow_ids)
    entrada_id = create_flow(
        "F_Entrada_Omnicanal",
        "Punto de entrada para Telegram: evita volver al menu en cada mensaje",
        "CONTACT_FLOW",
        entrada_actions,
        entrada_start,
    )

    print("\nDone. Next steps:")
    print(f"  1. Set CONNECT_CONTACT_FLOW_ID={entrada_id} in .env and the")
    print("     deployed Lambda's environment.")
    print(
        "  2. Update infra/permissions-policy.json's ConnectStartChat "
        f"Resource to {flow_arn(entrada_id)}"
    )
    print("     and re-apply it with `aws iam put-role-policy`.")
    print("  3. Re-run scripts/deploy.ps1 to pick up the settings change.")


if __name__ == "__main__":
    main()
