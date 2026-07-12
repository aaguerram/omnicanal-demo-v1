# context.md — Omnicanalidad: Telegram ↔ Amazon Connect

> **Para el agente que lea esto**: este archivo es la fuente de verdad de qué
> existe hoy y por qué. Antes de tocar algo, léelo. Después de implementar
> algo nuevo (una funcionalidad, un fix no trivial, un cambio de arquitectura),
> **actualiza este archivo en el mismo turno** — no lo dejes para después. Ver
> la sección "Cómo mantener este archivo" al final.

## Qué es esto

Integración omnicanal: clientes escriben por **Telegram**, la conversación se
enruta a **Amazon Connect** (colas, routing profile, contact flows) para que
un asesor humano la atienda desde el CCP (Contact Control Panel). Es un
piloto — todavía no hay IA real resolviendo casos ni agentes reales
conectados de forma permanente.

Cuenta AWS: `042278586355`, región `us-east-1`.
Instancia Connect: `intuito-connect-omni` (`1029ff15-e0f3-4b9c-bab2-377c17509765`).
Bot de Telegram: `@intuito_soporte_test_v1_bot`.

## Los tres servicios

El código vive en tres proyectos Python **independientes**, hermanos en este
mismo directorio, cada uno con su propio `pyproject.toml`, `.venv` y
`pytest`. Los dos primeros no comparten código entre sí (hay algo de
duplicación intencional: `TelegramClient`, `SessionRepository`,
`telemetry.py` existen en ambos, cada uno con la porción que necesita) — el
contrato entre ellos es la tabla DynamoDB y el secreto de Secrets Manager,
ambos propiedad de `telegram-inbound-adapter`. El tercero
(`connect-nlu-router-menu/`) se invoca directo desde el contact flow
`F_Menu_Router` (bloque nativo de Connect, no desde código Python de los
otros dos) — código listo, despliegue/permisos contra la cuenta real
pendientes (ver su propia sección más abajo).

### `telegram-inbound-adapter/` — Telegram → Connect

Lambda `telegram-inbound-adapter`, detrás de API Gateway
(`POST /telegram/webhook`). Recibe updates de Telegram y los mete a Connect.

```
Telegram → API Gateway → Lambda telegram-inbound-adapter
    1. Valida X-Telegram-Bot-Api-Secret-Token
    2. Busca sesión activa en DynamoDB (pk = telegram#<chat_id>)
    3. Si existe: SendMessage (Connect Participant Service) con el texto del usuario
    4. Si no existe (o el SendMessage de arriba fallo por sesion stale):
         StartChatContact (el texto del usuario viaja SOLO como el atributo de
         contacto `initialMessage` -- a proposito, NUNCA como InitialMessage
         ni SendMessage; ver gotcha #7/#12, resuelto 2026-07-11: un mensaje
         real de cliente sentado en el canal desde el arranque del contacto
         rompe el primer GetParticipantInput que el contacto encuentre)
         → StartContactStreaming   (ANTES de crear la conexión, ver gotchas)
         → CreateParticipantConnection (con ConnectParticipant=True)
    5. Responde 200 a Telegram
```

Estructura (`src/telegram_inbound_adapter/`):
- `handler.py` — entrypoint Lambda, wiring de dependencias en cold start.
- `validation.py` — valida el secret token del webhook y parsea el payload de Telegram.
- `services/chat_service.py` — orquestación: sesión existente vs. nueva, reconexión si el contacto de Connect ya murió.
- `repositories/session_repository.py` — tabla `ConversationSessions` (dueño de la escritura).
- `clients/connect_client.py` — wrapper de boto3 `connect` / `connectparticipant`.
- `clients/telegram_client.py` — `sendMessage` a la Bot API.
- `models.py` — `TelegramUpdate`/`TelegramMessage` (parseo de webhook), `SessionRecord`, `SessionStatus`.
- `settings.py` — env vars: `CONNECT_INSTANCE_ID`, `CONNECT_CONTACT_FLOW_ID`, `CHAT_EVENTS_TOPIC_ARN`, `DYNAMODB_TABLE_NAME`, `TELEGRAM_SECRET_NAME` (todos obligatorios salvo overrides locales).
- `telemetry.py` — OpenTelemetry a consola, **solo para dev local** (`handler.py` nunca lo importa).

Scripts clave (`scripts/`):
- `provision.ps1` — setup inicial: tabla DynamoDB, secreto, rol IAM, Lambda, ruta API Gateway, webhook de Telegram.
- `provision_queues_routing.ps1` — las 3 colas + el routing profile compartido.
- `provision_connect_flows.py` — los 8 contact flows (ver más abajo). Soporta `--update` para aplicar cambios a los flows YA desplegados sin recrearlos (preserva IDs referenciados por otros flows).
- `package_lambda.ps1` / `deploy.ps1` — build + push de código.
- `set_webhook.py` — apunta el webhook de Telegram al API Gateway desplegado o a un túnel local.
- `run_local.py` / `run_local_logged.ps1` — corre el handler detrás de un server HTTP local para probar sin desplegar.

README completo con tabla de "Currently deployed": `telegram-inbound-adapter/README.md`.

### `telegram-outbound-adapter/` — Connect → Telegram

Lambda `telegram-outbound-adapter`, suscrita al SNS topic
`telegram-inbound-adapter-chat-events` (real-time chat message streaming de
Connect). Relee mensajes de agente/flow y los manda a Telegram.

