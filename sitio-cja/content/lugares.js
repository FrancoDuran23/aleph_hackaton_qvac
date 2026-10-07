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
    nombre: "",                       // quién atiende a los sponsors (ej. "Agus Liquin"); vacío = no se muestra
    email: "colarqjuy@gmail.com",
    telefono: "+54 388 498-8578",
    whatsapp: "543884988578",
    instagram: "colegioarquitecturajujuy",
    web: "arquitectosjujuy.org.ar"
  },
  zonas: {
    frontal:   { nombre: "Banner frontal",   corto: "Frontal",   medida: "Lona 2,00 × 1,00 m en bastidor", donde: "Junto al poste delantero, fuera de la tarima", foto: "En toda foto de frente y en tres cuartos, de día y de noche" },
    posterior: { nombre: "Banner posterior", corto: "Posterior", medida: "Lona 2,00 × 1,00 m en bastidor", donde: "Junto al poste trasero, fuera de la tarima", foto: "Detrás de la luz en las fotos nocturnas" },
    tesis:     { nombre: "Banner de la exposición de tesis", corto: "Tesis", medida: "Lona 2,00 × 1,00 m en bastidor", donde: "Donde se exponen las láminas de tesis (opcional)", foto: "En la exposición y en las fotos de las presentaciones" }
  },
  lugares: [
    { n: 1,  zona: "frontal",   nombre: "Frontal · 1",   tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 2,  zona: "frontal",   nombre: "Frontal · 2",   tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,45 × 0,70 m", estado: "reservado",  sponsor: "Ejemplo S.A.", logo: "", url: "" },
    { n: 3,  zona: "frontal",   nombre: "Frontal · 3",   tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 4,  zona: "frontal",   nombre: "Frontal · 4",   tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 5,  zona: "posterior", nombre: "Posterior · 1", tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 6,  zona: "posterior", nombre: "Posterior · 2", tier: "oro",    paquete: "Socio actividad", precio: "Desde $3 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 7,  zona: "posterior", nombre: "Posterior · 3", tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 8,  zona: "posterior", nombre: "Posterior · 4", tier: "plata",  paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 9,  zona: "tesis",     nombre: "Tesis · 1",     tier: "bronce", paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 10, zona: "tesis",     nombre: "Tesis · 2",     tier: "bronce", paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 11, zona: "tesis",     nombre: "Tesis · 3",     tier: "bronce", paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" },
    { n: 12, zona: "tesis",     nombre: "Tesis · 4",     tier: "bronce", paquete: "Socio evento",    precio: "Desde $1 M", medida: "0,45 × 0,70 m", estado: "disponible", sponsor: "", logo: "", url: "" }
  ]
};
