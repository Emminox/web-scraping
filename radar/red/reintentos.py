"""Cálculo de esperas entre reintentos: backoff exponencial con jitter (sección 8 del enunciado).

¿Por qué exponencial? Si un sitio está saturado, reintentar enseguida lo empeora. Duplicar la espera
en cada intento (1 s, 2 s, 4 s, ...) le da tiempo de recuperarse.

¿Por qué jitter (variación aleatoria)? Si 30 hilos fallan al mismo tiempo y todos esperan exactamente
2 s, vuelven a golpear el sitio todos juntos ("manada atronadora"). Con una espera aleatoria entre 0 y
el tope, los reintentos se reparten en el tiempo. Esta variante se llama "full jitter".
"""

from __future__ import annotations

import random


def calcular_espera(
    intento: int, base_segundos: float, maximo_segundos: float, aleatorio: random.Random
) -> float:
    """Segundos a esperar antes del reintento número ``intento`` (0 = primer reintento).

    El tope crece como ``base * 2^intento`` sin pasar de ``maximo_segundos``; la espera real es
    un valor uniforme entre 0 y ese tope.

    ``aleatorio`` se recibe como parámetro (en vez de usar ``random`` global) para poder fijar una
    semilla en las pruebas y obtener siempre los mismos valores.
    """
    tope = min(maximo_segundos, base_segundos * (2**intento))
    # random.Random.uniform es seguro de llamar desde varios hilos en CPython: el generador interno
    # está implementado en C y cada llamada se ejecuta completa sin que otro hilo la interrumpa.
    return aleatorio.uniform(0.0, tope)


def leer_retry_after(cabeceras: dict[str, str], maximo_segundos: float) -> float | None:
    """Lee la cabecera ``Retry-After`` (segundos que el servidor pide esperar), si existe.

    Los servidores la envían con HTTP 429 (demasiadas solicitudes) o 503. Respetarla es parte del
    scraping responsable. Solo se acepta el formato en segundos; la variante con fecha se ignora.
    El valor se limita a ``maximo_segundos`` para que un servidor no nos deje esperando horas.
    """
    for nombre, valor in cabeceras.items():
        if nombre.lower() == "retry-after":
            try:
                segundos = float(valor.strip())
            except ValueError:
                return None  # Formato de fecha u otro valor raro: usamos nuestro propio backoff.
            return max(0.0, min(segundos, maximo_segundos))
    return None
