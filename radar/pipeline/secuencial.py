"""Modo 1 · Secuencial: un solo hilo, un juego y una fuente a la vez (sección 7 del enunciado).

Es la LÍNEA BASE contra la que se calcula el speedup absoluto: ``S_abs(p) = T_sec / T_par(p)``.

Por qué no reutiliza el orquestador concurrente con 1 worker: eso mediría ``T_par(1)``, que incluye
el costo de crear hilos, poner y sacar de colas y sincronizar. El enunciado pide reportar ambos y
explicar su diferencia (``T_par(1) − T_sec`` = costo del andamiaje paralelo, pregunta 6). Por eso
aquí no hay hilos, colas ni locks en el camino principal: solo bucles que llaman a los mismos pasos
de ``pasos.py`` que usan los otros modos.

(El medidor y el registro de errores sí usan locks internamente, pero sin otros hilos nunca hay
espera: tomar un lock libre cuesta del orden de decenas de nanosegundos.)
"""

from __future__ import annotations

from radar.pipeline.medicion import MedidorEtapas
from radar.pipeline.modelos import DefinicionPipeline, ResultadoEjecucion, ResultadoFuente
from radar.pipeline.pasos import (
    Deduplicador,
    RegistroErrores,
    armar_paquete,
    listar_paginas,
    paso_descargar,
    paso_descubrir,
    paso_emparejar,
    paso_parsear,
    paso_persistir,
    paso_publicar,
    paso_tareas,
)


def ejecutar_secuencial(definicion: DefinicionPipeline) -> ResultadoEjecucion:
    """Ejecuta el pipeline completo en el hilo actual."""
    medidor = MedidorEtapas()  # Desde aquí corre el reloj de la ejecución.
    registro = RegistroErrores()
    deduplicador = Deduplicador()
    persistidos = 0

    with medidor.medir("descubrir", elementos=0):
        paginas = listar_paginas(definicion, registro)

    for pagina in paginas:
        with medidor.medir("descubrir"):
            juegos = paso_descubrir(definicion, pagina, registro)

        for juego in juegos:
            if not deduplicador.es_nuevo(juego.clave):
                continue
            with medidor.medir("descubrir", elementos=0):
                tareas = paso_tareas(definicion, juego, registro)
            if not tareas:
                continue

            # Una fuente a la vez: descargar y parsear cada tarea antes de pasar a la siguiente.
            resultados: list[ResultadoFuente] = []
            for tarea in tareas:
                with medidor.medir("descargar"):
                    descarga = paso_descargar(definicion, tarea, registro)
                with medidor.medir("parsear"):
                    resultados.append(paso_parsear(definicion, descarga, registro))

            paquete = armar_paquete(juego, resultados)
            with medidor.medir("emparejar"):
                exito, resultado = paso_emparejar(definicion, paquete, registro)
            if not exito:
                continue
            with medidor.medir("persistir"):
                if paso_persistir(definicion, juego.clave, resultado, registro):
                    persistidos += 1

    with medidor.medir("publicar"):
        paso_publicar(definicion, registro)

    return ResultadoEjecucion(
        modo="secuencial",
        duracion_total_s=medidor.transcurrido(),
        etapas=medidor.estadisticas(),
        juegos_persistidos=persistidos,
        fallidos=registro.fallidos,
        errores=registro.errores,
    )
