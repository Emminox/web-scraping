"""Une todas las piezas para ejecutar el Radar de Ofertas de punta a punta.

Secuencia de una ejecución (``ejecutar``):

1. Abre la base, registra las fuentes y crea la fila de la ejecución (hilo principal).
2. Descarga el sitemap de Nintendo y arma su índice (una sola vez, antes del pipeline).
3. Ejecuta el pipeline en el modo configurado (secuencial, concurrente o paralelo). Durante el pipeline,
   el ÚNICO que escribe en la base es la etapa Persistir (ADR-003).
4. **Reintento final de la cola de fallidos** (sección 8): vuelve a procesar, en modo secuencial, los
   juegos que tuvieron alguna descarga fallida. Las fuentes que sí funcionaron salen de la caché.
5. Guarda las métricas (tiempos por etapa, solicitudes por sitio, fallidos) y regenera el panel.

En modo replay se usan una base y un sitio aparte ("-replay") para no mezclar precios capturados con
el historial real.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from radar.bd import abrir_bd
from radar.catalogo import ErrorCatalogo, leer_catalogo
from radar.config import Config
from radar.emparejamiento.emparejar import emparejar_juego
from radar.emparejamiento.normalizar import quitar_anio_entre_parentesis, texto_basico
from radar.fuentes import bestbuy, cheapshark, gog, metacritic, nintendo, steam
from radar.fuentes.cheapshark import CHEAPSHARK
from radar.fuentes.modelos import BESTBUY, GOG, NINTENDO, STEAM, Candidato
from radar.persistencia import Persistidor
from radar.pipeline import DefinicionPipeline, Descarga, Juego, ResultadoEjecucion, TareaDescarga, ejecutar_pipeline
from radar.pipeline.secuencial import ejecutar_secuencial
from radar.red import ClienteHttp
from radar.red.modelos import ahora_utc
from radar.sitio import generar_metricas, generar_sitio

# Fuentes registradas en la tabla ``fuente``: (código, nombre, tipo, dominio, método). Ver ADR-004.
FUENTES = (
    ("metacritic-listado", "Metacritic (listado)", "descubrimiento", "www.metacritic.com", "html"),
    ("metacritic", "Metacritic", "calificacion", "www.metacritic.com", "html"),
    ("steam", "Steam", "tienda_plataforma", "store.steampowered.com", "html"),
    ("steam-resenas", "Reseñas de usuarios de Steam", "calificacion", "store.steampowered.com", "html"),
    ("nintendo", "Nintendo eShop", "tienda_plataforma", "www.nintendo.com", "html"),
    ("gog", "GOG", "tienda_plataforma", "catalog.gog.com", "api"),
    ("bestbuy", "Best Buy", "minorista", "www.bestbuy.com", "html"),
    # Tiendas de PC que llegan por la API de CheapShark (ADR-011): una fila por tienda.
    *((codigo, nombre, tipo, "www.cheapshark.com", "api") for codigo, nombre, tipo in cheapshark.TIENDAS.values()),
)

# Qué tiendas se consultan para cada plataforma (CHEAPSHARK es una consulta que trae varias tiendas de PC).
FUENTES_POR_PLATAFORMA = {
    "pc": (STEAM, GOG, CHEAPSHARK),
    "switch": (NINTENDO, BESTBUY),
    "switch2": (NINTENDO, BESTBUY),
    "ps5": (BESTBUY,),
    "ps4": (BESTBUY,),
    "xbox-series": (BESTBUY,),
    "xbox-one": (BESTBUY,),
}

PLATAFORMAS_VALIDAS = set(FUENTES_POR_PLATAFORMA)


@dataclass(frozen=True)
class OpcionesEjecucion:
    """Opciones de una ejecución (las de la línea de comandos)."""

    modo: str
    fuente_datos: str                 # 'vivo' o 'replay'.
    plataformas: tuple[str, ...]      # Plataformas de Metacritic a recorrer.
    paginas_por_plataforma: int | None = None  # Si se indica (--paginas), reemplaza la configuración de TODAS.
    por_pagina: int | None = None     # Para pruebas rápidas: solo los primeros N juegos de cada página.


@dataclass(frozen=True)
class ResumenCorrida:
    ejecucion_id: int
    resultado: ResultadoEjecucion
    resueltos_al_final: int
    publicados: int
    sitio: Path
    base_datos: Path


def rutas_para(config: Config, fuente_datos: str) -> tuple[Path, Path]:
    """Base y carpeta del sitio. En replay se usan otras, para no mezclar datos capturados con los reales."""
    base, sitio = config.rutas.base_datos, config.rutas.sitio
    if fuente_datos == "replay":
        base = base.with_name(f"{base.stem}-replay{base.suffix}")
        sitio = sitio.with_name(f"{sitio.name}-replay")
    return base, sitio


def registrar_fuentes(conexion: sqlite3.Connection) -> dict[str, int]:
    with conexion:
        conexion.executemany(
            "INSERT OR IGNORE INTO fuente (codigo, nombre, tipo, dominio, metodo) VALUES (?, ?, ?, ?, ?)", FUENTES
        )
    return {f["codigo"]: f["id"] for f in conexion.execute("SELECT id, codigo FROM fuente")}


def palabras_para_indice(titulo: str) -> frozenset[str]:
    """Palabras de un título con el mismo estilo que los identificadores de Nintendo ('hades-ii-switch').

    Reutiliza el paso común del emparejamiento (``texto_basico``) para no mantener dos copias de las mismas reglas.
    """
    return frozenset(texto_basico(quitar_anio_entre_parentesis(titulo)).split())


def cargar_indice_nintendo(cliente: ClienteHttp) -> nintendo.IndiceNintendo:
    """Descarga el sitemap (o lo lee de la caché / del replay) y arma el índice de productos."""
    respuesta = cliente.obtener(nintendo.URL_SITEMAP)
    return nintendo.IndiceNintendo(nintendo.parsear_sitemap(respuesta.cuerpo))


def juegos_del_catalogo(config: Config) -> list[Juego]:
    """Juegos agregados a mano en catalogo/*.json, una entrada por plataforma."""
    if not config.rutas.catalogo.exists():
        return []
    juegos = []
    for entrada in leer_catalogo(config.rutas.catalogo, PLATAFORMAS_VALIDAS):
        if not entrada.activo:
            continue
        for plataforma in entrada.plataformas:
            juegos.append(Juego(
                clave=f"{entrada.clave}@{plataforma.codigo}", titulo=entrada.titulo,
                titulos_alternativos=entrada.titulos_alternativos, clave_catalogo=entrada.clave,
                plataforma=plataforma.codigo, fecha_lanzamiento=plataforma.fecha_lanzamiento, origen="manual",
            ))
    return juegos


def construir_definicion(config: Config, opciones: OpcionesEjecucion, cliente: ClienteHttp,
                         indice: nintendo.IndiceNintendo, persistidor: Persistidor, ruta_bd: Path,
                         destino_sitio: Path) -> DefinicionPipeline:
    """Arma la ``DefinicionPipeline`` con las fuentes reales: QUÉ hace cada etapa."""

    def paginas() -> list[tuple]:
        # Orden INTERCALADO (página 1 de cada plataforma, luego la 2...). Si se recorrieran primero todas las
        # páginas de consola, sus tareas de Best Buy (el dominio más lento) llenarían la cola acotada de
        # tareas y los juegos de PC no entrarían al pipeline: Steam y GOG quedarían ociosos (bloqueo por
        # cabeza de cola, observado en la primera ejecución completa). El orden no cambia los resultados.
        def paginas_de(plataforma: str) -> int:
            return opciones.paginas_por_plataforma or config.descubrimiento.paginas_de(plataforma)

        maximo = max(paginas_de(p) for p in opciones.plataformas)
        lista = [("metacritic", plataforma, numero)
                 for numero in range(1, maximo + 1)
                 for plataforma in opciones.plataformas
                 if numero <= paginas_de(plataforma)]
        return lista + [("catalogo", None, 0)]

    def descubrir_pagina(pagina: tuple) -> list[Juego]:
        tipo, plataforma_mc, numero = pagina
        if tipo == "catalogo":
            try:
                return juegos_del_catalogo(config)
            except ErrorCatalogo as error:
                raise ValueError(f"catálogo manual inválido: {error.problemas[:3]}") from error
        respuesta = cliente.obtener(metacritic.url_listado(plataforma_mc, numero))
        plataforma = metacritic.PLATAFORMAS[plataforma_mc]
        tarjetas = metacritic.parsear_listado(respuesta.cuerpo.decode("utf-8", errors="replace"), plataforma)
        if opciones.por_pagina is not None:
            tarjetas = tarjetas[: opciones.por_pagina]
        obtenida = respuesta.obtenida_en.isoformat()
        return [Juego(
            clave=f"{t.slug}@{plataforma}", titulo=t.titulo, clave_catalogo=t.slug, plataforma=plataforma,
            fecha_lanzamiento=t.fecha_lanzamiento, imagen_url=t.imagen_url, metascore=t.metascore,
            origen="descubrimiento", obtenida_en=obtenida,
        ) for t in tarjetas]

    def fuentes_de(juego: Juego) -> list[tuple[str, str]]:
        resultado = []
        for fuente in FUENTES_POR_PLATAFORMA.get(juego.plataforma, ()):
            if fuente == STEAM:
                resultado.append((fuente, steam.url_busqueda(juego.titulo)))
            elif fuente == GOG:
                resultado.append((fuente, gog.url_busqueda(juego.titulo)))
            elif fuente == CHEAPSHARK:
                resultado.append((fuente, cheapshark.url_busqueda(juego.titulo)))
            elif fuente == BESTBUY:
                resultado.append((fuente, bestbuy.url_busqueda(juego.titulo)))
            elif fuente == NINTENDO:
                url = indice.buscar(palabras_para_indice(juego.titulo), juego.plataforma)
                if url:  # Si el sitemap no tiene un producto parecido, Nintendo no se consulta.
                    resultado.append((fuente, url))
        return resultado

    def descargar(tarea: TareaDescarga):
        return cliente.obtener(tarea.url)

    def parsear(descarga: Descarga) -> tuple[Candidato, ...]:
        respuesta = descarga.respuesta
        fuente = descarga.tarea.fuente
        if fuente == STEAM:
            candidatos = steam.parsear_busqueda(respuesta.cuerpo)
        elif fuente == GOG:
            candidatos = gog.parsear_busqueda(respuesta.cuerpo)
        elif fuente == CHEAPSHARK:
            candidatos = cheapshark.parsear_busqueda(respuesta.cuerpo)
        elif fuente == BESTBUY:
            candidatos = bestbuy.parsear_busqueda(respuesta.cuerpo)
        elif fuente == NINTENDO:
            candidatos = nintendo.parsear_producto(respuesta.cuerpo, descarga.tarea.url)
        else:
            raise ValueError(f"fuente desconocida: {fuente}")
        obtenida = respuesta.obtenida_en.isoformat()
        return tuple(replace(c, obtenida_en=obtenida) for c in candidatos)

    def publicar() -> None:
        # Conexión propia para leer: esta etapa corre en el hilo principal, cuando Persistir ya terminó.
        lectura = abrir_bd(ruta_bd)
        try:
            generar_sitio(lectura, destino_sitio, config.rutas.mediciones)
        finally:
            lectura.close()

    return DefinicionPipeline(
        paginas=paginas, descubrir_pagina=descubrir_pagina, fuentes_de=fuentes_de, descargar=descargar,
        parsear=parsear, emparejar=emparejar_juego, persistir=persistidor, publicar=publicar,
    )


def _registrar_inicio(conexion: sqlite3.Connection, config: Config, opciones: OpcionesEjecucion) -> int:
    configuracion = {
        "modo": opciones.modo, "fuente_datos": opciones.fuente_datos, "plataformas": opciones.plataformas,
        "paginas_por_plataforma": {p: opciones.paginas_por_plataforma or config.descubrimiento.paginas_de(p)
                                   for p in opciones.plataformas},
        "por_pagina": opciones.por_pagina,
        "pipeline": config.pipeline.__dict__, "replay": config.replay.__dict__,
    }
    with conexion:
        return conexion.execute(
            "INSERT INTO ejecucion (iniciada_en, modo, fuente_datos, configuracion) VALUES (?, ?, ?, ?) RETURNING id",
            (ahora_utc().isoformat(), opciones.modo, opciones.fuente_datos, json.dumps(configuracion)),
        ).fetchone()[0]


def _registrar_fin(conexion: sqlite3.Connection, ejecucion_id: int, resultado: ResultadoEjecucion,
                   metricas_red: dict, resueltos: set[tuple[str, str]], estado: str) -> None:
    claves = {f["clave"]: f["id"] for f in conexion.execute("SELECT id, clave FROM juego")}
    with conexion:
        conexion.execute("UPDATE ejecucion SET terminada_en = ?, estado = ? WHERE id = ?",
                         (ahora_utc().isoformat(), estado, ejecucion_id))
        conexion.executemany(
            "INSERT OR REPLACE INTO ejecucion_etapa (ejecucion_id, etapa, duracion_segundos, elementos, ventana_segundos) "
            "VALUES (?, ?, ?, ?, ?)",
            [(ejecucion_id, e.nombre, e.tiempo_ocupado_s, e.elementos, e.ventana_s) for e in resultado.etapas.values()],
        )
        conexion.executemany(
            "INSERT OR REPLACE INTO ejecucion_metricas_dominio (ejecucion_id, dominio, exitosas, reintentos, fallidas, "
            "desde_almacen, bloqueadas_robots) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(ejecucion_id, dominio, c["exitosas"], c["reintentos"], c["fallidas"], c["desde_almacen"], c["bloqueadas_robots"])
             for dominio, c in sorted(metricas_red.items())],
        )
        for descarga in resultado.fallidos:
            tarea = descarga.tarea
            intentos = re.search(r"(\d+) intentos", descarga.error or "")
            conexion.execute(
                "INSERT INTO fallo (ejecucion_id, url, dominio, juego_id, tipo_error, mensaje, intentos, resuelto_al_final) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ejecucion_id, tarea.url, urlsplit(tarea.url).hostname or "-", claves.get(tarea.juego.clave_catalogo),
                 (descarga.error or "").split(":", 1)[0], descarga.error or "", int(intentos.group(1)) if intentos else 1,
                 int((tarea.juego.clave, tarea.fuente) in resueltos)),
            )


def ejecutar(config: Config, opciones: OpcionesEjecucion) -> ResumenCorrida:
    """Ejecuta el Radar completo (ver la secuencia en el docstring del módulo)."""
    config = replace(config, ejecucion=replace(config.ejecucion, modo=opciones.modo, fuente=opciones.fuente_datos))
    ruta_bd, destino_sitio = rutas_para(config, opciones.fuente_datos)
    conexion = abrir_bd(ruta_bd)
    try:
        fuentes = registrar_fuentes(conexion)
        cliente = ClienteHttp(config)
        indice = cargar_indice_nintendo(cliente)
        ejecucion_id = _registrar_inicio(conexion, config, opciones)

        persistidor = Persistidor(ruta_bd, ejecucion_id, fuentes)
        definicion = construir_definicion(config, opciones, cliente, indice, persistidor, ruta_bd, destino_sitio)
        try:
            resultado = ejecutar_pipeline(definicion, opciones.modo, config.pipeline)
        finally:
            persistidor.cerrar()  # Después de join(): ya ningún hilo usa la conexión de Persistir.

        # Reintento final de la cola de fallidos (sección 8), en modo secuencial y con otro Persistidor.
        resueltos: set[tuple[str, str]] = set()
        juegos_con_fallos = sorted({d.tarea.juego for d in resultado.fallidos}, key=lambda j: j.clave)
        if juegos_con_fallos:
            # Si algún sitio pidió esperar (Retry-After largo), se espera a que termine la pausa: reintentar antes
            # volvería a fallar al instante (y algunos sitios renuevan el bloqueo).
            pendientes = cliente.pausas_pendientes()
            if pendientes:
                print("Esperando pausas pedidas por los sitios antes del reintento final: "
                      + ", ".join(f"{d} {s:.0f} s" for d, s in sorted(pendientes.items())), flush=True)
                cliente.esperar_pausas()
            persistidor_final = Persistidor(ruta_bd, ejecucion_id, fuentes)
            reintento = replace(
                construir_definicion(config, opciones, cliente, indice, persistidor_final, ruta_bd, destino_sitio),
                paginas=lambda: ["reintento-final"], descubrir_pagina=lambda _pagina: juegos_con_fallos,
            )
            try:
                segundo = ejecutar_secuencial(reintento)
            finally:
                persistidor_final.cerrar()
            siguen_fallando = {(d.tarea.juego.clave, d.tarea.fuente) for d in segundo.fallidos}
            resueltos = {(d.tarea.juego.clave, d.tarea.fuente) for d in resultado.fallidos} - siguen_fallando

        estado = "completa" if resultado.juegos_persistidos > 0 else "fallida"
        _registrar_fin(conexion, ejecucion_id, resultado, cliente.metricas.instantanea(), resueltos, estado)
        generar_metricas(conexion, destino_sitio, config.rutas.mediciones, resultado.errores)
        publicados = len(json.loads((destino_sitio / "datos" / "juegos.json").read_text(encoding="utf-8"))["juegos"])
        return ResumenCorrida(ejecucion_id, resultado, len(resueltos), publicados, destino_sitio, ruta_bd)
    finally:
        conexion.close()
