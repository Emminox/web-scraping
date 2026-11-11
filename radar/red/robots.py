"""Consulta y respeta el archivo robots.txt de cada sitio (scraping responsable, sección 10).

robots.txt es el archivo donde un sitio indica qué rutas no deben visitar los programas
automáticos. Antes de descargar cualquier URL preguntamos aquí si está permitida para nuestro
User-Agent. El archivo de cada sitio se descarga UNA sola vez por ejecución y se guarda en memoria.
"""

from __future__ import annotations

import threading
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

    def __init__(self, descargar: Callable[[str], Respuesta], agente: str) -> None:
        """
        :param descargar: función que hace GET a una URL. El cliente le pasa una que ya respeta
            el límite por dominio, para que pedir robots.txt también cuente como solicitud.
        :param agente: nombre con el que nos identificamos ante las reglas de robots.txt.
        """
        self._descargar = descargar
        self._agente = agente
        # origen -> reglas ya interpretadas.
        self._reglas: dict[str, RobotFileParser] = {}
        # Un lock por origen, para que dos hilos no descarguen el robots.txt del mismo sitio a la vez,
        # pero sin bloquear a los hilos que consultan otros sitios.
        self._locks_por_origen: dict[str, threading.Lock] = {}
        self._lock_registro = threading.Lock()

    def _lock_de(self, origen: str) -> threading.Lock:
        """Devuelve (creándolo si hace falta) el lock de un origen. Mismo patrón que en el limitador."""
        with self._lock_registro:
            return self._locks_por_origen.setdefault(origen, threading.Lock())

    def _reglas_de(self, origen: str) -> RobotFileParser:
        """Devuelve las reglas del sitio, descargándolas la primera vez que se piden."""
        with self._lock_de(origen):
            reglas = self._reglas.get(origen)
            if reglas is None:
                reglas = self._descargar_reglas(origen)
                self._reglas[origen] = reglas
            return reglas

    def _descargar_reglas(self, origen: str) -> RobotFileParser:
        """Descarga robots.txt e interpreta su contenido según el código de respuesta."""
        reglas = RobotFileParser()
        reglas.set_url(f"{origen}/robots.txt")
        try:
            respuesta = self._descargar(f"{origen}/robots.txt")
        except ErrorTemporal:
            # No pudimos saber qué permite el sitio: por prudencia no descargamos nada de él
            # en esta ejecución (mismo criterio que usan los buscadores grandes).
            reglas.disallow_all = True
            return reglas

        if respuesta.estado in (401, 403):
            # El sitio prohíbe incluso leer sus reglas: lo tomamos como "no permitido".
            reglas.disallow_all = True
        elif 400 <= respuesta.estado < 500:
            # 404 u otro 4xx: el sitio no publica robots.txt, así que no impone restricciones.
            reglas.allow_all = True
        elif respuesta.estado >= 500:
            # Error del servidor: no sabemos las reglas -> prudencia, no descargar.
            reglas.disallow_all = True
        else:
            texto = respuesta.cuerpo.decode("utf-8", errors="replace")
            # ``parse`` también marca las reglas como "leídas"; sin eso, can_fetch devolvería False.
            reglas.parse(texto.splitlines())
        return reglas

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
