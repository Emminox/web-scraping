"""Etapa 4 · Persistir: guarda en SQLite el resultado de cada juego (ADR-003: un único escritor).

Qué guarda por cada ``ResultadoJuego`` (un juego en una plataforma), en UNA transacción:
1. El juego (si es nuevo) y su plataforma con la fecha de lanzamiento.
2. El Metascore de esa plataforma (observación de calificación).
3. El mejor producto de cada tienda, con su estado de emparejamiento (aceptado, dudoso o rechazado).
4. Una observación de precio por producto aceptado o dudoso (nunca se sobrescribe: historial).
5. Las reseñas de Steam del producto aceptado (segunda calificación).
6. El MSRP de la plataforma, la primera vez que se conoce (precio regular de la tienda oficial).

Determinismo entre modos: los juegos llegan a esta etapa en un orden distinto según el modo. Todo lo
que se escribe aquí da el mismo estado final sin importar ese orden (ver ``_debe_reclamar``).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from radar.bd import abrir_bd
from radar.emparejamiento.emparejar import Emparejamiento, ResultadoJuego
from radar.fuentes.modelos import GOG, METACRITIC, METACRITIC_LISTADO, NINTENDO, STEAM, STEAM_RESENAS
from radar.red.modelos import ahora_utc

# Tiendas oficiales de cada plataforma, en orden de preferencia para tomar el MSRP. El precio regular
# de la tienda oficial es la mejor aproximación pública al precio sugerido (ver ADR-005).
PREFERENCIA_MSRP = (STEAM, NINTENDO, GOG)


class Persistidor:
    """Callable que la ``DefinicionPipeline`` usa como etapa ``persistir``."""

    def __init__(self, ruta_bd: Path, ejecucion_id: int, fuentes: dict[str, int]) -> None:
        self._ruta_bd = ruta_bd
        self._ejecucion_id = ejecucion_id
        self._fuentes = fuentes  # código de fuente -> id en la tabla ``fuente``.
        self._conexion: sqlite3.Connection | None = None
        self._hilo: int | None = None

    def __call__(self, resultado: ResultadoJuego) -> None:
        # La conexión se abre en el PRIMER llamado, es decir, dentro del hilo de persistencia.
        if self._conexion is None:
            self._conexion = abrir_bd(self._ruta_bd, cerrable_desde_otro_hilo=True)
            self._hilo = threading.get_ident()
        elif threading.get_ident() != self._hilo:
            # Si esto pasa, el orquestador tiene un bug: habría dos escritores (contradice el ADR-003).
            raise RuntimeError("Persistir debe ejecutarse siempre desde el mismo hilo (ADR-003)")
        with self._conexion:  # Una transacción por juego: o se guarda todo el juego, o nada.
            self._guardar(self._conexion, resultado)

    def cerrar(self) -> None:
        """Se llama desde el hilo principal DESPUÉS de que el pipeline terminó (ya nadie la usa)."""
        if self._conexion is not None:
            self._conexion.close()
            self._conexion = None

    # ------------------------------------------------------------------

    def _guardar(self, conexion: sqlite3.Connection, resultado: ResultadoJuego) -> None:
        juego = resultado.juego
        ahora = ahora_utc().isoformat()
        descubridor = self._fuentes.get(METACRITIC_LISTADO) if juego.origen == "descubrimiento" else None

        # 1) El juego. Si ya existe y fue cargado a mano (catalogo/*.json), su título manda.
        juego_id = conexion.execute(
            """
            INSERT INTO juego (clave, titulo_canonico, origen, descubierto_por, imagen_url, imagen_fuente_id,
                               activo, agregado_en)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT (clave) DO UPDATE SET
                titulo_canonico = CASE WHEN juego.origen = 'manual' THEN juego.titulo_canonico
                                       ELSE excluded.titulo_canonico END,
                -- La imagen más reciente gana (antes se conservaba la primera y una mejora del parser nunca
                -- llegaba a la base). Si esta vez no vino imagen, se mantiene la anterior.
                imagen_url = COALESCE(excluded.imagen_url, juego.imagen_url),
                imagen_fuente_id = COALESCE(excluded.imagen_fuente_id, juego.imagen_fuente_id),
                activo = 1
            RETURNING id
            """,
            (juego.clave_catalogo, juego.titulo, juego.origen, descubridor, juego.imagen_url,
             self._fuentes.get(METACRITIC_LISTADO) if juego.imagen_url else None, ahora),
        ).fetchone()[0]

        conexion.execute(
            """
            INSERT INTO juego_plataforma (juego_id, plataforma_codigo, fecha_lanzamiento) VALUES (?, ?, ?)
            ON CONFLICT (juego_id, plataforma_codigo) DO UPDATE SET
                fecha_lanzamiento = COALESCE(juego_plataforma.fecha_lanzamiento, excluded.fecha_lanzamiento)
            """,
            (juego_id, juego.plataforma, juego.fecha_lanzamiento),
        )

        # 2) Metascore de esta plataforma (viene del listado de descubrimiento).
        if juego.metascore is not None:
            conexion.execute(
                "INSERT OR IGNORE INTO observacion_calificacion (juego_id, fuente_id, plataforma_codigo, puntaje, "
                "escala, ejecucion_id, obtenida_en) VALUES (?, ?, ?, ?, 100, ?, ?)",
                (juego_id, self._fuentes[METACRITIC], juego.plataforma, float(juego.metascore),
                 self._ejecucion_id, juego.obtenida_en or ahora),
            )

        msrp_guardado = False
        for emparejamiento in sorted(resultado.emparejamientos, key=lambda e: PREFERENCIA_MSRP.index(e.candidato.fuente)
                                     if e.candidato.fuente in PREFERENCIA_MSRP else len(PREFERENCIA_MSRP)):
            producto_id = self._guardar_producto(conexion, juego_id, juego.clave_catalogo, emparejamiento, ahora)
            if producto_id is None or emparejamiento.estado == "rechazado":
                continue
            candidato = emparejamiento.candidato
            obtenida = candidato.obtenida_en or ahora
            # 4) Precio: SOLO INSERT. "OR IGNORE" evita duplicar si el reintento final reprocesa el juego.
            if candidato.precio_actual_centavos is not None:
                conexion.execute(
                    "INSERT OR IGNORE INTO observacion_precio (producto_id, ejecucion_id, obtenida_en, "
                    "precio_actual_centavos, precio_regular_centavos) VALUES (?, ?, ?, ?, ?)",
                    (producto_id, self._ejecucion_id, obtenida, candidato.precio_actual_centavos,
                     candidato.precio_regular_centavos),
                )
            if emparejamiento.estado != "aceptado":
                continue
            # 5) Reseñas de usuarios de Steam (segunda fuente de calificación).
            if candidato.fuente == STEAM and candidato.resena_porcentaje is not None:
                conexion.execute(
                    "INSERT OR IGNORE INTO observacion_calificacion (juego_id, fuente_id, plataforma_codigo, puntaje, "
                    "escala, cantidad_resenas, ejecucion_id, obtenida_en) VALUES (?, ?, 'pc', ?, 100, ?, ?, ?)",
                    (juego_id, self._fuentes[STEAM_RESENAS], float(candidato.resena_porcentaje),
                     candidato.resena_cantidad, self._ejecucion_id, obtenida),
                )
            # 6) MSRP de la plataforma: el precio regular de la tienda oficial preferida, si aún no hay uno.
            if (not msrp_guardado and candidato.fuente in PREFERENCIA_MSRP
                    and candidato.precio_regular_centavos and candidato.plataforma == juego.plataforma):
                conexion.execute(
                    "UPDATE juego_plataforma SET msrp_centavos = COALESCE(msrp_centavos, ?) "
                    "WHERE juego_id = ? AND plataforma_codigo = ?",
                    (candidato.precio_regular_centavos, juego_id, juego.plataforma),
                )
                msrp_guardado = True

    def _guardar_producto(self, conexion: sqlite3.Connection, juego_id: int, clave: str,
                          emparejamiento: Emparejamiento, ahora: str) -> int | None:
        """Crea o actualiza el producto de la tienda. Devuelve su id, o None si otro juego lo reclamó mejor."""
        candidato = emparejamiento.candidato
        fuente_id = self._fuentes[candidato.fuente]
        existente = conexion.execute(
            "SELECT p.id, p.similitud, p.estado_emparejamiento, j.clave AS clave_juego FROM producto_tienda p "
            "LEFT JOIN juego j ON j.id = p.juego_id WHERE p.fuente_id = ? AND p.url = ?",
            (fuente_id, candidato.url),
        ).fetchone()
        valores = (candidato.titulo, candidato.plataforma, candidato.formato, candidato.tipo, juego_id,
                   emparejamiento.similitud, emparejamiento.estado, emparejamiento.motivo, candidato.imagen_url)
        if existente is None:
            return conexion.execute(
                "INSERT INTO producto_tienda (titulo_en_tienda, plataforma_codigo, formato, tipo, juego_id, similitud, "
                "estado_emparejamiento, motivo_duda, imagen_url, fuente_id, url, visto_por_primera_vez) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                (*valores, fuente_id, candidato.url, ahora),
            ).fetchone()[0]
        if not _debe_reclamar(emparejamiento, clave, existente):
            return None
        conexion.execute(
            "UPDATE producto_tienda SET titulo_en_tienda = ?, plataforma_codigo = ?, formato = ?, tipo = ?, "
            "juego_id = ?, similitud = ?, estado_emparejamiento = ?, motivo_duda = ?, "
            "imagen_url = COALESCE(?, imagen_url) WHERE id = ?",
            (*valores, existente["id"]),
        )
        return existente["id"]


ORDEN_ESTADO = {"aceptado": 2, "dudoso": 1, "rechazado": 0}


def _debe_reclamar(nuevo: Emparejamiento, clave_nueva: str, existente: sqlite3.Row) -> bool:
    """¿El nuevo emparejamiento reemplaza al que ya tiene el producto?

    Si el producto ya pertenecía a OTRO juego, gana el de mejor estado, luego el de mayor similitud y,
    si todo empata, la clave de juego menor. Este orden total hace que el resultado final no dependa del
    orden de llegada (que cambia entre modos). Si es el mismo juego, siempre se actualiza.
    """
    if existente["clave_juego"] in (None, clave_nueva):
        return True
    nuevo_orden = (ORDEN_ESTADO[nuevo.estado], nuevo.similitud, _invertir(clave_nueva))
    viejo_orden = (ORDEN_ESTADO[existente["estado_emparejamiento"]], existente["similitud"] or 0.0,
                   _invertir(existente["clave_juego"]))
    return nuevo_orden > viejo_orden


def _invertir(texto: str) -> tuple[int, ...]:
    """Convierte un texto en algo que ordena al REVÉS (para que, al comparar con '>', gane la clave menor)."""
    return tuple(-ord(c) for c in texto) + (1,)
