"""Best Buy (EE. UU.): precios de un minorista (formato físico, consolas).

Detalles encontrados en el spike:
- Desde fuera de EE. UU., Best Buy muestra primero una página para elegir el país. El parámetro
  ``intl=nosplash`` equivale a elegir "Estados Unidos" (es una opción normal del sitio, no una evasión
  de bloqueos).
- La página de búsqueda no muestra los precios en el HTML visible (se completan con JavaScript), pero
  los primeros resultados vienen con todos sus datos en un JSON incrustado
  (``ApolloSSRDataTransport``). Se lee ese JSON.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote

from radar.fuentes.modelos import BESTBUY, Candidato, a_centavos

PREFIJO_DATOS = '(window[Symbol.for("ApolloSSRDataTransport")] ??= []).push('

# Texto de plataforma en el nombre del producto -> código del proyecto. El orden importa:
# "Nintendo Switch 2" debe probarse antes que "Nintendo Switch".
PLATAFORMAS = (
    ("nintendo switch 2", "switch2"),
    ("nintendo switch", "switch"),
    ("playstation 5", "ps5"),
    ("playstation 4", "ps4"),
    ("xbox series x", "xbox-series"),
    ("xbox one", "xbox-one"),
    ("windows", "pc"),
)


def url_busqueda(titulo: str) -> str:
    return f"https://www.bestbuy.com/site/searchpage.jsp?st={quote(titulo)}&intl=nosplash"


def _plataforma(nombre: str) -> str | None:
    """'Hades - Nintendo Switch Lite, Nintendo Switch' -> 'switch' (se mira la parte después del último ' - ')."""
    sufijo = nombre.rsplit(" - ", 1)[-1].lower() if " - " in nombre else nombre.lower()
    for texto, codigo in PLATAFORMAS:
        if texto in sufijo:
            return codigo
    return None


def parsear_busqueda(cuerpo: bytes) -> tuple[Candidato, ...]:
    texto = cuerpo.decode("utf-8", errors="replace")
    precios: dict[str, tuple] = {}
    nombres: dict[str, str] = {}
    urls: dict[str, str] = {}
    imagenes: dict[str, str] = {}

    def recorrer(nodo: object) -> None:
        if isinstance(nodo, dict):
            sku = nodo.get("skuId")
            if sku and nodo.get("customerPrice") is not None:
                precios[sku] = (nodo["customerPrice"], nodo.get("displayableRegularPrice"))
            if sku and isinstance(nodo.get("name"), dict) and nodo["name"].get("short"):
                nombres[sku] = nodo["name"]["short"]
            imagen = nodo.get("primaryImage")
            if sku and isinstance(imagen, dict) and str(imagen.get("piscesHref", "")).startswith("https://"):
                imagenes.setdefault(sku, imagen["piscesHref"])
            producto = nodo.get("product")
            if nodo.get("pdpUrl") and isinstance(producto, dict) and producto.get("skuId"):
                urls[producto["skuId"]] = nodo["pdpUrl"]
            for valor in nodo.values():
                recorrer(valor)
        elif isinstance(nodo, list):
            for valor in nodo:
                recorrer(valor)

    for script in re.findall(r"<script[^>]*>(.*?)</script>", texto, re.S):
        if not script.startswith(PREFIJO_DATOS):
            continue
        # Es JavaScript, no JSON puro: puede contener "undefined", que JSON no admite.
        contenido = re.sub(r":undefined([,}\]])", r":null\1", script[len(PREFIJO_DATOS):])
        try:
            datos, _ = json.JSONDecoder().raw_decode(contenido)
        except json.JSONDecodeError:
            continue
        recorrer(datos)

    candidatos: list[Candidato] = []
    for sku in sorted(set(precios) & set(nombres)):  # Orden fijo por SKU.
        nombre = nombres[sku]
        actual, regular = precios[sku]
        minusculas = nombre.lower()
        candidatos.append(
            Candidato(
                fuente=BESTBUY,
                titulo=nombre,
                url=urls.get(sku, f"https://www.bestbuy.com/site/{sku}.p?skuId={sku}"),
                plataforma=_plataforma(nombre),
                formato="digital" if "digital" in minusculas else "fisico",
                precio_actual_centavos=a_centavos(actual),
                precio_regular_centavos=a_centavos(regular) if regular is not None else a_centavos(actual),
                tipo="otro" if "bundle" in minusculas else "juego",
                # Carátula de la caja a 600x900 como máximo (el servicio de imágenes de Best Buy acepta el tamaño
                # en la URL): ~80 KB, proporción de portada. Se usa en el sitio para juegos sin portada en Steam.
                imagen_url=f"{imagenes[sku]};maxHeight=900;maxWidth=600" if sku in imagenes else None,
            )
        )
    return tuple(candidatos)
