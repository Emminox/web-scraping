"""Modos 2 (concurrente) y 3 (paralelo): etapas conectadas por colas acotadas (secciones 6 y 7).

Estructura (ver el diagrama en docs/pipeline.md)::

    orquestador ─páginas─▶ [Descubrir ×W0] ─cola_tareas─▶ [Descargar ×W1] ─cola_descargas─▶
    [Parsear ×1] ─cola_resultados─▶ [Despachador de Emparejar ×1 (+ ejecutor ×W3 en modo paralelo)]
    ─cola_persistir─▶ [Persistir ×1] ─▶ (al final) Publicar

Diferencia entre modos:
- **concurrente**: Descubrir y Descargar con varios hilos (E/S); el resto con un solo hilo. El
  despachador empareja él mismo, en su hilo.
- **paralelo**: igual, pero el despachador envía cada juego a un ``ProcessPoolExecutor`` (o
  ``ThreadPoolExecutor`` si ``ejecutor_emparejar = "hilos"``, para la comparación de la pregunta 5).

Por qué hilos para la E/S: mientras un hilo espera la red, ``socket.recv`` y ``time.sleep`` liberan el
GIL y otro hilo avanza. Por eso esa etapa escala con más workers que núcleos (concurrencia).
Por qué procesos para el emparejamiento: es cálculo puro en Python; con hilos el GIL deja ejecutar
solo uno a la vez. Cada proceso tiene su propio intérprete y su propio GIL (paralelismo real).
"""

from __future__ import annotations

