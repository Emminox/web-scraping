"""Cliente HTTP del proyecto: el único punto por el que se piden páginas.

Combina todas las piezas de ``radar.red`` y aplica las reglas del enunciado en este orden:

Modo vivo::

    ¿hay copia fresca en el almacén? --sí--> devolverla (caché, sin tocar la red)
              |no
    ¿robots.txt lo permite? --no--> BloqueadoPorRobots (nunca se descarga)
              |sí
    repetir hasta max_reintentos:
        pedir turno al limitador del dominio -> descargar con timeout
        2xx           -> guardar en el almacén y devolver
        429 / 5xx / sin respuesta -> esperar (backoff + jitter o Retry-After) y reintentar
        429/503 con Retry-After > backoff máximo -> pausar el dominio y DominioEnPausa (sin reintentar)
        otro 4xx      -> ErrorDefinitivo (reintentar no sirve)
    si se agotan -> ReintentosAgotados (va a la cola de fallidos del pipeline)

Modo replay::

    leer del almacén -> si no está: SinCaptura
    ocupar el turno del dominio y esperar la latencia simulada -> devolver la captura

En ambos modos el resto del pipeline llama al mismo método ``obtener``: es lo que exige la sección 11
("mismo código en replay y en vivo; solo cambia la fuente de los datos").
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from urllib.parse import urlsplit

from radar.config import Config
from radar.red.almacen import AlmacenCapturas
from radar.red.limitador import LimitadorPorDominio
from radar.red.metricas import MetricasRed
from radar.red.modelos import (
    BloqueadoPorRobots,
    DominioEnPausa,
    ErrorDefinitivo,
    ErrorRed,
    ErrorTemporal,
    ReintentosAgotados,
    Respuesta,
    SinCaptura,
    ahora_utc,
)
from radar.red.reintentos import calcular_espera, leer_retry_after
from radar.red.robots import VerificadorRobots
from radar.red.transporte import Transporte, TransporteUrllib


def dominio_de(url: str) -> str:
    """Nombre de dominio de una URL en minúsculas (p. ej. ``store.steampowered.com``)."""
    return (urlsplit(url).hostname or "").lower()


class ClienteHttp:
    """Obtiene páginas respetando robots.txt, límites por dominio, timeouts y reintentos.

    Una sola instancia se comparte entre todos los hilos del pipeline: así todos usan los mismos
    semáforos por dominio y los mismos contadores. Todas sus partes internas son seguras para hilos.
    """

    def __init__(
        self,
        config: Config,
        *,
        transporte: Transporte | None = None,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        :param config: configuración cargada con ``radar.config.cargar_config``.
        :param transporte: quién hace la solicitud real; las pruebas pasan uno falso.
        :param dormir: función de espera; las pruebas pasan una que no espera de verdad.
        :param reloj: reloj monotónico para el limitador (inyectable por las mismas razones).
        """
        self._config = config
        self._modo_replay = config.ejecucion.fuente == "replay"
        self._transporte = transporte if transporte is not None else TransporteUrllib()
        self._dormir = dormir
        self._reloj = reloj
        # dominio -> instante (reloj monotónico) hasta el que el sitio nos pidió no volver. Protegido por un lock
        # porque lo leen y escriben todos los hilos de descarga.
        self._pausas: dict[str, float] = {}
        self._lock_pausas = threading.Lock()
        self.almacen = AlmacenCapturas(config.rutas.capturas)
        self.metricas = MetricasRed()
        # En replay no hay sitio real que cuidar: se quita el intervalo de cortesía, pero el semáforo
        # de conexiones por dominio se mantiene porque forma parte del diseño que se está midiendo.
        self._limitador = LimitadorPorDominio(
            config.red, aplicar_intervalo=not self._modo_replay, reloj=reloj, dormir=dormir
        )
        self._robots = VerificadorRobots(self._descargar_robots, config.red.user_agent)
        # Un candado por URL (ver ``obtener``). Son pocos miles por ejecución: no hace falta liberarlos.
        self._candados_url: dict[str, threading.Lock] = {}
        self._lock_candados = threading.Lock()
        # Generador aleatorio propio con semilla: hace repetibles el jitter y la latencia simulada.
        self._aleatorio = random.Random(config.replay.semilla)
        # Cabeceras que se envían en TODAS las solicitudes.
        self._cabeceras = {
            # Identificación honesta del cliente (sección 10).
            "User-Agent": config.red.user_agent,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            # Se piden páginas en inglés de EE. UU. para que los precios vengan en USD en todas las
            # tiendas y sean comparables entre sí. (El ADR de fuentes debe confirmarlo por sitio.)
            "Accept-Language": "en-US,en;q=0.8",
        }

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def obtener(self, url: str, *, usar_almacen: bool = True) -> Respuesta:
        """Devuelve la respuesta de ``url`` según el modo configurado (vivo o replay).

        :param usar_almacen: solo en modo vivo; ``False`` obliga a descargar aunque haya copia fresca
            (lo usa la herramienta de exploración de fuentes).
        :raises BloqueadoPorRobots, ErrorDefinitivo, ReintentosAgotados, SinCaptura:
            ver ``radar.red.modelos``.
        """
        dominio = dominio_de(url)
        if self._modo_replay:
            return self._obtener_replay(url, dominio)
        if not usar_almacen:
            return self._descargar_permitida(url, dominio)

        # Una sola descarga por URL a la vez. Sin esto, dos tareas con la misma URL (p. ej. la búsqueda de Best Buy
        # de un juego que sale en PS5, Xbox y Switch) veían la caché vacía al mismo tiempo y descargaban lo mismo
        # dos o tres veces, justo en el sitio más lento. Con el candado de la URL, la segunda espera y luego
        # encuentra la copia fresca que dejó la primera.
        # Orden de candados: primero el de la URL y, adentro, el semáforo del dominio; nunca al revés -> no hay
        # interbloqueo posible.
        with self._candado_de_url(url):
            guardada = self.almacen.leer(url)
            if guardada is not None and self._es_fresca(guardada):
                self.metricas.registrar(dominio, "desde_almacen")
                return guardada
            return self._descargar_permitida(url, dominio)

    def _candado_de_url(self, url: str) -> threading.Lock:
        """Candado de una URL (se crea la primera vez; mismo patrón "comprobar y crear" protegido que el limitador)."""
        with self._lock_candados:
            return self._candados_url.setdefault(url, threading.Lock())

    def _descargar_permitida(self, url: str, dominio: str) -> Respuesta:
        """Descarga ``url`` si robots.txt lo permite (con reintentos)."""
        # La pausa se revisa ANTES que robots.txt: si el sitio pidió esperar, tampoco se le pide robots.txt.
        self._revisar_pausa(dominio)
        if not self._robots.permitido(url):
            self.metricas.registrar(dominio, "bloqueadas_robots")
            raise BloqueadoPorRobots(f"robots.txt no permite descargar {url}")
        return self._descargar_con_reintentos(url, dominio)

    # ------------------------------------------------------------------
    # Pausas pedidas por el sitio (Retry-After largo)
    # ------------------------------------------------------------------

    def _pausa_restante(self, dominio: str) -> float:
        with self._lock_pausas:
            hasta = self._pausas.get(dominio, 0.0)
        return max(0.0, hasta - self._reloj())

    def _revisar_pausa(self, dominio: str) -> None:
        """Lanza ``DominioEnPausa`` si el sitio pidió esperar y todavía no pasó ese tiempo."""
        restante = self._pausa_restante(dominio)
        if restante > 0:
            self.metricas.registrar(dominio, "fallidas")
            raise DominioEnPausa(dominio, restante)

    def _pausar(self, dominio: str, segundos: float) -> None:
        """Pausa ``dominio`` durante ``segundos``. Si ya había una pausa más larga, se conserva (``max``)."""
        with self._lock_pausas:
            self._pausas[dominio] = max(self._pausas.get(dominio, 0.0), self._reloj() + segundos)
        self.metricas.registrar(dominio, "pausas")

    def pausas_pendientes(self) -> dict[str, float]:
        """Dominios en pausa ahora mismo -> segundos que faltan."""
        with self._lock_pausas:
            dominios = list(self._pausas)
        return {d: r for d in dominios if (r := self._pausa_restante(d)) > 0}

    def esperar_pausas(self) -> float:
        """Espera a que terminen las pausas (si la más larga no pasa de ``pausa_maxima_segundos``).

        Lo usa el reintento final de la cola de fallidos: sin esperar, las tareas de un dominio en pausa volverían
        a fallar al instante. Devuelve los segundos esperados (0 si no había pausas o eran demasiado largas).
        """
        pendientes = self.pausas_pendientes()
        if not pendientes:
            return 0.0
        espera = max(pendientes.values())
        if espera > self._config.red.pausa_maxima_segundos:
            return 0.0
        self._dormir(espera)
        return espera

    def permitido_por_robots(self, url: str) -> bool:
        """Pregunta a robots.txt sin descargar la página (lo usa la herramienta de exploración)."""
        return self._robots.permitido(url)

    def retraso_sugerido_por_robots(self, url: str) -> float | None:
        """``Crawl-delay`` que declara el sitio para nuestro agente, si existe."""
        return self._robots.retraso_sugerido(url)

    # ------------------------------------------------------------------
    # Modo vivo
    # ------------------------------------------------------------------

    def _es_fresca(self, respuesta: Respuesta) -> bool:
        """True si la copia guardada es más reciente que el TTL configurado."""
        ttl = timedelta(hours=self._config.red.ttl_almacen_horas)
        return ttl > timedelta(0) and ahora_utc() - respuesta.obtenida_en < ttl

    def _descargar_una_vez(self, url: str) -> Respuesta:
        """Una sola solicitud, ocupando un turno del dominio. Sin reintentos ni almacén."""
        with self._limitador.turno(dominio_de(url)):
            return self._transporte.obtener(url, self._cabeceras, self._config.red.timeout_segundos)

    def _descargar_robots(self, url: str) -> Respuesta:
        """Descarga robots.txt. Un 429 ahí también pausa el dominio: antes solo se marcaba "no permitido" por 60 s y
        se volvía a pedir robots.txt cada minuto a un sitio que ya había pedido parar (pasó con CheapShark)."""
        respuesta = self._descargar_una_vez(url)
        if respuesta.estado == 429:
            pedida = leer_retry_after(respuesta.cabeceras, float("inf"))
            self._pausar(dominio_de(url), pedida if pedida is not None else self._config.red.pausa_429_segundos)
        return respuesta

    def _descargar_con_reintentos(self, url: str, dominio: str) -> Respuesta:
        """Descarga ``url`` reintentando los fallos temporales con backoff exponencial y jitter."""
        red = self._config.red
        ultimo_error: ErrorRed | None = None
        total_intentos = red.max_reintentos + 1  # El primer intento más los reintentos.

        for intento in range(total_intentos):
            # Otra tarea pudo pausar el dominio mientras este hilo esperaba su backoff: no se insiste.
            self._revisar_pausa(dominio)
            try:
                respuesta = self._descargar_una_vez(url)
                if respuesta.ok:
                    self.almacen.guardar(respuesta)
                    self.metricas.registrar(dominio, "exitosas")
                    return respuesta
                if respuesta.estado == 429 or respuesta.estado >= 500:
                    # 429 = "demasiadas solicitudes"; 5xx = error del servidor. Ambos son pasajeros.
                    # Sin tope: la pausa dura lo que pidió el sitio aunque supere ``pausa_maxima_segundos`` (ese
                    # tope solo decide si el reintento final la espera o se rinde con ese dominio).
                    pedida = leer_retry_after(respuesta.cabeceras, float("inf"))
                    if pedida is None and respuesta.estado == 429:
                        # 429 sin Retry-After: el sitio pidió parar pero no dijo cuánto. Se pausa un tiempo fijo en vez
                        # de reintentar a los pocos segundos (un 503 sin Retry-After sí usa el backoff normal).
                        pedida = red.pausa_429_segundos
                    if pedida is not None and pedida > red.backoff_max_segundos:
                        # El sitio pidió una espera larga (CheapShark: ~16 min). Reintentar antes la renueva, y
                        # dormir aquí dejaría este hilo de descarga parado todo ese rato sin atender otros sitios.
                        # Se pausa el dominio y la tarea va a la cola de fallidos.
                        self._pausar(dominio, pedida)
                        self.metricas.registrar(dominio, "fallidas")
                        raise DominioEnPausa(dominio, pedida)
                    raise ErrorTemporal(f"{url}: HTTP {respuesta.estado}", espera_sugerida=pedida)
                # Cualquier otro código (404, 403, 410...) no mejora reintentando.
                self.metricas.registrar(dominio, "fallidas")
                raise ErrorDefinitivo(f"{url}: HTTP {respuesta.estado}", estado=respuesta.estado)
            except ErrorTemporal as error:
                ultimo_error = error
                if intento + 1 < total_intentos:
                    self.metricas.registrar(dominio, "reintentos")
                    espera = error.espera_sugerida
                    if espera is None:
                        espera = calcular_espera(
                            intento, red.backoff_base_segundos, red.backoff_max_segundos,
                            self._aleatorio,
                        )
                    # Se espera FUERA del turno del limitador (el ``with`` ya terminó), así este
                    # hilo no ocupa una conexión del dominio mientras solo está esperando.
                    self._dormir(espera)

        self.metricas.registrar(dominio, "fallidas")
        assert ultimo_error is not None  # Solo se llega aquí si todos los intentos fallaron.
        raise ReintentosAgotados(url, total_intentos, ultimo_error)

    # ------------------------------------------------------------------
    # Modo replay
    # ------------------------------------------------------------------

    def _latencia_simulada(self) -> float:
        """Segundos de latencia para una solicitud en replay: fija o con variación aleatoria."""
        replay = self._config.replay
        milisegundos = float(replay.latencia_ms)
        if replay.variacion_ms > 0:
            milisegundos += self._aleatorio.uniform(-replay.variacion_ms, replay.variacion_ms)
        return max(0.0, milisegundos) / 1000.0

    def _obtener_replay(self, url: str, dominio: str) -> Respuesta:
        """Sirve la captura guardada simulando la espera de red."""
        captura = self.almacen.leer(url)
        if captura is None:
            self.metricas.registrar(dominio, "fallidas")
            raise SinCaptura(f"No hay captura guardada para {url}")
        # La espera se hace DENTRO del turno: igual que en vivo, la "conexión" queda ocupada mientras
        # se espera la respuesta. time.sleep libera el GIL, así que con varios hilos estas esperas
        # se solapan: es la concurrencia de E/S que el experimento quiere medir.
        with self._limitador.turno(dominio):
            self._dormir(self._latencia_simulada())
        self.metricas.registrar(dominio, "exitosas")
        return captura


def crear_cliente(config: Config) -> ClienteHttp:
    """Atajo para crear el cliente con el transporte real."""
    return ClienteHttp(config)