```
Amazon Connect (mensaje de agente o de un flow) → SNS → Lambda telegram-outbound-adapter
    1. Parsea el evento (ConnectStreamingMessage)
    2. Busca a qué chat de Telegram pertenece (pk = contact#<ContactId>)
    3. Si ContentType es "chat.ended" -> marca la sesión ENDED en DynamoDB
    4. Si el rol es CUSTOMER -> ignora (sería hacerle eco a su propio mensaje)
    5. Si no -> TelegramClient.send_message(chat_id, contenido)
```

Estructura (`src/telegram_outbound_adapter/`): mismo patrón que el inbound
pero recortado — `handler.py`, `models.py` (`ConnectStreamingMessage`,
`SessionStatus`), `repositories/session_repository.py` (solo lectura +
`mark_ended`, sin `put_session`), `clients/telegram_client.py`,
`settings.py` (sin nada de Connect: `DYNAMODB_TABLE_NAME`,
`TELEGRAM_SECRET_NAME`), `telemetry.py` (igual que el inbound).

Scripts: mismo patrón (`provision.ps1`, `package_lambda.ps1`, `deploy.ps1`).
`run_local.py` aquí es distinto: como este Lambda lo dispara SNS (no HTTP),
el script invoca `lambda_handler` directo con un JSON de evento de ejemplo
(`scripts/sample_sns_event.json`).

README completo: `telegram-outbound-adapter/README.md`.

### `connect-nlu-router-menu/` — NLU de intención (invocado desde F_Menu_Router)

Servicio de detección de intención (`soporte`/`ventas`/`cobranza`) que
reemplaza el enrutamiento por menú numérico dentro de `F_Menu_Router` con
NLU real.

- **Stack:** grafo de **LangGraph** (un solo nodo, clasifica el mensaje del
  cliente) desplegado como **AWS Lambda** (`handler.py` / `lambda_handler`).
- **Modelo:** `amazon.nova-micro-v1:0` vía `ChatBedrockConverse`
  (`langchain-aws`) — mismo modelo que la implementación anterior embebida
  en `telegram-inbound-adapter` (ver Historial), ahora aislado en este
  servicio.
- **Contrato:** soporta dos formas de invocación —
  1. directa por boto3 (`{"message": "..."}` en el nivel superior), y
  2. desde el bloque "Invoke AWS Lambda function" de un contact flow de
     Connect (`event["Details"]["Parameters"]["message"]`) — es la que usa
     `F_Menu_Router` hoy.
  En ambos casos responde `{"intent": "ventas" | "soporte" | "cobranza" |
  ""}` — `""` (no `null`) significa clasificación inconclusa, respuesta
  explícita "ninguna" del modelo, o falla del modelo, porque Connect exige
  `STRING_MAP` (sin `null`) en la respuesta de un Lambda invocado desde un
  flow. El llamador cae a su propio fallback en ese caso (nunca propaga
  excepciones).
  **"atencion" ya no es una intención clasificable** (se eliminó
  2026-07-11, ver Historial): el system prompt definía "atencion" como
  catch-all para "saludos, consultas generales, o si la intención no es
  clara" -- eso hacía que CUALQUIER saludo matcheara una cola real en vez de
  caer al loop de `F_Menu_Reintento`. Ahora el modelo responde
  explícitamente "ninguna" para esos casos (fuera de `VALID_INTENTS`, mismo
  tratamiento que cualquier clasificación inconclusa).
- **Estructura** (`src/connect_nlu_router_menu/`): `handler.py` (entrypoint
  Lambda, `_extract_message()` soporta las dos formas de evento),
  `graph.py` (el grafo de LangGraph), `models.py` (`Intent`, `IntentState`),
  `settings.py` (`AWS_REGION`, `NOVA_MODEL_ID`).
- **Deploy:** `scripts/package_lambda.ps1` + `scripts/deploy.ps1`. Rol de
  ejecución + policies en `infra/`.
- **Integración con `F_Menu_Router`:** el flow (generado por
  `telegram-inbound-adapter/scripts/provision_connect_flows.py`, función
  `build_menu_router`) YA NO pide el mensaje con `GetParticipantInput` --
  invoca este Lambda directo sobre `$.Attributes.initialMessage` (síncrono,
  timeout 8s — máximo que permite Connect en ese modo) y branchea con un
  `Compare` sobre `$.External.intent`. Match → transfiere al `F_IA_*`
  correspondiente. Sin match → `F_Menu_Reintento` (ver la sección de contact
  flows). Falla del Lambda (técnica, no "no entendí") → fallback directo a
  `F_IA_Soporte` (`TECHNICAL_FALLBACK_INTENT`).
  **Desplegado contra la cuenta real** (042278586355, 2026-07-10, redeploy
  2026-07-11 con el prompt sin "atencion"): Lambda provisionada, asociada a
  la instancia de Connect (`AssociateLambdaFunction`) con permiso
  `lambda:InvokeFunction` para `connect.amazonaws.com`. Confirmado con `aws
  lambda invoke` directo: "Hola" → `{"intent": ""}`, un pedido real →
  clasifica bien. Pendiente: una prueba end-to-end disparando un chat
  contact real de punta a punta.

README completo con detalle de arquitectura, contrato y pasos de deploy:
`connect-nlu-router-menu/README.md`.

## Recurso compartido: DynamoDB `ConversationSessions`

Tabla single-table, PK = `pk` (string), sin sort key. Dos formas de ítem:

