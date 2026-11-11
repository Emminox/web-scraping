"""Metacritic: descubrimiento del catálogo (etapa 0) y calificación (Metascore) por plataforma.

Se recorre el listado público "mejores juegos de todos los tiempos" de cada plataforma, que está
paginado (50 juegos por página). Cada tarjeta trae: el identificador del juego en la URL
(``/game/elden-ring/``), el título, la fecha, la imagen y el Metascore EN ESA PLATAFORMA. Así una sola
fuente resuelve el catálogo, la calificación obligatoria por plataforma y la imagen.

robots.txt permite ``/browse/`` y ``/game/`` (prohíbe ``/search/``, que no se usa).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime

from radar.fuentes.modelos import texto_plano

BASE = "https://www.metacritic.com"

# Plataforma en la URL de Metacritic -> código de plataforma del proyecto (tabla ``plataforma``).
PLATAFORMAS = {
    "ps5": "ps5",
    "xbox-series-x": "xbox-series",
    "nintendo-switch": "switch",
    "nintendo-switch-2": "switch2",
    "pc": "pc",
}


@dataclass(frozen=True)
class TarjetaListado:
    """Un juego tal como aparece en una página del listado."""

    slug: str                 # Identificador estable en Metacritic ('elden-ring'); se usa como clave del juego.
    titulo: str
    plataforma: str           # Código del proyecto ('ps5', 'pc'...).
    fecha_lanzamiento: str | None   # 'AAAA-MM-DD'
    metascore: int | None     # None si todavía no tiene ("tbd").
    imagen_url: str | None


def url_listado(plataforma_metacritic: str, pagina: int) -> str:
    """URL de la página ``pagina`` (desde 1) del listado ordenado por Metascore de una plataforma."""
    return (
        f"{BASE}/browse/game/{plataforma_metacritic}/all/all-time/metascore/"
        f"?platform={plataforma_metacritic}&page={pagina}"
    )


def _fecha(texto: str) -> str | None:
    """'Feb 25, 2022' -> '2022-02-25'."""
    try:
        return datetime.strptime(texto.strip(), "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def parsear_listado(contenido: str, plataforma: str) -> list[TarjetaListado]:
    """Extrae las tarjetas de una página del listado.

    Cada tarjeta empieza con ``data-testid="filter-results"``; se corta el HTML en esos puntos y se
    leen los campos de cada trozo. Si una tarjeta no tiene identificador o título, se descarta.
    """
    tarjetas: list[TarjetaListado] = []
    trozos = contenido.split('data-testid="filter-results"')[1:]
    for trozo in trozos:
        slug = re.search(r'href="/game/([^"/]+)/"', trozo)
        titulo = re.search(r'data-title="([^"]*)"', trozo)
        if not slug or not titulo:
            continue
        fecha = re.search(r"<span>([A-Z][a-z]{2} \d{1,2}, \d{4})</span>", trozo)
        puntaje = re.search(r'title="Metascore (\d{1,3}) out of 100"', trozo)
        # Se prefiere la imagen "2x" del srcset (192x288): la de src es de 96x144 y se ve borrosa en la tarjeta.
        imagen = (re.search(r'(https://www\.metacritic\.com/a/img/[^\s"]+) 2x', trozo)
                  or re.search(r'src="(https://www\.metacritic\.com/a/img/[^"]+)"', trozo))
        tarjetas.append(
            TarjetaListado(
                slug=slug.group(1),
                titulo=texto_plano(titulo.group(1)),
                plataforma=plataforma,
                fecha_lanzamiento=_fecha(fecha.group(1)) if fecha else None,
                metascore=int(puntaje.group(1)) if puntaje else None,
                imagen_url=html.unescape(imagen.group(1)) if imagen else None,
            )
        )
    return tarjetas
