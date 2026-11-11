"""Datos que producen los parsers de las fuentes."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Códigos de fuente que usa todo el proyecto (coinciden con la tabla ``fuente`` de la base).
STEAM = "steam"
GOG = "gog"
NINTENDO = "nintendo"
BESTBUY = "bestbuy"
METACRITIC = "metacritic"                  # Calificación (Metascore).
METACRITIC_LISTADO = "metacritic-listado"  # Descubrimiento (etapa 0) e imágenes.
STEAM_RESENAS = "steam-resenas"


@dataclass(frozen=True)
class Candidato:
    """Un producto que devolvió una tienda: posible coincidencia de un juego del catálogo.

    Es inmutable y solo contiene tipos simples: viaja por las colas del pipeline y, en el modo
    paralelo, se envía con pickle a los procesos del emparejamiento.
    """

    fuente: str                          # STEAM, GOG, NINTENDO o BESTBUY.
    titulo: str                          # Como lo nombra la tienda (sin normalizar).
    url: str                             # Enlace a la página del producto.
    plataforma: str | None               # Código de plataforma ('pc', 'switch'...) o None si no se sabe.
    formato: str                         # 'digital' o 'fisico'.
    precio_actual_centavos: int | None   # None si la tienda no muestra precio (p. ej. aún no sale).
    precio_regular_centavos: int | None  # Precio "tachado" si la tienda lo muestra.
    tipo: str = "juego"                  # 'juego', 'juego_dlc', 'dlc' u 'otro' (según la tienda).
    resena_porcentaje: int | None = None  # Solo Steam: % de reseñas positivas.
    resena_cantidad: int | None = None    # Solo Steam: cantidad de reseñas.
    obtenida_en: str | None = None        # Cuándo se descargó la página de donde salió (ISO, UTC).


def a_centavos(valor: object) -> int | None:
    """Convierte un precio ('$12.99', '12.99', 12.99, Decimal) a centavos (1299), sin redondeos de float.

    Devuelve None si el valor no es un precio reconocible (p. ej. 'Free To Play' o vacío).
    """
    if valor is None or isinstance(valor, bool):
        return None
    texto = str(valor).replace("$", "").replace(",", "").replace("USD", "").strip()
    try:
        cantidad = Decimal(texto)
    except InvalidOperation:
        return None
    if cantidad < 0:
        return None
    return int((cantidad * 100).quantize(Decimal("1")))


def texto_plano(fragmento: str) -> str:
    """Quita etiquetas HTML, decodifica entidades (&amp; -> &) y compacta los espacios."""
    sin_etiquetas = re.sub(r"<[^>]+>", " ", fragmento)
    return re.sub(r"\s+", " ", html.unescape(sin_etiquetas)).strip()
