# Regla 04 — Features, seguridad, testing y definición de terminado

## Diagnóstico visual

El diagnóstico visual es orientación cosmética/informativa, no diagnóstico médico definitivo.

Reglas obligatorias:

- Pedir consentimiento antes de analizar una foto.
- Explicar que el resultado es preliminar y no reemplaza a un profesional de salud.
- Preguntar por alergias, sensibilidad, antecedentes relevantes y productos actuales antes de recomendar.
- No recomendar medicamentos ni tratamientos agresivos.
- Si hay irritación severa, lesión, infección, dolor intenso o empeoramiento, sugerir consulta con un profesional.
- No guardar fotos permanentemente salvo autorización explícita y política de privacidad.
- No registrar imágenes, rostros, nombres, teléfonos o datos sensibles en logs.

Flujo esperado:

```text
recopilar_datos
→ confirmar_consentimiento
→ validar_foto
→ analizar_condiciones
→ generar_conclusion_preliminar
→ recomendar_kit_si_aplica
→ confirmar_siguiente_paso
```

El subgrafo de diagnóstico debe tener estado local en `sub_state.py` y no contaminar el `AgentState` global con detalles innecesarios.

## Catálogo de productos

- Toda información de productos debe salir de DB, catálogo o fuente autorizada.
- El agente puede comparar productos solo con atributos disponibles.
- Para recomendaciones, considera tipo de piel, alergias, objetivo, contraindicaciones, disponibilidad y presupuesto.
- Si no existe un producto adecuado, dilo claramente y evita forzar una venta.
- Si el usuario pide ingredientes o beneficios, usa RAG asociado al producto.
- Si el usuario pide precio o stock, usa DB/inventario.

## Ventas y pagos

- `ventas/stripe_api.py` solo gestiona integración con la pasarela de pago.
- No mezcles cálculo comercial con lógica de pago.
- Antes de crear un pago, confirma producto, cantidad, precio, moneda y disponibilidad.
- No inventes descuentos, stock, promociones ni costos de envío.
- Si falta información crítica, pide el dato faltante.
- Nunca imprimas claves de Stripe, tokens de sesión ni URLs privadas.
- La creación de pago requiere `customer_confirmation = True`.

## Información corporativa

- Usa RAG para visión, misión, horarios, políticas, sucursales, canales y datos institucionales.
- No inventes datos legales, direcciones, teléfonos, garantías ni políticas.
- Si la información no está cargada en la fuente documental, responde que debe ser validada por la empresa.

## Soporte o reclamos

Si el usuario reporta reclamo, incidente o problema con producto:

- recolecta datos mínimos: producto, fecha aproximada, canal de compra, descripción del problema;
- no pidas datos sensibles innecesarios;
- crea ticket solo con confirmación si la herramienta lo requiere;
- escala a humano si hay reacción adversa, amenaza legal, pago fallido repetido o enojo alto.

## Seguridad y privacidad

- Nunca escribir secretos en código fuente.
- Usar variables de entorno para API keys, tokens y credenciales.
- No incluir `.env`, imágenes de clientes, dumps de DB ni logs sensibles en commits.
- No registrar información personal innecesaria.
- Minimizar datos: pedir solo lo necesario para completar el flujo.
- Enmascarar datos sensibles en logs.
- No mostrar stack traces al usuario final.

## Manejo de errores

- Los errores de herramientas deben convertirse en mensajes controlados.
- Diferencia errores de usuario, integración e internos.
- Si una feature falla, el grafo principal debe responder con fallback seguro.
- Toda integración externa debe tener respuesta alternativa si el servicio no está disponible.
- Los errores deben incluir `correlation_id` interno, pero no mostrarlo al usuario salvo que el negocio lo requiera para soporte.

## Estilo de código

- Usa Python 3.11+.
- Usa type hints en funciones públicas.
- Prefiere Pydantic o TypedDict para estados, tool inputs y respuestas estructuradas.
- Mantén funciones pequeñas y con una sola responsabilidad.
- Evita variables globales mutables.
- Usa nombres explícitos en español o inglés, pero no mezcles ambos en el mismo módulo.
- Prefiere `async` para I/O: APIs, DB, RAG, cache, almacenamiento y visión.
- No agregues dependencias nuevas sin justificar su uso.

## Testing obligatorio

Cuando modifiques código, agrega o actualiza pruebas cuando aplique.

Pruebas mínimas:

- router clasifica intenciones principales;
- router devuelve aclaración si la confianza es baja;
- `context_loader` carga resumen y facts, no historial completo;
- `system_prompt` compone base + contexto + feature sin duplicar reglas;
- schemas validan campos requeridos y rechazan datos inválidos;
- cada nodo actualiza el estado esperado;
- herramientas manejan éxito, error y timeout;
- cache no guarda PII ni fotos;
- RAG de catálogo no inventa ingredientes cuando no hay evidencia;
- catálogo no inventa productos cuando no hay resultados;
- ventas no crea pagos sin confirmación de datos críticos;
- diagnóstico visual no avanza sin consentimiento y foto válida;
- grounding bloquea respuestas comerciales sin fuente.

No consideres terminada una tarea si no se puede ejecutar o probar el flujo afectado.

## Forma correcta de agregar una nueva feature

1. Crear carpeta en `features/<nombre_feature>/`.
2. Agregar `schemas.py` para inputs/outputs del dominio.
3. Agregar `prompt.py` si usa LLM.
4. Agregar `*_tool.py` o `*_api.py` si usa datos externos.
5. Agregar `node.py` como punto de entrada.
6. Registrar intención en `core/router_agent.py`.
7. Conectar nodo en `core/main_graph.py`.
8. Agregar pruebas del router, schema, nodo y tools.
9. Documentar variables de entorno si existen.

No conectes una feature nueva directamente desde `main.py`.

## Modo de trabajo del agente

Antes de cambiar código:

1. Identifica la feature afectada.
2. Revisa archivos existentes antes de crear nuevos.
3. Mantén el cambio pequeño y localizado.
4. Explica brevemente qué vas a modificar si el cambio es grande.
5. Implementa.
6. Ejecuta o propone pruebas.
7. Resume archivos modificados y comportamiento resultante.

Si el usuario pide algo ambiguo, toma la decisión más simple y segura según esta arquitectura. Pregunta solo si falta un dato crítico.

## Definición de terminado

Una tarea está terminada solo si:

- respeta arquitectura por features;
- no rompe estado global;
- carga contexto histórico de forma mínima y segura;
- usa system prompt centralizado;
- usa schemas antes de herramientas;
- no introduce secretos ni logs sensibles;
- tiene manejo de errores básico;
- evita respuestas sin grounding;
- usa cache solo para información permitida;
- incluye pruebas o deja claro cómo probar;
- mantiene código simple y legible.
