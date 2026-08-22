"""Respuestas precalentadas para la demo. No depende de red ni de Postgres
para leer -- es un archivo JSON en disco, así que sigue funcionando aunque
se caiga la API o la base de datos durante el pitch.

Flujo:
1. Antes de la demo: llenás demo/preguntas.json con las preguntas exactas
   del recorrido que vas a mostrar.
2. Corrés `python -m app.precache` (con red, con la base levantada) -- eso
   ejecuta el pipeline real una vez por pregunta y guarda el resultado en
   demo/cache_calentado.json.
3. Durante la demo, cada pregunta que llega primero se busca acá. Si
   matchea (exacta o aproximada), la respuesta sale al instante sin tocar
   la red.
"""
import difflib
import json
import re
import sys
from pathlib import Path

PREGUNTAS_PATH = Path(__file__).parent.parent / "demo" / "preguntas.json"
CACHE_PATH = Path(__file__).parent.parent / "demo" / "cache_calentado.json"

UMBRAL_SIMILITUD = 0.85  # qué tan parecida tiene que ser la pregunta en vivo a la precalentada


def _normalizar(texto: str) -> str:
    texto = texto.lower().strip()
    texto = re.sub(r"[^\w\s]", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def _cargar_cache() -> dict[str, str]:
    """Lee el archivo en cada llamada (nunca lo guarda en memoria de proceso):
    el archivo es chico y así el server recoge un cache recién calentado sin
    necesidad de reiniciarse -- un `_cache` module-level cacheado quedaría
    pisado en vacío para siempre si el primer request llega antes de correr
    `python -m app.precache`."""
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def buscar_en_cache(pregunta: str) -> str | None:
    """None si no hay nada parecido precalentado -- el caller debe seguir
    con el flujo normal (red/DB) en ese caso."""
    cache = _cargar_cache()
    if not cache:
        return None

    clave = _normalizar(pregunta)
    if clave in cache:
        return cache[clave]

    coincidencias = difflib.get_close_matches(clave, cache.keys(), n=1, cutoff=UMBRAL_SIMILITUD)
    if coincidencias:
        return cache[coincidencias[0]]

    return None


def calentar(preguntas: list[str]) -> dict[str, str]:
    """Corre el pipeline real (con red) una vez por pregunta y persiste el
    resultado. Se importa acá adentro, no arriba del módulo, para que
    buscar_en_cache() nunca dependa de que la DB/red estén disponibles."""
    from . import answer

    resultado = {}
    for i, pregunta in enumerate(preguntas, 1):
        print(f"[{i}/{len(preguntas)}] calentando: {pregunta!r}")
        respuesta = answer.responder(pregunta, historial=[], usar_cache=False)
        resultado[_normalizar(pregunta)] = respuesta
        print(f"  -> {respuesta[:100]}...")

    CACHE_PATH.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(resultado)} respuestas guardadas en {CACHE_PATH}")
    return resultado


if __name__ == "__main__":
    if not PREGUNTAS_PATH.exists():
        print(f"No existe {PREGUNTAS_PATH}. Copiá demo/preguntas.example.json y llenalo primero.", file=sys.stderr)
        sys.exit(1)

    preguntas = json.loads(PREGUNTAS_PATH.read_text(encoding="utf-8"))
    calentar(preguntas)
