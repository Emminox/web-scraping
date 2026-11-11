"""Medidas de similitud entre títulos, en Python PURO (sin librerías compiladas).

El enunciado lo exige: si se usara una librería en C (rapidfuzz, python-Levenshtein), el cálculo
liberaría el GIL o sería tan rápido que el paralelismo de CPU no se podría observar ni medir.

Se usa la distancia de Levenshtein: el mínimo de inserciones, borrados y sustituciones de letras para
convertir un texto en otro. Ejemplo: "hades" -> "hadez" = 1 (una sustitución).
"""

from __future__ import annotations

from radar.emparejamiento.normalizar import TituloNormalizado


def levenshtein(a: str, b: str) -> int:
    """Distancia de Levenshtein con programación dinámica en dos filas: O(len(a)·len(b)) de tiempo.

    ``previa[j]`` es la distancia entre los primeros ``i-1`` caracteres de ``a`` y los ``j`` primeros de
    ``b``; ``actual`` se calcula a partir de ella. Guardar solo dos filas (y no la matriz completa)
    reduce la memoria de O(n·m) a O(m).
    """
    if len(a) < len(b):
        a, b = b, a  # La fila más corta ocupa menos memoria.
    previa = list(range(len(b) + 1))
    for i, letra_a in enumerate(a, start=1):
        actual = [i]
        for j, letra_b in enumerate(b, start=1):
            actual.append(
                min(
                    previa[j] + 1,                          # Borrar letra_a.
                    actual[j - 1] + 1,                      # Insertar letra_b.
                    previa[j - 1] + (letra_a != letra_b),   # Sustituir (gratis si son iguales).
                )
            )
        previa = actual
    return previa[-1]


def proporcion(a: str, b: str) -> float:
    """Similitud entre 0 y 1: 1 - distancia / longitud del texto más largo."""
    if not a and not b:
        return 1.0
    return 1.0 - levenshtein(a, b) / max(len(a), len(b))


# Factor que se aplica cuando los números no coinciden ("hades" vs "hades 2"): son juegos distintos
# aunque el texto sea casi igual. Ver ADR-006.
PENALIZACION_NUMEROS = 0.6


def similitud(a: TituloNormalizado, b: TituloNormalizado) -> float:
    """Similitud final entre dos títulos normalizados (0 a 1).

    Toma el máximo entre comparar el texto tal cual y comparar las palabras ordenadas alfabéticamente;
    lo segundo tolera cambios de orden ("zelda breath of wild" vs "breath of wild zelda").
    """
    if not a.texto or not b.texto:
        return 0.0
    directo = proporcion(a.texto, b.texto)
    ordenado = proporcion(" ".join(sorted(a.palabras)), " ".join(sorted(b.palabras)))
    valor = max(directo, ordenado)
    if a.numeros != b.numeros:
        valor *= PENALIZACION_NUMEROS
    return valor
