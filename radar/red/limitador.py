"""Límites de cortesía por dominio: conexiones simultáneas e intervalo mínimo entre solicitudes.

Para qué sirve (secciones 7 y 10 del enunciado): aunque el pipeline tenga 64 workers de descarga,
no podemos mandar 64 solicitudes a la vez al mismo sitio: lo saturaríamos y nos bloquearía. Este
módulo impone, POR DOMINIO:

1. Un máximo de conexiones simultáneas -> un ``threading.BoundedSemaphore`` por dominio.
2. Un intervalo mínimo entre el inicio de dos solicitudes -> un "reloj de turnos" protegido por lock.

Así, los dominios distintos avanzan en paralelo (cada uno con su semáforo), pero cada sitio recibe
un ritmo de solicitudes controlado. En la defensa pueden preguntar "¿qué pasa si quito el semáforo?":
la respuesta es que todos los workers golpearían el mismo sitio a la vez.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from radar.config import ConfigRed


class _EstadoDominio:
    """Estado de sincronización de UN dominio. Se crea una sola vez por dominio y se reutiliza."""

    def __init__(self, max_conexiones: int, intervalo_segundos: float) -> None:
        # BoundedSemaphore (y no Semaphore) lanza error si alguien libera más veces de las que
        # adquirió: convierte un bug silencioso (el límite crece solo) en un error visible.
        self.semaforo = threading.BoundedSemaphore(max_conexiones)
        # Protege ``siguiente_turno``. Es un lock distinto del semáforo porque protege otra cosa.
        self.lock_turnos = threading.Lock()
        # Instante (según el reloj monotónico) a partir del cual puede empezar la próxima solicitud.
        self.siguiente_turno = 0.0
        self.intervalo_segundos = intervalo_segundos


class LimitadorPorDominio:
    """Reparte "turnos" para hablar con cada dominio respetando sus límites.

    Uso::

        with limitador.turno("store.steampowered.com"):
            respuesta = transporte.obtener(...)

    Mientras se está dentro del ``with`` se ocupa una de las conexiones permitidas para ese dominio.
    """

    def __init__(
        self,
        config_red: ConfigRed,
        *,
        aplicar_intervalo: bool = True,
        reloj: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        """
        :param config_red: de aquí salen los límites por defecto y los específicos por dominio.
        :param aplicar_intervalo: en modo replay se pone en False: no hay sitio real que cuidar,
            pero el semáforo de conexiones se sigue aplicando porque es parte del diseño que se mide.
        :param reloj: función que da la hora; se usa ``time.monotonic`` porque nunca retrocede
            (la hora del sistema sí puede cambiar, p. ej. al sincronizar con internet).
        :param dormir: función para esperar; las pruebas pasan una falsa para no esperar de verdad.
        """
        self._config_red = config_red
        self._aplicar_intervalo = aplicar_intervalo
        self._reloj = reloj
        self._dormir = dormir
        # Diccionario dominio -> estado, compartido por todos los hilos.
        self._dominios: dict[str, _EstadoDominio] = {}
        # Protege el diccionario anterior (ver ``_estado``).
        self._lock_registro = threading.Lock()

    def _estado(self, dominio: str) -> _EstadoDominio:
        """Devuelve el estado del dominio, creándolo la primera vez.

        El lock evita una condición de carrera clásica de "comprobar y luego crear": sin él, dos
        hilos podrían ver a la vez que el dominio no existe, crear cada uno SU propio semáforo, y
        cada hilo quedaría limitado por un semáforo distinto (el límite real se duplicaría).
        """
        with self._lock_registro:
            estado = self._dominios.get(dominio)
            if estado is None:
                limite = self._config_red.limite_para(dominio)
                estado = _EstadoDominio(limite.max_conexiones, limite.intervalo_minimo_segundos)
                self._dominios[dominio] = estado
            return estado

    def _esperar_intervalo(self, estado: _EstadoDominio) -> None:
        """Espera hasta que le toque el turno a esta solicitud según el intervalo mínimo."""
        # 1) Con el lock tomado SOLO reservamos el turno (operación rapidísima).
        with estado.lock_turnos:
            ahora = self._reloj()
            mi_turno = max(ahora, estado.siguiente_turno)
            estado.siguiente_turno = mi_turno + estado.intervalo_segundos
        # 2) Dormimos FUERA del lock. Si durmiéramos con el lock tomado, los demás hilos de este
        #    dominio quedarían bloqueados sin poder ni siquiera reservar su turno, y todo se
        #    serializaría más de lo necesario (más fracción serial en Amdahl).
        espera = mi_turno - ahora
        if espera > 0:
            self._dormir(espera)

    @contextmanager
    def turno(self, dominio: str) -> Iterator[None]:
        """Ocupa una conexión del dominio durante el bloque ``with`` y respeta el intervalo."""
        estado = self._estado(dominio)
        estado.semaforo.acquire()  # Si ya hay ``max_conexiones`` en uso, este hilo espera aquí.
        try:
            if self._aplicar_intervalo:
                self._esperar_intervalo(estado)
            yield
        finally:
            # ``finally`` garantiza liberar la conexión aunque la solicitud lance una excepción
            # (timeout, error HTTP...). Si no se liberara, el dominio perdería una conexión para
            # siempre y, tras varios errores, el pipeline se quedaría colgado esperando.
            estado.semaforo.release()
