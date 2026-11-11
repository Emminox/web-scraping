"""Mide cuánto tiempo pasa cada etapa trabajando, de forma segura entre hilos.

Para qué sirve: el enunciado pide medir "cada etapa por separado y el pipeline completo", y el panel
de métricas muestra el tiempo por etapa. Varios workers registran sus tiempos a la vez, por eso los
datos se protegen con un lock (mismo razonamiento que en radar/red/metricas.py).

Se usa ``time.perf_counter``: es el reloj de mayor resolución de Python y nunca retrocede.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from radar.pipeline.modelos import EstadisticaEtapa


class MedidorEtapas:
    """Acumula, por etapa: cantidad de elementos, tiempo ocupado y ventana (primer inicio, último fin)."""

    def __init__(self, reloj: Callable[[], float] = time.perf_counter) -> None:
        self._reloj = reloj
        self._origen = reloj()  # Instante de inicio de la ejecución; los tiempos se reportan desde aquí.
        self._lock = threading.Lock()
        # etapa -> [elementos, tiempo ocupado, primer inicio, último fin]
        self._datos: dict[str, list[float]] = {}

    def ahora(self) -> float:
        return self._reloj()

    def transcurrido(self) -> float:
        """Segundos desde el inicio de la ejecución (el mismo origen que usan las etapas).

        La duración total DEBE medirse desde este mismo origen: si se tomara otro instante de inicio,
        aunque sea microsegundos después, una etapa podría aparecer terminando "después" del final.
        """
        return self._reloj() - self._origen

    def registrar(
        self, etapa: str, inicio: float, fin: float, *, ocupado: float | None = None, elementos: int = 1
    ) -> None:
        """Registra un trabajo de ``etapa`` entre ``inicio`` y ``fin``.

        :param ocupado: tiempo de trabajo real si difiere de ``fin - inicio`` (en el modo paralelo, el
            tiempo que el proceso hijo pasó emparejando, sin contar la espera en la cola del ejecutor).
        :param elementos: cuántos elementos cuenta este registro (0 para trabajos auxiliares, como
            listar las páginas, que consumen tiempo pero no son "un elemento" de la etapa).
        """
        trabajo = fin - inicio if ocupado is None else ocupado
        with self._lock:
            datos = self._datos.get(etapa)
            if datos is None:
                self._datos[etapa] = [elementos, trabajo, inicio, fin]
            else:
                datos[0] += elementos
                datos[1] += trabajo
                datos[2] = min(datos[2], inicio)
                datos[3] = max(datos[3], fin)

    @contextmanager
    def medir(self, etapa: str, *, elementos: int = 1) -> Iterator[None]:
        """Mide el bloque ``with``: ``with medidor.medir("descargar"): ...``."""
        inicio = self._reloj()
        try:
            yield
        finally:
            self.registrar(etapa, inicio, self._reloj(), elementos=elementos)

    def estadisticas(self) -> dict[str, EstadisticaEtapa]:
        """Copia de las estadísticas acumuladas, con tiempos relativos al inicio de la ejecución."""
        with self._lock:
            return {
                etapa: EstadisticaEtapa(
                    nombre=etapa,
                    elementos=int(datos[0]),
                    tiempo_ocupado_s=datos[1],
                    inicio_s=datos[2] - self._origen,
                    fin_s=datos[3] - self._origen,
                )
                for etapa, datos in self._datos.items()
            }
