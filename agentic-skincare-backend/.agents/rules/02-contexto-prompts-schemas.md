# Regla 02 — Contexto histórico, system prompt y schemas

## Carga de contexto histórico

La conversación debe cargar contexto histórico antes del router, pero solo en forma resumida, mínima y útil.

`core/context_loader.py` debe encargarse de recuperar:

- `session_id`, `channel`, `tenant_id` si existe;
- últimos mensajes relevantes, no toda la conversación;
- resumen conversacional vigente;
- facts persistentes permitidos: tipo de piel declarado, alergias informadas, preferencias, productos vistos, carrito activo, consentimiento vigente;
- estado del flujo activo: diagnóstico, venta, reclamo o consulta de producto;
- flags de seguridad: usuario pidió humano, usuario negó consentimiento, usuario reportó alergia o reacción.

No cargues todo el historial completo en el prompt. Usa una estrategia de ventana + resumen:

```text
contexto_corto = últimos N turnos relevantes
contexto_resumido = resumen estable de la sesión
facts = datos confirmados y permitidos
estado_flujo = paso actual + campos faltantes
```

## Reglas de privacidad del contexto

- No guardes fotos, URLs temporales de fotos ni biometría en memoria persistente.
- No guardes datos sensibles salvo que sean necesarios para la operación y exista política de privacidad.
- No uses contexto histórico para asumir alergias, diagnósticos o consentimiento si el dato no está explícitamente confirmado.
- Si el usuario contradice un dato histórico, prioriza el último dato confirmado.
- El contexto histórico debe poder expirar por TTL o cerrarse al finalizar la sesión.

## Datos que sí pueden guardarse como memoria de sesión

```python
{
    "skin_type": "grasa",
    "reported_allergies": ["fragancia"],
    "budget_range": "medio",
    "preferred_channel": "whatsapp",
    "cart_items": ["producto_123"],
    "last_intent": "catalogo_productos",
    "active_flow": "diagnostico_visual",
    "consent_photo_analysis": True
}
```

Guarda solo datos confirmados. No infieras datos sensibles desde la foto o conversación sin validación del usuario.

## System prompt global

El system prompt global debe vivir en `core/system_prompt.py`. No lo dupliques dentro de cada nodo.

Debe incluir:

- rol del asistente;
- límites del negocio;
- política de no inventar datos;
- reglas de grounding;
- tono de atención al cliente;
- tratamiento de datos personales;
- cuándo pedir aclaración;
- cuándo escalar a humano;
- formato general de respuesta.

Ejemplo de componentes:

```python
SYSTEM_PROMPT_BASE = """
Eres un asistente virtual de atención al cliente.
Responde solo con información soportada por fuentes autorizadas, DB o herramientas.
No inventes precios, stock, diagnósticos, políticas, ingredientes ni beneficios.
Si falta información, pide aclaración o indica que debe validarse con la empresa.
"""
```

El prompt final por turno debe componerse así:

```text
system_prompt_base
+ reglas globales de seguridad
+ contexto histórico resumido
+ prompt de la feature
+ evidencia recuperada por RAG/DB/tool
+ formato esperado de salida
```

No mezcles el historial completo dentro del system prompt. El historial va como contexto separado y resumido.

## Prompts por feature

Cada `features/*/prompt.py` debe definir instrucciones específicas del dominio:

- `info_corporativa`: visión, misión, políticas, horarios, sucursales, canales.
- `catalogo_productos`: ingredientes, beneficios, modo de uso, comparación, recomendación.
- `ventas`: carrito, confirmación, pago, entrega, facturación.
- `diagnostico_visual`: recopilación de datos, consentimiento, análisis preliminar, recomendación segura.

Cada prompt debe declarar fuentes permitidas y prohibidas.

## Schemas para extracción de información

Toda información que vaya a una herramienta debe extraerse primero a un schema validado.

Usa Pydantic o TypedDict para:

- decisión del router;
- consulta de producto;
- perfil de piel;
- datos de alergias;
- solicitud de pago;
- solicitud de análisis visual;
- reclamo o soporte;
- plan de tool call.

Ejemplo de schema para catálogo:

```python
from pydantic import BaseModel, Field
from typing import Literal

class ProductQueryInput(BaseModel):
    query: str = Field(..., description="Pregunta o necesidad del usuario")
    product_name: str | None = None
    skin_type: Literal["grasa", "seca", "mixta", "sensible", "normal", "desconocida"] = "desconocida"
    allergies: list[str] = []
    budget: str | None = None
    needs_stock: bool = False
    needs_price: bool = False
```

Ejemplo de schema para diagnóstico visual:

```python
class VisualDiagnosisInput(BaseModel):
    consent: bool
    photo_url_temp: str | None
    reported_symptoms: list[str]
    allergies: list[str]
    current_products: list[str]
    pregnancy_or_medical_condition: bool | None = None
```

Ejemplo de schema para ventas:

```python
class PaymentRequestInput(BaseModel):
    product_id: str
    quantity: int
    currency: str
    confirmed_price: float
    customer_confirmation: bool
```

## Reglas para usar schemas

- Ninguna herramienta debe recibir el texto libre del usuario como único input si necesita campos concretos.
- Si faltan campos requeridos, el nodo debe pedir aclaración antes de llamar la herramienta.
- Si el schema falla validación, devuelve una pregunta breve y concreta.
- Las herramientas no deben reparar datos ambiguos; la normalización ocurre antes.
- No conviertas valores inciertos en confirmados.
- No uses schemas gigantes. Crea modelos pequeños por caso de uso.

## Manejo de campos faltantes

Cuando falte información:

```python
{
    "status": "needs_clarification",
    "missing_fields": ["skin_type", "allergies"],
    "question": "Para recomendarte mejor, ¿tu piel es grasa, seca, mixta o sensible? ¿Tienes alguna alergia conocida?"
}
```

El agente no debe ejecutar pagos, diagnóstico visual o recomendaciones personalizadas si faltan campos críticos.

## Resumen para memoria conversacional

Al final del turno, guarda un resumen corto y datos confirmados:

```python
{
    "summary": "El usuario consultó por productos para piel grasa y acné leve.",
    "confirmed_facts": {
        "skin_type": "grasa",
        "reported_allergies": []
    },
    "active_flow": "catalogo_productos"
}
```

No guardes mensajes completos si un resumen cumple el objetivo.
