"""Etapas falsas (sin internet) para probar el orquestador del pipeline.

Todo es determinista: los mismos parámetros producen siempre los mismos datos, así las pruebas pueden
exigir que los tres modos den resultados idénticos. Los juegos son inventados ("juego-000"...).

``emparejar_falso`` está a nivel de módulo porque en el modo paralelo se envía a otros procesos.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from radar.pipeline import DefinicionPipeline, Descarga, Juego, PaqueteJuego, TareaDescarga
from radar.red.modelos import ErrorTemporal, ReintentosAgotados, Respuesta

# Fecha fija: si se usara la hora actual, los resultados cambiarían entre modos.
OBTENIDA = datetime(2026, 11, 11, tzinfo=timezone.utc)

# Los juegos cuya clave empieza así hacen fallar al emparejamiento (prueba de errores en otro proceso).
PREFIJO_EXPLOTA = "explota"


def emparejar_falso(paquete: PaqueteJuego) -> tuple:
    """Emparejamiento de mentira: un poco de cálculo determinista sobre los datos del juego."""
    if paquete.juego.clave.startswith(PREFIJO_EXPLOTA):
        raise ValueError(f"fallo simulado en {paquete.juego.clave}")
    huella = 0
    for resultado in paquete.resultados:
        for caracter in str(resultado.datos) + str(resultado.error):
            huella = (huella * 31 + ord(caracter)) % 1_000_003
    return (
        paquete.juego.clave,
        tuple((r.fuente, r.datos, r.error) for r in paquete.resultados),
        huella,
    )


class PipelineFalso:
    """Construye una DefinicionPipeline falsa y registra lo que pasó durante la ejecución."""

    def __init__(
        self,
        *,
        juegos: int = 12,
        fuentes: tuple[str, ...] = ("resenas", "tienda-a", "tienda-b"),
        paginas: int = 3,
        latencia: float = 0.0,
        fallar_descarga: frozenset[tuple[str, str]] = frozenset(),
        fallar_parseo: frozenset[tuple[str, str]] = frozenset(),
        sin_fuentes: frozenset[str] = frozenset(),
        claves_extra: tuple[str, ...] = (),
    ) -> None:
        self.claves = [f"juego-{numero:03d}" for numero in range(juegos)] + list(claves_extra)
        self.fuentes = fuentes
        self.cantidad_paginas = paginas
        self.latencia = latencia
        self.fallar_descarga = fallar_descarga
        self.fallar_parseo = fallar_parseo
        self.sin_fuentes = sin_fuentes
        # Lo que se observa durante la ejecución:
        self.persistidos: list[tuple] = []
        self.hilos_persistir: set[int] = set()
        self.publicaciones = 0
        self._lock = threading.Lock()
        self._descargas_activas = 0
        self.max_descargas_simultaneas = 0

    def definicion(self) -> DefinicionPipeline:
        return DefinicionPipeline(
            paginas=lambda: range(self.cantidad_paginas),
            descubrir_pagina=self._descubrir_pagina,
            fuentes_de=self._fuentes_de,
            descargar=self._descargar,
            parsear=self._parsear,
            emparejar=emparejar_falso,
            persistir=self._persistir,
            publicar=self._publicar,
        )

    def _descubrir_pagina(self, pagina: int) -> list[Juego]:
        juegos = [
            Juego(clave, clave.replace("-", " ").title())
            for numero, clave in enumerate(self.claves)
            if numero % self.cantidad_paginas == pagina
        ]
        if pagina == 1:  # El primer juego aparece repetido en otra página: debe procesarse una sola vez.
            juegos.append(Juego(self.claves[0], self.claves[0].replace("-", " ").title()))
        return juegos

    def _fuentes_de(self, juego: Juego) -> list[tuple[str, str]]:
        if juego.clave in self.sin_fuentes:
            return []
        return [(fuente, f"https://{fuente}.ejemplo/{juego.clave}") for fuente in self.fuentes]

    def _descargar(self, tarea: TareaDescarga) -> Respuesta:
        with self._lock:
            self._descargas_activas += 1
            self.max_descargas_simultaneas = max(self.max_descargas_simultaneas, self._descargas_activas)
        try:
            if self.latencia:
                time.sleep(self.latencia)  # Simula la espera de red (libera el GIL, como un socket).
            if (tarea.juego.clave, tarea.fuente) in self.fallar_descarga:
                raise ReintentosAgotados(tarea.url, 4, ErrorTemporal("HTTP 503"))
            precio = len(tarea.juego.clave) * 100 + len(tarea.fuente)
            cuerpo = f"{tarea.juego.titulo}|{tarea.fuente}|{precio}".encode()
            return Respuesta(url=tarea.url, estado=200, cuerpo=cuerpo, cabeceras={}, obtenida_en=OBTENIDA)
        finally:
            with self._lock:
                self._descargas_activas -= 1

    def _parsear(self, descarga: Descarga) -> str:
        tarea = descarga.tarea
        if (tarea.juego.clave, tarea.fuente) in self.fallar_parseo:
            raise ValueError("el HTML no tiene el formato esperado")
        return descarga.respuesta.cuerpo.decode()

    def _persistir(self, resultado: tuple) -> None:
        self.hilos_persistir.add(threading.get_ident())
        self.persistidos.append(resultado)

    def _publicar(self) -> None:
        self.publicaciones += 1
