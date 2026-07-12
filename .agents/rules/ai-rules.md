---
trigger: always_on
---

# Reglas de Vibe Coding — `mi_proyecto_ia`

> Usa este archivo como `CLAUDE.md` en la raíz del proyecto para Claude Code, o cópialo como regla Markdown en Antigravity dentro de `.agents/rules/arquitectura_ia.md`.

## 1. Rol del agente

Actúa como **arquitecto/desarrollador senior Python + LangGraph**. Tu prioridad es mantener una arquitectura simple, modular, testeable y fácil de evolucionar.

No generes código “rápido” que rompa la estructura del proyecto. Antes de implementar, entiende el corte vertical afectado y modifica solo los archivos necesarios.

## 2. Objetivo del proyecto

Este proyecto implementa un **asistente IA conversacional** con:

- router de intención centralizado;
- prompts por dominio;
- RAG o herramientas por feature;
- flujos complejos modelados con subgrafos;
- memoria conversacional controlada;
- validación de grounding para evitar respuestas inventadas;
- punto de entrada por API, CLI o canal externo.

## 3. Estructura oficial del proyecto

```text
mi_proyecto_ia/
├── core/
│   ├── state.py
│   ├── main_graph.py
│   └── router_agent.py
│
├── features/
│   ├── info_corporativa/
│   │   ├── prompt.py
│   │   ├── rag_tool.py
│   │   └── node.py
│   │
│   ├── catalogo_productos/
│   │   ├── prompt.py
│   │   ├── db_tool.py
│   │   └── node.py
│   │
│   ├── ventas/
│   │   ├── prompt.py
│   │   ├── stripe_api.py
│   │   └── node.py
│   │
│   └── diagnostico_visual/
│       ├── sub_state.py
│       ├── sub_graph.py
│       ├── agent_recopilador.py
│       ├── tool_validar_foto.py
│       └── agent_conclusion.py
│
└── main.py
```

## 4. Reglas de arquitectura obligatorias

### 4.1 Separación por capas

- `core/` contiene únicamente piezas compartidas y orquestación general.
- `features/` contiene cortes verticales independientes por dominio.
- Cada feature debe ser dueña de su prompt, herramientas, nodo y lógica de dominio.
- No mezcles lógica de ventas dentro de catálogo, ni lógica de catálogo dentro de diagnóstico visual.
- No coloques prompts, queries SQL, llamadas HTTP o reglas de negocio dentro de `main.py`.

### 4.2 Responsabilidad de cada archivo

- `core/state.py`: define el `AgentState` global. Solo debe contener variables compartidas clave.
- `core/router_agent.py`: clasifica la intención del usuario y devuelve una ruta estructurada.
- `core/main_graph.py`: construye el `StateGraph` principal y conecta nodos.
- `features/*/prompt.py`: contiene únicamente plantillas de prompt y reglas del dominio.
- `features/*/*_tool.py`: contiene integración con RAG, DB, APIs externas o servicios.
- `features/*/node.py`: adapta el estado global, ejecuta la feature y devuelve cambios al estado.
- `diagnostico_visual/sub_graph.py`: maneja solo el flujo secuencial de diagnóstico visual.
- `diagnostico_visual/sub_state.py`: define estado local del subgrafo, no reemplaza el estado global.

## 5. Reglas para LangGraph

- Todo nodo debe recibir `state` y devolver un diccionario parcial con los cambios.
- No mutar el estado de forma implícita si se puede devolver un nuevo fragmento de estado.
- Las rutas deben usar constantes o enums, no strings sueltos repetidos.
- El router debe tener siempre una ruta segura de fallback: `fuera_de_alcance`, `aclaracion` o `handoff_humano`.
- Los subgrafos se usan solo cuando el flujo tenga varios pasos dependientes entre sí.
- No conviertas un flujo simple en subgrafo sin necesidad.

## 6. Reglas del router de intención

El router principal solo clasifica y decide a qué feature enviar el mensaje. No debe responder directamente al usuario salvo en fallback.

