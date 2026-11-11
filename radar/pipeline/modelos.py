"""Tipos de datos que viajan entre las etapas del pipeline y que describen una ejecución.

Recorrido de un juego por el pipeline (ver docs/pipeline.md)::

    0 Descubrir ──Juego──▶ (se divide en una TareaDescarga por fuente)
    1 Descargar ──TareaDescarga──▶ Descarga
    2 Parsear   ──Descarga──▶ ResultadoFuente
    3 Emparejar ──(se juntan todos los ResultadoFuente del juego)──▶ PaqueteJuego ──▶ resultado
    4 Persistir ──resultado──▶ base de datos
    5 Publicar  ──(al final, una vez)──▶ sitio

Todas las clases son ``frozen`` (inmutables): un objeto que viaja por una cola nunca se modifica, así
que ningún hilo puede ver un dato cambiado a medias por otro. Además, todo lo que llega al
emparejamiento debe poder serializarse con pickle, porque en el modo paralelo se envía a otro proceso.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from radar.red.modelos import Respuesta

# Nombres de las etapas, en orden (coinciden con el CHECK de la tabla ejecucion_etapa).
ETAPAS = ("descubrir", "descargar", "parsear", "emparejar", "persistir", "publicar")


@dataclass(frozen=True)
class Juego:
    """Un juego del catálogo, tal como entra al pipeline."""

    clave: str                                  # Identificador estable (ver catalogo/README.md).
    titulo: str
    titulos_alternativos: tuple[str, ...] = ()


@dataclass(frozen=True)
class TareaDescarga:
    """Una consulta a UNA fuente para UN juego. Es la unidad de trabajo de la etapa de descarga.

    Que cada fuente sea una tarea separada es lo que permite el paralelismo "por fuente" del enunciado:
    varias tiendas del mismo juego se consultan al mismo tiempo en workers distintos.
    """

    juego: Juego
    fuente: str          # Código de la fuente (p. ej. 'steam-precios').
    url: str
    total_fuentes: int   # Cuántas tareas tiene este juego en total: así Emparejar sabe cuándo están todas.


@dataclass(frozen=True)
class Descarga:
    """Resultado de una TareaDescarga: la respuesta, o el error si la fuente falló."""

    tarea: TareaDescarga
    respuesta: Respuesta | None
    error: str | None = None


@dataclass(frozen=True)
class ResultadoFuente:
    """Lo que el parser extrajo de una fuente para un juego (o el error, si no se pudo)."""

    juego: Juego
    fuente: str
    total_fuentes: int
    datos: Any = None        # Lo que devuelve el parser de esa fuente (precio, candidatos, puntaje...).
    error: str | None = None  # Si no es None, esta fuente no aportó datos en esta ejecución.


@dataclass(frozen=True)
class PaqueteJuego:
    """Todos los resultados de un juego, listos para emparejar.

    ``resultados`` va SIEMPRE ordenado por fuente. Los resultados llegan en un orden distinto en cada
    modo (y en cada ejecución concurrente); ordenarlos aquí garantiza que el emparejamiento reciba
    exactamente la misma entrada en los tres modos y, por lo tanto, produzca el mismo resultado.
    """

    juego: Juego
    resultados: tuple[ResultadoFuente, ...]


@dataclass(frozen=True)
class DefinicionPipeline:
    """Qué hace cada etapa. El orquestador (secuencial o concurrente) decide CÓMO se ejecutan.

    Separar el "qué" del "cómo" es lo que permite que los tres modos usen exactamente las mismas
    funciones y, así, produzcan los mismos resultados (sección 7 del enunciado).

    Reglas para quien implemente las etapas reales:
    - ``descargar`` debe lanzar ``radar.red.ErrorRed`` cuando la fuente falla (el ClienteHttp ya lo hace).
    - ``emparejar`` debe ser una función definida a nivel de módulo (no una lambda ni una función
      interna) y trabajar solo con su argumento: en el modo paralelo se envía a otro proceso con pickle.
    - ``persistir`` se llama siempre desde UN solo hilo (ADR-003).
    """

    paginas: Callable[[], Iterable[Any]]                      # Páginas del listado público (etapa 0).
    descubrir_pagina: Callable[[Any], Iterable[Juego]]        # Juegos que aparecen en una página.
    fuentes_de: Callable[[Juego], Iterable[tuple[str, str]]]  # (fuente, url) a consultar por juego.
    descargar: Callable[[TareaDescarga], Respuesta]           # E/S: obtiene la página de una fuente.
    parsear: Callable[[Descarga], Any]                        # Extrae los datos de una descarga exitosa.
    emparejar: Callable[[PaqueteJuego], Any]                  # CPU: decide qué corresponde a cada juego.
    persistir: Callable[[Any], None]                          # Guarda el resultado de un juego.
    publicar: Callable[[], None]                              # Genera el sitio al final.


@dataclass(frozen=True)
class ErrorEtapa:
    """Un problema ocurrido en una etapa, que no detuvo el pipeline."""

    etapa: str
    clave: str     # Juego (o página) afectado; "-" si no se sabe.
    mensaje: str


@dataclass(frozen=True)
class EstadisticaEtapa:
    """Tiempos de una etapa en una ejecución (para el panel de métricas y el informe).

    - ``tiempo_ocupado_s``: suma del trabajo de TODOS sus workers. Con 8 workers trabajando 1 s cada uno
      a la vez, vale 8 s aunque solo haya pasado 1 s de reloj.
    - ``ventana_s``: tiempo de reloj desde que la etapa empezó su primer elemento hasta que terminó el
      último. Comparar ambos muestra cuánto se solapó realmente el trabajo de la etapa.
    """

    nombre: str
    elementos: int
    tiempo_ocupado_s: float
    inicio_s: float    # Segundos desde el inicio de la ejecución.
    fin_s: float

    @property
    def ventana_s(self) -> float:
        return self.fin_s - self.inicio_s


@dataclass(frozen=True)
class ResultadoEjecucion:
    """Resumen de una ejecución del pipeline."""

    modo: str
    duracion_total_s: float
    etapas: dict[str, EstadisticaEtapa]
    juegos_persistidos: int
    fallidos: tuple[Descarga, ...]   # Descargas que fallaron (cola de fallidos, sección 8).
    errores: tuple[ErrorEtapa, ...]  # Otros problemas (parseo, emparejamiento, persistencia...).
