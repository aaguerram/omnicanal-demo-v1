# Agentic Skincare Backend

Proyecto backend para un asistente virtual de comercio de cuidado de la piel con IA, utilizando **LangGraph**, **Amazon Bedrock (`amazon.nova-micro-v1:0` vía `ChatBedrockConverse`, mismo modelo que `connect-nlu-router-menu`)** y **Feature Slice Architecture**.

El único servicio de Google que usa este proyecto es **Firestore**, como vector store del RAG de `info_productos` (ver `../context.md`). El chat y los embeddings corren en Bedrock.

## Prerrequisitos

1. **Credenciales de AWS**: el chat (`ChatBedrockConverse`) y los embeddings (`BedrockEmbeddings`) se autentican con la cadena estándar de credenciales de AWS (perfil local, variables de entorno, o el rol de ejecución del Lambda) -- no hace falta nada adicional acá.
2. **Google Cloud SDK**: Debes tener instalado y configurado `gcloud` (solo para Firestore).
3. **Autenticación en GCP**:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project skincare-ai-commerce
   ```
4. **Firestore**: Asegúrate de tener una base de datos de Firestore nativa creada (`gcloud firestore databases create --location=us-central1 --type=firestore-native`).

## Configuración del Entorno

1. El entorno virtual de Python está en la carpeta `venv`. Para activarlo en Windows:
   ```bash
   .\venv\Scripts\activate
   ```
   En macOS/Linux:
   ```bash
   source venv/bin/activate
   ```
2. Instala las dependencias (si no se han instalado):
   ```bash
   pip install -r requirements.txt
   ```
3. Crea tu archivo `.env` basándote en `.env.example`:
   ```env
   ENVIRONMENT=development
   GOOGLE_CLOUD_PROJECT=skincare-ai-commerce
   ```

## Arquitectura

El proyecto utiliza **Feature Slice Architecture**:
- `/core`: Contiene el estado global de LangGraph (`state.py`), el enrutador (`router.py`) y el grafo principal (`main_graph.py`).
- `/features/diagnostico_sintomas`: Subgrafo encargado del análisis de síntomas, imágenes (visual) y 'slot filling' conversacional.
- `/features/info_productos`: Subgrafo encargado del RAG contra la base de datos de Firestore.
- `/entrypoints`: Punto de entrada de la aplicación. En este caso `web.py` levanta una interfaz con **Gradio**.
- `/pdf_productos`: Directorio donde se deben colocar los PDFs de manuales e información de productos.
- `/scripts`: Scripts utilitarios, como `ingestar_pdfs.py`.

## Ingesta de PDFs (Base de Datos RAG)

1. Coloca los archivos `.pdf` con la información de los productos dentro del directorio `pdf_productos`.
2. Ejecuta el script de ingesta para procesarlos y guardar los embeddings (Vector Search) en Firestore:
   ```bash
   python scripts/ingestar_pdfs.py
   ```

## Ejecución del Servidor Web (Gradio)

Para levantar la interfaz conversacional, ejecuta:
```bash
python entrypoints/web.py
```
Por defecto, la interfaz estará disponible en `http://localhost:7860`.
Podrás escribir texto sobre tus síntomas o dudas de productos y adjuntar imágenes de tu piel para un análisis visual.

## Despliegue como AWS Lambda (`F_IA_Ventas`)

Además del demo de Gradio, este agente se despliega como una función Lambda
(`entrypoints/lambda_handler.py`) invocada directo desde el contact flow
`F_IA_Ventas` de Amazon Connect (ver
`../telegram-inbound-adapter/scripts/provision_connect_flows.py` y
`../context.md`), con el mismo patrón de logging que
`telegram-inbound-adapter`/`connect-nlu-router-menu`
(`logging.basicConfig()` + `logging.getLogger().setLevel(logging.INFO)`
explícito -- el runtime de Lambda ya le adjunta un handler al logger raíz
antes de correr el código, así que `basicConfig()` solo no alcanza; y nada de
`extra={...}` en `logger.info`, el formatter default de CloudWatch solo
renderiza `%(message)s`).

**A diferencia de esos dos proyectos, acá los logs NUNCA incluyen el texto
del mensaje del cliente ni `patient_info`** (nivel de acné, alergias, tipo de
piel) -- son datos de salud/sensibles y las reglas del proyecto
(`.agents/rules/04-features-seguridad-testing.md`) prohíben registrarlos.
Solo se loguea metadata de control (presencia del id, largo del mensaje,
`turn_status`, contador de intentos, `end_conversation`, `escalate`), nunca
identificadores.

### Por qué hace falta estado persistido