import pickle
import queue
import threading
from collections.abc import Callable
from concurrent.futures import (
    ALL_COMPLETED,
    FIRST_COMPLETED,
    Executor,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from typing import Any

from radar.config import ConfigPipeline
from radar.pipeline.medicion import MedidorEtapas
from radar.pipeline.modelos import DefinicionPipeline, Descarga, PaqueteJuego, ResultadoEjecucion, TareaDescarga
from radar.pipeline.pasos import (
    AgrupadorPorJuego,
    Deduplicador,
    RegistroErrores,
    describir,
    emparejar_medido,
    listar_paginas,
    paso_descargar,
    paso_descubrir,
    paso_emparejar,
    paso_parsear,
    paso_persistir,
    paso_publicar,
    paso_tareas,
)

# Centinela ("poison pill"): un objeto único que significa "no vendrán más elementos, termina".
# Se usa ``object()`` porque no puede confundirse con ningún dato real (ni siquiera con None).
FIN = object()


def _consumir(cola: queue.Queue, procesar: Callable[[Any], None], registro: RegistroErrores, etapa: str) -> None:
    """Bucle de un worker: saca elementos de ``cola`` y los procesa hasta recibir el centinela FIN.

    ``procesar`` usa los pasos de pasos.py, que ya convierten los errores esperables en datos. El
    try/except de aquí es una segunda red de seguridad para bugs: si un elemento hace fallar al worker,
    se registra y el worker SIGUE consumiendo. Si el hilo muriera, nadie sacaría elementos de esta
    cola, la etapa anterior se bloquearía al llenarla y el pipeline completo quedaría colgado.
    """
    while True:
        elemento = cola.get()
        if elemento is FIN:
            return
        try:
            procesar(elemento)
        except Exception as error:
            registro.error(etapa, "-", f"error interno del worker: {describir(error)}")


def _iniciar(nombre: str, cantidad: int, objetivo: Callable[[], None]) -> list[threading.Thread]:
    """Crea y arranca ``cantidad`` hilos que ejecutan ``objetivo``.

    ``daemon=True``: si por un bug el programa principal termina con hilos aún vivos, estos no impiden
    que el proceso se cierre (en un pipeline sano todos terminan antes por el centinela).
    """
    hilos = [threading.Thread(target=objetivo, name=f"{nombre}-{numero}", daemon=True) for numero in range(cantidad)]
    for hilo in hilos:
        hilo.start()
    return hilos


def _cerrar(cola: queue.Queue, hilos: list[threading.Thread]) -> None:
    """Avisa a los consumidores de ``cola`` que terminen, y espera a que lo hagan.

    Se pone UN centinela por cada hilo consumidor: cada worker que recibe FIN termina sin devolverlo a
    la cola, así que con menos centinelas que hilos, alguno se quedaría esperando en ``get()`` para
    siempre y ``join()`` no regresaría nunca.
    """
    for _ in hilos:
        cola.put(FIN)
    for hilo in hilos:
        hilo.join()


def _crear_ejecutor(config: ConfigPipeline) -> Executor:
    """Pool de trabajadores del emparejamiento (solo modo paralelo)."""
    if config.ejecutor_emparejar == "procesos":
        return ProcessPoolExecutor(max_workers=config.workers_emparejar)
    return ThreadPoolExecutor(max_workers=config.workers_emparejar, thread_name_prefix="emparejar")


def ejecutar_concurrente(
    definicion: DefinicionPipeline, config: ConfigPipeline, *, paralelo: bool
) -> ResultadoEjecucion:
    """Ejecuta el pipeline con colas acotadas entre etapas.

    :param paralelo: False = modo 2 (concurrente); True = modo 3 (emparejamiento repartido entre núcleos).
    """
    if paralelo and config.ejecutor_emparejar == "procesos":
        # Se comprueba ANTES de empezar: si ``emparejar`` no se puede enviar a otro proceso (p. ej. es
        # una lambda), cada juego fallaría por separado con un error confuso.
        try:
            pickle.dumps(definicion.emparejar)
        except Exception as error:
            raise ValueError(
                "En modo paralelo con procesos, 'emparejar' debe ser una función definida a nivel de "
                f"módulo (no una lambda ni una función interna): {describir(error)}"
            ) from error

    # Desde aquí corre el reloj de la ejecución: el tiempo total incluye crear hilos y pools, que es
    # parte del costo del andamiaje paralelo (T_par(1) − T_sec).
    medidor = MedidorEtapas()
    registro = RegistroErrores()
    deduplicador = Deduplicador()

    # Colas ACOTADAS (maxsize). Si una etapa produce más rápido de lo que la siguiente consume, la cola
    # se llena y ``put()`` bloquea al productor hasta que haya espacio (contrapresión). Sin límite, una
    # etapa rápida acumularía miles de elementos en memoria delante de una lenta.
    cola_paginas: queue.Queue = queue.Queue(maxsize=2 * config.workers_descubrir)
    cola_tareas: queue.Queue = queue.Queue(maxsize=config.cola_tareas)
    cola_descargas: queue.Queue = queue.Queue(maxsize=config.cola_descargas)
    cola_resultados: queue.Queue = queue.Queue(maxsize=config.cola_resultados)
    cola_persistir: queue.Queue = queue.Queue(maxsize=config.cola_persistir)

    # Contador que SOLO modifica el hilo de persistir: no necesita lock. Se lee después de join(), que
    # garantiza que el orquestador ve el valor final escrito por ese hilo.
    persistidos = 0

    # ----- Trabajo de cada etapa -------------------------------------------------------------------
    # Regla en todas: se MIDE solo el trabajo, no el ``put()``. El tiempo bloqueado esperando espacio
    # en la cola siguiente no es trabajo de la etapa, es contrapresión de la etapa de después.

    def descubrir(pagina: Any) -> None:
        tareas: list[TareaDescarga] = []
        with medidor.medir("descubrir"):
            for juego in paso_descubrir(definicion, pagina, registro):
                if deduplicador.es_nuevo(juego.clave):
                    tareas.extend(paso_tareas(definicion, juego, registro))
        for tarea in tareas:
            cola_tareas.put(tarea)

    def descargar(tarea: TareaDescarga) -> None:
        with medidor.medir("descargar"):
            descarga = paso_descargar(definicion, tarea, registro)
        cola_descargas.put(descarga)

    def parsear(descarga: Descarga) -> None:
        with medidor.medir("parsear"):
            resultado = paso_parsear(definicion, descarga, registro)
        cola_resultados.put(resultado)

    def persistir(elemento: tuple[str, Any]) -> None:
        nonlocal persistidos
        clave, resultado = elemento
        with medidor.medir("persistir"):
            guardado = paso_persistir(definicion, clave, resultado, registro)
        if guardado:
            persistidos += 1

    def despachar() -> None:
        """Etapa 3. Junta los resultados de cada juego y, cuando están todos, lo empareja.

        Es UN solo hilo, así que el agrupador no necesita lock. En modo paralelo no empareja él mismo:
        envía el paquete al ejecutor y recoge los resultados.
        """
        agrupador = AgrupadorPorJuego()
        ejecutor: Executor | None = None
        if paralelo:
            try:
                ejecutor = _crear_ejecutor(config)
            except Exception as error:  # Si no se pudo crear el pool, se empareja en este hilo.
                registro.error("emparejar", "-", f"no se pudo crear el ejecutor: {describir(error)}")

        # Futuros en curso: futuro -> (clave del juego, instante de envío).
        pendientes: dict[Future, tuple[str, float]] = {}
        # Máximo de juegos enviados al ejecutor sin recoger. Sin este tope, ``submit`` aceptaría todos
        # los juegos de golpe (la cola interna del ejecutor no tiene límite) y se perdería la
        # contrapresión: el doble de workers basta para que ninguno se quede sin trabajo.
        maximo_pendientes = 2 * config.workers_emparejar

        def recoger(cuando: str) -> None:
            # Los resultados se recogen en ESTE hilo (y no con callbacks del futuro) a propósito: los
            # callbacks corren en un hilo interno del ejecutor, y si ese hilo se bloqueara en
            # ``cola_persistir.put()`` con la cola llena, el ejecutor dejaría de procesar.
            listos, _ = wait(pendientes, return_when=cuando)
            for futuro in listos:
                clave, enviado = pendientes.pop(futuro)
                try:
                    resultado, duracion = futuro.result()
                except Exception as error:  # La excepción del proceso hijo llega aquí.
                    registro.error("emparejar", clave, describir(error))
                    continue
                medidor.registrar("emparejar", enviado, medidor.ahora(), ocupado=duracion)
                cola_persistir.put((clave, resultado))

        def entregar(paquete: PaqueteJuego) -> None:
            clave = paquete.juego.clave
            if ejecutor is None:  # Modo concurrente: se empareja en este mismo hilo.
                with medidor.medir("emparejar"):
                    exito, resultado = paso_emparejar(definicion, paquete, registro)
                if exito:
                    cola_persistir.put((clave, resultado))
                return
            futuro = ejecutor.submit(emparejar_medido, definicion.emparejar, paquete)
            pendientes[futuro] = (clave, medidor.ahora())
            if len(pendientes) >= maximo_pendientes:
                recoger(FIRST_COMPLETED)  # Espera a que termine al menos uno antes de enviar más.

        try:
            while True:
                elemento = cola_resultados.get()
                if elemento is FIN:
                    break
                try:
                    paquete = agrupador.agregar(elemento)
                    if paquete is not None:
                        entregar(paquete)
                except Exception as error:  # Red de seguridad: este hilo NUNCA debe dejar de consumir.
                    registro.error("emparejar", "-", f"error interno del despachador: {describir(error)}")
            # Juegos a los que les faltan resultados: indica un bug, pero se publican con lo disponible.
            for paquete in agrupador.incompletos():
                registro.error("emparejar", paquete.juego.clave, "llegaron menos resultados de los esperados")
                entregar(paquete)
            if pendientes:
                recoger(ALL_COMPLETED)
        finally:
            if ejecutor is not None:
                ejecutor.shutdown(wait=True)  # Espera a que terminen los procesos antes de seguir.

    # ----- Arranque ---------------------------------------------------------------------------------
    # Se arrancan TODAS las etapas a la vez: así trabajan en paralelo como en un procesador segmentado
    # (mientras un juego se descarga, otro se parsea y otro se empareja).
    hilos_descubrir = _iniciar(
        "descubrir", config.workers_descubrir, lambda: _consumir(cola_paginas, descubrir, registro, "descubrir")
    )
    hilos_descargar = _iniciar(
        "descargar", config.workers_descargar, lambda: _consumir(cola_tareas, descargar, registro, "descargar")
    )
    # Parsear y Persistir tienen 1 hilo: el enunciado pide que en el modo concurrente "el resto" sea
    # secuencial, y Persistir es el único escritor de la base (ADR-003).
    hilos_parsear = _iniciar("parsear", 1, lambda: _consumir(cola_descargas, parsear, registro, "parsear"))
    hilo_despachar = _iniciar("emparejar", 1, despachar)
    hilo_persistir = _iniciar("persistir", 1, lambda: _consumir(cola_persistir, persistir, registro, "persistir"))

    with medidor.medir("descubrir", elementos=0):
        paginas = listar_paginas(definicion, registro)
    for pagina in paginas:
        cola_paginas.put(pagina)

    # ----- Apagado ordenado -------------------------------------------------------------------------
    # Se cierra etapa por etapa, de la primera a la última. Cuando TODOS los workers de una etapa
    # terminaron, es seguro que no entrará nada más a la cola siguiente; recién entonces se ponen allí
    # los centinelas. Como la cola es FIFO, los centinelas quedan DETRÁS de todos los datos reales: los
    # consumidores procesan todo antes de recibir FIN. Si se cerrara una etapa antes de que terminara
    # la anterior, se perderían elementos que llegaran después del centinela.
    _cerrar(cola_paginas, hilos_descubrir)
    _cerrar(cola_tareas, hilos_descargar)
    _cerrar(cola_descargas, hilos_parsear)
    _cerrar(cola_resultados, hilo_despachar)
    _cerrar(cola_persistir, hilo_persistir)

    # Publicar va al final y una sola vez: necesita que todo esté persistido.
    with medidor.medir("publicar"):
        paso_publicar(definicion, registro)

    return ResultadoEjecucion(
        modo="paralelo" if paralelo else "concurrente",
        duracion_total_s=medidor.transcurrido(),
        etapas=medidor.estadisticas(),
        juegos_persistidos=persistidos,
        fallidos=registro.fallidos,
        errores=registro.errores,
    )
