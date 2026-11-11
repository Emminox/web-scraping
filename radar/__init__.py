"""Radar de Ofertas Multinúcleo.

Paquete principal del proyecto. Subpaquetes:
- ``radar.config``: lectura y validación de ``config/config.toml``.
- ``radar.red``: capa de red responsable (robots.txt, límites por dominio, reintentos, almacén/replay).
- ``radar.herramientas``: utilidades de línea de comandos (p. ej. explorar una fuente en los spikes).
"""

import sys

# Versión mínima de Python del proyecto (ADR-001).
VERSION_MINIMA = (3, 14)

# Este archivo se ejecuta cada vez que se importa cualquier parte del paquete ``radar``, así que es el
# lugar ideal para comprobar la versión UNA vez para todo el proyecto.
#
# ¿Por qué no basta con ``requires-python`` en pyproject.toml? Porque esa regla solo se revisa al
# instalar el paquete con pip, y aquí ejecutamos el código directamente con ``py -3.14 -m ...``.
# En Windows es fácil que ``python`` apunte a otra versión instalada (p. ej. 3.12) sin darse cuenta;
# eso haría que cada integrante mida con un Python distinto y los resultados no serían comparables.
if sys.version_info < VERSION_MINIMA:
    raise RuntimeError(
        f"El proyecto requiere Python {VERSION_MINIMA[0]}.{VERSION_MINIMA[1]} o superior (ADR-001), "
        f"pero se está ejecutando con {sys.version.split()[0]}. "
        "En Windows usen: py -3.14 -m <módulo>"
    )
