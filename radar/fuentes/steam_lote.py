"""Precios de Steam por lote (ADR-013): muchos juegos en una sola solicitud.

Desde GitHub Actions, Steam frenaba la búsqueda por título (una solicitud por juego) con 429 después de unas
200–300 búsquedas: los servidores de GitHub son compartidos y Steam cuenta todas las solicitudes de esa IP.

Para los juegos cuyo producto de Steam YA está emparejado (se conoce su número de aplicación, el "appid" de la URL
``/app/<appid>/``), el precio se pide a ``/api/appdetails`` con ``filters=price_overview``, que acepta muchos
appids a la vez: los ~400 juegos de Steam de la base se actualizan con 2 solicitudes. robots.txt de
store.steampowered.com no prohíbe /api/ y el enunciado permite la API de Steam. No es una API documentada por
Valve: si deja de responder, esos juegos vuelven a buscarse por título (la búsqueda sigue siendo el respaldo).

Solo se usa en ejecuciones EN VIVO. En replay (experimentos de rendimiento) la carga de trabajo debe ser siempre la
misma (ver ``radar.ejecucion``).
"""

from __future__ import annotations

import json
import re

URL_LOTE = "https://store.steampowered.com/api/appdetails?appids={appids}&filters=price_overview&cc=us"
TAMANO_LOTE = 200   # Probado con 250 sin problemas; 200 deja margen en el largo de la URL.

_APPID = re.compile(r"store\.steampowered\.com/app/(\d+)")


def appid_de(url: str) -> str | None:
    """Número de aplicación de una URL de producto de Steam (``…/app/1145360/Hades/`` -> ``"1145360"``)."""
    encontrado = _APPID.search(url or "")
    return encontrado.group(1) if encontrado else None


def urls_por_lote(appids, tamano: int = TAMANO_LOTE) -> list[str]:
    """URLs de consulta, ``tamano`` appids cada una. Ordenados: mismas URLs (y misma caché) en cada corrida."""
    ordenados = sorted(set(appids), key=int)
    return [URL_LOTE.format(appids=",".join(ordenados[i:i + tamano])) for i in range(0, len(ordenados), tamano)]


def parsear_lote(cuerpo: bytes) -> dict[str, tuple[int, int]]:
    """appid -> (precio actual, precio regular) en centavos de USD.

    Se omiten los juegos sin ``price_overview`` (gratuitos o no a la venta) y cualquier precio que no venga en USD:
    esos se siguen buscando por título.
    """
    datos = json.loads(cuerpo)
    precios: dict[str, tuple[int, int]] = {}
    for appid, entrada in datos.items():
        if not isinstance(entrada, dict) or not entrada.get("success"):
            continue
        detalle = entrada.get("data")
        precio = detalle.get("price_overview") if isinstance(detalle, dict) else None
        if not isinstance(precio, dict) or precio.get("currency") != "USD":
            continue
        actual, regular = precio.get("final"), precio.get("initial")
        if isinstance(actual, int) and actual >= 0:
            precios[str(appid)] = (actual, regular if isinstance(regular, int) and regular >= 0 else actual)
    return precios
