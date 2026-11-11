"""Carga y valida la configuración del proyecto (``config/config.toml``).

Para qué sirve: el enunciado exige que los tres modos de ejecución sean "seleccionables por
configuración" y que los límites (workers, conexiones por dominio, colas) sean decisiones
explícitas. Tener todo en un archivo TOML permite cambiar esos valores sin tocar el código,
y validarlos aquí evita que un error de tipeo produzca una medición inválida sin que nadie lo note.

Todas las clases son ``frozen`` (inmutables): una vez cargada, la configuración se puede compartir
entre hilos y procesos sin locks, porque nadie puede modificarla.
"""

from __future__ import annotations

import tomllib  # Lector de TOML de la biblioteca estándar (Python 3.11+).
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Raíz del repositorio: este archivo está en <raiz>/radar/config.py, así que subimos dos niveles.
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

# Ubicación por defecto del archivo de configuración.
RUTA_CONFIG_POR_DEFECTO = RAIZ_PROYECTO / "config" / "config.toml"

# Valores admitidos para los campos de tipo "elección".
MODOS_VALIDOS = ("secuencial", "concurrente", "paralelo")
FUENTES_VALIDAS = ("vivo", "replay")
EJECUTORES_EMPAREJAR = ("procesos", "hilos")

# En Windows, ProcessPoolExecutor no admite más de 61 procesos (límite del sistema operativo para
# esperar objetos a la vez). Se valida aquí para dar un mensaje claro en vez de un error interno.
MAX_PROCESOS_WINDOWS = 61


class ErrorConfiguracion(ValueError):
    """Se lanza cuando el archivo de configuración tiene un valor ausente o inválido."""


@dataclass(frozen=True)
class LimiteDominio:
    """Límites de cortesía para UN dominio (p. ej. ``store.steampowered.com``)."""

    # Cuántas solicitudes simultáneas se permiten a ese dominio (tamaño del semáforo).
    max_conexiones: int
    # Separación mínima, en segundos, entre el inicio de dos solicitudes al dominio.
    intervalo_minimo_segundos: float


@dataclass(frozen=True)
class ConfigRed:
    """Parámetros de la capa de red (sección 8 y 10 del enunciado)."""

    user_agent: str
    timeout_segundos: float
    max_reintentos: int
    backoff_base_segundos: float
    backoff_max_segundos: float
    # Límite que se aplica a cualquier dominio sin regla propia.
    limite_por_defecto: LimiteDominio
    ttl_almacen_horas: float
    # Reglas específicas: nombre de dominio -> límite.
    dominios: dict[str, LimiteDominio] = field(default_factory=dict)

    def limite_para(self, dominio: str) -> LimiteDominio:
        """Devuelve el límite que corresponde a ``dominio`` (el específico o el de por defecto)."""
        return self.dominios.get(dominio, self.limite_por_defecto)


@dataclass(frozen=True)
class ConfigReplay:
    """Parámetros del modo replay (sección 11 del enunciado)."""

    latencia_ms: int
    variacion_ms: int
    semilla: int


@dataclass(frozen=True)
class ConfigRutas:
    """Carpetas que usa el proyecto, ya convertidas a rutas absolutas."""

    capturas: Path
    fixtures: Path
    catalogo: Path
    base_datos: Path


@dataclass(frozen=True)
class ConfigPipeline:
    """Límites de concurrencia por etapa (sección 7 del enunciado). Ver docs/pipeline.md."""

    workers_descubrir: int
    workers_descargar: int
    workers_emparejar: int
    ejecutor_emparejar: str   # "procesos" o "hilos"
    cola_tareas: int
    cola_descargas: int
    cola_resultados: int
    cola_persistir: int


@dataclass(frozen=True)
class ConfigEjecucion:
    """Qué modo del pipeline se ejecuta y de dónde salen los datos."""

    modo: str
    fuente: str


@dataclass(frozen=True)
class Config:
    """Configuración completa del proyecto."""

    ejecucion: ConfigEjecucion
    pipeline: ConfigPipeline
    red: ConfigRed
    replay: ConfigReplay
    rutas: ConfigRutas