```jsonc
// Sesión — escrita solo por el inbound (put_session)
{
  "pk": "telegram#<chat_id>",
  "channel": "telegram",
  "external_user_id": "<chat_id>",
  "connect_contact_id": "...",
  "participant_id": "...",
  "participant_token": "...",
  "connection_token": "...",
  "status": "ACTIVE" | "ENDED",
  "created_at": "...", "updated_at": "...",
  "ttl": <epoch seconds>
}

// Índice secundario contact -> chat — también escrito por el inbound,
// leído por el outbound para resolver "este ContactId es de qué chat"
{
  "pk": "contact#<connect_contact_id>",
  "channel": "telegram",
  "external_user_id": "<chat_id>",
  "ttl": <epoch seconds>
}
```

El outbound solo lee y hace `mark_ended` — nunca escribe una sesión nueva.
Este contrato de forma de ítem está **duplicado en ambos proyectos** (cada
uno tiene su propia clase `SessionRepository`); si cambia el shape, hay que
actualizar los dos.

## Amazon Connect: colas, routing profile, contact flows

Diseño: **una cola por motivo de atención**, no por canal (el canal es un
atributo del contacto: `channel=telegram`). Así Web/WhatsApp podrían
sumarse después sin duplicar colas ni flows.

- **Colas** (3): `Q_Soporte`, `Q_Ventas`, `Q_Cobranza`.
  (`Q_No_Detectado_Humano` existió y se eliminó — ver Historial. `Q_Atencion`
  también existió y se eliminó 2026-07-11 — ver Historial y la sección de
  `connect-nlu-router-menu` más arriba.)
- **Routing profile** (1): `RP_Asesores_Mensajeria_Omnicanal`, asociado a
  las 3 colas (`DefaultOutboundQueueId` apunta a `Q_Soporte` desde que se
  borró `Q_Atencion`). Un solo pool de asesores atiende todo.
- **Contact flows** (8), sin IA real de resolución todavía — los `F_IA_*` son
  stubs (salvo `F_IA_Ventas`, que ya agrega un mensaje fijo de servicios):

  | Flow | Qué hace |
  | --- | --- |
  | `F_Entrada_Omnicanal` | Punto de entrada (`CONNECT_CONTACT_FLOW_ID`). Si `activeIntent` ya está seteado, transfiere directo al `F_IA_*` correspondiente (evita repetir el menú en cada mensaje); si no, va a `F_Menu_Router`. |
  | `F_Menu_Router` | Maneja SOLO el mensaje que disparó el contacto -- invoca el Lambda `connect-nlu-router-menu` directo sobre `$.Attributes.initialMessage` (`InvokeLambdaFunction`, síncrono, 8s) y compara `$.External.intent` (`Compare`). Ya no manda ningún prompt ni usa `GetParticipantInput` (ver gotcha #7, resuelto 2026-07-11): el cliente ya dijo algo para iniciar el contacto, no hay nada que esperar en este primer turno. Match → transfiere al `F_IA_*` correspondiente. Sin match de intención → transfiere a `F_Menu_Reintento` (ver abajo). Fallo del Lambda (falla técnica, no "no entendí") → fallback directo a `F_IA_Soporte` (`TECHNICAL_FALLBACK_INTENT`). |
  | `F_Menu_Reintento` | A donde cae `F_Menu_Router` cuando no se detectó una intención válida. Manda un mensaje explicando el alcance ("no pude identificar tu consulta, solo puedo ayudarte con Soporte/Ventas/Cobranza...", `REINTENTO_MESSAGE` en `provision_connect_flows.py`), pide el mensaje con `GetParticipantInput` (acá sí, porque en este punto no hay nada pendiente que pueda "contestar" el prompt antes de tiempo) y re-clasifica. Sin match otra vez → se **retransfiere a sí mismo** (`TransferToFlow` con su propio `ContactFlowId`) — sin límite de vueltas y **sin caer nunca a una cola humana en este punto**, a pedido explícito: el cliente no pasa a una cola sin que antes se haya detectado una intención válida. Timeout/fallo técnico sigue cayendo a `TECHNICAL_FALLBACK_INTENT` (no cuenta como "vuelta" del reintento). Ver "por qué el loop es entre flows y no un back-edge interno" más abajo. |
  | `F_IA_Soporte` / `Cobranza` | Stub: setea `activeIntent`/`activeQueue`/`activeFlow`, transfiere a `F_Handoff_Humano`. Acá es donde engancharía una IA de resolución real más adelante. |
  | `F_IA_Ventas` | Igual que los otros stubs, pero primero manda un `MessageParticipant` fijo con el listado de servicios (`VENTAS_SERVICES_MESSAGE` en `provision_connect_flows.py`) antes de transferir a `F_Handoff_Humano` — el agente humano sigue interviniendo después. |
  | `F_Handoff_Humano` | Lee `activeQueue`, manda mensaje de "Gracias, un asesor te atenderá en breve.", `Set working queue`, `Transfer to queue`. |
  | `F_Espera_Cola` | Flow tipo `CUSTOMER_QUEUE` con mensaje de espera. **Existe pero no está enganchado** a ninguna cola todavía (se decidió no arriesgar un parámetro de Connect no verificado). Sin esto, el hold es el silencio/música por defecto de Connect. |

  **`F_Menu_Reintento` y por qué el loop es entre flows, no dentro de uno
  solo** (2026-07-11): el requisito era "si no se detecta la intención,
  repetir el ciclo de pregunta/clasificación indefinidamente, sin límite y
  sin pasar nunca a un humano en este punto". Un loop clásico (`Compare`
  apuntando hacia atrás a su propio `GetParticipantInput` dentro del mismo
  flow) es exactamente el patrón que causó el incidente real de la gotcha
  #7 más abajo. La solución fue partir esto en dos flows: `F_Menu_Router`
  maneja solo el primer intento, y `F_Menu_Reintento` es quien absorbe
  todos los reintentos, transfiriéndose **a sí mismo** (`TransferToFlow`)
  cada vez que no matchea. La diferencia clave: `TransferToFlow` termina la
  ejecución actual y arranca una completamente nueva desde el
  `StartAction` del flow destino — no es una flecha `NextAction` dentro del
  mismo grafo de acciones. Como `$.StoredCustomerInput` es un atributo de
  contacto que no se limpia entre pasadas, un back-edge interno relee el
  valor viejo sin esperar un mensaje nuevo; cruzar el límite de flow evita
  eso porque cada `GetParticipantInput` de cada vuelta nueva es una acción
  con un `Identifier` que aparece una sola vez en su propio grafo (nunca se
  reejecuta el mismo nodo dos veces dentro de una misma ejecución). Como el
  `ContactFlowId` de un flow solo lo asigna Connect al crearlo, no se puede
  escribir la auto-referencia por adelantado: `F_Menu_Reintento` se crea
  primero con contenido placeholder (un `EndFlowExecution` vacío) solo para
  obtener su Id, y después se sobreescribe con el contenido real que ya
  puede apuntarse a sí mismo (`create_or_update_reintento_flow` en
  `provision_connect_flows.py`). Verificado estructuralmente (sin ciclos
  internos, todas las referencias resuelven) con un chequeo ad hoc antes de
  aplicar contra la cuenta real; **pendiente la prueba end-to-end real**
  (escribir texto sin sentido varias veces seguidas en un chat contact real
  y confirmar que cada vuelta espera un mensaje nuevo del cliente, no un
  loop a velocidad de máquina como la vez pasada).

  **Pendiente/asunción a confirmar:** el texto de `VENTAS_SERVICES_MESSAGE`
  ("Facturación electrónica, TaxFlash, etc.") es un placeholder — reemplazar
  por el listado real y completo de servicios cuando se confirme.

  Los 8 flows se generan programáticamente en
  `telegram-inbound-adapter/scripts/provision_connect_flows.py` (no a mano)
  para no cometer errores de referencias entre `Identifier`/`NextAction`.
  Para modificar un flow: editar el builder correspondiente
  (`build_menu_router`, `build_handoff_humano`, etc.) y correr
  `--update` (aplica in-place, conserva IDs). Antes de aplicar contra la
  cuenta real, correr el chequeo de ciclos/referencias que se usó durante el
  desarrollo (ver Historial) — un flow con un ciclo puede causar un loop de
  mensajes real en producción.

