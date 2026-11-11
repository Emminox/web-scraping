"""GOG: precios (tienda de plataforma, PC) mediante su catálogo público en JSON.

Es una fuente por API (el enunciado permite APIs para las fuentes que no son las 3 obligatorias por
HTML). ``catalog.gog.com`` no publica robots.txt (responde 404), lo que según la convención significa
que no impone restricciones; igual se respeta el límite por dominio.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from radar.fuentes.modelos import GOG, Candidato, a_centavos

CANTIDAD_RESULTADOS = 10


def url_busqueda(titulo: str) -> str:
    return (
        "https://catalog.gog.com/v1/catalog"
        f"?limit={CANTIDAD_RESULTADOS}&query=like:{quote(titulo)}&order=desc:score"
        "&productType=in:game,pack&countryCode=US&locale=en-US&currencyCode=USD"
    )


def parsear_busqueda(cuerpo: bytes) -> tuple[Candidato, ...]:
    datos = json.loads(cuerpo.decode("utf-8"))
    candidatos: list[Candidato] = []
    for producto in datos.get("products", []):
        titulo = producto.get("title")
        url = producto.get("storeLink")
        if not titulo or not url:
            continue
        precio = producto.get("price") or {}
        actual = a_centavos((precio.get("finalMoney") or {}).get("amount"))
        regular = a_centavos((precio.get("baseMoney") or {}).get("amount"))
        candidatos.append(
            Candidato(
                fuente=GOG,
                titulo=titulo,
                url=url,
                plataforma="pc",
                formato="digital",
                precio_actual_centavos=actual,
                precio_regular_centavos=regular if regular is not None else actual,
                # 'pack' en GOG es un paquete de varios productos: se marca como 'otro' (caso dudoso).
                tipo="juego" if producto.get("productType") == "game" else "otro",
            )
        )
    return tuple(candidatos)
