"""Lee el catálogo de juegos desde ``catalogo/*.json``, lo valida y lo carga en la base de datos.

Para qué sirve (sección 4 del enunciado): el catálogo no puede estar escrito en el código y debe poder
cambiarse sin tocarlo. Los archivos JSON de ``catalogo/`` son la fuente de verdad; la base se
sincroniza con ellos. El formato está explicado en ``catalogo/README.md``.

Está dividido en tres pasos independientes, para poder probar cada uno por separado:

1. ``leer_catalogo``       -> lee y valida los archivos. No toca la base.
2. ``cargar_en_bd``        -> escribe en la base, en UNA sola transacción (todo o nada).
3. ``verificar_requisitos`` -> compara lo cargado con los mínimos del enunciado (500 juegos, etc.).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

# Valores permitidos. DEBEN coincidir con los CHECK de radar/bd/esquema.sql
# (hay una prueba que lo verifica: tests/test_catalogo.py).
TIPOS = ("juego", "juego_dlc", "dlc", "otro")
CATEGORIAS_DIFICULTAD = (
    "remasterizacion", "edicion", "secuela", "numeros_romanos",
    "subtitulo", "caracteres_especiales", "otro",
)
ORIGENES = ("manual", "descubrimiento")

# Campos que puede tener cada juego y cada plataforma. Cualquier otro se rechaza: así un error de
# tipeo ("titulos_alternativo") se detecta en vez de ignorarse en silencio.
CAMPOS_JUEGO = {
    "clave", "titulo", "titulos_alternativos", "tipo", "plataformas",
    "caso_dificil", "activo", "origen", "descubierto_por",
}
CAMPOS_PLATAFORMA = {"plataforma", "fecha_lanzamiento", "msrp"}

# Clave: minúsculas, números y guiones simples, sin guion al inicio ni al final ("the-witcher-3").
PATRON_CLAVE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Fecha con formato estricto AAAA-MM-DD.
PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Mínimos que exige el enunciado (sección 4).
MINIMO_JUEGOS = 500
MINIMO_FAMILIAS = 3
MINIMO_CASOS_DIFICILES = 50


class ErrorCatalogo(ValueError):
    """El catálogo tiene problemas. ``problemas`` los lista todos (no solo el primero)."""

    def __init__(self, problemas: list[str]) -> None:
        super().__init__(f"El catálogo tiene {len(problemas)} problema(s):\n- " + "\n- ".join(problemas))
        self.problemas = problemas


@dataclass(frozen=True)
class PlataformaJuego:
    """Una plataforma en la que sale un juego."""

    codigo: str
    fecha_lanzamiento: str | None   # 'AAAA-MM-DD' o None si aún no se conoce.
    msrp_centavos: int | None       # 5999 = 59.99 USD; None si aún no se conoce.


@dataclass(frozen=True)
class EntradaJuego:
    """Un juego del catálogo, ya validado."""

    clave: str
    titulo: str
    titulos_alternativos: tuple[str, ...]
    tipo: str
    plataformas: tuple[PlataformaJuego, ...]
    categoria_dificultad: str | None
    activo: bool
    origen: str
    descubierto_por: str | None
    archivo: str                    # De qué archivo salió (para mensajes de error).


@dataclass(frozen=True)
class ResumenCarga:
    """Qué cambió en la base al cargar el catálogo."""

    total: int          # Juegos leídos de los archivos.
    nuevos: int         # Claves que no estaban en la base.
    actualizados: int   # Claves que ya estaban (sus datos se reescriben con los del archivo).
    desactivados: int   # Juegos activos antes que ahora quedaron inactivos.


@dataclass(frozen=True)
class Requisito:
    """Un mínimo del enunciado y cuánto se tiene."""

    descripcion: str
    actual: int
    minimo: int

    @property
    def cumplido(self) -> bool:
        return self.actual >= self.minimo


# ---------------------------------------------------------------------------
# 1. Lectura y validación
# ---------------------------------------------------------------------------


def _dolares_a_centavos(valor: Any, donde: str, problemas: list[str]) -> int | None:
    """Convierte un MSRP en dólares (59.99) a centavos (5999) sin errores de redondeo.

    Los números con decimales del JSON se leen como ``Decimal`` (ver ``leer_catalogo``), no como
    ``float``: con float, 0.29 * 100 da 28.999999999999996 y se guardaría 28 en vez de 29 centavos.
    """
    if isinstance(valor, bool) or not isinstance(valor, (int, Decimal)) or valor <= 0:
        problemas.append(f"{donde}: 'msrp' debe ser un número mayor que 0, se recibió {valor!r}")
        return None
    valor = Decimal(valor)
    if valor != valor.quantize(Decimal("0.01")):
        problemas.append(f"{donde}: 'msrp' admite como máximo 2 decimales, se recibió {valor}")
        return None
    return int(valor * 100)


def _validar_plataforma(
    datos: Any, donde: str, plataformas_validas: set[str], problemas: list[str]
) -> PlataformaJuego | None:
    """Valida una entrada de la lista ``plataformas`` de un juego."""
    if not isinstance(datos, dict):
        problemas.append(f"{donde}: cada plataforma debe ser un objeto {{...}}")
        return None
    for campo in sorted(set(datos) - CAMPOS_PLATAFORMA):
        problemas.append(f"{donde}: campo desconocido '{campo}'")

    codigo = datos.get("plataforma")
    if not isinstance(codigo, str) or codigo not in plataformas_validas:
        problemas.append(
            f"{donde}: plataforma {codigo!r} no existe; use una de {sorted(plataformas_validas)}"
        )

    fecha = datos.get("fecha_lanzamiento")
    if fecha is not None:
        # Dos comprobaciones: el patrón exige exactamente AAAA-MM-DD (fromisoformat también aceptaría
        # "20180420"), y fromisoformat rechaza fechas que no existen, como "2018-02-30".
        try:
            if not isinstance(fecha, str) or not PATRON_FECHA.match(fecha):
                raise ValueError
            date.fromisoformat(fecha)
        except ValueError:
            problemas.append(f"{donde}: 'fecha_lanzamiento' debe ser una fecha real con formato AAAA-MM-DD, se recibió {fecha!r}")
            fecha = None

    msrp = datos.get("msrp")
    centavos = _dolares_a_centavos(msrp, donde, problemas) if msrp is not None else None
    return PlataformaJuego(codigo=codigo, fecha_lanzamiento=fecha, msrp_centavos=centavos)


def _validar_juego(
    datos: Any, donde: str, archivo: str, plataformas_validas: set[str], problemas: list[str]
) -> EntradaJuego | None:
    """Valida un juego. Agrega a ``problemas`` todo lo que encuentre y devuelve la entrada."""
    if not isinstance(datos, dict):
        problemas.append(f"{donde}: cada juego debe ser un objeto {{...}}")
        return None
    cantidad_antes = len(problemas)

    for campo in sorted(set(datos) - CAMPOS_JUEGO):
        problemas.append(f"{donde}: campo desconocido '{campo}'")

    clave = datos.get("clave")
    if not isinstance(clave, str) or not PATRON_CLAVE.match(clave):
        problemas.append(f"{donde}: 'clave' debe usar minúsculas, números y guiones (p. ej. 'the-witcher-3'), se recibió {clave!r}")
    # A partir de aquí los mensajes incluyen la clave, para encontrar el juego más fácil.
    donde = f"{donde} ({clave})"

    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        problemas.append(f"{donde}: 'titulo' es obligatorio")
        titulo = ""

    alternativos = datos.get("titulos_alternativos", [])
    if not isinstance(alternativos, list) or not all(isinstance(t, str) and t.strip() for t in alternativos):
        problemas.append(f"{donde}: 'titulos_alternativos' debe ser una lista de textos no vacíos")
        alternativos = []
    # dict.fromkeys quita repetidos conservando el orden.
    alternativos = tuple(dict.fromkeys(t.strip() for t in alternativos))

    tipo = datos.get("tipo", "juego")
    if tipo not in TIPOS:
        problemas.append(f"{donde}: 'tipo' debe ser uno de {TIPOS}, se recibió {tipo!r}")

    lista_plataformas = datos.get("plataformas")
    plataformas: list[PlataformaJuego] = []
    if not isinstance(lista_plataformas, list) or not lista_plataformas:
        problemas.append(f"{donde}: 'plataformas' debe ser una lista con al menos una plataforma")
    else:
        for posicion, item in enumerate(lista_plataformas):
            plataforma = _validar_plataforma(item, f"{donde} plataforma #{posicion + 1}", plataformas_validas, problemas)
            if plataforma is not None:
                plataformas.append(plataforma)
        codigos = [p.codigo for p in plataformas]
        if len(codigos) != len(set(codigos)):
            problemas.append(f"{donde}: hay plataformas repetidas")

    categoria = datos.get("caso_dificil")
    if categoria is not None and categoria not in CATEGORIAS_DIFICULTAD:
        problemas.append(f"{donde}: 'caso_dificil' debe ser uno de {CATEGORIAS_DIFICULTAD}, se recibió {categoria!r}")

    activo = datos.get("activo", True)
    if not isinstance(activo, bool):
        problemas.append(f"{donde}: 'activo' debe ser true o false")

    origen = datos.get("origen", "manual")
    if origen not in ORIGENES:
        problemas.append(f"{donde}: 'origen' debe ser uno de {ORIGENES}, se recibió {origen!r}")
    descubierto_por = datos.get("descubierto_por")
    if origen == "descubrimiento" and not descubierto_por:
        problemas.append(f"{donde}: si 'origen' es 'descubrimiento', falta 'descubierto_por'")

    if len(problemas) > cantidad_antes:
        return None  # Este juego tuvo errores: no se devuelve una entrada a medio validar.
    return EntradaJuego(
        clave=clave,
        titulo=titulo.strip(),
        titulos_alternativos=alternativos,
        tipo=tipo,
        plataformas=tuple(plataformas),
        categoria_dificultad=categoria,
        activo=activo,
        origen=origen,
        descubierto_por=descubierto_por,
        archivo=archivo,
    )


def leer_catalogo(carpeta: Path, plataformas_validas: set[str]) -> list[EntradaJuego]:
    """Lee y valida todos los ``*.json`` de ``carpeta``.

    :param plataformas_validas: códigos de plataforma aceptados (se leen de la tabla ``plataforma``).
    :raises ErrorCatalogo: con TODOS los problemas encontrados, si hay al menos uno.
    """
    problemas: list[str] = []
    entradas: list[EntradaJuego] = []
    # sorted: el orden de lectura no depende del sistema operativo, así los mensajes son repetibles.
    for ruta in sorted(Path(carpeta).glob("*.json")):
        try:
            # parse_float=Decimal: los decimales del JSON se leen exactos (ver _dolares_a_centavos).
            contenido = json.loads(ruta.read_text(encoding="utf-8"), parse_float=Decimal)
        except json.JSONDecodeError as error:
            problemas.append(f"{ruta.name}: JSON inválido en línea {error.lineno}, columna {error.colno}: {error.msg}")
            continue
        if not isinstance(contenido, list):
            problemas.append(f"{ruta.name}: el archivo debe contener una lista [ ... ] de juegos")
            continue
        for posicion, datos in enumerate(contenido):
            entrada = _validar_juego(datos, f"{ruta.name} #{posicion + 1}", ruta.name, plataformas_validas, problemas)
            if entrada is not None:
                entradas.append(entrada)

    # Claves repetidas, aunque estén en archivos distintos.
    vistas: dict[str, str] = {}
    for entrada in entradas:
        if entrada.clave in vistas:
            problemas.append(f"clave '{entrada.clave}' repetida en {vistas[entrada.clave]} y {entrada.archivo}")
        else:
            vistas[entrada.clave] = entrada.archivo

    if problemas:
        raise ErrorCatalogo(problemas)
    return entradas


# ---------------------------------------------------------------------------
# 2. Carga en la base
# ---------------------------------------------------------------------------


def cargar_en_bd(conexion: sqlite3.Connection, entradas: list[EntradaJuego], ahora: str) -> ResumenCarga:
    """Sincroniza la tabla ``juego`` (y sus tablas hijas) con las entradas del catálogo.

    Todo ocurre en UNA transacción: si algo falla a la mitad, la base queda exactamente como estaba
    (no hay catálogos a medio cargar).

    Los juegos que están en la base pero ya no en los archivos quedan con ``activo = 0``. No se borran,
    para conservar su historial de precios.

    :param ahora: fecha ISO-8601 en UTC que se guarda como ``agregado_en`` de los juegos nuevos.
    :raises ErrorCatalogo: si un ``descubierto_por`` no existe en la tabla ``fuente``.
    """
    # Se verifica ANTES de escribir nada, para no empezar una carga que va a fallar.
    fuentes = {fila["codigo"]: fila["id"] for fila in conexion.execute("SELECT id, codigo FROM fuente")}
    desconocidas = sorted({e.descubierto_por for e in entradas if e.descubierto_por and e.descubierto_por not in fuentes})
    if desconocidas:
        raise ErrorCatalogo([f"'descubierto_por' usa fuentes que no existen en la tabla fuente: {desconocidas}"])

    claves_previas = {fila["clave"] for fila in conexion.execute("SELECT clave FROM juego")}
    activas_previas = {fila["clave"] for fila in conexion.execute("SELECT clave FROM juego WHERE activo = 1")}

    # "with conexion": abre una transacción y hace COMMIT al salir; si hay una excepción, ROLLBACK.
    with conexion:
        # Paso 1: se marca todo como inactivo. Paso 2: cada juego del catálogo vuelve a activarse
        # (si su entrada lo indica). Lo que no esté en los archivos queda inactivo.
        conexion.execute("UPDATE juego SET activo = 0")
        for entrada in entradas:
            # INSERT ... ON CONFLICT ... DO UPDATE ("upsert"): inserta si la clave es nueva o actualiza
            # si ya existía, en una sola sentencia. agregado_en NO se actualiza: conserva la fecha original.
            # RETURNING id devuelve el id del juego en ambos casos.
            juego_id = conexion.execute(
                """
                INSERT INTO juego (clave, titulo_canonico, tipo, es_caso_dificil, categoria_dificultad,
                                   origen, descubierto_por, activo, agregado_en)
                VALUES (:clave, :titulo, :tipo, :es_caso_dificil, :categoria, :origen, :descubierto_por,
                        :activo, :ahora)
                ON CONFLICT (clave) DO UPDATE SET
                    titulo_canonico      = excluded.titulo_canonico,
                    tipo                 = excluded.tipo,
                    es_caso_dificil      = excluded.es_caso_dificil,
                    categoria_dificultad = excluded.categoria_dificultad,
                    origen               = excluded.origen,
                    descubierto_por      = excluded.descubierto_por,
                    activo               = excluded.activo
                RETURNING id
                """,
                {
                    "clave": entrada.clave,
                    "titulo": entrada.titulo,
                    "tipo": entrada.tipo,
                    "es_caso_dificil": int(entrada.categoria_dificultad is not None),
                    "categoria": entrada.categoria_dificultad,
                    "origen": entrada.origen,
                    "descubierto_por": fuentes.get(entrada.descubierto_por),
                    "activo": int(entrada.activo),
                    "ahora": ahora,
                },
            ).fetchone()[0]

            # Títulos alternativos y plataformas se reemplazan completos por los del archivo.
            # (No son observaciones: aquí sí está bien borrar y volver a insertar.)
            conexion.execute("DELETE FROM titulo_alternativo WHERE juego_id = ?", (juego_id,))
            conexion.executemany(
                "INSERT INTO titulo_alternativo (juego_id, titulo) VALUES (?, ?)",
                [(juego_id, titulo) for titulo in entrada.titulos_alternativos],
            )
            conexion.execute("DELETE FROM juego_plataforma WHERE juego_id = ?", (juego_id,))
            conexion.executemany(
                "INSERT INTO juego_plataforma (juego_id, plataforma_codigo, fecha_lanzamiento, msrp_centavos) "
                "VALUES (?, ?, ?, ?)",
                [(juego_id, p.codigo, p.fecha_lanzamiento, p.msrp_centavos) for p in entrada.plataformas],
            )

    claves_nuevas = {e.clave for e in entradas}
    activas_ahora = {e.clave for e in entradas if e.activo}
    return ResumenCarga(
        total=len(entradas),
        nuevos=len(claves_nuevas - claves_previas),
        actualizados=len(claves_nuevas & claves_previas),
        desactivados=len(activas_previas - activas_ahora),
    )


# ---------------------------------------------------------------------------
# 3. Verificación de los mínimos del enunciado
# ---------------------------------------------------------------------------


def verificar_requisitos(conexion: sqlite3.Connection) -> list[Requisito]:
    """Cuenta, sobre los juegos ACTIVOS, cuánto falta para cumplir la sección 4 del enunciado."""

    def contar(sql: str) -> int:
        return conexion.execute(sql).fetchone()[0]

    activos = contar("SELECT COUNT(*) FROM juego WHERE activo = 1")
    # Para los campos que pueden faltar, el "mínimo" es tener todos los juegos completos.
    con_msrp = contar(
        "SELECT COUNT(DISTINCT j.id) FROM juego j JOIN juego_plataforma jp ON jp.juego_id = j.id "
        "WHERE j.activo = 1 AND jp.msrp_centavos IS NOT NULL"
    )
    con_fecha = contar(
        "SELECT COUNT(DISTINCT j.id) FROM juego j JOIN juego_plataforma jp ON jp.juego_id = j.id "
        "WHERE j.activo = 1 AND jp.fecha_lanzamiento IS NOT NULL"
    )
    return [
        Requisito("Juegos activos", activos, MINIMO_JUEGOS),
        Requisito(
            "Familias de plataforma distintas",
            contar(
                "SELECT COUNT(DISTINCT p.familia) FROM juego j "
                "JOIN juego_plataforma jp ON jp.juego_id = j.id "
                "JOIN plataforma p ON p.codigo = jp.plataforma_codigo WHERE j.activo = 1"
            ),
            MINIMO_FAMILIAS,
        ),
        Requisito(
            "Casos difíciles", contar("SELECT COUNT(*) FROM juego WHERE activo = 1 AND es_caso_dificil = 1"),
            MINIMO_CASOS_DIFICILES,
        ),
        Requisito("Juegos con MSRP en al menos una plataforma", con_msrp, activos),
        Requisito("Juegos con fecha de lanzamiento", con_fecha, activos),
    ]
