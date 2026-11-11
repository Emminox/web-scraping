"""Transporte HTTP: la única parte del código que habla con la red de verdad.

Para qué sirve tenerlo aparte: el resto del sistema depende de la interfaz ``Transporte``, no de
urllib. Así las pruebas usan un transporte falso (sin internet) y, si el equipo decide cambiar a
``httpx`` (ver ADR-002), solo se escribe otra clase con el mismo método ``obtener``.
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from typing import Protocol

from radar.red.modelos import ErrorTemporal, Respuesta, ahora_utc


class Transporte(Protocol):
    """Interfaz mínima que debe cumplir cualquier transporte HTTP."""

    def obtener(self, url: str, cabeceras: dict[str, str], timeout: float) -> Respuesta:
        """Hace un GET a ``url`` y devuelve la respuesta (aunque sea 4xx o 5xx).

        Debe lanzar ``ErrorTemporal`` si no hubo respuesta (timeout, conexión rechazada, etc.).
        """
        ...


class TransporteUrllib:
    """Transporte basado en ``urllib.request`` de la biblioteca estándar.

    Seguro para usar desde varios hilos a la vez: no guarda estado entre llamadas y cada
    solicitud abre su propia conexión TCP (no hay pool de conexiones compartido).
    """

    def obtener(self, url: str, cabeceras: dict[str, str], timeout: float) -> Respuesta:
        solicitud = urllib.request.Request(url, headers=cabeceras, method="GET")
        try:
            # ``timeout`` aplica a CADA operación del socket (conectar, cada lectura), no al total.
            # Un servidor que envía bytes muy lentamente podría tardar más que ``timeout`` en total;
            # es una limitación conocida de urllib (documentada en el ADR-002).
            with urllib.request.urlopen(solicitud, timeout=timeout) as respuesta:
                return Respuesta(
                    url=url,
                    estado=respuesta.status,
                    cuerpo=respuesta.read(),
                    cabeceras=dict(respuesta.headers.items()),
                    obtenida_en=ahora_utc(),
                )
        except urllib.error.HTTPError as error:
            # urllib lanza excepción con 4xx/5xx, pero para nosotros eso SÍ es una respuesta:
            # el cliente decide si reintentar (429, 5xx) o no (404, 403). Por eso la convertimos.
            # Este bloque va ANTES que URLError porque HTTPError es una subclase de URLError.
            cuerpo = error.read() if error.fp is not None else b""
            return Respuesta(
                url=url,
                estado=error.code,
                cuerpo=cuerpo,
                cabeceras=dict(error.headers.items()) if error.headers else {},
                obtenida_en=ahora_utc(),
            )
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            # Sin respuesta del servidor: DNS que falla, conexión rechazada o reiniciada, timeout
            # (TimeoutError es subclase de OSError) o respuesta cortada a la mitad (IncompleteRead).
            # Todo esto puede ser pasajero, así que se marca como temporal para reintentar.
            raise ErrorTemporal(f"{url}: {type(error).__name__}: {error}") from error
