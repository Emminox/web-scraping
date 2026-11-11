"""Pasos del pipeline compartidos por los tres modos de ejecución.

Por qué existe este módulo: el enunciado exige que los modos secuencial, concurrente y paralelo
"produzcan los mismos resultados con los mismos datos". La forma más segura de lograrlo es que los
tres llamen EXACTAMENTE a estas funciones; lo único que cambia entre modos es quién las llama y
desde cuántos hilos o procesos.

Cada ``paso_*`` envuelve una función de la ``DefinicionPipeline`` y convierte sus errores en datos
(``ErrorEtapa`` o un resultado con ``error``). Así, un error en un juego nunca detiene el pipeline ni
deja una etapa esperando para siempre: el juego sigue con los datos disponibles (sección 8).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from radar.pipeline.modelos import (
    DefinicionPipeline,
    Descarga,
    ErrorEtapa,
    Juego,
    PaqueteJuego,
    ResultadoFuente,
    TareaDescarga,
)
from radar.red.modelos import ErrorRed


def describir(error: BaseException) -> str:
    """Texto corto y repetible de una excepción: 'TipoDeError: mensaje'."""
    return f"{type(error).__name__}: {error}"


class RegistroErrores:
    """Lista de errores y de descargas fallidas, compartida por todos los workers.

    Se protege con un lock aunque en CPython ``list.append`` ya es atómico gracias al GIL: eso es un
    detalle de implementación que no está garantizado (por ejemplo, en la compilación sin GIL de
    Python 3.14), y el código no debe depender de él.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._errores: list[ErrorEtapa] = []
        self._fallidos: list[Descarga] = []

    def error(self, etapa: str, clave: str, mensaje: str) -> None:
        with self._lock:
            self._errores.append(ErrorEtapa(etapa, clave, mensaje))

    def fallido(self, descarga: Descarga) -> None:
        with self._lock:
            self._fallidos.append(descarga)

    @property
    def errores(self) -> tuple[ErrorEtapa, ...]:
        with self._lock:
            return tuple(self._errores)

    @property
    def fallidos(self) -> tuple[Descarga, ...]:
        with self._lock:
            return tuple(self._fallidos)


