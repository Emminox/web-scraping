"""Abre la base de datos SQLite con la configuración que el proyecto necesita.

Para qué sirve: SQLite tiene opciones importantes que vienen APAGADAS por defecto y que hay que
activar cada vez que se abre una conexión (sobre todo las claves foráneas). Si cada parte del código
abriera la base a su manera, alguna se olvidaría. Por eso todo el proyecto abre la base con
``abrir_bd``.

Sobre los hilos: una conexión de ``sqlite3`` solo se puede usar desde el hilo que la creó (Python lo
verifica y lanza ``ProgrammingError`` si otro hilo la usa). Eso encaja con el diseño del ADR-003: la
etapa Persistir es un único hilo que abre su propia conexión y es el único que escribe. Los otros
hilos y los procesos del emparejamiento nunca reciben la conexión.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Versión actual del esquema. Si se cambia esquema.sql de forma incompatible, se sube este número y
# se escribe una migración; así una base vieja no se usa por error con código nuevo.
VERSION_ESQUEMA = 1

RUTA_ESQUEMA = Path(__file__).with_name("esquema.sql")


class ErrorEsquema(RuntimeError):
    """La base existe pero su versión de esquema no coincide con la que espera el código."""


def abrir_bd(ruta: Path | str) -> sqlite3.Connection:
    """Abre (o crea) la base en ``ruta``, la configura y aplica el esquema si es nueva.

    :param ruta: archivo de la base, o ``":memory:"`` para una base temporal en memoria (pruebas).
    :raises ErrorEsquema: si la base fue creada con otra versión del esquema.
    """
    en_memoria = str(ruta) == ":memory:"
    if not en_memoria:
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)

    # timeout=10: si la base está ocupada por otra conexión (p. ej. el generador del sitio leyendo
    # mientras Persistir escribe), se espera hasta 10 s en lugar de fallar al instante.
    conexion = sqlite3.connect(ruta, timeout=10.0)
    try:
        # Las filas se pueden leer por nombre de columna: fila["titulo_canonico"].
        conexion.row_factory = sqlite3.Row

        # Las claves foráneas (REFERENCES) NO se verifican si no se activa esto, y hay que hacerlo en
        # CADA conexión nueva. Sin esto se podría guardar un precio de un producto que no existe.
        conexion.execute("PRAGMA foreign_keys = ON")
        if not en_memoria:
            # WAL ("write-ahead log"): permite que los lectores lean mientras el escritor escribe, sin
            # bloquearse entre sí. Es útil cuando el generador del sitio consulta la base.
            conexion.execute("PRAGMA journal_mode = WAL")
            # Con WAL, NORMAL es seguro ante caídas del programa y bastante más rápido que FULL.
            conexion.execute("PRAGMA synchronous = NORMAL")

        _aplicar_esquema(conexion)
    except BaseException:
        # Si algo falla (p. ej. versión de esquema incorrecta), se cierra la conexión antes de
        # propagar el error. Si no, quedaría abierta sin que nadie pueda cerrarla y, en Windows,
        # el archivo de la base quedaría bloqueado hasta que termine el programa.
        conexion.close()
        raise
    return conexion


def _aplicar_esquema(conexion: sqlite3.Connection) -> None:
    """Crea las tablas si la base es nueva; verifica la versión si ya existía."""
    version = conexion.execute("PRAGMA user_version").fetchone()[0]
    if version == VERSION_ESQUEMA:
        return  # La base ya tiene el esquema correcto.
    if version != 0:
        raise ErrorEsquema(
            f"La base tiene el esquema versión {version}, pero el código espera la {VERSION_ESQUEMA}. "
            "Hace falta una migración (o regenerar la base desde el catálogo)."
        )
    # Base nueva (user_version = 0): se ejecuta el archivo completo y se marca la versión.
    # executescript ejecuta varias sentencias SQL seguidas. Si fallara a la mitad, la versión seguiría
    # en 0 y la próxima apertura volvería a ejecutar el archivo; como todo usa IF NOT EXISTS / OR
    # IGNORE, repetirlo es seguro. La versión se marca SOLO al final, cuando todo salió bien.
    conexion.executescript(RUTA_ESQUEMA.read_text(encoding="utf-8"))
    conexion.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
