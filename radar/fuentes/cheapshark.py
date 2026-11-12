"""CheapShark: precios de tiendas oficiales de PC (Humble, Fanatical, Epic, Green Man Gaming…) por API pública.

Por qué (ADR-011): con Steam y GOG solo el ~20 % del catálogo tenía precio en 2 tiendas, porque GOG vende pocos
de los juegos de PC del listado, y PlayStation Store y Xbox no se pueden consultar (búsqueda y catálogo solo con
JavaScript, API interna prohibida o sin sitemap). CheapShark es una API pública, gratuita y documentada
(https://apidocs.cheapshark.com/) que reúne los precios de varias tiendas oficiales de PC. El enunciado permite
APIs para las fuentes que no son las tres obligatorias por HTML.

Una sola solicitud por juego (``/deals?title=...``) devuelve ofertas de VARIAS tiendas. Cada tienda se trata como
una fuente distinta (``Candidato.fuente`` = código de la tienda): el emparejamiento elige el mejor producto de
CADA tienda. Se excluyen Steam y GOG porque ya se consultan directamente.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote

from radar.fuentes.modelos import Candidato, a_centavos

# Código de la tarea de descarga (una consulta a CheapShark por juego de PC).
CHEAPSHARK = "cheapshark"

# storeID de CheapShark -> (código de fuente del proyecto, nombre, tipo de la tabla ``fuente``).
# Solo tiendas activas (consultado el 2026-11-11 en /api/1.0/stores). Steam (1) y GOG (7) se excluyen a propósito.
TIENDAS = {
    "2": ("gamersgate", "GamersGate", "minorista"),
    "3": ("greenmangaming", "Green Man Gaming", "minorista"),
    "11": ("humble", "Humble Store", "minorista"),
    "13": ("ubisoft", "Ubisoft Store", "tienda_plataforma"),
    "15": ("fanatical", "Fanatical", "minorista"),
    "21": ("wingamestore", "WinGameStore", "minorista"),
    "23": ("gamebillet", "GameBillet", "minorista"),
    "25": ("epic", "Epic Games Store", "tienda_plataforma"),
    "27": ("gamesplanet", "Gamesplanet", "minorista"),
    "30": ("indiegala", "IndieGala", "minorista"),
    "35": ("dreamgame", "DreamGame", "minorista"),
}

CANTIDAD_RESULTADOS = 60  # Máximo que permite la API por página.


def _deal_id_para_url(deal_id: str) -> str:
    """El dealID de la API YA viene codificado para URL ("…%2F…%3D"): se usa tal cual, como en la documentación.

    Antes se volvía a codificar ("%252F") y CheapShark no reconocía la oferta: en vez de redirigir a la tienda
    (GameBillet, Fanatical…) dejaba al usuario en su propia página. Solo si trae caracteres fuera de los seguros
    para una URL (no debería pasar) se codifica, para no romper el enlace.
    """
    if re.fullmatch(r"[A-Za-z0-9%._~-]+", deal_id):
        return deal_id
    return quote(deal_id, safe="")


def url_busqueda(titulo: str) -> str:
    return f"https://www.cheapshark.com/api/1.0/deals?title={quote(titulo)}&pageSize={CANTIDAD_RESULTADOS}"


def parsear_busqueda(cuerpo: bytes) -> tuple[Candidato, ...]:
    ofertas = json.loads(cuerpo.decode("utf-8"))
    candidatos = []
    for oferta in ofertas:
        tienda = TIENDAS.get(str(oferta.get("storeID")))
        titulo, oferta_id = oferta.get("title"), oferta.get("dealID")
        if tienda is None or not titulo or not oferta_id:
            continue
        actual = a_centavos(oferta.get("salePrice"))
        regular = a_centavos(oferta.get("normalPrice"))
        candidatos.append(
            Candidato(
                fuente=tienda[0],
                titulo=titulo,
                # Enlace de redirección de CheapShark: la forma que su documentación pide para enlazar una oferta.
                url=f"https://www.cheapshark.com/redirect?dealID={_deal_id_para_url(oferta_id)}",
                plataforma="pc",
                formato="digital",
                precio_actual_centavos=actual,
                precio_regular_centavos=regular if regular is not None else actual,
            )
        )
    return tuple(candidatos)
