"""Consulta y respeta el archivo robots.txt de cada sitio (scraping responsable, sección 10).

robots.txt es el archivo donde un sitio indica qué rutas no deben visitar los programas
automáticos. Antes de descargar cualquier URL preguntamos aquí si está permitida para nuestro
User-Agent. El archivo de cada sitio se descarga UNA sola vez por ejecución y se guarda en memoria.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from radar.red.modelos import ErrorTemporal, Respuesta


def origen_de(url: str) -> str:
    """Devuelve ``esquema://dominio[:puerto]`` de una URL (p. ej. ``https://store.steampowered.com``)."""
    partes = urlsplit(url)
    return f"{partes.scheme}://{partes.netloc}".lower()


class VerificadorRobots:
    """Descarga, interpreta y consulta robots.txt, con una copia en memoria por sitio."""

    def __init__(self, descargar: Callable[[str], Respuesta], agente: str, *,
                 reloj: Callable[[], float] = time.monotonic, espera_tras_fallo: float = 60.0) -> None:
        """
        :param descargar: función que hace GET a una URL. El cliente le pasa una que ya respeta
            el límite por dominio, para que pedir robots.txt también cuente como solicitud.
        :param agente: nombre con el que nos identificamos ante las reglas de robots.txt.
        :param espera_tras_fallo: si robots.txt no se pudo leer por un error TEMPORAL (timeout, 5xx), el sitio
            queda bloqueado solo durante estos segundos y luego se vuelve a intentar. Antes quedaba bloqueado toda
            la ejecución: un único timeout dejaba sin precios a todo el sitio (y el reintento final de la cola de
            fallidos tampoco lo recuperaba).
        """
        self._descargar = descargar
        self._agente = agente
        self._reloj = reloj
        self._espera_tras_fallo = espera_tras_fallo
        # origen -> (reglas ya interpretadas, instante hasta el que valen). Las reglas leídas bien valen para
        # toda la ejecución (vence = infinito); las de un fallo temporal vencen a los ``espera_tras_fallo`` s.
        self._reglas: dict[str, tuple[RobotFileParser, float]] = {}
        # Un lock por origen, para que dos hilos no descarguen el robots.txt del mismo sitio a la vez,
        # pero sin bloquear a los hilos que consultan otros sitios.
        self._locks_por_origen: dict[str, threading.Lock] = {}
        self._lock_registro = threading.Lock()

    def _lock_de(self, origen: str) -> threading.Lock:
        """Devuelve (creándolo si hace falta) el lock de un origen. Mismo patrón que en el limitador."""
        with self._lock_registro:
            return self._locks_por_origen.setdefault(origen, threading.Lock())

    def _reglas_de(self, origen: str) -> RobotFileParser:
        """Devuelve las reglas del sitio, descargándolas la primera vez (o cuando vence un fallo temporal)."""
        with self._lock_de(origen):
            guardadas = self._reglas.get(origen)
            if guardadas is None or self._reloj() >= guardadas[1]:
                reglas, temporal = self._descargar_reglas(origen)
                vence = self._reloj() + self._espera_tras_fallo if temporal else float("inf")
                guardadas = (reglas, vence)
                self._reglas[origen] = guardadas
            return guardadas[0]

    def _descargar_reglas(self, origen: str) -> tuple[RobotFileParser, bool]:
        """Descarga robots.txt e interpreta su contenido. Devuelve (reglas, ¿fue un fallo temporal?)."""
        reglas = RobotFileParser()
        reglas.set_url(f"{origen}/robots.txt")
        try:
            respuesta = self._descargar(f"{origen}/robots.txt")
        except ErrorTemporal:
            # No pudimos saber qué permite el sitio: por prudencia no se descarga nada de él (mismo criterio que
            # los buscadores grandes), pero solo por un rato: es un fallo pasajero y se vuelve a intentar.
            reglas.disallow_all = True
            return reglas, True

        temporal = False
        if respuesta.estado == 429:
            # "Demasiadas solicitudes": no dice nada de las reglas. Antes caía en la rama de 4xx y se tomaba como
            # "sin robots.txt" (= todo permitido). Es un fallo pasajero: prudencia y reintentar más tarde.
            reglas.disallow_all = True
            temporal = True
        elif respuesta.estado in (401, 403):
            # El sitio prohíbe incluso leer sus reglas: lo tomamos como "no permitido" (definitivo).
            reglas.disallow_all = True
        elif 400 <= respuesta.estado < 500:
            # 404 u otro 4xx: el sitio no publica robots.txt, así que no impone restricciones.
            reglas.allow_all = True
        elif respuesta.estado >= 500:
            # Error del servidor: no sabemos las reglas -> prudencia, no descargar, y reintentar más tarde.
            reglas.disallow_all = True
            temporal = True
        else:
            texto = respuesta.cuerpo.decode("utf-8", errors="replace")
            # ``parse`` también marca las reglas como "leídas"; sin eso, can_fetch devolvería False.
            reglas.parse(texto.splitlines())
        return reglas, temporal

    def permitido(self, url: str) -> bool:
        """True si robots.txt permite descargar ``url`` con nuestro agente."""
        return self._reglas_de(origen_de(url)).can_fetch(self._agente, url)

    def retraso_sugerido(self, url: str) -> float | None:
        """Valor de ``Crawl-delay`` del sitio para nuestro agente, si lo declara.

        No se aplica automáticamente: sirve para que el equipo lo considere al fijar el intervalo
        del dominio en el ADR de límites (la herramienta de exploración lo muestra).
        """
        retraso = self._reglas_de(origen_de(url)).crawl_delay(self._agente)
        return float(retraso) if retraso is not None else None