Amazon Connect invoca este servicio de forma stateless por turno (pasa el
mensaje y un `conversation_id` estable; `ContactId` queda como fallback):
`InvokeLambdaFunction`) -- sin nada más, Luna olvidaría el historial de la
conversación y `patient_info` en cada mensaje nuevo. `repositories/session_repository.py`
persiste ambos (más el contador de turnos "no_resuelto" seguidos) en DynamoDB,
tabla `SkincareAgentSessions` (PK histórica `pk` = `contact#<conversation_id>`, TTL
en `ttl`, mismo patrón single-table que `ConversationSessions`).

### Contrato de AgentCore y del Lambda directo legado

Igual que `connect-nlu-router-menu`, soporta dos formas de invocación:
1. Directa por boto3: `{"conversation_id": "...", "contact_id": "...", "message": "..."}`.
2. Bloque "Invoke AWS Lambda function" de un contact flow de Connect:
   `event["Details"]["Parameters"]` (+ `ContactData.ContactId` como fallback
   si el flow no pasa `conversation_id` explícito).

AgentCore responde con booleanos nativos para que
`agentic-skincare-adapter` traduzca el resultado a Amazon Connect:

```json
{"response_text": "...", "status": "en_progreso|finalizado|no_resuelto", "escalate": false, "end_conversation": false}
```

El Lambda directo legado responde siempre un `STRING_MAP` plano (Connect lo
exige):

```json
{"response_text": "...", "status": "en_progreso|finalizado|no_resuelto", "escalate": "true|false", "end_conversation": "true|false"}
```
`escalate="true"` es la señal que el contact flow usa (bloque `Compare`) para
transferir a `F_Handoff_Humano` (`Q_Ventas`). Se pone en `true` cuando:
- `status == "no_resuelto"` durante `max_consecutive_unresolved` turnos
  seguidos (default 3, ver `core/settings.py`) -- se resetea a 0 apenas un
  turno vuelve a ser `en_progreso` o `finalizado`.

`status == "finalizado"` solo indica que Luna resolvió el objetivo del turno:
no escala ni cobra atención humana. El siguiente mensaje continúa en el mismo
AgentCore mientras el routing siga vigente.

`end_conversation=true` es una señal independiente. El mismo clasificador de
estado del turno la activa, sin otra llamada al modelo, solo cuando el último
mensaje del cliente expresa inequívocamente que ya no necesita ayuda o que
desea cerrar el chat (por ejemplo, "eso es todo" o "puedes cerrar"). Un
agradecimiento con otra pregunta o el rechazo de un producto mantienen el
valor en `false`; tampoco se infiere a partir de `status="finalizado"`.

Cuando se activa, `process_turn` devuelve una despedida determinística, fuerza
`status="finalizado"`, conserva `escalate=false` y entrega
`end_conversation=true`. El adapter puede entonces limpiar el routing de
skincare; Amazon Connect envía esa despedida y desconecta el contacto. El
siguiente mensaje del cliente vuelve a comenzar por el NLU inicial.

Nunca propaga excepciones: cualquier falla (Bedrock caído, Firestore, DynamoDB,
evento mal formado) devuelve una disculpa genérica con `escalate="true"`,
para que el contact flow nunca tenga que distinguir "error técnico" de "no
pude ayudarte" -- ambos terminan en el asesor humano.

### Autenticación con AWS y GCP

El chat (`ChatBedrockConverse`) y los embeddings (`BedrockEmbeddings`) se
autentican con la cadena estándar de credenciales de AWS -- en Lambda, el rol
de ejecución (`infra/permissions-policy.json` incluye `bedrock:InvokeModel`
para `amazon.nova-micro-v1:0` y `amazon.titan-embed-text-v2:0`); en local, tu
perfil de AWS CLI. El Lambda además necesita credenciales de GCP, pero solo
para Firestore (RAG de `info_productos`): en Lambda (a diferencia de local,
que usa `gcloud auth application-default login`), se usa una service account
dedicada cuyo JSON key vive en Secrets Manager y se carga una sola vez por
cold start (`entrypoints/lambda_handler.py`, `_load_gcp_credentials`),
apuntando `GOOGLE_APPLICATION_CREDENTIALS` a un archivo temporal.

### Scripts de despliegue

- `scripts/create_gcp_service_account.ps1` — crea la service account de GCP
  (`agentic-skincare-lambda@skincare-ai-commerce.iam.gserviceaccount.com`,
  rol `datastore.viewer`, solo para Firestore) y descarga su JSON key.
