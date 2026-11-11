"""Contadores de solicitudes por sitio, para el panel de métricas (sección 9 del enunciado).

El panel debe mostrar "solicitudes exitosas, reintentadas y fallidas por sitio". Varios hilos
actualizan estos contadores a la vez, así que se protegen con un lock.

¿Por qué hace falta el lock si Python tiene GIL? Porque ``contador += 1`` NO es una operación
atómica: son varios pasos (leer el valor, sumar, escribir). El GIL puede pasar a otro hilo entre
leer y escribir, y entonces dos hilos que leyeron el mismo valor escriben el mismo resultado: se
pierde un incremento. Esa es exactamente la condición de carrera que el experimento de contención
debe reproducir y explicar.

Aquí se usa un lock global (la opción más simple). Es adecuado porque cada solicitud tarda cientos
de milisegundos y la actualización del contador microsegundos: la contención es mínima.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass

# Nombres de los contadores que se registran por dominio.
CAMPOS = ("exitosas", "reintentos", "fallidas", "desde_almacen", "bloqueadas_robots")


@dataclass
class ContadoresDominio:
    """Contadores de UN dominio."""

    exitosas: int = 0           # Respuestas 2xx obtenidas de la red (o del replay).
    reintentos: int = 0         # Veces que se volvió a intentar tras un fallo temporal.
    fallidas: int = 0           # Solicitudes que terminaron sin éxito (van a la cola de fallidos).
    desde_almacen: int = 0      # Respuestas servidas desde la caché sin tocar la red.
    bloqueadas_robots: int = 0  # URLs no descargadas porque robots.txt no lo permite.


class MetricasRed:
    """Registro seguro para hilos de los contadores de todos los dominios."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._por_dominio: dict[str, ContadoresDominio] = {}

    def registrar(self, dominio: str, campo: str, cantidad: int = 1) -> None:
        """Suma ``cantidad`` al contador ``campo`` del ``dominio``."""
        if campo not in CAMPOS:
            raise ValueError(f"Campo de métrica desconocido: {campo!r}")
        with self._lock:  # Toda la operación leer-sumar-escribir ocurre sin que otro hilo entre.
            contadores = self._por_dominio.setdefault(dominio, ContadoresDominio())
            setattr(contadores, campo, getattr(contadores, campo) + cantidad)

    def instantanea(self) -> dict[str, dict[str, int]]:
        """Copia de todos los contadores en este momento (para reportes o el panel).

        Se devuelve una copia, no los objetos internos, para que quien la lea no vea valores
        cambiando mientras otros hilos siguen registrando.
        """
        with self._lock:
            return {dominio: asdict(c) for dominio, c in self._por_dominio.items()}