# ---------------------------------------------------------------------------
# Funciones auxiliares de validación.
# Cada una lee un campo de una sección del TOML y comprueba su tipo y rango.
# Si algo está mal, el mensaje dice exactamente qué campo revisar.
# ---------------------------------------------------------------------------


def _requerido(seccion: dict[str, Any], nombre_seccion: str, clave: str) -> Any:
    """Devuelve ``seccion[clave]`` o lanza un error claro si falta."""
    if clave not in seccion:
        raise ErrorConfiguracion(f"Falta '{clave}' en la sección [{nombre_seccion}].")
    return seccion[clave]


def _numero_positivo(valor: Any, nombre: str, *, permitir_cero: bool = False) -> float:
    """Valida que ``valor`` sea un número (int o float) mayor que 0 (o >= 0 si se permite)."""
    # bool es subclase de int en Python; lo excluimos para que "true" no pase como 1.
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorConfiguracion(f"'{nombre}' debe ser un número, se recibió {valor!r}.")
    if valor < 0 or (valor == 0 and not permitir_cero):
        condicion = ">= 0" if permitir_cero else "> 0"
        raise ErrorConfiguracion(f"'{nombre}' debe ser {condicion}, se recibió {valor!r}.")
    return float(valor)


def _entero_positivo(valor: Any, nombre: str, *, permitir_cero: bool = False) -> int:
    """Igual que ``_numero_positivo`` pero exige un entero."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErrorConfiguracion(f"'{nombre}' debe ser un entero, se recibió {valor!r}.")
    _numero_positivo(valor, nombre, permitir_cero=permitir_cero)
    return valor


def _eleccion(valor: Any, nombre: str, opciones: tuple[str, ...]) -> str:
    """Valida que ``valor`` sea una de las ``opciones`` permitidas."""
    if valor not in opciones:
        raise ErrorConfiguracion(f"'{nombre}' debe ser uno de {opciones}, se recibió {valor!r}.")
    return valor


def _leer_limite(datos: dict[str, Any], prefijo: str) -> LimiteDominio:
    """Construye un ``LimiteDominio`` a partir de una tabla del TOML."""
    return LimiteDominio(
        max_conexiones=_entero_positivo(
            _requerido(datos, prefijo, "max_conexiones"), f"{prefijo}.max_conexiones"
        ),
        intervalo_minimo_segundos=_numero_positivo(
            _requerido(datos, prefijo, "intervalo_minimo_segundos"),
            f"{prefijo}.intervalo_minimo_segundos",
            permitir_cero=True,
        ),
    )


# ---------------------------------------------------------------------------
# Punto de entrada público.
# ---------------------------------------------------------------------------


def cargar_config(ruta: Path | str | None = None) -> Config:
    """Lee el archivo TOML, valida cada campo y devuelve un objeto ``Config``.

    :param ruta: archivo a leer; si es ``None`` se usa ``config/config.toml``.
    :raises ErrorConfiguracion: si falta un campo o tiene un valor inválido.
    """
    ruta = Path(ruta) if ruta is not None else RUTA_CONFIG_POR_DEFECTO
    with ruta.open("rb") as archivo:  # tomllib exige abrir en modo binario.
        datos = tomllib.load(archivo)

    # Las rutas relativas del TOML se interpretan desde la raíz del repo (carpeta padre de config/),
    # así el programa funciona igual sin importar desde qué carpeta se ejecute.
    base_rutas = ruta.resolve().parent.parent

    ejecucion = datos.get("ejecucion", {})
    pipeline = datos.get("pipeline", {})
    red = datos.get("red", {})
    replay = datos.get("replay", {})
    rutas = datos.get("rutas", {})

    # Reglas específicas por dominio: [red.dominios."dominio"] -> LimiteDominio.
    dominios = {
        nombre: _leer_limite(tabla, f"red.dominios.{nombre}")
        for nombre, tabla in red.get("dominios", {}).items()
    }

    config_red = ConfigRed(
        user_agent=str(_requerido(red, "red", "user_agent")).strip(),
        timeout_segundos=_numero_positivo(
            _requerido(red, "red", "timeout_segundos"), "red.timeout_segundos"
        ),
        max_reintentos=_entero_positivo(
            _requerido(red, "red", "max_reintentos"), "red.max_reintentos", permitir_cero=True
        ),
        backoff_base_segundos=_numero_positivo(
            _requerido(red, "red", "backoff_base_segundos"), "red.backoff_base_segundos"
        ),
        backoff_max_segundos=_numero_positivo(
            _requerido(red, "red", "backoff_max_segundos"), "red.backoff_max_segundos"
        ),
        limite_por_defecto=LimiteDominio(
            max_conexiones=_entero_positivo(
                _requerido(red, "red", "max_conexiones_por_dominio"),
                "red.max_conexiones_por_dominio",
            ),
            intervalo_minimo_segundos=_numero_positivo(
                _requerido(red, "red", "intervalo_minimo_segundos"),
                "red.intervalo_minimo_segundos",
                permitir_cero=True,
            ),
        ),
        ttl_almacen_horas=_numero_positivo(
            _requerido(red, "red", "ttl_almacen_horas"), "red.ttl_almacen_horas", permitir_cero=True
        ),
        dominios=dominios,
    )
    if not config_red.user_agent:
        raise ErrorConfiguracion("'red.user_agent' no puede estar vacío: debe nombrar el proyecto.")

    def entero_pipeline(clave: str) -> int:
        return _entero_positivo(_requerido(pipeline, "pipeline", clave), f"pipeline.{clave}")

    config_pipeline = ConfigPipeline(
        workers_descubrir=entero_pipeline("workers_descubrir"),
        workers_descargar=entero_pipeline("workers_descargar"),
        workers_emparejar=entero_pipeline("workers_emparejar"),
        ejecutor_emparejar=_eleccion(
            _requerido(pipeline, "pipeline", "ejecutor_emparejar"),
            "pipeline.ejecutor_emparejar",
            EJECUTORES_EMPAREJAR,
        ),
        cola_tareas=entero_pipeline("cola_tareas"),
        cola_descargas=entero_pipeline("cola_descargas"),
        cola_resultados=entero_pipeline("cola_resultados"),
        cola_persistir=entero_pipeline("cola_persistir"),
    )
    if (
        config_pipeline.ejecutor_emparejar == "procesos"
        and config_pipeline.workers_emparejar > MAX_PROCESOS_WINDOWS
    ):
        raise ErrorConfiguracion(
            f"'pipeline.workers_emparejar' no puede superar {MAX_PROCESOS_WINDOWS} con procesos "
            "(límite de Windows para ProcessPoolExecutor)."
        )

    config_replay = ConfigReplay(
        latencia_ms=_entero_positivo(
            _requerido(replay, "replay", "latencia_ms"), "replay.latencia_ms", permitir_cero=True
        ),
        variacion_ms=_entero_positivo(
            _requerido(replay, "replay", "variacion_ms"), "replay.variacion_ms", permitir_cero=True
        ),
        semilla=int(_requerido(replay, "replay", "semilla")),
    )

    return Config(
        ejecucion=ConfigEjecucion(
            modo=_eleccion(_requerido(ejecucion, "ejecucion", "modo"), "ejecucion.modo", MODOS_VALIDOS),
            fuente=_eleccion(
                _requerido(ejecucion, "ejecucion", "fuente"), "ejecucion.fuente", FUENTES_VALIDAS
            ),
        ),
        pipeline=config_pipeline,
        red=config_red,
        replay=config_replay,
        rutas=ConfigRutas(
            capturas=base_rutas / _requerido(rutas, "rutas", "capturas"),
            fixtures=base_rutas / _requerido(rutas, "rutas", "fixtures"),
            catalogo=base_rutas / _requerido(rutas, "rutas", "catalogo"),
            base_datos=base_rutas / _requerido(rutas, "rutas", "base_datos"),
        ),
    )
