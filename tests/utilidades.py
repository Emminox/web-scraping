"""Piezas reutilizables para las pruebas: configuración de prueba y transporte falso (sin internet)."""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from pathlib import Path

from radar.config import (
    Config,
    ConfigEjecucion,
    ConfigRed,
    ConfigReplay,
    ConfigRutas,
    LimiteDominio,
)
from radar.red.modelos import ErrorTemporal, Respuesta, ahora_utc


def config_de_prueba(
    directorio: Path,
    *,
    fuente: str = "vivo",
    max_reintentos: int = 2,
    max_conexiones: int = 2,
    intervalo: float = 0.0,
    ttl_horas: float = 12.0,
    latencia_ms: int = 100,
) -> Config:
    """Configuración pequeña que guarda todo en ``directorio`` (una carpeta temporal)."""
    return Config(
        ejecucion=ConfigEjecucion(modo="secuencial", fuente=fuente),
        red=ConfigRed(
            user_agent="RadarPruebas/0.1",
            timeout_segundos=1.0,
            max_reintentos=max_reintentos,
            backoff_base_segundos=1.0,
            backoff_max_segundos=8.0,
            limite_por_defecto=LimiteDominio(max_conexiones, intervalo),
            ttl_almacen_horas=ttl_horas,
        ),
        replay=ConfigReplay(latencia_ms=latencia_ms, variacion_ms=0, semilla=1),
        rutas=ConfigRutas(capturas=directorio / "capturas", fixtures=directorio / "fixtures"),
    )


def respuesta(url: str, estado: int = 200, cuerpo: bytes = b"<html>ok</html>", **cabeceras: str) -> Respuesta:
    """Crea una respuesta falsa con Content-Type HTML."""
    todas = {"Content-Type": "text/html; charset=utf-8", **cabeceras}
    return Respuesta(url=url, estado=estado, cuerpo=cuerpo, cabeceras=todas, obtenida_en=ahora_utc())


class TransporteFalso:
    """Transporte que no usa la red: devuelve respuestas preprogramadas por URL.

    - ``programar(url, r1, r2, ...)`` encola respuestas (o excepciones) que se entregan en orden.
    - Si una URL no tiene nada programado y es robots.txt, responde 404 (= "sin restricciones").
    - ``llamadas`` registra cada URL pedida, para comprobar cuántas veces se tocó la "red".
    """

    def __init__(self) -> None:
        self._programadas: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self.llamadas: list[str] = []

    def programar(self, url: str, *resultados: Respuesta | Exception) -> None:
        self._programadas[url].extend(resultados)

    def obtener(self, url: str, cabeceras: dict[str, str], timeout: float) -> Respuesta:
        with self._lock:
            self.llamadas.append(url)
            cola = self._programadas[url]
            resultado = cola.popleft() if cola else None
        if resultado is None:
            if url.endswith("/robots.txt"):
                return respuesta(url, 404, b"")
            raise ErrorTemporal(f"Nada programado para {url}")
        if isinstance(resultado, Exception):
            raise resultado
        return resultado
