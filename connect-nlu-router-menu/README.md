# connect-nlu-router-menu

Servicio de NLU (detección de intención) para el enrutamiento omnicanal de
Amazon Connect. Clasifica el mensaje de un cliente en una de tres
intenciones (`soporte`, `ventas`, `cobranza`) usando un grafo de
**LangGraph** desplegado como **AWS Lambda**. Hubo una cuarta intención,
`atencion`, usada como catch-all para saludos/mensajes ambiguos -- se
eliminó 2026-07-11 (ver `../context.md`, Historial) porque ese catch-all
matcheaba cualquier saludo como una intención "válida", evitando que el
mensaje cayera en el loop de reintento de `F_Menu_Reintento`.

Ver `../context.md` para cómo encaja en el resto del proyecto omnicanal —
este servicio se invoca hoy directamente desde el contact flow
`F_Menu_Router` de Amazon Connect (ver "Estado de la integración" más
abajo); el código está listo pero el despliegue/permiso contra la cuenta
real todavía no se aplicó.

## Por qué existe

`telegram-inbound-adapter` enrutaba la intención inicial con un menú
numérico (`F_Menu_Router`). Este servicio es el reemplazo basado en NLU:
recibe el texto libre del cliente y devuelve la intención detectada, para
que `F_Menu_Router` pueda saltarse la comparación numérica y branchear
directo al `F_IA_*` correspondiente.

## Arquitectura

```
src/connect_nlu_router_menu/
  handler.py    entrypoint de Lambda (lambda_handler)
  graph.py      grafo de LangGraph: un nodo que clasifica la intencion
  models.py     Intent, VALID_INTENTS, IntentState (el estado del grafo)
  settings.py   env vars: AWS_REGION, NOVA_MODEL_ID
```

### El grafo (LangGraph)

Un solo nodo (`classify_intent`) que le pasa el mensaje a un chat model
(`ChatBedrockConverse`, por defecto `amazon.nova-micro-v1:0` — el modelo más
barato/rápido de Bedrock para clasificación de texto, ver `../context.md`)
con un system prompt que fuerza una respuesta de una sola palabra entre
`soporte`, `ventas`, `cobranza` o `ninguna` (saludos, consultas generales,
o cualquier cosa que no encaje claramente en las otras tres -- ver
`SYSTEM_PROMPT` en `graph.py`). `ninguna` no es una intención válida
(`VALID_INTENTS` no la incluye a propósito): recibe el mismo tratamiento
que cualquier clasificación inconclusa (`intent: None`).

El `SYSTEM_PROMPT` se amplió 2026-07-11 con definiciones y reglas de
desambiguación más detalladas por categoría (ej.: un mensaje de factura con
palabras como "error" sigue siendo `cobranza`, no `soporte`; no asumir que
el cliente ya tiene un servicio si no lo dice) y una instrucción explícita
de ignorar cualquier intento de prompt injection dentro del mensaje del
cliente -- en base a dos prompts de referencia que aportó el negocio. El
contrato de salida (una palabra, mismo `VALID_INTENTS`) no cambió.

**Nunca propaga excepciones.** Cualquier falla del modelo (throttling,
Bedrock caído, credenciales faltantes, respuesta inesperada), la respuesta
"ninguna", o cualquier clasificación inconclusa dejan `intent: None` —
quien invoque este servicio debe caer a su propio fallback en ese caso
(`F_Menu_Router` transfiere a `F_Menu_Reintento` sin match, y a una cola
fija en caso de falla técnica -- ver "Estado de la integración" más abajo).

El LLM se inyecta en `build_graph(llm)` en vez de construirse adentro —
`ChatBedrockConverse` resuelve credenciales de AWS **al construirse** (a
diferencia de un `boto3.client()` plano, que no valida nada hasta la primera
llamada real), así que si se construyera a nivel de módulo, **importar
`handler.py` fallaría en cualquier entorno sin credenciales reales** (tests,
`pip install -e .`, etc.). Por eso `handler.py` arma el grafo perezosamente en
`_get_graph()`, cacheado, en el primer `lambda_handler()` real — donde el rol
de ejecución de Lambda ya tiene credenciales.

