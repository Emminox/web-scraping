"""Steam: precios (tienda de plataforma, PC) y reseñas de usuarios (segunda calificación).

Se usa la búsqueda de la tienda (``/search/results/``), que devuelve un JSON con un campo
``results_html``: el HTML de las filas de resultados. Cada fila trae título, URL, precio final en
centavos (``data-price-final``), precio original si hay descuento y el resumen de reseñas.
Se parsea ese HTML (cuenta como fuente por HTML, no por API).

Parámetros: ``category1=998`` limita a juegos (sin DLC ni bandas sonoras), ``cc=us`` fija la tienda
de EE. UU. (precios en USD) y ``l=english`` el idioma de los textos que se leen.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import quote

from radar.fuentes.modelos import STEAM, Candidato, a_centavos, texto_plano

CANTIDAD_RESULTADOS = 10


def url_busqueda(titulo: str) -> str:
    return (
        "https://store.steampowered.com/search/results/"
        f"?term={quote(titulo)}&category1=998&cc=us&l=english&infinite=1&count={CANTIDAD_RESULTADOS}"
    )


def _sin_parametros(url: str) -> str:
    """Quita '?snr=...' (parámetro de seguimiento) para que la URL del producto sea estable."""
    return url.split("?", 1)[0]


def parsear_busqueda(cuerpo: bytes) -> tuple[Candidato, ...]:
    datos = json.loads(cuerpo.decode("utf-8"))
    resultados_html = datos.get("results_html", "")
    candidatos: list[Candidato] = []
    # Cada resultado es un <a ... class="search_result_row ..."> ... </a>.
    for fila in re.findall(r'<a href="[^"]+"[^>]*class="search_result_row[^"]*"[^>]*>.*?</a>', resultados_html, re.S):
        url = re.search(r'<a href="([^"]+)"', fila)
        titulo = re.search(r'<span class="title">(.*?)</span>', fila, re.S)
        if not url or not titulo:
            continue
        # Precio final en centavos, ya calculado por Steam (0 = gratis). Puede faltar si aún no sale.
        final = re.search(r'data-price-final="(\d+)"', fila)
        original = re.search(r'<div class="discount_original_price">([^<]+)</div>', fila)
        precio_actual = int(final.group(1)) if final else None
        precio_regular = a_centavos(original.group(1)) if original else precio_actual

        porcentaje = cantidad = None
        resena = re.search(r'data-tooltip-html="([^"]+)"', fila)
        if resena:
            texto = html.unescape(resena.group(1))
            encontrado = re.search(r"(\d+)% of the ([\d,]+) user reviews", texto)
            if encontrado:
                porcentaje = int(encontrado.group(1))
                cantidad = int(encontrado.group(2).replace(",", ""))

        candidatos.append(
            Candidato(
                fuente=STEAM,
                titulo=texto_plano(titulo.group(1)),
                url=_sin_parametros(html.unescape(url.group(1))),
                plataforma="pc",
                formato="digital",
                precio_actual_centavos=precio_actual,
                precio_regular_centavos=precio_regular,
                tipo="otro" if "/bundle/" in url.group(1) or "/sub/" in url.group(1) else "juego",
                resena_porcentaje=porcentaje,
                resena_cantidad=cantidad,
            )
        )
    return tuple(candidatos)
