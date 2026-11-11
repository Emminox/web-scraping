"""Almacén de capturas: guarda en disco cada respuesta descargada.

Cumple dos papeles a la vez (secciones 10 y 11 del enunciado):

- En modo **vivo** es la **caché local**: si una página se descargó hace poco, no se vuelve a pedir.
- En modo **replay** es la **fuente de datos**: el pipeline lee de aquí en lugar de la red, así las
  mediciones son repetibles. Como todo lo que se descarga en vivo queda guardado, cada ejecución
  en vivo va construyendo las capturas que después usa el replay.

Formato en disco (fácil de inspeccionar a mano)::

    datos/capturas/<dominio>/<clave>.meta.json   -> URL, estado, cabeceras, fecha de obtención
    datos/capturas/<dominio>/<clave>.html|.json|.bin -> el contenido tal cual llegó

``<clave>`` es un resumen SHA-256 de la URL: convierte cualquier URL (con ``?``, ``/``, ``&``...)
en un nombre de archivo válido y siempre igual para la misma URL.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from radar.red.modelos import Respuesta


def normalizar_url(url: str) -> str:
    """Normaliza una URL para que variantes triviales compartan la misma captura.

    Solo se pasa a minúsculas el esquema y el dominio, y se quita el fragmento (``#...``), que nunca
    llega al servidor. NO se reordenan los parámetros: en algunos sitios el orden sí importa.
    """
    partes = urlsplit(url)
    return urlunsplit(
        (partes.scheme.lower(), partes.netloc.lower(), partes.path, partes.query, "")
    )


def _extension_para(tipo_contenido: str) -> str:
    """Elige la extensión del archivo de contenido según el Content-Type."""
    if "html" in tipo_contenido:
        return ".html"
    if "json" in tipo_contenido:
        return ".json"
    if "text" in tipo_contenido or "xml" in tipo_contenido:
        return ".txt"
    return ".bin"


def _escribir_atomico(ruta: Path, datos: bytes) -> None:
    """Escribe ``datos`` en ``ruta`` de forma atómica.

    Primero se escribe en un archivo temporal de la MISMA carpeta y luego se reemplaza el destino
    con ``os.replace``. Así, aunque varios hilos guarden la misma URL a la vez, o el programa se
    interrumpa a mitad de la escritura, nadie lee nunca un archivo a medio escribir.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=".tmp-")
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(datos)
        # En Windows, ``os.replace`` falla con PermissionError si otro proceso tiene el archivo
        # abierto en ese instante (un lector, el antivirus o la sincronización de OneDrive).
        # Se reintenta unas pocas veces con una pausa corta antes de rendirse.
        for intento in range(5):
            try:
                os.replace(temporal, ruta)
                return
            except PermissionError:
                if intento == 4:
                    raise
                time.sleep(0.05 * (intento + 1))
    finally:
        # Si algo falló antes del reemplazo, se borra el temporal para no dejar basura.
        if os.path.exists(temporal):
            os.remove(temporal)


class AlmacenCapturas:
    """Lee y guarda respuestas en disco. Seguro para usar desde varios hilos y procesos."""

    def __init__(self, directorio: Path) -> None:
        self._directorio = Path(directorio)

    @property
    def directorio(self) -> Path:
        return self._directorio

    def _ruta_meta(self, url: str) -> Path:
        """Ruta del archivo de metadatos de una URL."""
        url_normal = normalizar_url(url)
        dominio = urlsplit(url_normal).hostname or "sin-dominio"
        # 32 caracteres hexadecimales del SHA-256: la probabilidad de que dos URL distintas
        # coincidan es despreciable para el tamaño de este proyecto.
        clave = hashlib.sha256(url_normal.encode("utf-8")).hexdigest()[:32]
        return self._directorio / dominio / f"{clave}.meta.json"

    def guardar(self, respuesta: Respuesta) -> None:
        """Guarda (o reemplaza) la captura de ``respuesta.url``."""
        ruta_meta = self._ruta_meta(respuesta.url)
        base = ruta_meta.name.removesuffix(".meta.json")
        nombre_cuerpo = base + _extension_para(respuesta.tipo_contenido)
        metadatos = {
            "url": respuesta.url,
            "estado": respuesta.estado,
            "cabeceras": respuesta.cabeceras,
            "obtenida_en": respuesta.obtenida_en.isoformat(),
            "archivo_cuerpo": nombre_cuerpo,
        }
        # Orden importante: primero el contenido y DESPUÉS los metadatos. Un lector busca primero
        # los metadatos; si existen, el contenido al que apuntan ya está completo en disco.
        _escribir_atomico(ruta_meta.parent / nombre_cuerpo, respuesta.cuerpo)
        _escribir_atomico(
            ruta_meta, json.dumps(metadatos, ensure_ascii=False, indent=2).encode("utf-8")
        )

    def leer(self, url: str) -> Respuesta | None:
        """Devuelve la captura guardada de ``url`` o ``None`` si no existe."""
        ruta_meta = self._ruta_meta(url)
        try:
            metadatos = json.loads(ruta_meta.read_text(encoding="utf-8"))
            cuerpo = (ruta_meta.parent / metadatos["archivo_cuerpo"]).read_bytes()
        except FileNotFoundError:
            return None
        return Respuesta(
            url=metadatos["url"],
            estado=metadatos["estado"],
            cuerpo=cuerpo,
            cabeceras=metadatos["cabeceras"],
            obtenida_en=datetime.fromisoformat(metadatos["obtenida_en"]),
            desde_almacen=True,
        )
