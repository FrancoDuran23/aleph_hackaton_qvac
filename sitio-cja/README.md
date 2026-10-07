# Tu marca en la luz · sitio de sponsors

Sitio estático de la **Comisión de Jóvenes Arquitectos de Jujuy** para vender lugares
de sponsor sobre la estructura de luz de la Semana de la Arquitectura 2026
(Parque Xibi-Xibi, 04 al 06 de noviembre). Mismo concepto que brandmymac.com:
la obra en 3D con los banners numerados junto a los postes, se eligen, se arma la reserva.

Sin build, sin dependencias: HTML + CSS + JS. Se abre con doble click en
`index.html` y se deploya arrastrando la carpeta a Vercel, Netlify o
Cloudflare Pages.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La página |
| `styles.css` | Estilos (paleta del brochure COPAUJ 2026) |
| `app.js` | Motor 3D de la estructura, lugares numerados, panel de selección, mensaje de reserva |
| `content/lugares.js` | **Único archivo que se edita**: evento, contacto, zonas y los 12 lugares (3 banners × 4) |
| `content/modelo.js` | Líneas de la estructura, generadas del GLB exportado de SketchUp (no editar a mano) |
| `sponsors/` | Logos de sponsors (PNG o SVG con fondo transparente) |

## Cómo reservar o confirmar un lugar

1. Abrí `content/lugares.js`.
2. Buscá el lugar por su número `n`.
3. Cambiá `estado` a `"reservado"` o `"confirmado"` y escribí `sponsor` (hasta 28 caracteres se ven en el banner).
4. Opcional: `url` del sponsor y `logo` (archivo dentro de `sponsors/`).
5. Guardá y volvé a deployar (o hacé commit y push si el hosting está conectado al repo).

Un lugar vuelve a estar disponible poniendo `estado: "disponible"` y `sponsor: ""`.

## Pendientes de definición (octubre 2026)

- Logo del Colegio: el pie de página lleva solo texto hasta que Comunicación del Colegio baje la línea gráfica.
- Ficha técnica: la estructura se está recalculando; la ficha no detalla secciones de materiales.
- Contacto de sponsors: `contacto.nombre` en `content/lugares.js` (vacío = no se muestra).
- Banner de tesis: queda como opcional; se saca borrando sus 4 lugares y la zona `tesis`.

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

La placa física de la obra lista a los sponsors; esta página es su espejo digital.

## Pendientes

- `og.png`: render de la estructura para la vista previa en WhatsApp e Instagram (1200 × 630).
- La estructura del visor sale del GLB exportado de `publicidad.skp` (tarima, viga diagonal a 3,205 m, postes de 4,00 m, cable y riendas). Los hilos no viajan en el GLB porque en SketchUp son líneas; se generan en `app.js` cada 0,20 m con la regla medida en el archivo. Si el modelo cambia, exportar de nuevo a GLB y regenerar `content/modelo.js`.
