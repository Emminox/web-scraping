"""Tipos de datos y excepciones que comparte toda la capa de red.

Separar las excepciones por tipo permite que el cliente decida qué hacer con cada fallo:
- ``ErrorTemporal``: vale la pena reintentar (timeout, conexión caída, HTTP 429 o 5xx).
- ``ErrorDefinitivo``: reintentar no ayuda (HTTP 404, 403...). Se registra y se sigue.
- ``BloqueadoPorRobots``: robots.txt no permite esa URL; NUNCA se descarga.
- ``SinCaptura``: en modo replay se pidió una URL que no se capturó.
- ``ReintentosAgotados``: se intentó el máximo de veces y siguió fallando; va a la cola de fallidos.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone


def ahora_utc() -> datetime:
    """Fecha y hora actual en UTC.

    Se usa UTC (y no la hora local) para que las fechas de obtención de precios sean comparables
    entre las máquinas del equipo, GitHub Actions y el sitio publicado.
    """
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Respuesta:
    """Resultado de pedir una URL, venga de la red o del almacén.

    Es inmutable (``frozen``) para poder pasarla entre hilos y etapas del pipeline sin copiarla
    ni protegerla con locks.
    """

    url: str
    # Código de estado HTTP (200, 404, 503...).
    estado: int
    # Contenido sin decodificar. Se guarda en bytes porque cada sitio usa su propia codificación;
    # decodificar es trabajo del parser de cada fuente.
    cuerpo: bytes
    # Cabeceras HTTP de la respuesta (p. ej. Content-Type, Retry-After).
    cabeceras: dict[str, str]
    # Cuándo se descargó DE VERDAD del sitio. En replay o caché conserva la fecha original:
    # así el sitio puede mostrar "precio obtenido el ..." y marcar datos desactualizados (sección 8).
    obtenida_en: datetime
    # True si salió del almacén (caché o replay) en vez de la red en este momento.
    desde_almacen: bool = False

    @property
    def ok(self) -> bool:
        """True si el estado es 2xx (éxito)."""
        return 200 <= self.estado < 300

    @property
    def tipo_contenido(self) -> str:
        """Valor de Content-Type (en minúsculas) o cadena vacía si el servidor no lo envió."""
        for nombre, valor in self.cabeceras.items():
            if nombre.lower() == "content-type":
                return valor.lower()
        return ""

    def marcada_desde_almacen(self) -> Respuesta:
        """Devuelve una copia con ``desde_almacen=True`` (la original no se modifica)."""
        return replace(self, desde_almacen=True)


class ErrorRed(Exception):
    """Clase base de todos los errores de la capa de red."""


class ErrorTemporal(ErrorRed):
    """Fallo que puede resolverse solo si se espera y se reintenta."""

    def __init__(self, mensaje: str, *, espera_sugerida: float | None = None) -> None:
        super().__init__(mensaje)
        # Segundos que el servidor pidió esperar (cabecera Retry-After), si los indicó.
        self.espera_sugerida = espera_sugerida


class ErrorDefinitivo(ErrorRed):
    """Fallo que no se arregla reintentando (p. ej. la página no existe)."""

    def __init__(self, mensaje: str, *, estado: int) -> None:
        super().__init__(mensaje)
        self.estado = estado


class BloqueadoPorRobots(ErrorRed):
    """robots.txt del sitio prohíbe descargar esta URL con nuestro User-Agent."""


class SinCaptura(ErrorRed):
    """Modo replay: no existe una respuesta guardada para esta URL."""


class ReintentosAgotados(ErrorRed):
    """Se agotaron los reintentos; la solicitud debe ir a la cola de fallidos."""

    def __init__(self, url: str, intentos: int, ultimo_error: ErrorRed) -> None:
        super().__init__(f"{url}: {intentos} intentos fallidos; último error: {ultimo_error}")
        self.url = url
        self.intentos = intentos
        self.ultimo_error = ultimo_error