- **Atributos de contacto** usados: `channel`, `telegramUserId`,
  `telegramUsername`, `source`, `conversationState`, `initialMessage`,
  `activeIntent`, `activeQueue`, `activeFlow`. Sembrados por el inbound en
  `StartChatContact` (los primeros 5) y por los flows de Connect (los
  últimos 3). `initialMessage` (agregado 2026-07-11) es el mensaje que
  disparó el contacto -- lo lee `F_Menu_Router` para clasificar sin
  necesidad de `GetParticipantInput` (ver gotcha #7).

## Gotchas / lecciones aprendidas (no las vuelvas a descubrir)

Estos son bugs reales que costaron tiempo de debugging en producción. Si vas
a tocar el streaming, los flows, o el logging, leé esto primero.

1. **`logging.basicConfig()` no funciona en Lambda.** El runtime de Python
   de Lambda ya le adjunta un handler al logger raíz antes de que corra tu
   código, así que `basicConfig()` es un no-op y tus `logger.info(...)`
   quedan mudos. Fix: `logging.getLogger().setLevel(logging.INFO)` explícito
   (ya aplicado en ambos `handler.py`).

2. **`extra={...}` en `logger.info()` no aparece en el texto de CloudWatch.**
   El formatter por defecto solo renderiza `%(message)s`. Cualquier dato que
   quieras ver en los logs tiene que ir embebido en el string del mensaje
   (f-string), no en `extra=`. Ya corregido en ambos proyectos.

3. **Política del SNS topic: `ArnEquals`, no `ArnLike`.** El
   `aws:SourceArn` que manda Connect al publicar es el ARN pelado de la
   instancia (`arn:aws:connect:region:account:instance/<id>`), sin sufijo.
   Una condición `ArnLike` con `/*` al final **nunca hace match** →
   Connect nunca logra autorización para publicar → cero mensajes en el
   topic, cero métricas de fallo, cero error visible en ningún lado. Ver
   `telegram-outbound-adapter/scripts/provision.ps1` para la política
   correcta.

4. **`CreateParticipantConnection` necesita `ConnectParticipant=True`**
   para que el streaming en tiempo real realmente entregue eventos al SNS
   topic. Sin este flag, `StartContactStreaming` "funciona" (no tira error)
   pero no fluye nada.

5. **Orden de llamadas al crear una sesión**: `StartChatContact` →
   `StartContactStreaming` → `CreateParticipantConnection` (documentado así
   por AWS). El flow de Connect puede empezar a correr apenas se llama
   `StartChatContact`, así que si streaming no está activo lo antes posible,
   se pierden los primeros mensajes del flow (p. ej. el menú).

6. **`GetParticipantInput` no soporta `Transitions.Conditions` directamente**
   — solo guarda el texto en `$.StoredCustomerInput` (si `StoreInput=True`).
   Para ramificar por el valor hay que poner un `Compare` aparte justo
   después, leyendo `$.StoredCustomerInput`.

7. **NUNCA hagas que `Compare`/`GetParticipantInput` vuelvan a apuntar a sí
   mismos o al bloque anterior dentro del mismo flow.**
   `$.StoredCustomerInput` es un atributo a nivel de **contacto**, no se
   limpia entre pasadas — un loop de "si no matchea, volvé a preguntar" re-lee
   el mismo valor viejo por siempre, sin esperar input nuevo real. Esto causó
   un incidente real: el bot le mandó el menú al usuario cada ~2.5 segundos
   sin parar hasta que se cortó el contacto a mano (`aws connect
   stop-contact`). El diseño original evitaba esto directamente: sin match,
   `F_Menu_Router` transfería derecho a `F_IA_Atencion` (fallback
   determinístico, sin ciclos). Desde 2026-07-11 sí hay un loop real
   (`F_Menu_Reintento`, ver la sección de contact flows más arriba) porque el
   negocio lo pidió explícitamente — pero implementado como `TransferToFlow`
   **entre dos flows** (termina la ejecución actual y arranca una nueva desde
   cero), nunca como una flecha `NextAction`/`Errors` hacia atrás **dentro**
   del mismo flow, que es específicamente lo que rompió esto la vez pasada.

   **Efecto colateral relacionado, RESUELTO 2026-07-11 (en dos pasadas, ver
   gotcha #12 para la segunda):** el primer mensaje del cliente (el que
   dispara `StartChatContact`) casi siempre se terminaba "consumiendo" como
   respuesta al menú antes de que el usuario lo viera -- `telegram-inbound-adapter`
   mandaba ese texto con un `SendMessage` separado justo después de crear el
   contacto, y ese envío competía con el propio `GetParticipantInput` de
   `F_Menu_Router`, que no descarta mensajes que ya existían antes de
   empezar a esperar. Síntoma real observado: el cliente escribía "Hola" y
   recibía "Contanos brevemente..." Y "Gracias, un asesor te atenderá en
   breve." pegados, sin pausa real, y "Hola" terminaba clasificado (por el
   catch-all de "atencion" que también se eliminó ese día, ver la sección de
   `connect-nlu-router-menu`) como si fuera una consulta real. Primer intento
   de fix: `F_Menu_Router` se rediseñó para clasificar el mensaje desde un
   atributo de contacto (`$.Attributes.initialMessage`) en vez de
   `GetParticipantInput`, y ese mismo texto se mandó también como
   `InitialMessage` de `StartChatContact` para que siguiera viéndose en la
   transcripción -- **esto resultó incompleto, ver gotcha #12**: dejaba un
   mensaje real sin consumir en el canal, que rompía el primer
   `GetParticipantInput` que el contacto SÍ llegaba a usar (el de
   `F_Menu_Reintento`). El fix final fue sacar `InitialMessage` por completo
   -- el texto viaja únicamente como atributo, nunca como mensaje de chat.

