# Tu marca en la luz · sitio de sponsors

Sitio estático de la **Comisión de Jóvenes Arquitectos de Jujuy** para vender lugares
de sponsor sobre la estructura de luz de la Semana de la Arquitectura 2026
(Parque Xibi-Xibi, 04 al 06 de noviembre). Mismo concepto que brandmymac.com:
la obra en 3D con lugares numerados, se eligen, se arma la reserva.

Sin build, sin dependencias: HTML + CSS + JS. Se abre con doble click en
`index.html` y se deploya arrastrando la carpeta a Vercel, Netlify o
Cloudflare Pages.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La página |
| `styles.css` | Estilos (paleta del brochure COPAUJ 2026) |
| `app.js` | Motor 3D de la estructura, lugares numerados, panel de selección, mensaje de reserva |
| `content/lugares.js` | **Único archivo que se edita**: evento, contacto, zonas y los 15 lugares |
| `sponsors/` | Logos de sponsors (PNG o SVG con fondo transparente) |

## Cómo reservar o confirmar un lugar

1. Abrí `content/lugares.js`.
2. Buscá el lugar por su número `n`.
3. Cambiá `estado` a `"reservado"` o `"confirmado"` y escribí `sponsor` (hasta 28 caracteres se ven en el banner).
4. Opcional: `url` del sponsor y `logo` (archivo dentro de `sponsors/`).
5. Guardá y volvé a deployar (o hacé commit y push si el hosting está conectado al repo).

Un lugar vuelve a estar disponible poniendo `estado: "disponible"` y `sponsor: ""`.

## Cómo cambiar precios, fechas o contacto

Todo está en `content/lugares.js`: `evento` (fechas, lugar, cierre de reservas),
`contacto` (email, WhatsApp en formato internacional sin `+`, Instagram, web),
`zonas` (medidas y visibilidad) y `precio` / `paquete` de cada lugar. Los precios
de referencia salen del brochure COPAUJ 2026 (Socio evento desde $1 M, Socio
actividad desde $3 M).

## Deploy

- **Vercel / Netlify**: importar el repo, directorio raíz `sitio-cja`, sin comando de build.
- **Cloudflare Pages**: igual, output directory `sitio-cja`.
- **GitHub Pages**: Settings → Pages → carpeta `/sitio-cja` (o mover el contenido a la raíz).

Para el QR de la placa física usá la URL final del deploy.

## Pendientes

- `og.png`: render de la estructura para la vista previa en WhatsApp e Instagram (1200 × 630).
- Modelo GLB real cuando exista: el canvas actual es un dibujo procedimental a partir de la planta y la vista del proyecto.