Intenciones mínimas:

```text
info_corporativa
catalogo_productos
ventas
diagnostico_visual
soporte_o_reclamo
fuera_de_alcance
aclaracion
```

El router debe devolver una salida estructurada como:

```python
{
    "intent": "catalogo_productos",
    "confidence": 0.87,
    "reason": "El usuario pregunta por beneficios e ingredientes de un producto.",
    "missing_fields": []
}
```

Si la confianza es baja, pide aclaración antes de ejecutar herramientas costosas o sensibles.

## 7. Reglas de prompts

- Los prompts viven en `prompt.py` de cada feature.
- Cada prompt debe incluir: rol, objetivo, fuentes permitidas, restricciones y formato de salida.
- No inventes datos de empresa, productos, precios, stock, pagos o diagnóstico.
- Si no hay evidencia suficiente, responde que no se encontró información suficiente.
- Mantén tono conversacional, claro y profesional.
- Para clientes finales, usa lenguaje simple y evita tecnicismos.

## 8. Reglas de RAG y grounding

- Toda respuesta basada en documentos debe indicar de qué fuente proviene internamente.
- Si el RAG no devuelve evidencia relevante, no inventes una respuesta.
- Separa claramente:
  - datos encontrados;
  - interpretación del agente;
  - recomendación sugerida.
- El nodo debe validar que la respuesta esté soportada por contexto antes de entregarla.
- No uses conocimiento general para completar información comercial específica del negocio.

## 9. Reglas de herramientas externas

Toda llamada a DB, RAG, Stripe, APIs de visión o servicios externos debe:

- estar encapsulada en un archivo `*_tool.py` o `*_api.py` de su feature;
- tener timeout explícito;
- manejar errores sin romper toda la conversación;
- devolver una respuesta tipada o un diccionario normalizado;
- no exponer secretos, tokens, URLs privadas ni trazas internas al usuario;
- registrar logs técnicos sin guardar información sensible.

Nunca llames APIs externas directamente desde `main.py`, `router_agent.py` o prompts.

## 10. Reglas para diagnóstico visual

El diagnóstico visual es un flujo sensible. Debe funcionar como **orientación cosmética/informativa**, no como diagnóstico médico definitivo.

Reglas obligatorias:

- Pedir consentimiento antes de analizar una foto.
- Explicar que el resultado es una evaluación preliminar, no un diagnóstico médico.
- Preguntar por alergias, antecedentes relevantes y sensibilidad antes de sugerir productos.
- No recomendar tratamientos agresivos ni medicamentos.
- Si hay señales de irritación severa, lesión, infección, dolor intenso o empeoramiento, sugerir consulta con un profesional de salud.
- No guardar fotos de forma permanente salvo que exista autorización explícita y política de privacidad.
- No registrar imágenes, rostros, nombres, teléfonos o datos sensibles en logs.

Flujo esperado:

```text
recopilar_datos → validar_foto → analizar_condiciones → generar_conclusion → recomendar_kit → confirmar_siguiente_paso
```

## 11. Reglas para ventas y pagos

- `ventas/stripe_api.py` solo gestiona integración con pasarela de pago.
- No mezcles cálculo comercial con lógica de pago.
- Antes de crear un pago, confirma producto, cantidad, precio, moneda y disponibilidad.
- No inventes descuentos, stock, promociones ni costos de envío.
- Si falta información crítica, pide el dato faltante.
- Nunca imprimas claves de Stripe ni tokens de sesión.

## 12. Reglas para catálogo de productos

- Toda información de productos debe salir de la base de datos, catálogo o fuente autorizada.
- El agente puede comparar productos solo con atributos disponibles.
- Para recomendaciones, considera: tipo de piel, alergias, objetivo, contraindicaciones, disponibilidad y presupuesto.
- Si no existe un producto adecuado, dilo claramente y evita forzar una venta.

## 13. Reglas para información corporativa

