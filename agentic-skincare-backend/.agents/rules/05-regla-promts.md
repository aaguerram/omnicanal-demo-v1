---
trigger: manual
---

# Regla 05 – Lineamientos de Diseño Conversacional para Prompts del Agente

> Fuentes oficiales:
> - https://developers.google.com/assistant/conversation-design/language?hl=es-419
> - https://developers.google.com/assistant/conversation-design/capitalization-and-punctuation?hl=es-419

Cada vez que se redacte, modifique o revise un **prompt del sistema, mensaje de respuesta o texto de interfaz** del agente de skincare, se deben seguir los lineamientos que se describen a continuación. Estas reglas aplican tanto a los **mensajes de voz (TTS)** como a los **mensajes de visualización (pantalla)**, chips de sugerencia y texto en imágenes.

---

## 1. Lenguaje Natural y Conversacional

- **Escribe como se habla.** Los prompts deben sonar como si los dijera una persona real, no como texto formal o técnico.
- **Usa contracciones y lenguaje coloquial** cuando corresponda. Los mensajes sin contracciones suenan forzados y robóticos.
  - ✅ `"¿Qué tipo de piel tienes?"`
  - ❌ `"¿Cuál es el tipo de piel que usted posee?"`
- **Evita jerga técnica o palabras poco comunes.** Si el usuario no lo diría en una conversación cotidiana, el agente tampoco debe usarlo.
- **Prefiere oraciones cortas y directas.** Divide las ideas complejas en varios turnos conversacionales en lugar de un solo bloque de texto.
- **Usa la segunda persona (tú/usted)** de forma consistente según el tono definido para el agente. No mezcles tratamientos dentro de la misma conversación.

---

## 2. Tono y Estilo del Mensaje

- **Sé amable pero conciso.** El agente no debe sonar ni demasiado formal ni demasiado efusivo.
- **Evita los signos de exclamación (`!`).** Pueden percibirse como que el agente está gritando o siendo artificialmente entusiasta.
  - ✅ `"Encontré estas opciones para ti."`
  - ❌ `"¡Aquí están tus resultados!"`
- **No uses frases de relleno innecesarias** como "por supuesto", "desde luego", "absolutamente", que suenan robóticas en exceso.
- **Anticipa la siguiente acción del usuario.** Termina los prompts orientando al usuario sobre qué puede hacer o preguntar a continuación.

---

## 3. Mensajes de Voz vs. Mensajes de Pantalla

Cuando el agente genere respuestas que puedan ser tanto habladas como mostradas en pantalla, aplica las siguientes diferencias:

### Mensajes de Voz (TTS)
- Escribe para el oído, no para la vista. Las oraciones deben sonar bien al escucharlas.
- Evita listas largas con viñetas; en su lugar, usa frases encadenadas: *"Tienes tres opciones: hidratante, suero o tónico."*
- Usa SSML o marcado fonético si hay palabras técnicas (nombres de ingredientes, marcas).
- Evita abreviaturas que el sintetizador de voz pueda leer incorrectamente.
- No uses markdown (asteriscos, corchetes, guiones de lista) en texto destinado a TTS.

### Mensajes de Pantalla (Display)
- Puedes usar listas, negritas y estructura visual cuando el canal lo permita.
- Los chips de sugerencia deben ser cortos (1–3 palabras) y representar opciones reales que el usuario podría decir o tocar.
- El texto de las imágenes debe ser breve, claro y usar **solo mayúscula inicial** (ver sección de mayúsculas).

---

## 4. Uso de Mayúsculas

Aplica **sentence case** (mayúscula solo en la primera palabra de la oración) en todos los mensajes de pantalla, títulos, chips y etiquetas. Las investigaciones demuestran que el sentence case es más fácil de leer que el title case.

