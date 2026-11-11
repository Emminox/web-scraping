"""Normalización de títulos (primer paso del emparejamiento).

Cada tienda nombra el mismo juego de forma distinta: "Hades - Nintendo Switch Lite, Nintendo Switch",
"HADES™", "Hades (PS5)". Antes de comparar se lleva cada título a una forma canónica y, de paso, se
anotan sus "marcas": números (para distinguir secuelas), ediciones especiales y señales de DLC. Las
marcas no se usan para la similitud de texto, sino para decidir si el caso es dudoso.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Frases de plataforma que se quitan (el enunciado pide normalizar "sin sufijos de plataforma").
# Ordenadas de más larga a más corta para quitar "nintendo switch 2" antes que "nintendo switch".
FRASES_PLATAFORMA = sorted(
    [
        "nintendo switch 2", "nintendo switch lite", "nintendo switch oled model", "nintendo switch oled",
        "oled model", "nintendo switch", "switch 2 edition", "playstation 5 pro", "playstation 5",
        "playstation 4", "playstation vr2", "ps5 pro", "ps5", "ps4",
        "xbox series x s", "xbox series x", "xbox series", "xbox one", "windows", "pc", "steam",
    ],
    key=len,
    reverse=True,
)

# Frases de edición que se quitan del texto pero se anotan (una edición distinta es un caso dudoso).
FRASES_EDICION = sorted(
    [
        "game of the year edition", "game of the year", "goty edition", "goty",
        "definitive edition", "deluxe edition", "digital deluxe edition", "digital deluxe", "deluxe",
        "complete edition", "ultimate edition", "gold edition", "premium edition", "special edition",
        "collectors edition", "launch edition", "standard edition", "enhanced edition", "enhanced", "edition",
        "remastered", "remaster", "director s cut", "directors cut",
    ],
    key=len,
    reverse=True,
)
# Ediciones que NO cambian el producto: no hacen que el caso sea dudoso.
EDICIONES_NEUTRAS = {"standard edition", "edition"}

# Palabras que indican que el producto no es el juego base.
PALABRAS_DLC = {
    "dlc", "soundtrack", "ost", "season pass", "expansion pass", "expansion", "bundle", "pack",
    "upgrade", "add on", "artbook", "demo", "costume", "skin", "currency", "coins", "points",
}

ROMANOS = {
    "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9",
    "x": "10", "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15", "xvi": "16",
}


@dataclass(frozen=True)
class TituloNormalizado:
    texto: str                     # Forma canónica para comparar ("legend of zelda breath of wild").
    palabras: tuple[str, ...]      # Palabras del texto, en orden.
    numeros: frozenset[str]        # Números presentes ("2" en "Hades II"): distinguen secuelas.
    ediciones: frozenset[str]      # Ediciones especiales encontradas (sin las neutras).
    dlc: frozenset[str]            # Palabras de DLC encontradas.


def _quitar_frases(texto: str, frases: list[str]) -> tuple[str, set[str]]:
    """Quita del texto cada frase (como palabras completas) y devuelve las que encontró."""
    encontradas = set()
    for frase in frases:
        patron = rf"\b{re.escape(frase)}\b"
        if re.search(patron, texto):
            encontradas.add(frase)
            texto = re.sub(patron, " ", texto)
    return texto, encontradas


def quitar_anio_entre_parentesis(titulo: str) -> str:
    """Quita un año entre paréntesis: "Unreal Tournament (1999)" -> "Unreal Tournament ".

    Metacritic agrega el año para distinguir juegos con el mismo nombre, pero las tiendas no lo escriben. Si se
    dejara, "1999" contaría como un número distinto y la penalización de números hundiría un par correcto. Solo se
    quita entre paréntesis: "FIFA 2004" o "Tom Clancy's Rainbow Six 2049" siguen teniendo su número.
    """
    return re.sub(r"\((?:19|20)\d{2}\)", " ", titulo)


def texto_basico(titulo: str) -> str:
    """Minúsculas sin acentos, símbolos ni puntuación: "Pokémon™: Let's Go!" -> "pokemon lets go".

    Es el paso común que usan ``normalizar`` y el índice de Nintendo (``radar.ejecucion.palabras_para_indice``);
    así las dos partes no pueden quedar con reglas distintas.
    """
    # Los símbolos de marca se quitan ANTES de NFKD, porque NFKD convierte "™" en las letras "TM" ("hadestm").
    # NFKD separa la letra de su tilde y luego se descarta la tilde.
    texto = re.sub(r"[™®©℠]", " ", titulo)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    texto = texto.replace("&", " and ").replace("'", "")  # "Assassin's" -> "assassins"
    # Toda la puntuación pasa a ser espacio: "Zelda: Breath of the Wild – Switch" -> palabras sueltas.
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def quitar_etiquetas_entre_corchetes(titulo: str) -> str:
    """Quita etiquetas entre corchetes: "Death's Door - Nintendo Switch [Digital]" -> "Death's Door - Nintendo Switch ".

    Best Buy las usa para el formato o la plataforma ("[Digital]", "[PlayStation 5]", "[Standard]"). Ningún título
    de juego del catálogo usa corchetes, y dejar "digital" bajaba la similitud de 177 juegos de Switch por debajo
    del umbral (p. ej. 0.58 para "Death's Door").
    """
    return re.sub(r"\[[^\]]*\]", " ", titulo)


def normalizar(titulo: str) -> TituloNormalizado:
    # 1) y 2) Etiquetas entre corchetes, año entre paréntesis, acentos, símbolos y puntuación (funciones de arriba).
    texto = texto_basico(quitar_anio_entre_parentesis(quitar_etiquetas_entre_corchetes(titulo)))
    # 3) Sufijos de plataforma y edición.
    texto, _ = _quitar_frases(texto, FRASES_PLATAFORMA)
    texto, ediciones = _quitar_frases(texto, FRASES_EDICION)
    # Las palabras de DLC también se quitan del texto y se anotan: así "Hades Soundtrack" se parece a
    # "Hades" (y aparece como caso dudoso, como pide el enunciado) en vez de descartarse sin aviso.
    texto, dlc = _quitar_frases(texto, sorted(PALABRAS_DLC, key=len, reverse=True))
    # 4) Romanos a arábigos ("final fantasy vii" -> "final fantasy 7") y artículos que no aportan.
    palabras = [ROMANOS.get(p, p) for p in texto.split() if p not in ("the", "a", "an", "of")]
    return TituloNormalizado(
        texto=" ".join(palabras),
        palabras=tuple(palabras),
        numeros=frozenset(p for p in palabras if p.isdigit()),
        ediciones=frozenset(ediciones - EDICIONES_NEUTRAS),
        dlc=frozenset(dlc),
    )
