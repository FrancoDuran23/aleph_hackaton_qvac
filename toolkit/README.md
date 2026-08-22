# toolkit

Piezas reusables, cada una en su propia carpeta con su propio README.

| Carpeta | Qué es |
|---|---|
| [`qvac_brain/`](qvac_brain/README.md) | Inferencia local QVAC: generación de texto + embeddings |
| [`whatsapp_wasender/`](whatsapp_wasender/README.md) | Cliente de WASenderApi: parsear webhook, mandar mensaje |
| [`hybrid_rag/`](hybrid_rag/README.md) | Ingesta de PDFs a pgvector + búsqueda híbrida RRF + multihop |

Cada módulo es standalone: solo importa de otro módulo del toolkit cuando
hay una dependencia real (p. ej. `hybrid_rag/multihop.py` usa
`qvac_brain/brain.py` para descomponer consultas), nunca
por conveniencia. Podés copiar una sola carpeta a otro repo sin arrastrar
las demás, excepto esa dependencia puntual.

## Cuándo usar qué

- ¿El hackathon necesita un bot de WhatsApp? → `whatsapp_wasender/` +
  `qvac_brain/`.
- ¿Necesita responder preguntas sobre documentos propios? → `hybrid_rag/`
  + `qvac_brain/` para la respuesta final.
- ¿Necesita las dos cosas? Mirá `app/` en la raíz de este repo — es
  exactamente esa combinación, ya armada.

## Convención

Todo el código de acá está en español (nombres de función, comentarios),
para ser consistente con los tres proyectos de origen y con el resto de
los proyectos del usuario. El código nuevo bajo `app/` en la raíz del
repo también sigue esta convención.