8. **`Compare` no acepta `NoMatchingError` como `ErrorType`** — para el caso
   de "ninguna condición matcheó" es `NoMatchingCondition`. Otros bloques sí
   usan `NoMatchingError`. Si `create-contact-flow`/`update-contact-flow-content`
   tira `InvalidContactFlowException` con mensaje vacío, mirar el campo
   `problems` de la respuesta cruda (no viaja en `str(exception)`, hay que
   capturar `e.response`).

9. **PowerShell 5.1 + `aws.exe` + JSON inline**: pasar JSON como argumento
   directo (`--media-concurrencies '[...]'`) rompe por escapado de comillas,
   y `Set-Content -Encoding utf8` agrega BOM que el parser de JSON de la CLI
   no tolera (cae al parser de shorthand y tira un error confuso de
   `Expected: '='`). Solución: escribir a un archivo temporal con
   `-Encoding ascii` (sin BOM) y pasar `file://ruta`.

10. **Eventos de Connect sin `ContactId`**: los eventos
    `connect:event:participant.joined` y
    `application/vnd.amazonaws.connect.event.chat.ended` que llegan por el
    streaming usan `InitialContactId`, no `ContactId`. Hoy
    `ConnectStreamingMessage` solo tiene `ContactId` como alias, así que
    estos eventos fallan el parseo y quedan logueados como
    `outbound_message_parse_failed` (inofensivo — se ignoran — pero es
    ruido). Pendiente de arreglo, ver Roadmap.

11. **`pip install --platform X` (cross-compilación para Lambda) hace match
    exacto de un solo tag, no la cadena de compatibilidad manylinux
    descendente que sí usa una instalación nativa.** `numpy` (dependencia
    transitiva de `langchain-aws`, usada en `connect-nlu-router-menu`) solo
    publica wheels `cp314` con tag `manylinux_2_27`/`manylinux_2_28`,
    mientras que `pydantic-core` (vía `pydantic`) solo publica
    `manylinux_2_17`/`manylinux2014` -- pedir un único `--platform` deja
    siempre a uno de los dos sin wheel instalable, y pip cae a
    `pydantic-core==0.0.1` (un placeholder vacío reservado en PyPI, no la
    librería real) o falla directo. Fix: pasar `--platform` **varias veces**
    en el mismo comando (`manylinux2014_x86_64`, `manylinux_2_27_x86_64`,
    `manylinux_2_28_x86_64`) para cubrir ambos tags. Además,
    `$ErrorActionPreference = "Stop"` de PowerShell **no** detiene el script
    si `pip install` falla -- un exit code no-cero de un ejecutable nativo no
    cuenta como error de PowerShell, así que sin chequear `$LASTEXITCODE`
    explícito el script sigue y empaqueta un zip sin dependencias en
    silencio (esto pasó de verdad: `connect-nlu-router-menu` quedó
    "provisionado" con éxito aparente pero con un paquete de ~0MB sin
    `langgraph`/`langchain-aws` instalados, hasta que se detectó al invocar
    la función real). Ambos fixes ya aplicados en
    `connect-nlu-router-menu/scripts/package_lambda.ps1`.

