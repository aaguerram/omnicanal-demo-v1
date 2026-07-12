# Regla 03 — RAG, cache y herramientas externas

## Principio general

Las herramientas entregan datos. El LLM interpreta y redacta. No inviertas esta responsabilidad.

Toda llamada a DB, RAG, Stripe, API de visión, inventario o soporte debe estar encapsulada en `*_tool.py` o `*_api.py` dentro de su feature.

## RAG para catálogo de productos

El catálogo debe combinar datos estructurados y evidencia documental.

Usa DB/inventario para:

- `product_id`;
- nombre oficial;
- precio;
- moneda;
- stock;
- estado activo/inactivo;
- variantes;
- restricciones comerciales;
- disponibilidad.

Usa RAG para complementar con información no estructurada:

- beneficios explicados;
- ingredientes y función cosmética;
- modo de uso;
- preguntas frecuentes;
- advertencias del fabricante;
- comparaciones entre productos;
- políticas de uso cuando estén documentadas.

No uses RAG como fuente principal de precio, stock o pagos. Esa información debe venir de DB o herramienta transaccional.

## Flujo recomendado para consulta de producto

```text
extraer ProductQueryInput
→ buscar producto candidato en DB
→ validar product_id activo
→ recuperar documentos RAG asociados al producto o categoría
→ fusionar evidencia estructurada + documental
→ validar grounding
→ responder con datos y recomendaciones
```

Si el usuario pregunta “qué producto me recomiendas”, el flujo debe considerar:

- necesidad declarada;
- tipo de piel;
- alergias;
- objetivo;
- contraindicaciones;
- presupuesto;
- disponibilidad real;
- evidencia documental disponible.

Si no existe evidencia suficiente, responde que necesitas más datos o que no hay producto adecuado registrado.

## Contrato mínimo de resultado RAG

Toda herramienta RAG debe devolver una estructura normalizada:

```python
{
    "query": "serum para piel grasa",
    "results": [
        {
            "doc_id": "prod_123_ficha",
            "product_id": "prod_123",
            "title": "Ficha técnica Sérum Balance",
            "source_type": "product_sheet",
            "snippet": "Texto relevante recuperado",
            "score": 0.82,
            "metadata": {
                "version": "2026-06",
                "category": "serum"
            }
        }
    ]
}
```

El nodo debe filtrar resultados con baja relevancia antes de enviarlos al LLM.

## Grounding obligatorio

Antes de responder, valida:

- que cada afirmación comercial importante esté soportada por DB o RAG;
- que precios y stock salgan solo de herramientas transaccionales;
- que beneficios, ingredientes y modo de uso estén soportados por documentos;
- que no se afirme una indicación médica;
- que no se recomiende un producto incompatible con alergias conocidas.

Separa en la respuesta interna:

```text
datos_encontrados
interpretacion_del_agente
recomendacion_sugerida
campos_faltantes
```

Solo entrega al usuario una respuesta simple, pero conserva trazabilidad interna.

## Cache

Implementa cache en `core/cache.py` con una interfaz simple.

Capas recomendadas:

```text
L1: cache en memoria por proceso, TTL corto.
L2: Redis o cache distribuida, TTL configurable.
DB/RAG/API: fuente de verdad.
```

Usa cache para:

- búsquedas frecuentes de catálogo;
- fichas de producto no sensibles;
- resultados RAG por `query_normalizada + product_version`;
- información corporativa pública;
- catálogos, categorías y FAQs;
- embeddings o resultados rerankeados si no contienen PII.

No uses cache para:

- fotos de clientes;
- URLs temporales de imágenes;
- diagnósticos visuales;
- datos médicos o sensibles;
- tokens de pago;
- secretos;
- mensajes completos de conversación;
- decisiones de consentimiento.

## Diseño de claves de cache

Las claves deben ser explícitas y versionadas:

```text
catalogo:{tenant_id}:{locale}:product:{product_id}:v{catalog_version}
rag:{tenant_id}:{locale}:{feature}:{hash_query}:v{index_version}
corp:{tenant_id}:{locale}:faq:v{doc_version}
```

Incluye `tenant_id` si el sistema atiende varias empresas. Incluye versión de catálogo o índice para invalidación.

## TTL recomendado

- Información corporativa pública: TTL medio.
- Fichas de producto: TTL medio, invalidación por versión de catálogo.
- Resultados RAG: TTL corto/medio según frecuencia de actualización.
- Stock/precio: TTL muy corto o sin cache si la precisión es crítica.
- Pagos: no cachear.
- Diagnóstico visual: no cachear.

## Invalidación de cache

Invalida cuando:

- cambia precio;
- cambia stock;
- se actualiza ficha técnica;
- se actualiza índice RAG;
- cambia política comercial;
- se desactiva un producto;
- cambia versión del catálogo.

Nunca uses cache vieja para cerrar una venta si precio, stock o disponibilidad son críticos.

## Herramientas externas

Cada herramienta debe:

- recibir input validado por schema;
- tener timeout explícito;
- manejar errores sin romper el grafo;
- devolver datos normalizados;
- registrar logs técnicos sin PII;
- no exponer secretos, tokens ni trazas internas;
- tener tests con éxito, error y timeout.

Ejemplo de respuesta de error normalizada:

```python
{
    "status": "tool_error",
    "tool": "product_db",
    "error_type": "timeout",
    "user_message": "No pude consultar el catálogo en este momento. Puedes intentar de nuevo o pedir ayuda humana.",
    "retryable": True
}
```

## Reglas de llamadas costosas

Antes de llamar herramientas costosas o lentas:

- valida intención;
- valida campos requeridos;
- revisa cache cuando aplique;
- evita llamadas duplicadas en el mismo turno;
- registra `correlation_id`;
- usa fallback seguro si falla.

## RAG por dominio

Cada feature debe tener su propio RAG o índice lógico cuando los documentos tengan semánticas distintas:

- `info_corporativa`: documentos institucionales.
- `catalogo_productos`: fichas de producto, ingredientes, beneficios y FAQs.
- `diagnostico_visual`: guías cosméticas internas permitidas, no guías médicas no autorizadas.
- `soporte_o_reclamo`: políticas, garantías, cambios y devoluciones.

No mezcles fuentes sin metadata de dominio. El retriever debe filtrar por `feature`, `tenant_id`, `locale`, `source_type` y versión.
