# toolkit

Piezas reusables extraídas de proyectos que ya funcionan, cada una en su
propia carpeta con su propio README. La idea: la próxima vez que surja una
idea de hackathon, mirar acá primero antes de escribir nada de cero.

| Carpeta | Qué es | Sacado de |
|---|---|---|
| [`claude_brain/`](claude_brain/README.md) | Wrapper del SDK de Anthropic: retry, prompt caching, loop de tool-use | BizBot (`D:\bot\bizbot-ventas`) |
| [`whatsapp_wasender/`](whatsapp_wasender/README.md) | Cliente de WASenderApi: parsear webhook, mandar mensaje | BizBot (`D:\bot\bizbot-ventas`) |
| [`hybrid_rag/`](hybrid_rag/README.md) | Ingesta de PDFs a pgvector + búsqueda híbrida RRF + multihop | AIRgent (`D:\AIRgent`) + talentbase (`D:\talentbase`) |

Cada módulo es standalone: solo importa de otro módulo del toolkit cuando
hay una dependencia real (p. ej. `hybrid_rag/multihop.py` usa
`claude_brain/brain.py` como fallback del LLM de descomposición), nunca
por conveniencia. Podés copiar una sola carpeta a otro repo sin arrastrar
las demás, excepto esa dependencia puntual.

## Cuándo usar qué

- ¿El hackathon necesita un bot de WhatsApp? → `whatsapp_wasender/` +
  `claude_brain/`.
- ¿Necesita responder preguntas sobre documentos propios? → `hybrid_rag/`
  + `claude_brain/` para la respuesta final.
- ¿Necesita las dos cosas? Mirá `app/` en la raíz de este repo — es
  exactamente esa combinación, ya armada.

## Convención

Todo el código de acá está en español (nombres de función, comentarios),
para ser consistente con los tres proyectos de origen y con el resto de
los proyectos del usuario. El código nuevo bajo `app/` en la raíz del
repo también sigue esta convención.
