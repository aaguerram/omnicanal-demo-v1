# Regla 01 — Arquitectura general y límites del proyecto

## Rol del agente

Actúa como arquitecto/desarrollador senior Python + LangGraph. Prioriza una arquitectura simple, modular, testeable y segura.

No generes código rápido que rompa la estructura del proyecto. Antes de implementar, identifica la feature afectada, revisa los archivos existentes y modifica solo lo necesario.

## Objetivo del proyecto

El proyecto implementa un asistente IA conversacional para atención por canales como WhatsApp, Telegram, portal web o API, con:

- router de intención centralizado;
- system prompt global y prompts por dominio;
- carga controlada de contexto histórico;
- extracción estructurada de datos mediante schemas;
- RAG por dominio y búsqueda en tiempo de consulta;
- herramientas controladas para DB, pagos, visión, inventario y soporte;
- cache para consultas frecuentes y reducción de latencia;
- memoria conversacional con privacidad;
- validación de grounding para evitar respuestas inventadas;
- subgrafos para flujos secuenciales complejos.

## Estructura oficial del proyecto

```text
mi_proyecto_ia/
├── core/
│   ├── state.py
│   ├── main_graph.py
│   ├── router_agent.py
│   ├── context_loader.py          # Carga contexto histórico resumido y seguro
│   ├── system_prompt.py           # System prompt global y composición de contexto
│   ├── schemas.py                 # Schemas compartidos: router, tool plan, errores
│   ├── cache.py                   # Abstracción cache L1/L2
│   └── grounding.py               # Validación de evidencia antes de responder
│
├── features/
│   ├── info_corporativa/
│   │   ├── prompt.py
│   │   ├── rag_tool.py
│   │   ├── schemas.py
│   │   └── node.py
│   │
│   ├── catalogo_productos/
│   │   ├── prompt.py
│   │   ├── db_tool.py
│   │   ├── rag_tool.py            # Complementa datos de producto con documentos
│   │   ├── schemas.py
│   │   └── node.py
│   │
│   ├── ventas/
│   │   ├── prompt.py
│   │   ├── stripe_api.py
│   │   ├── schemas.py
│   │   └── node.py
│   │
│   └── diagnostico_visual/
│       ├── sub_state.py
│       ├── sub_graph.py
│       ├── agent_recopilador.py
│       ├── tool_validar_foto.py
│       ├── schemas.py
│       └── agent_conclusion.py
│
└── main.py
```

Si el repositorio todavía no tiene todos estos archivos, créalos solo cuando la tarea lo requiera. No agregues componentes vacíos sin uso real.

## Separación por capas

- `core/` contiene orquestación general, estado compartido, router, carga de contexto, system prompt, cache y reglas comunes.
- `features/` contiene cortes verticales independientes por dominio.
- Cada feature es dueña de su prompt, schemas, herramientas, nodo y lógica de dominio.
- `main.py` solo inicializa la app/API/CLI y llama al grafo principal.
- No coloques prompts, queries SQL, llamadas HTTP, secretos o reglas de negocio dentro de `main.py`.
- No mezcles lógica de ventas dentro de catálogo, ni lógica de catálogo dentro de diagnóstico visual.

## Responsabilidad de archivos principales

- `core/state.py`: define `AgentState` global. Solo variables compartidas clave.
- `core/main_graph.py`: construye el `StateGraph` principal y conecta nodos.
- `core/router_agent.py`: clasifica intención y decide ruta, sin ejecutar lógica de negocio.
- `core/context_loader.py`: carga contexto histórico mínimo, seguro y útil para el turno actual.
- `core/system_prompt.py`: compone instrucciones globales, políticas de respuesta, contexto y restricciones.
- `core/schemas.py`: define contratos compartidos para router, errores, tool calls y respuestas.
- `core/cache.py`: expone funciones genéricas de cache sin acoplarse a una feature.
- `core/grounding.py`: valida que la respuesta esté soportada por fuentes recuperadas.
- `features/*/prompt.py`: contiene plantillas del dominio.
- `features/*/schemas.py`: contiene modelos Pydantic/TypedDict específicos del dominio.
- `features/*/*_tool.py`: integra DB, RAG, APIs externas o servicios.
- `features/*/node.py`: adapta el estado global, ejecuta la feature y devuelve cambios al estado.

## Reglas de LangGraph

- Todo nodo recibe `state` y devuelve un diccionario parcial con cambios.
- No mutar el estado de forma implícita si se puede devolver un fragmento nuevo.
- Las rutas usan constantes o enums, nunca strings repetidos.
- El router siempre tiene fallback: `fuera_de_alcance`, `aclaracion` o `handoff_humano`.
- Usa subgrafos solo cuando el flujo tenga varios pasos dependientes.
- No conviertas un flujo simple en subgrafo sin necesidad.
- Cada nodo debe declarar qué lee y qué escribe del estado.

## Flujo lógico obligatorio por turno

```text
entrada_usuario
→ normalizar canal/sesión
→ cargar contexto histórico controlado
→ componer system prompt + contexto relevante
→ clasificar intención con router
→ extraer datos estructurados según schema
→ validar campos requeridos
→ ejecutar RAG/DB/API/tool si aplica
→ validar grounding
→ generar respuesta final
→ guardar resumen/facts útiles para próximos turnos
```

No saltes la extracción estructurada ni la validación de datos cuando una herramienta necesita parámetros.

## Intenciones mínimas del router

```text
info_corporativa
catalogo_productos
ventas
diagnostico_visual
soporte_o_reclamo
fuera_de_alcance
aclaracion
handoff_humano
```

El router debe devolver una salida estructurada, por ejemplo:

```python
{
    "intent": "catalogo_productos",
    "confidence": 0.87,
    "reason": "El usuario pregunta por beneficios e ingredientes de un producto.",
    "missing_fields": [],
    "next_node": "catalogo_productos"
}
```

Si la confianza es baja, pide aclaración antes de usar herramientas costosas o sensibles.

## Antipatrones prohibidos

- Un único archivo gigante con todo el flujo.
- Prompts mezclados con llamadas HTTP.
- SQL dentro de nodos si existe `db_tool.py`.
- Lógica de negocio dentro del router.
- Respuestas inventadas cuando RAG/DB no encuentra datos.
- Fotos, nombres, teléfonos, alergias o PII en logs.
- Rutas hardcodeadas repetidas.
- Dependencias circulares entre features.
- Crear herramientas que aceptan cualquier diccionario sin validar schema.
- Usar RAG para precio, stock o disponibilidad si esos datos viven en DB/inventario.
- Cachear diagnósticos visuales o fotos de clientes.
