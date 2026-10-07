/* =====================================================================
   LUGARES PARA SPONSORS — editar este archivo, nada más.
   ---------------------------------------------------------------------
   Para reservar o confirmar un lugar:
     estado: "disponible" | "reservado" | "confirmado"
     sponsor: nombre que se muestra en la estructura (máx. 28 caracteres)
     logo: archivo en /sponsors/ (opcional, PNG o SVG con fondo transparente)
     url: sitio del sponsor (opcional)
   Precios de referencia según brochure COPAUJ 2026 ("Socios de la
   arquitectura"): Socio evento desde $1 M · Socio actividad desde $3 M.
   ===================================================================== */
window.CJA = {
  evento: {
    titulo: "Arquitectura en Diálogo: Tesis, Luz y Ciudad",
    proyecto: "La luz en la Arquitectura",
    fechas: "04 al 06 de noviembre",
    lugar: "Parque Xibi-Xibi “Las Lavanderas”, San Salvador de Jujuy",
    organiza: "Comisión de Jóvenes Arquitectos · Colegio de Profesionales de la Arquitectura de Jujuy",
    cierreReservas: "25 de octubre"
  },
  contacto: {
    email: "colarqjuy@gmail.com",
    telefono: "+54 388 498-8578",
    whatsapp: "543884988578",
    instagram: "colegioarquitecturajujuy",
    web: "arquitectosjujuy.org.ar"
  },
  zonas: {
    izq:    { nombre: "Banner lateral izquierdo", medida: "Roll-up 0,85 × 2,20 m", donde: "A la izquierda de la tarima, 0,20 m por delante", foto: "En toda foto de frente y en tres cuartos" },
    der:    { nombre: "Banner lateral derecho",   medida: "Roll-up 0,85 × 2,20 m", donde: "A la derecha de la tarima, 0,20 m por delante",  foto: "En toda foto de frente y en tres cuartos" },
    fondo:  { nombre: "Banner de fondo",          medida: "Lona 4,00 × 1,20 m a 1,90 m de altura", donde: "Detrás de la estructura, entre dos parantes", foto: "Detrás de la luz, en todas las fotos nocturnas" },
    postes: { nombre: "Postes",                   medida: "Vinilo envolvente 0,32 × 2,00 m", donde: "Los dos postes de 4 m que tensan la estructura", foto: "Siempre en cuadro: son parte de la obra" },
    tarima: { nombre: "Frente de tarima",         medida: "Franja 3,00 × 0,10 m", donde: "Canto frontal de la tarima de madera", foto: "Al pie de todas las fotos de frente" },
    extras: { nombre: "Alrededor de la obra",     medida: "Varios", donde: "Láminas de tesis, equipo de montaje", foto: "En la exposición y en el registro del montaje" }
  },
  lugares: [
    { n: 1,  zona: "izq",    nombre: "Lateral izquierdo · arriba",  tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,70 × 0,45 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 2,  zona: "izq",    nombre: "Lateral izquierdo · medio",   tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,70 × 0,45 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 3,  zona: "izq",    nombre: "Lateral izquierdo · abajo",   tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,70 × 0,45 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 4,  zona: "der",    nombre: "Lateral derecho · arriba",    tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,70 × 0,45 m", estado: "reservado",  sponsor: "Ejemplo S.A.", logo: "", url: "" },
    { n: 5,  zona: "der",    nombre: "Lateral derecho · medio",     tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,70 × 0,45 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 6,  zona: "der",    nombre: "Lateral derecho · abajo",     tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,70 × 0,45 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 7,  zona: "fondo",  nombre: "Fondo · 1",                   tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,90 × 0,80 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 8,  zona: "fondo",  nombre: "Fondo · 2",                   tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,90 × 0,80 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 9,  zona: "fondo",  nombre: "Fondo · 3",                   tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,90 × 0,80 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 10, zona: "fondo",  nombre: "Fondo · 4",                   tier: "bronce", paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,90 × 0,80 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 11, zona: "postes", nombre: "Poste frontal",               tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,32 × 2,00 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 12, zona: "postes", nombre: "Poste posterior",             tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,32 × 2,00 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 13, zona: "tarima", nombre: "Franja frontal de tarima",    tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "3,00 × 0,10 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 14, zona: "extras", nombre: "Pie de las láminas de tesis", tier: "bronce", paquete: "Socio evento",    precio: "Desde $1 M", medida: "Logo en el cajetín de las 18 láminas A2", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 15, zona: "extras", nombre: "Remeras del equipo de montaje", tier: "bronce", paquete: "Socio evento",  precio: "Desde $1 M", medida: "Espalda, 25 remeras", estado: "disponible", sponsor: "", logo: "", url: "" }
  ]
};