### El entrypoint (AWS Lambda)

```python
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    ...
```

Sin API Gateway ni SNS de por medio. Soporta dos formas de invocación:

1. **Directa vía boto3** (`lambda.invoke`, ver "Invocar la función desplegada"
   más abajo): `event = {"message": "..."}` en el nivel superior.
2. **Bloque "Invoke AWS Lambda function" de un contact flow de Amazon
   Connect** (usado hoy por `F_Menu_Router`, ver "Estado de la integración"):
   Connect envuelve los parámetros configurados en el bloque
   (`LambdaInvocationAttributes`) dentro de `event["Details"]["Parameters"]`,
   junto con `event["Details"]["ContactData"]` -- no manda `message` en el
   nivel superior. `_extract_message()` en `handler.py` soporta ambas formas.

**Contrato de la petición/respuesta de este servicio:**

```jsonc
// event (invocación directa)
{ "message": "quiero contratar facturacion electronica" }

// event (desde un contact flow de Connect)
{
  "Details": { "ContactData": { ... }, "Parameters": { "message": "..." } },
  "Name": "ContactFlowEvent"
}

// respuesta (ambos casos)
{ "intent": "ventas" }         // "" (string vacio) si fue inconclusa/fallo
```

La respuesta usa `""` en vez de `null` para el caso inconclusivo/fallo porque
Connect exige que la respuesta de un Lambda invocado con
`ResponseValidation: STRING_MAP` sea un dict plano de **strings** -- rechaza
`null`. El estado interno del grafo (`IntentState.intent`) sigue siendo
`Intent | None`; la conversión a `""` ocurre solo en el borde de
`lambda_handler`.

### Logging — mismo patrón que los otros dos proyectos

```python
logging.basicConfig(level=logging.INFO)
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)
```

El segundo call es necesario porque el runtime de Lambda le adjunta un
handler al logger raíz antes de que corra el código, así que `basicConfig()`
solo es un no-op sin él. Igual que en `telegram-inbound-adapter`/
`telegram-outbound-adapter`: **nada de `logger.info(msg, extra={...})`** — el
formatter por defecto solo renderiza `%(message)s` y descarta `extra` en
silencio; todo dato que se necesite ver va embebido en el string del mensaje
(f-string).

## Requirements

- Python 3.12+ (Lambda usa el runtime `python3.14`, ver "Deployment")
- Una cuenta AWS con acceso a Amazon Bedrock (`amazon.nova-micro-v1:0`
  habilitado en `us-east-1`).

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env
pytest
```

## Correr localmente (sin desplegar)

```powershell
.venv\Scripts\python.exe scripts\run_local.py "quiero contratar facturacion electronica"
```

Esto sí necesita credenciales de AWS reales resueltas localmente (`aws
login`, ver gotcha de `botocore[crt]` en `../context.md`) porque
`ChatBedrockConverse` las valida al construirse, en el primer invoke.

## Configuración

| Variable | Propósito |
| --- | --- |
| `AWS_REGION` | Región de Bedrock (default `us-east-1`) — en Lambda la provee el runtime automáticamente, no hace falta setearla a mano |
| `NOVA_MODEL_ID` | Modelo usado para clasificar (default `amazon.nova-micro-v1:0`) |

## Deployment

- `scripts/package_lambda.ps1` — builds `lambda-package.zip` con wheels
  Linux/x86_64 para el runtime `python3.14` de Lambda (`pip install
  --platform manylinux2014_x86_64 --only-binary=:all:` para bajar los wheels
  correctos desde Windows).
- `scripts/provision.ps1` — creación única: rol IAM (`infra/trust-policy.json`
  + `infra/permissions-policy.json`) y la función Lambda.
- `scripts/deploy.ps1` — reconstruye el paquete y sube el código nuevo a la
  función ya existente.

### Currently deployed (cuenta 042278586355, us-east-1)

| Resource | Value |
| --- | --- |
| Lambda function | `connect-nlu-router-menu` (python3.14, x86_64) |
| IAM role | `connect-nlu-router-menu-lambda-role` |

Para desplegar cambios de código: `.\scripts\deploy.ps1`.

### Invocar la función desplegada

```python
import boto3, json

