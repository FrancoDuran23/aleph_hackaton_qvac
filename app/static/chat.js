const mensajesEl = document.getElementById("mensajes");
const formEl = document.getElementById("form");
const inputEl = document.getElementById("input");

let historial = [];

function agregarMensaje(role, texto) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = texto;
  mensajesEl.appendChild(div);
  mensajesEl.scrollTop = mensajesEl.scrollHeight;
  return div;
}

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const pregunta = inputEl.value.trim();
  if (!pregunta) return;

  inputEl.value = "";
  inputEl.disabled = true;
  agregarMensaje("user", pregunta);
  const loadingEl = agregarMensaje("assistant loading", "pensando...");

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta, historial }),
    });
    const data = await res.json();
    loadingEl.textContent = data.respuesta;
    loadingEl.className = "msg assistant";
    historial.push({ role: "user", content: pregunta });
    historial.push({ role: "assistant", content: data.respuesta });
  } catch (err) {
    loadingEl.textContent = "Error de conexión. ¿Está levantado el servidor?";
    loadingEl.className = "msg assistant";
  } finally {
    inputEl.disabled = false;
    inputEl.focus();
  }
});
