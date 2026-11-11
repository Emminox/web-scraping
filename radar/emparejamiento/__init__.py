"""Emparejamiento de títulos: la etapa de CPU obligatoria (sección 6 del enunciado).

- ``normalizar.py`` -> minúsculas, sin acentos ni puntuación, sin sufijos de plataforma y edición,
  números romanos convertidos a arábigos.
- ``similitud.py``  -> distancia de Levenshtein y sus derivados, escritos en Python puro (sin librerías
  compiladas) para que el efecto del GIL sea observable.
- ``emparejar.py``  -> decide, para cada tienda, qué producto corresponde al juego, y marca los dudosos.

Algoritmo y umbral justificados en docs/adr/006-algoritmo-de-emparejamiento.md.
"""
