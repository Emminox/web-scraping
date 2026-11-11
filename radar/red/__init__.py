"""Capa de red responsable del Radar de Ofertas.

Todas las solicitudes del proyecto pasan por ``ClienteHttp`` (en ``cliente.py``), que combina:

- ``transporte.py``  -> hace la solicitud HTTP real (urllib, ver ADR-002).
- ``robots.py``      -> consulta y respeta robots.txt de cada sitio.
- ``limitador.py``   -> limita conexiones simultáneas e impone un intervalo mínimo por dominio.
- ``reintentos.py``  -> calcula la espera de backoff exponencial con jitter.
- ``almacen.py``     -> guarda cada respuesta en disco (caché en vivo, fuente en replay).
- ``metricas.py``    -> cuenta solicitudes exitosas, reintentadas y fallidas por sitio.
- ``modelos.py``     -> tipos de datos y excepciones compartidas.

La idea central (sección 11 del enunciado): el pipeline usa EXACTAMENTE el mismo código en modo
vivo y en modo replay; lo único que cambia es de dónde sale la respuesta.
"""

from radar.red.cliente import ClienteHttp, crear_cliente
from radar.red.modelos import (
    BloqueadoPorRobots,
    DominioEnPausa,
    ErrorDefinitivo,
    ErrorRed,
    ErrorTemporal,
    ReintentosAgotados,
    Respuesta,
    SinCaptura,
)

__all__ = [
    "BloqueadoPorRobots",
    "ClienteHttp",
    "DominioEnPausa",
    "ErrorDefinitivo",
    "ErrorRed",
    "ErrorTemporal",
    "ReintentosAgotados",
    "Respuesta",
    "SinCaptura",
    "crear_cliente",
]