| Tipo de texto | Regla | Ejemplo correcto |
|---|---|---|
| Mensajes de respuesta | Sentence case | `"¿Cuál es tu tipo de piel?"` |
| Chips de sugerencia | Sentence case | `"Ver productos"` / `"Piel seca"` |
| Títulos en tarjetas | Sentence case | `"Suero vitamina C"` |
| Texto en imágenes | Sentence case | `"Limpiador facial para piel sensible"` |
| Nombres propios / marcas | Mayúscula propia | `"Cerave"`, `"La Roche-Posay"` |

- **NO uses title case** a menos que sea un nombre propio o marca registrada.
  - ✅ `"Recomendaciones del día"`
  - ❌ `"Recomendaciones Del Día"`
- **NO uses ALL CAPS** en mensajes de respuesta ni chips (excepción: siglas oficiales como `"SPF"`, `"UVA"`).

---

## 5. Puntuación

### Comas
- Usa la **coma de enumeración (Oxford comma)** en listas de 3 o más elementos para agregar claridad.
  - ✅ `"Puedo recomendar limpiadores, tónicos, y cremas hidratantes."`
- En listas de solo 2 elementos, no se usa coma antes de "y".
  - ✅ `"Limpiador y tónico."`

### Puntos
- Usa punto al final de oraciones completas en mensajes de respuesta.
- En chips de sugerencia y etiquetas cortas, **no uses punto final**.
  - ✅ chip: `"Piel seca"` (sin punto)
  - ✅ oración: `"Encontré 5 productos para ti."`

### Signos de interrogación
- En español, usa siempre los signos de apertura y cierre (`¿...?`).
  - ✅ `"¿Tienes alguna alergia conocida?"`
  - ❌ `"Tienes alguna alergia conocida?"`

### Signos de exclamación
- Evítalos en la mayoría de los casos. Si son absolutamente necesarios, usa apertura en español (`¡...!`).

### Guiones y paréntesis
- Evita el uso excesivo de paréntesis en mensajes de voz; la información entre paréntesis puede confundir al TTS.
- Usa guiones largos (–) para pausas naturales en mensajes de pantalla si es necesario, pero con moderación.

### Puntos suspensivos
- Úsalos solo para indicar que el agente está procesando o que hay más información. No los uses para vaguedad.
  - ✅ `"Un momento, estoy buscando..."` (estado de carga)
  - ❌ `"Depende de varios factores..."` (vaguedad)

---

## 6. Numerales y Símbolos

- **Usa números en lugar de texto** para cifras. Los números hacen el contenido visual más claro.
  - ✅ `"Encontré 5 productos para ti."`
  - ❌ `"Encontré cinco productos para ti."`
- **Usa símbolos monetarios** cuando corresponda.
  - ✅ `"El precio es $45"` → no `"cuarenta y cinco dólares"`
- **Formato de hora:** usa `"a.m."` o `"p.m."` con puntos, en minúsculas.
  - ✅ `"Tu cita es a las 10 a.m."`
  - ❌ `"Tu cita es a las 10 AM"`
- **Porcentajes:** usa el símbolo `%` en pantalla, di "por ciento" en mensajes de voz.
  - Pantalla: `"Contiene 2% de ácido salicílico"`
  - Voz: `"Contiene dos por ciento de ácido salicílico"`

---

## 7. Estructura de los Prompts del Sistema

Cuando se escriba o modifique un **system prompt** para el agente, seguir este orden:

1. **Define el rol claramente** al inicio, en lenguaje natural y primera persona.
2. **Lista las capacidades y limitaciones** con frases cortas y concretas.
3. **Especifica el tono y tratamiento** (tú vs. usted, formal vs. informal) — elegir uno y no mezclarlo.
4. **Incluye ejemplos de respuesta** siguiendo estas reglas de lenguaje.
5. **Evita instrucciones negativas ambiguas** ("nunca digas X"); en su lugar, indica la conducta esperada positivamente ("en cambio, di Y").
6. **No uses markdown en respuestas de voz**; solo úsalo en respuestas destinadas a pantalla.
7. **Delimita claramente cada sección** del prompt con encabezados o comentarios para facilitar su mantenimiento.

### Ejemplo de estructura de prompt bien redactado:

