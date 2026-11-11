"""Pipeline del Radar de Ofertas: seis etapas conectadas por colas acotadas (sección 6 del enunciado).

- ``modelos.py``     -> datos que viajan entre etapas y el resumen de una ejecución.
- ``pasos.py``       -> lo que hace cada etapa; lo comparten los tres modos (mismos resultados).
- ``secuencial.py``  -> modo 1: un solo hilo, sin colas (línea base T_sec).
- ``concurrente.py`` -> modos 2 y 3: hilos para la E/S y, en el 3, procesos para el emparejamiento.
- ``medicion.py``    -> tiempos por etapa.

Uso::

    resultado = ejecutar_pipeline(definicion, config.ejecucion.modo, config.pipeline)

El diseño completo, con diagrama, está en docs/pipeline.md.
"""

from radar.config import MODOS_VALIDOS, ConfigPipeline
from radar.pipeline.concurrente import ejecutar_concurrente
from radar.pipeline.modelos import (
    ETAPAS,
    DefinicionPipeline,
    Descarga,
    ErrorEtapa,
    EstadisticaEtapa,
    Juego,
    PaqueteJuego,
    ResultadoEjecucion,
    ResultadoFuente,
    TareaDescarga,
)
from radar.pipeline.secuencial import ejecutar_secuencial


def ejecutar_pipeline(definicion: DefinicionPipeline, modo: str, config: ConfigPipeline) -> ResultadoEjecucion:
    """Ejecuta el pipeline en el ``modo`` indicado ("secuencial", "concurrente" o "paralelo").

    El modo sale de la configuración (``[ejecucion] modo``): cambiar de modo no requiere tocar el código.
    """
    if modo == "secuencial":
        return ejecutar_secuencial(definicion)
    if modo == "concurrente":
        return ejecutar_concurrente(definicion, config, paralelo=False)
    if modo == "paralelo":
        return ejecutar_concurrente(definicion, config, paralelo=True)
    raise ValueError(f"Modo desconocido {modo!r}; use uno de {MODOS_VALIDOS}")


__all__ = [
    "ETAPAS",
    "DefinicionPipeline",
    "Descarga",
    "ErrorEtapa",
    "EstadisticaEtapa",
    "Juego",
    "PaqueteJuego",
    "ResultadoEjecucion",
    "ResultadoFuente",
    "TareaDescarga",
    "ejecutar_pipeline",
]