12. **`StartChatContact`'s `InitialMessage` deja un mensaje real "sin
    consumir" en el canal del participante -- rompe el PRIMER
    `GetParticipantInput` que el contacto encuentre, no importa cuál sea.**
    Descubierto 2026-07-11 arreglando la gotcha #7: se cambió
    `chat_service.py` para mandar el primer mensaje del cliente como
    `InitialMessage` de `StartChatContact` (entrega atómica, en vez de un
    `SendMessage` separado) y `F_Menu_Router` se rediseñó para clasificarlo
    desde un atributo (`$.Attributes.initialMessage`) sin usar
    `GetParticipantInput`. Contraintuitivo: como `F_Menu_Router` ya no toca
    `GetParticipantInput`, ese mensaje nunca queda "marcado como leído" por
    el motor de flows -- y el PRIMER `GetParticipantInput` que el contacto sí
    llega a ejecutar (el de `F_Menu_Reintento`, cuando no se detecta
    intención) lo encuentra ahí. Pero en vez de devolverlo como si fuera
    input nuevo, tira `NoMatchingError` casi al instante (confirmado con
    logs: el Lambda de NLU se invocó una sola vez para todo el contacto, y
    aun así el cliente terminó en la cola de fallback técnico
    `TECHNICAL_FALLBACK_INTENT` menos de 15 segundos después de crearse el
    contacto -- muy por debajo de los 120s de `InputTimeLimitSeconds`).
    Síntoma real observado: cliente escribe "Hola" → bot responde
    correctamente "No pude identificar tu consulta..." (`F_Menu_Reintento`
    sí corrió una vez) → **inmediatamente después**, sin que el cliente
    escriba nada más, "Gracias, un asesor te atenderá en breve." (cayó a
    `F_IA_Soporte`/`Q_Soporte` por el `NoMatchingError` fantasma). Fix: sacar
    `InitialMessage` por completo de `start_chat_contact`
    (`connect_client.py`) -- el mensaje que dispara el contacto viaja SOLO
    como el atributo `initialMessage`, nunca como mensaje de chat real.
    Trade-off conocido y aceptado: el primerísimo mensaje de una
    conversación ya no aparece como burbuja propia en la transcripción de
    Connect/CCP (sí sigue llegando al cliente de Telegram, porque eso lo
    maneja Telegram, no Connect) -- todos los mensajes siguientes sí se ven
    normal vía `SendMessage`. Lección más general: cualquier mecanismo que
    inyecte un mensaje de cliente "ya resuelto" en el canal (`InitialMessage`,
    o cualquier API futura similar) es tan peligroso para `GetParticipantInput`
    como el `SendMessage` racing de la gotcha #7 -- el problema no es
    el timing, es la sola presencia de un mensaje no consumido por un
    `GetParticipantInput` anterior.

## Diagnóstico — cómo mirar qué está pasando

```powershell
# Logs recientes de cada Lambda (ajustar la ventana de tiempo)
aws logs filter-log-events --log-group-name "/aws/lambda/telegram-inbound-adapter" `
  --start-time <epoch_ms> --region us-east-1 --query "events[].message" --output text
aws logs filter-log-events --log-group-name "/aws/lambda/telegram-outbound-adapter" `
  --start-time <epoch_ms> --region us-east-1 --query "events[].message" --output text

# Estado de la sesión actual de un chat_id en DynamoDB
aws dynamodb get-item --table-name ConversationSessions `
  --key file://key.json --region us-east-1
# key.json: {"pk":{"S":"telegram#<chat_id>"}}

# Estado / cola / atributos de un contacto de Connect
aws connect describe-contact --instance-id 1029ff15-e0f3-4b9c-bab2-377c17509765 `
  --contact-id <id> --region us-east-1

# Cortar un contacto que quedó colgado o en loop
aws connect stop-contact --instance-id 1029ff15-e0f3-4b9c-bab2-377c17509765 `
  --contact-id <id> --region us-east-1

# Webhook de Telegram: a dónde apunta, si hay errores de entrega
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Notas:
- `aws.exe` en este entorno usa `aws login` (device auth), no keys estáticas
  — si un script de Python falla al importar con
  `MissingDependencyException` sobre el "login credential provider",
  instalar `botocore[crt]` (ya está en los `pyproject.toml` de dev de ambos
  proyectos).
- Después de una sesión de pruebas, si el contacto quedó "colgado" esperando
  agente (sin loop, solo silencioso porque no hay agente conectado), no es
  un bug — hace falta alguien logueado como agente en el CCP de Connect para
  que conteste de verdad. Para limpiar antes del próximo test: `stop-contact`
  + borrar el ítem `telegram#<chat_id>` de DynamoDB.

## Roadmap / gaps conocidos (no implementado todavía)

- **IA real** en los `F_IA_*` (hoy son stubs que enrutan directo a la cola
  humana, salvo `F_IA_Ventas` que ya agrega un mensaje fijo antes del
  handoff). Mencionado explícitamente como fase futura desde el diseño
  original.
- **Prueba end-to-end de `connect-nlu-router-menu` vía `F_Menu_Router`**:
  desplegado y verificado con invocaciones directas del Lambda y con
  `describe-contact-flow` (ver su sección), pero todavía no se disparó un
  chat contact real de punta a punta para confirmar el bloque
  `InvokeLambdaFunction` corriendo dentro de una ejecución real del flow.