- Usa RAG para visión, misión, horarios, políticas, sucursales, canales y datos institucionales.
- No inventes datos legales, direcciones, teléfonos, garantías ni políticas.
- Si la información no está cargada en la fuente documental, responde que debe ser validada por la empresa.

## 14. Estilo de código

- Usa Python 3.11+.
- Usa type hints en funciones públicas.
- Prefiere Pydantic o TypedDict para estados y respuestas estructuradas.
- Mantén funciones pequeñas y con una sola responsabilidad.
- Evita variables globales mutables.
- Usa nombres explícitos en español o inglés, pero no mezcles ambos en el mismo módulo.
- Prefiere `async` para llamadas I/O: APIs, DB, RAG, almacenamiento y visión.
- No agregues dependencias nuevas sin justificar su uso.

## 15. Manejo de errores

- Los errores de herramientas deben convertirse en mensajes controlados.
- No mostrar stack traces al usuario final.
- Diferencia errores de usuario, errores de integración y errores internos.
- Si una feature falla, el grafo principal debe poder responder con fallback seguro.
- Toda integración externa debe tener una respuesta alternativa cuando el servicio no esté disponible.

## 16. Seguridad y privacidad

- Nunca escribir secretos en código fuente.
- Usar variables de entorno para API keys, tokens y credenciales.
- No incluir `.env`, imágenes de clientes, dumps de DB ni logs sensibles en commits.
- No registrar información personal innecesaria.
- Minimizar datos: pedir solo lo necesario para completar el flujo.
- Enmascarar datos sensibles en logs.

## 17. Testing obligatorio

Cuando modifiques código, agrega o actualiza pruebas cuando aplique.

Pruebas mínimas:

- router clasifica intenciones principales;
- cada nodo actualiza el estado esperado;
- herramientas manejan errores y timeouts;
- diagnóstico visual no avanza sin consentimiento/foto válida;
- catálogo no inventa productos cuando no hay resultados;
- ventas no crea pagos sin confirmación de datos críticos.

No consideres terminada una tarea si no se puede ejecutar o probar el flujo afectado.

## 18. Forma correcta de agregar una nueva feature

Para crear una feature nueva:

1. Crear carpeta en `features/<nombre_feature>/`.
2. Agregar `prompt.py` si usa LLM.
3. Agregar `*_tool.py` o `*_api.py` si usa datos externos.
4. Agregar `node.py` como punto de entrada de la feature.
5. Registrar la intención en `core/router_agent.py`.
6. Conectar el nodo en `core/main_graph.py`.
7. Agregar pruebas del router y del nodo.
8. Documentar variables de entorno si existen.

No conectes una feature nueva directamente desde `main.py`.

## 19. Antipatrones prohibidos

No hagas esto:

- un único archivo gigante con todo el flujo;
- prompts mezclados con llamadas HTTP;
- SQL dentro de nodos si existe `db_tool.py`;
- lógica de negocio dentro del router;
- respuestas inventadas cuando RAG/DB no encuentra datos;
- fotos o PII en logs;
- rutas hardcodeadas repetidas;
- dependencias circulares entre features;
- modificar estructura del proyecto sin explicar por qué;
- sobreingeniería con subgrafos innecesarios.

## 20. Modo de trabajo del agente

Antes de cambiar código:

1. Identifica la feature afectada.
2. Revisa archivos existentes antes de crear nuevos.
3. Mantén el cambio pequeño y localizado.
4. Explica brevemente qué vas a modificar si el cambio es grande.
5. Implementa.
6. Ejecuta o propone pruebas.
7. Resume archivos modificados y comportamiento resultante.

Si el usuario pide algo ambiguo, toma la decisión más simple y segura de acuerdo con esta arquitectura. Pregunta solo si falta un dato crítico.

## 21. Definición de terminado

Una tarea está terminada solo si:

- respeta la arquitectura por features;
- no rompe el estado global;
- no introduce secretos ni logs sensibles;
- tiene manejo de errores básico;
- evita respuestas sin grounding;
- incluye pruebas o deja claro cómo probar;
- mantiene el código simple y legible.
