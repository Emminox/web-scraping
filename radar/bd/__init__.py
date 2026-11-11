"""Base de datos del proyecto (SQLite, ver ADR-003).

- ``esquema.sql``: tablas, restricciones, triggers y vistas (explicado en ``docs/esquema-bd.md``).
- ``conexion.py``: abre la base con la configuración correcta y aplica el esquema.

Regla de diseño: SOLO la etapa Persistir (un único hilo) escribe en la base.
"""

from radar.bd.conexion import VERSION_ESQUEMA, ErrorEsquema, abrir_bd

__all__ = ["VERSION_ESQUEMA", "ErrorEsquema", "abrir_bd"]