```
Eres Luna, asesora de skincare virtual de [Marca].
Hablas en español, con tono amigable y profesional, usando "tú".

Puedes ayudar a los usuarios a:
- Identificar su tipo de piel.
- Encontrar productos adecuados para sus necesidades.
- Entender los ingredientes clave de un producto.

Cuando no tengas información suficiente, pregunta antes de recomendar.
Cuando el usuario pregunte por un producto específico, menciona precio y disponibilidad.
Si el usuario hace una pregunta fuera de skincare, redirige amablemente.

Ejemplo de respuesta esperada:
"Cuéntame un poco más sobre tu piel. ¿La sientes seca, grasa o mixta?"
```

---

## 8. Chips de Sugerencia

Los chips aparecen como botones de respuesta rápida en la interfaz. Reglas:

- Máximo **3 palabras** por chip.
- Deben representar **frases reales** que el usuario diría o tocaría.
- Usan **sentence case** (mayúscula solo en la primera palabra).
- No llevan **punto final**.
- Deben ser **distintos entre sí** y cubrir las opciones más probables del usuario.
- No repetir la misma opción con diferentes palabras.

| ✅ Correcto | ❌ Incorrecto |
|---|---|
| `"Piel grasa"` | `"Tengo la piel grasa"` |
| `"Ver precio"` | `"¿Cuál Es El Precio?"` |
| `"Más opciones"` | `"Mostrarme más opciones disponibles"` |
| `"Piel sensible"` | `"PIEL SENSIBLE"` |

---

## 9. Anti-patrones a Evitar

| Anti-patrón | Descripción | ❌ Incorrecto | ✅ Corrección |
|---|---|---|---|
| Exceso de entusiasmo | Signos de exclamación o frases exageradas | `"¡Excelente elección!"` | `"Buena elección."` |
| Lenguaje robótico | Sin contracciones, demasiado formal | `"Usted ha seleccionado la opción número tres."` | `"Seleccionaste la opción 3."` |
| Respuestas sin cierre | Dejar al usuario sin saber qué hacer | `"Aquí tienes los productos."` | `"Aquí tienes los productos. ¿Cuál te interesa más?"` |
| Listas demasiado largas | Más de 3 opciones sin filtro previo | Enumerar 7 productos | Ofrecer las 2–3 mejores y preguntar si quiere ver más |
| Title Case innecesario | Mayúscula en cada palabra | `"Recomendaciones Del Día"` | `"Recomendaciones del día"` |
| Números en texto | Escribir números como palabras en pantalla | `"Cinco productos disponibles"` | `"5 productos disponibles"` |
| Markdown en voz | Asteriscos o guiones en respuestas TTS | `"**Recomiendo** este producto"` | `"Te recomiendo este producto"` |
| Tratamiento mixto | Mezclar tú y usted en la misma sesión | `"Dime tu tipo de piel. Usted también puede..."` | Usar solo tú o solo usted consistentemente |

---

## 10. Checklist de Revisión de Prompts

Antes de finalizar cualquier prompt o mensaje del agente, verificar:

- [ ] ¿Suena como lo diría una persona real en una conversación cotidiana?
- [ ] ¿Evita signos de exclamación innecesarios?
- [ ] ¿Usa sentence case en mensajes de pantalla y chips?
- [ ] ¿Los números están escritos como dígitos (no como palabras)?
- [ ] ¿Usa coma de enumeración en listas de 3 o más elementos?
- [ ] ¿Los signos de interrogación tienen apertura en español (`¿`)?
- [ ] ¿Los chips tienen máximo 3 palabras y no tienen punto final?
- [ ] ¿El prompt orienta al usuario sobre qué hacer a continuación?
- [ ] ¿El tono (tú/usted) es consistente con el resto del sistema?
- [ ] ¿Las respuestas de voz evitan markdown y listas con viñetas?
- [ ] ¿Las abreviaturas y símbolos se usan correctamente según el canal (voz vs. pantalla)?
- [ ] ¿El system prompt incluye ejemplos de respuesta esperada?