class Deduplicador:
    """Recuerda qué juegos ya entraron al pipeline, para no procesar dos veces el mismo.

    Un mismo juego puede aparecer en dos páginas del listado (p. ej. si el ranking cambia mientras se
    recorre). Con varios workers de descubrimiento, "¿ya lo vi? si no, lo marco" debe ser UNA sola
    operación atómica: si no, dos workers podrían ver el mismo juego a la vez y ambos lo darían por nuevo.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._vistos: set[str] = set()

    def es_nuevo(self, clave: str) -> bool:
        with self._lock:
            if clave in self._vistos:
                return False
            self._vistos.add(clave)
            return True


# ---------------------------------------------------------------------------
# Etapa 0: descubrir
# ---------------------------------------------------------------------------


def listar_paginas(definicion: DefinicionPipeline, registro: RegistroErrores) -> list[Any]:
    """Obtiene la lista de páginas del listado público."""
    try:
        return list(definicion.paginas())
    except Exception as error:
        registro.error("descubrir", "-", f"no se pudieron listar las páginas: {describir(error)}")
        return []


def paso_descubrir(definicion: DefinicionPipeline, pagina: Any, registro: RegistroErrores) -> list[Juego]:
    """Juegos de una página. Si la página falla, se registra y se sigue con las demás."""
    try:
        return list(definicion.descubrir_pagina(pagina))
    except Exception as error:
        registro.error("descubrir", f"página {pagina}", describir(error))
        return []


def paso_tareas(definicion: DefinicionPipeline, juego: Juego, registro: RegistroErrores) -> list[TareaDescarga]:
    """Divide un juego en una tarea de descarga por cada fuente (paralelismo "por fuente")."""
    try:
        fuentes = list(definicion.fuentes_de(juego))
    except Exception as error:
        registro.error("descubrir", juego.clave, f"no se pudieron obtener sus fuentes: {describir(error)}")
        return []
    if not fuentes:
        registro.error("descubrir", juego.clave, "el juego no tiene fuentes para consultar")
        return []
    nombres = [fuente for fuente, _ in fuentes]
    if len(nombres) != len(set(nombres)):
        # Dos tareas con la misma fuente romperían el orden estable de PaqueteJuego.
        registro.error("descubrir", juego.clave, f"fuentes repetidas: {sorted(nombres)}")
        return []
    total = len(fuentes)
    return [TareaDescarga(juego, fuente, url, total) for fuente, url in fuentes]


# ---------------------------------------------------------------------------
# Etapas 1 y 2: descargar y parsear
# ---------------------------------------------------------------------------


def paso_descargar(definicion: DefinicionPipeline, tarea: TareaDescarga, registro: RegistroErrores) -> Descarga:
    """Descarga una fuente. Nunca lanza excepciones: un fallo se devuelve como ``Descarga`` con error."""
    try:
        return Descarga(tarea, definicion.descargar(tarea))
    except ErrorRed as error:
        # Fallo esperable de red (timeout, bloqueo, reintentos agotados...): va a la cola de fallidos.
        descarga = Descarga(tarea, None, describir(error))
        registro.fallido(descarga)
        return descarga
    except Exception as error:
        # Error inesperado (un bug): se registra aparte para que se note y se corrija.
        registro.error("descargar", tarea.juego.clave, f"{tarea.fuente}: {describir(error)}")
        return Descarga(tarea, None, f"error inesperado: {describir(error)}")


def paso_parsear(definicion: DefinicionPipeline, descarga: Descarga, registro: RegistroErrores) -> ResultadoFuente:
    """Extrae los datos de una descarga. Si la descarga falló, propaga el error sin llamar al parser."""
    tarea = descarga.tarea
    if descarga.error is not None:
        return ResultadoFuente(tarea.juego, tarea.fuente, tarea.total_fuentes, error=descarga.error)
    try:
        datos = definicion.parsear(descarga)
    except Exception as error:
        # Típico cuando un sitio cambia su HTML sin aviso (sección 10).
        registro.error("parsear", tarea.juego.clave, f"{tarea.fuente}: {describir(error)}")
        return ResultadoFuente(
            tarea.juego, tarea.fuente, tarea.total_fuentes, error=f"error de parseo: {describir(error)}"
        )
    return ResultadoFuente(tarea.juego, tarea.fuente, tarea.total_fuentes, datos=datos)


# ---------------------------------------------------------------------------
# Etapa 3: emparejar
# ---------------------------------------------------------------------------


def armar_paquete(juego: Juego, resultados: list[ResultadoFuente]) -> PaqueteJuego:
    """Junta los resultados de un juego ORDENADOS por fuente (clave del determinismo, ver PaqueteJuego)."""
    return PaqueteJuego(juego, tuple(sorted(resultados, key=lambda resultado: resultado.fuente)))


class AgrupadorPorJuego:
    """Junta los ResultadoFuente que van llegando hasta tener todos los de un juego.

    Lo usa UN solo hilo (el despachador de la etapa Emparejar, o el bucle del modo secuencial), por eso
    no necesita lock. Si algún día lo usaran varios hilos, habría que protegerlo.
    """

    def __init__(self) -> None:
        self._grupos: dict[str, list[ResultadoFuente]] = {}

    def agregar(self, resultado: ResultadoFuente) -> PaqueteJuego | None:
        """Agrega un resultado; devuelve el paquete del juego si con este ya están todas sus fuentes."""
        grupo = self._grupos.setdefault(resultado.juego.clave, [])
        grupo.append(resultado)
        if len(grupo) < resultado.total_fuentes:
            return None
        del self._grupos[resultado.juego.clave]
        return armar_paquete(resultado.juego, grupo)

    def incompletos(self) -> list[PaqueteJuego]:
        """Paquetes de juegos a los que les faltan resultados (no debería pasar; indica un bug)."""
        paquetes = [armar_paquete(grupo[0].juego, grupo) for grupo in self._grupos.values()]
        self._grupos.clear()
        return sorted(paquetes, key=lambda paquete: paquete.juego.clave)


def paso_emparejar(
    definicion: DefinicionPipeline, paquete: PaqueteJuego, registro: RegistroErrores
) -> tuple[bool, Any]:
    """Empareja un juego en el hilo actual. Devuelve (True, resultado) o (False, None) si falló."""
    try:
        return True, definicion.emparejar(paquete)
    except Exception as error:
        registro.error("emparejar", paquete.juego.clave, describir(error))
        return False, None


def emparejar_medido(emparejar: Callable[[PaqueteJuego], Any], paquete: PaqueteJuego) -> tuple[Any, float]:
    """Ejecuta ``emparejar`` y devuelve (resultado, segundos de trabajo).

    Se usa en el modo paralelo: corre DENTRO del proceso (o hilo) trabajador, así se mide solo el tiempo
    de cálculo, sin la espera en la cola del ejecutor. Está definida a nivel de módulo porque
    ProcessPoolExecutor solo puede enviar a otro proceso funciones que pickle sepa ubicar por nombre.
    """
    inicio = time.perf_counter()
    resultado = emparejar(paquete)
    return resultado, time.perf_counter() - inicio


# ---------------------------------------------------------------------------
# Etapas 4 y 5: persistir y publicar
# ---------------------------------------------------------------------------


def paso_persistir(definicion: DefinicionPipeline, clave: str, resultado: Any, registro: RegistroErrores) -> bool:
    """Guarda el resultado de un juego. Devuelve True si se guardó."""
    try:
        definicion.persistir(resultado)
        return True
    except Exception as error:
        registro.error("persistir", clave, describir(error))
        return False


def paso_publicar(definicion: DefinicionPipeline, registro: RegistroErrores) -> None:
    """Genera el sitio con lo que haya en la base."""
    try:
        definicion.publicar()
    except Exception as error:
        registro.error("publicar", "-", describir(error))