- **Prueba end-to-end del loop de `F_Menu_Reintento`, con el fix de gotcha
  #12 (sin `InitialMessage`) ya aplicado**: la primera vez que se probó esto
  contra un chat real (ver Historial) reveló el bug de la gotcha #12, ya
  corregido y redeployado, pero **todavía no se volvió a probar contra un
  chat real después del fix**. Falta disparar un chat real por Telegram y
  confirmar en la conversación real: (a) un saludo suelto ya NO recibe el
  mensaje de handoff pegado -- debería ver SOLO el mensaje de
  `F_Menu_Reintento` ("no pude identificar tu consulta...") y NADA más hasta
  que el cliente escriba algo nuevo; (b) escribir texto sin sentido varias
  veces seguidas mantiene al cliente en el loop, con una pausa real entre
  cada mensaje del bot y la respuesta del cliente (no una ráfaga instantánea
  como en las gotchas #7 y #12); (c) un pedido real y claro desde el primer
  mensaje ("necesito soporte técnico") clasifica bien y pasa directo a la
  cola correcta sin pasar por `F_Menu_Reintento`. Tener `aws connect
  stop-contact` a mano por las dudas.
- **`VENTAS_SERVICES_MESSAGE` es un placeholder** — confirmar el listado real
  y completo de servicios de la empresa (hoy dice "Facturación electrónica,
  TaxFlash, etc.").
- **`F_Espera_Cola` no está enganchado** a ninguna cola — falta confirmar
  el mecanismo exacto de Connect para asociar un customer queue flow (ver
  gotcha, no se quiso arriesgar sin validar contra la API real).
- **`InitialContactId` vs `ContactId`** en eventos de Connect sin
  `ContactId` (gotcha #10) — genera ruido de error inofensivo en los logs
  del outbound.
- **Web y WhatsApp** no están integrados — el diseño de colas/flows es
  channel-agnostic a propósito para poder sumarlos después sin duplicar
  colas/flows, pero no hay ningún adapter para esos canales todavía.

## Historial relevante (para no repetir decisiones ya tomadas)

- **2026-07-11 (tercera vuelta el mismo día)**: El fix de `InitialMessage`
  descripto en la entrada anterior (punto 2) resultó incompleto -- probado
  contra un chat real, el patrón exacto que se creía resuelto volvió a pasar
  pero un paso más adelante: el cliente escribía "Hola", el bot respondía
  bien "No pude identificar tu consulta..." (`F_Menu_Reintento` corriendo
  como se esperaba), pero **sin que el cliente escribiera nada más**
  aparecía enseguida "Gracias, un asesor te atenderá en breve.". Diagnóstico
  con logs de CloudWatch: el Lambda de NLU se había invocado una sola vez en
  todo el contacto (la clasificación de `F_Menu_Router`), y aun así el
  contacto terminó con `activeIntent=soporte`/`activeQueue=Q_Soporte` -- solo
  posible si el propio `GetParticipantInput` de `F_Menu_Reintento` tiró
  `NoMatchingError` de inmediato (cae a `TECHNICAL_FALLBACK_INTENT`) en vez
  de esperar un mensaje real, confirmado con `describe-contact`
  (`EnqueueTimestamp` a los 14 segundos de creado el contacto, muy por
  debajo del timeout de 120s). Causa raíz real: ver gotcha #12 --
  `InitialMessage` deja un mensaje sin consumir en el canal que rompe el
  PRIMER `GetParticipantInput` que el contacto encuentre, sin importar cuál
  sea. Fix definitivo: sacar `InitialMessage` de `start_chat_contact` por
  completo (`connect_client.py`) -- el mensaje viaja solo como atributo.
  Aprovechado el mismo cambio para mejorar el `SYSTEM_PROMPT` del NLU
  (`connect-nlu-router-menu/graph.py`) con definiciones y reglas de
  desambiguación más detalladas entre soporte/ventas/cobranza/ninguna (a
  pedido explícito, en base a dos prompts de referencia que aportó el
  negocio) -- sin cambiar el contrato de salida (una palabra, mismo
  `VALID_INTENTS`). Ambos Lambdas redeployados; sesión de prueba y contacto
  viejo limpiados (`stop-contact` + borrado del ítem en DynamoDB). Pendiente
  la misma prueba end-to-end real (ver Roadmap) -- esta vez confirmar
  también que `F_Menu_Reintento` realmente espera un mensaje nuevo antes de
  reclasificar.
- **2026-07-11 (más tarde el mismo día)**: Se probó el loop de
  `F_Menu_Reintento` recién agregado contra un chat real de Telegram y
  aparecieron dos bugs relacionados, ambos corregidos el mismo día:
  1. Un saludo suelto ("Hola") seguía cayendo derecho a una cola humana en
     vez de entrar al loop -- causa: el system prompt del NLU definía
     "atencion" como catch-all de "saludos, consultas generales, o si la
     intención no es clara" (`connect-nlu-router-menu/graph.py`), así que
     CUALQUIER mensaje ambiguo matcheaba una intención válida y nunca
     llegaba a "sin match". Fix: se eliminó "atencion" como intención
     clasificable (el modelo ahora responde "ninguna" para esos casos, ver
     la sección de `connect-nlu-router-menu`), y se eliminó la cola
     `Q_Atencion` y el flow `F_IA_Atencion` de la cuenta real (pedido
     explícito: "elimina la cola de atencion" — no debía quedar ningún
     destino automático para saludos/mensajes ambiguos). Las fallas
     técnicas (timeout, error del Lambda) ahora caen a `Q_Soporte`
     (`TECHNICAL_FALLBACK_INTENT` en `provision_connect_flows.py`) en vez de
     `Q_Atencion` -- decisión arbitraria pero razonable dado que un solo
     pool de asesores atiende las 3 colas restantes.
  2. El mensaje de handoff ("Gracias, un asesor te atenderá en breve.")
     aparecía pegado al prompt del menú, sin pausa real -- causa distinta,
     ver el "Efecto colateral relacionado" dentro de la gotcha #7:
     `chat_service.py` mandaba el primer mensaje del cliente con un
     `SendMessage` que competía con el propio `GetParticipantInput` de
     `F_Menu_Router`. Fix intentado en esta vuelta (**resultó incompleto,
     ver la entrada siguiente y gotcha #12**): ese primer mensaje pasó a
     viajar como `InitialMessage` de `StartChatContact` y como el nuevo
     atributo de contacto `initialMessage`; `F_Menu_Router` se rediseñó para
     clasificar ese atributo directo, sin prompt ni `GetParticipantInput` en
     el primer turno (ver `build_menu_router` en
     `provision_connect_flows.py`).
  Verificado en esta vuelta: Lambda redeployado y probado con `aws lambda
  invoke` directo ("Hola" → `{"intent": ""}`), los 8 flows re-verificados
  estructuralmente (sin ciclos, sin referencias colgantes a
  `F_IA_Atencion`), `Q_Atencion` desasociada del routing profile (incluyendo
  su uso como `DefaultOutboundQueueId`, una asociación separada de la cola
  normal que no era obvia) y borrada, `F_IA_Atencion` borrado,
  `telegram-inbound-adapter` redeployado. La prueba end-to-end real que
  faltaba fue justamente la que destapó que el punto 2 no estaba resuelto
  del todo -- ver la entrada de arriba.
- **2026-07-11**: Se agregó `F_Menu_Reintento` para que "no se detectó la
  intención" ya no caiga directo a `F_IA_Atencion` — ahora explica el
  alcance del menú y reintenta indefinidamente hasta detectar una intención
  válida, sin fallback a cola humana en ese punto (pedido explícito). Se
  evaluó desenrollar el reintento en N repeticiones fijas dentro del mismo
  flow (sin ciclos, pero con tope) y se descartó porque el requisito era
  explícitamente "sin límite". El loop real se implementó como
  `TransferToFlow` de `F_Menu_Reintento` hacia sí mismo, no como una flecha
  interna — ver el detalle en la sección de contact flows y en la gotcha #7.
  Falla técnica/timeout sigue sin contar como "vuelta" del reintento, sigue
  cayendo directo a `Atencion` igual que antes.
- **2026-07-10**: `F_Menu_Router` se cambió de menú numérico (1-4) a NLU real
  vía `connect-nlu-router-menu`, invocado directo desde el flow con el
  bloque nativo `InvokeLambdaFunction` (no desde código Python de
  `telegram-inbound-adapter`). Se evaluó también invocar el NLU desde
  `chat_service.py` antes de `StartChatContact` (opción descartada por ahora
  — ver la sección del servicio) y ponerlo en `F_Entrada_Omnicanal` en vez
  de `F_Menu_Router` (descartado porque hubiera duplicado la captura de
  input que ya vive en `F_Menu_Router` y dejado ese flow como código
  muerto). Al desplegar se descubrió que `connect-nlu-router-menu` nunca se
  había provisionado de verdad en la cuenta (el README decía "desplegado"
  pero `list-functions` no lo mostraba) y que su script de empaquetado tenía
  un bug real de resolución de dependencias (ver gotcha #11) que dejaba un
  zip vacío sin fallar el script — ambos se corrigieron en el mismo cambio.
- El proyecto arrancó como un solo Lambda (`telegram-inbound-adapter`) que
  hacía las dos direcciones. Se separó en dos servicios independientes por
  pedido explícito, manteniendo la misma tabla/secreto compartidos.
- Hubo un incidente real de spam (ver gotcha #7) causado por un loop en
  `F_Menu_Router`; se cortó el contacto en caliente (`stop-contact`) y se
  rediseñó el flow para eliminar el ciclo.
- `Q_No_Detectado_Humano` existió como quinta cola de fallback y se eliminó
  a pedido explícito — el fallback de "no entendí" ahora es directo a
  `Q_Atencion`, sin cola separada.
- El documento de arquitectura original (Landing Zone, WhatsApp vía AWS End
  User Messaging Social, etc.) está en `../recomendacion_1_arquitectura.md`,
  un nivel arriba de este archivo. Es la visión de largo plazo; este
  `context.md` describe lo que **realmente existe hoy**.

## Cómo mantener este archivo

Reglas para el agente (y para vos, humano leyendo esto):

1. **Actualizalo en el mismo turno** en que implementás algo, no "después".
2. Si agregás un recurso de AWS nuevo (cola, flow, Lambda, tabla), sumalo a
   la sección correspondiente con su nombre/ID real.
3. Si encontrás un bug no obvio (algo que la documentación de AWS no dice
   claramente, o que costó tiempo de debugging), agregalo a "Gotchas" con la
   causa raíz, no solo el síntoma — el objetivo es que el próximo agente no
   pierda el mismo tiempo.
4. Si cerrás algo del Roadmap, movelo de ahí a la sección correspondiente y
   anotá la decisión en Historial si fue una decisión de diseño no trivial.
5. Preferí describir **comportamiento y por qué**, no listar código línea
   por línea — el código mismo es la referencia para el detalle; este
   archivo es para orientarse rápido antes de leer el código.
6. Si una sección se vuelve muy larga o deja de ser precisa vs. la realidad,
   recortala — un `context.md` desactualizado es peor que uno corto.