client = boto3.client("lambda", region_name="us-east-1")
response = client.invoke(
    FunctionName="connect-nlu-router-menu",
    Payload=json.dumps({"message": "quiero contratar facturacion electronica"}).encode(),
)
print(json.loads(response["Payload"].read()))
```

## Estado de la integración

**Enganchado directo desde `F_Menu_Router`** (contact flow de Connect,
generado por `telegram-inbound-adapter/scripts/provision_connect_flows.py`,
función `build_menu_router`): desde 2026-07-11 el flow YA NO pide el
mensaje con `GetParticipantInput` -- invoca esta función Lambda directo con
el bloque nativo "Invoke AWS Lambda function"
(`LambdaInvocationAttributes: {"message": "$.Attributes.initialMessage"}`,
síncrono, timeout 8s -- el máximo que permite Connect en ese modo), y
branchea con un `Compare` sobre `$.External.intent` hacia el `F_IA_*`
correspondiente. `$.Attributes.initialMessage` es el mensaje que disparó el
contacto, sembrado por `telegram-inbound-adapter/chat_service.py` en
`StartChatContact` -- ver `../context.md` (gotcha #7) para el porqué (evita
una carrera real con `GetParticipantInput` que existía antes). Sin match /
clasificación inconclusa ("ninguna") -> transfiere a `F_Menu_Reintento`, que
pregunta y reintenta indefinidamente hasta detectar una intención válida
(nunca cae a una cola humana en ese punto). Fallo técnico del Lambda ->
fallback directo a `F_IA_Soporte` (`TECHNICAL_FALLBACK_INTENT` en
`provision_connect_flows.py`).

**Ya aplicado contra la cuenta real** (042278586355, 2026-07-10, con
actualizaciones el 2026-07-11):
1. Función Lambda `connect-nlu-router-menu` provisionada (`scripts/provision.ps1`
   nunca se había corrido antes de esto -- ver Historial en `../context.md`
   sobre el bug de empaquetado que apareció en el primer intento real).
2. Asociada a la instancia de Connect (`connect associate-lambda-function`) y
   con permiso `lambda:InvokeFunction` para `connect.amazonaws.com`
   condicionado al ARN de la instancia (`lambda add-permission`).
3. `F_Menu_Router` actualizado (`provision_connect_flows.py --update`) --
   `describe-contact-flow` contra la cuenta real confirma que el bloque
   `InvokeLambdaFunction` y el `Compare` sobre `$.External.intent` quedaron
   publicados tal como los genera `build_menu_router`.
4. 2026-07-11: redeploy del Lambda con el prompt sin "atencion" (`ninguna`
   en su lugar) y `F_Menu_Router` regenerado para clasificar
   `$.Attributes.initialMessage` en vez de usar `GetParticipantInput`.

Verificado con `aws lambda invoke` directo -- "Hola" clasifica `{"intent":
""}` (antes de este cambio hubiera sido `"atencion"`), y un pedido real
clasifica bien. Pendiente: una prueba end-to-end real disparando un chat
contact completo por Telegram (no solo la función invocada de forma
directa) para confirmar el comportamiento dentro de una ejecución real del
flow -- ver Roadmap en `../context.md`.

La alternativa que se evaluó (invocar esta función desde
`chat_service.py` de `telegram-inbound-adapter`, antes de `StartChatContact`,
sembrando `activeIntent` directamente -- igual que la implementación
anterior con `NovaIntentClassifier`, ver Historial en `../context.md`) sigue
sin implementarse; `F_Entrada_Omnicanal` conserva su atajo por `activeIntent`
ya seteado, útil sobre todo para reconexiones.

## Tests

```powershell
pytest
```

`tests/test_graph.py` prueba el grafo con un LLM mockeado (sin red).
`tests/test_handler.py` prueba el entrypoint monkeypencheando `_get_graph`
(sin construir `ChatBedrockConverse` real, así no requiere credenciales de
AWS).