- `scripts/provision.ps1` — setup inicial en AWS: tabla DynamoDB
  (`SkincareAgentSessions`), secreto en Secrets Manager con el JSON de GCP,
  rol IAM (incluye `bedrock:InvokeModel`), repo ECR + imagen, función Lambda,
  y el permiso + asociación para que Amazon Connect pueda invocarla directo
  desde un contact flow. Requiere `$env:GCP_SERVICE_ACCOUNT_KEY_FILE`
  apuntando al key del paso anterior, y Docker Desktop corriendo localmente.
- `scripts/package_lambda.ps1` / `scripts/deploy.ps1` — build + push de la
  **imagen de contenedor** (`Dockerfile`, base `public.ecr.aws/lambda/python:3.12`)
  a ECR. No es un zip: la pila de LangChain/Firestore (`langchain-community`,
  transitivo de `langchain-google-firestore`) da **459 MB descomprimidos**,
  por encima del límite de 250 MB que permite un Lambda por zip -- una imagen
  soporta hasta 10 GB, así que evita tener que podar dependencias "no usadas"
  de forma frágil.
  `docker build` usa `--provenance=false`: el manifest OCI que genera buildx
  por default no lo acepta `CreateFunction` (`InvalidParameterValueException:
  image manifest ... not supported`).
- Después de `provision.ps1`, correr
  `../telegram-inbound-adapter/scripts/provision_connect_flows.py --update`
  para que `F_IA_Ventas` apunte a este Lambda (ver `SKINCARE_LAMBDA_ARN` ahí).

**Memoria/timeout: 2048 MB / 60s, no el default.** A 512 MB/20s, el cold
start (importar langchain/langgraph/google-cloud-firestore) por sí solo
superaba el límite de 10s de la fase INIT de Lambda (separado del timeout de
la función y no configurable) y la invocación fallaba antes de llegar al
handler. Lambda asigna CPU proporcional a la memoria, así que más memoria
acelera ese import; el timeout extra cubre además las 2-3 llamadas
secuenciales a Bedrock (router + nodo de feature + `estado_turno`) de una
invocación en frío.

### Variables de entorno (Lambda)

| Variable | Propósito |
| --- | --- |
| `DYNAMODB_TABLE_NAME` | Tabla de sesiones (default `SkincareAgentSessions`) |
| `GOOGLE_CLOUD_PROJECT` | Proyecto de GCP (`skincare-ai-commerce`), solo para Firestore |
| `GCP_SECRET_NAME` | Secreto en Secrets Manager con el JSON de la service account de GCP |
| `NOVA_MODEL_ID` | Modelo de Bedrock para chat/routing (default `amazon.nova-micro-v1:0`, mismo que `connect-nlu-router-menu`) |
| `AWS_REGION` | Región de Bedrock/DynamoDB (default `us-east-1`) -- en Lambda la provee el runtime automáticamente |

### Estado actual (cuenta real, 042278586355, us-east-1)

Desplegado: service account de GCP creada, tabla `SkincareAgentSessions`,
secreto en Secrets Manager, rol IAM, repo ECR + imagen, función Lambda
`agentic-skincare-backend` (2048 MB / 60s, ver arriba), asociada a la
instancia de Connect. Probado con `aws lambda invoke` directo, incluyendo
memoria de conversación entre dos turnos con el mismo `conversation_id`.

**Migración de Vertex AI/Gemini a Amazon Bedrock (2026-07-12, ver
`../context.md`):** todo el código y la infraestructura de este README ya
reflejan Bedrock (`amazon.nova-micro-v1:0`, mismo modelo que
`connect-nlu-router-menu`) como único proveedor de chat/embeddings. El rol
IAM en la cuenta real (`agentic-skincare-backend-lambda-role`) todavía no
tiene el statement `BedrockSkincareModels` de `infra/permissions-policy.json`
ni la function ya redesplegada con la imagen nueva -- falta correr
`put-role-policy` con la policy actualizada, redeploy (`scripts/deploy.ps1`)
y reingestar el catálogo (`scripts/ingestar_pdfs.py`) porque el embedding
model cambió (`text-embedding-004` de Vertex AI, 768 dim, a
`amazon.titan-embed-text-v2:0` de Bedrock, 1024 dim por default) -- los
vectores viejos en la colección `catalogo_productos` de Firestore no son
compatibles con el nuevo modelo de embeddings.

El flujo actual usa un contacto corto por turno: `F_IA_Ventas` invoca
`agentic-skincare-adapter`, envía siempre `response_text` mediante
`MessageParticipant` y desconecta si no hay escalamiento. El adaptador
mantiene un `conversation_id` estable en `ConversationSessions`, por lo que
el siguiente contacto recupera el historial de esta tabla y omite el NLU.
El antiguo `F_IA_Ventas_Loop` puede seguir existiendo como recurso legado en
Connect, pero no se actualiza ni se referencia.
