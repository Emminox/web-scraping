"""Nintendo eShop (EE. UU.): precios (tienda de plataforma, Switch y Switch 2).

Problema: la búsqueda del sitio se arma con JavaScript, así que no sirve para un programa.
Solución: Nintendo publica (y declara en su robots.txt) un **sitemap** con las URLs de todos sus
productos (~40 000), que justamente existe para que los programas automáticos encuentren páginas. Se
descarga una vez por ejecución y se usa como índice: para cada juego se elige la URL de producto
cuyo identificador más se parece al título. Luego se descarga esa página, que trae el nombre, la
plataforma y el precio en datos estructurados (JSON-LD y el estado inicial de la página).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from radar.fuentes.modelos import NINTENDO, Candidato, a_centavos

URL_SITEMAP = "https://www.nintendo.com/us/store/sitemap.xml"

# Sufijos con los que terminan los identificadores de producto, según la plataforma.
SUFIJOS = (("-switch-2", "switch2"), ("-switch", "switch"))


def parsear_sitemap(cuerpo: bytes) -> list[str]:
    """URLs de producto que aparecen en el sitemap."""
    texto = cuerpo.decode("utf-8", errors="replace")
    return [url for url in re.findall(r"<loc>([^<]+)</loc>", texto) if "/store/products/" in url]


class IndiceNintendo:
    """Índice de productos del sitemap para encontrar la página de un juego a partir de su título.

    Se arma UNA vez antes de iniciar el pipeline y después solo se lee: como nadie lo modifica, los
    hilos de la etapa 0 pueden consultarlo a la vez sin locks.
    """

    def __init__(self, urls: list[str]) -> None:
        # (plataforma, palabras del identificador) -> URL. Más un índice invertido palabra -> entradas,
        # para no comparar cada título contra los 40 000 productos.
        self._entradas: list[tuple[str, frozenset[str], str]] = []
        self._por_palabra: dict[str, list[int]] = defaultdict(list)
        for url in sorted(set(urls)):  # Orden fijo: el resultado no depende del orden del sitemap.
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            for sufijo, plataforma in SUFIJOS:
                if slug.endswith(sufijo):
                    palabras = frozenset(p for p in slug[: -len(sufijo)].split("-") if p)
                    indice = len(self._entradas)
                    self._entradas.append((plataforma, palabras, url))
                    for palabra in palabras:
                        self._por_palabra[palabra].append(indice)
                    break

    def __len__(self) -> int:
        return len(self._entradas)

    def buscar(self, palabras_titulo: frozenset[str], plataforma: str, minimo: float = 0.6) -> str | None:
        """URL del producto de ``plataforma`` cuyas palabras más se parecen a las del título.

        Usa similitud de Jaccard (palabras en común / palabras en total). Es una preselección barata:
        la decisión final la toma la etapa de emparejamiento comparando con el nombre real del producto.
        """
        if not palabras_titulo:
            return None
        candidatos = {i for palabra in palabras_titulo for i in self._por_palabra.get(palabra, ())}
        opciones = []
        for indice in candidatos:
            plataforma_producto, palabras, url = self._entradas[indice]
            if plataforma_producto == plataforma:
                parecido = len(palabras & palabras_titulo) / len(palabras | palabras_titulo)
                opciones.append((-parecido, url))  # Negativo: min() elige el MÁS parecido...
        if not opciones:
            return None
        menos_parecido, url = min(opciones)  # ...y, si empatan, la URL alfabéticamente menor (estable).
        return url if -menos_parecido >= minimo else None


def _plataforma(texto: str | None) -> str | None:
    if not texto:
        return None
    texto = texto.lower()
    if "switch 2" in texto:
        return "switch2"
    if "switch" in texto:
        return "switch"
    return None


def parsear_producto(cuerpo: bytes, url: str) -> tuple[Candidato, ...]:
    """Lee una página de producto: nombre, plataforma y precios (actual y regular)."""
    texto = cuerpo.decode("utf-8", errors="replace")
    producto = None
    for bloque in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', texto, re.S):
        datos = json.loads(bloque)
        for nodo in datos.get("@graph", [datos]):
            tipos = nodo.get("@type", [])
            if "Product" in (tipos if isinstance(tipos, list) else [tipos]):
                producto = nodo
                break
        if producto:
            break
    if producto is None:
        return ()

    ofertas = producto.get("offers") or {}
    actual = a_centavos(ofertas.get("price"))
    regular = actual
    # El precio regular y la imagen cuadrada están en el estado inicial de la página, bajo la clave del SKU.
    sku = producto.get("sku")
    imagen = None
    siguiente = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', texto, re.S)
    if sku and siguiente:
        estado = json.loads(siguiente.group(1)).get("props", {}).get("pageProps", {}).get("initialApolloState", {})
        datos_producto = estado.get(f'Product:{{"sku":"{sku}"}}') or {}
        precios = datos_producto.get('prices({"personalized":false})') or {}
        if precios.get("finalPrice") is not None:
            actual = a_centavos(precios["finalPrice"])
        if precios.get("regularPrice") is not None:
            regular = a_centavos(precios["regularPrice"])
        # Arte cuadrado oficial del eShop (1024x1024): no es vertical, pero sí de alta resolución. El sitio lo usa
        # solo si no hay una portada vertical con resolución suficiente (ver radar/sitio/estatico/app.js).
        cuadrada = (datos_producto.get('productImage({"shape":"square"})') or {}).get("url")
        if isinstance(cuadrada, str) and cuadrada.startswith("https://"):
            imagen = cuadrada

    edicion = producto.get("gameEdition")
    titulo = producto.get("name", "")
    if edicion and edicion != "Standard Edition" and edicion.lower() not in titulo.lower():
        titulo = f"{titulo} {edicion}"  # Así el emparejamiento ve que es una edición especial.
    return (
        Candidato(
            fuente=NINTENDO,
            titulo=titulo,
            url=url,
            plataforma=_plataforma(producto.get("gamePlatform")),
            formato="digital",
            precio_actual_centavos=actual,
            precio_regular_centavos=regular,
            imagen_url=imagen,
        ),
    )
