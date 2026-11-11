"""Etapa 5 · Publicar: genera el sitio estático a partir de la base de datos.

Salida (carpeta ``[rutas] sitio``)::

    index.html, juego.html, metricas.html, app.js, estilos.css   <- copiados de radar/sitio/estatico/
    datos/juegos.json                                            <- tarjetas de la página de resultados
    datos/juegos/<clave>.json                                    <- detalle de cada juego
    datos/metricas.json                                          <- panel de métricas

Reglas del enunciado que se aplican aquí (sección 9 y ADR-005):
- Solo se publican juegos con precio en **2 o más tiendas**.
- Solo cuentan precios de productos con emparejamiento **aceptado** (los dudosos van al panel).
- "En oferta": precio actual menor que el precio regular que muestra la tienda; si la tienda no muestra
  precio regular, menor que el MSRP de la plataforma.
- "Mínimo histórico": el mejor precio actual iguala o mejora el menor precio registrado, y hay al menos
  dos fechas de observación (con una sola, la etiqueta no informaría nada).
- Cada precio muestra cuándo se obtuvo y si está desactualizado (no es de la última ejecución en vivo).
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from radar.pipeline.modelos import ErrorEtapa
from radar.red.modelos import ahora_utc

ESTATICO = Path(__file__).with_name("estatico")
MINIMO_TIENDAS = 2
NOMBRES_TIENDA = {"steam": "Steam", "gog": "GOG", "nintendo": "Nintendo eShop", "bestbuy": "Best Buy"}
NOMBRES_FAMILIA = {"playstation": "PlayStation", "nintendo": "Nintendo", "xbox": "Xbox", "pc": "PC"}
NOTA_DURACION = ("No disponible: los términos de uso de How Long To Beat prohíben extraer sus datos con "
                 "programas automáticos. Ver ADR-004 y ADR-007 (respaldo con IGDB pendiente de credenciales).")
CLAVE_VALIDA = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _escribir_json(ruta: Path, datos: object) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def portada_steam(url_producto: str | None) -> str | None:
    """Portada vertical de 600x900 que Steam publica para cada juego, a partir de la URL del producto.

    Por qué no solo Metacritic: su servicio de imágenes está firmado y solo entrega 96x144 y 192x288 (otros
    tamaños dan 403), o el original de ~3,7 MB. 192 px se ve borroso en una tarjeta de ~220 px en pantallas con
    escala 125-150 %, y el original haría pesar cada página de resultados decenas de MB.

    Se usa ``library_600x900_2x.jpg`` y no ``library_600x900.jpg``: medido el 2026-11-11 sobre los 55 juegos
    publicados con Steam, la segunda entrega en realidad 300x450 y la "_2x" sí 600x900 (~100 KB, proporción 2:3).
    Unos pocos juegos no tienen ninguna (404); para ellos el sitio pasa a la siguiente imagen de la lista.
    """
    encontrado = re.search(r"store\.steampowered\.com/app/(\d+)/", url_producto or "")
    if not encontrado:
        return None
    return (f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{encontrado.group(1)}"
            "/library_600x900_2x.jpg")


def _candidatas(pares: list[tuple]) -> list[dict]:
    """Lista de imágenes candidatas ``[{"url", "hd", "solo_vertical"}]`` sin vacías ni repetidas, en orden de preferencia.

    Cada par es ``(url, hd)`` o ``(url, hd, solo_vertical)``. ``hd`` es una versión más grande de la misma imagen
    que el navegador puede preferir en pantallas con escala. ``solo_vertical`` marca imágenes que solo sirven si son
    verticales: las de Best Buy cuadradas son fotos del producto (a veces ampliadas), y su tamaño en píxeles no
    refleja su calidad, así que no deben competir como respaldo con el arte cuadrado de Nintendo.
    """
    vistas, resultado = set(), []
    for par in pares:
        url, hd, solo_vertical = (*par, False)[:3]
        if url and url not in vistas:
            vistas.add(url)
            resultado.append({"url": url, "hd": hd if hd and hd != url else None, "solo_vertical": solo_vertical})
    return resultado


def original_metacritic(url: str | None) -> str | None:
    """Imagen original (alta resolución) a partir de una URL redimensionada de Metacritic.

    '/a/img/resize/<firma>/catalog/...jpg?width=192...' -> '/a/img/catalog/...jpg'. Pesa ~3,7 MB: se usa solo en
    la página de detalle (una imagen), nunca en la rejilla de resultados.
    """
    if not url or "/a/img/resize/" not in url:
        return url
    return re.sub(r"/a/img/resize/[0-9a-f]+/", "/a/img/", url).split("?", 1)[0]


def _copiar_estaticos(destino: Path) -> None:
    """Copia HTML, JS y CSS; en los HTML agrega a app.js y estilos.css una huella de su contenido (``?v=...``).

    Sin la huella, el navegador sigue usando la copia vieja de app.js que guardó en su caché, y un visitante no ve
    los cambios del sitio hasta que fuerce la recarga. Con ella, si el archivo cambia, cambia su URL.
    """
    huellas = {
        nombre: hashlib.sha256((ESTATICO / nombre).read_bytes()).hexdigest()[:10]
        for nombre in ("app.js", "estilos.css")
    }
    for archivo in ESTATICO.iterdir():
        if archivo.suffix != ".html":
            shutil.copy2(archivo, destino / archivo.name)
            continue
        texto = archivo.read_text(encoding="utf-8")
        texto = texto.replace('src="app.js"', f'src="app.js?v={huellas["app.js"]}"')
        texto = texto.replace('href="estilos.css"', f'href="estilos.css?v={huellas["estilos.css"]}"')
        (destino / archivo.name).write_text(texto, encoding="utf-8")


def historial_por_dia(observaciones: list[tuple[str, int]]) -> list[list]:
    """[(fecha ISO con hora, centavos), ...] ordenadas -> [["AAAA-MM-DD", centavos], ...] con el ÚLTIMO precio de cada día.

    Las fechas están en UTC (como se guardan en la base), así que el "día" es el día UTC.
    """
    por_dia: dict[str, int] = {}
    for fecha, centavos in observaciones:  # Vienen ordenadas por fecha: la última del día sobrescribe a las demás.
        por_dia[fecha[:10]] = centavos
    return [[dia, centavos] for dia, centavos in sorted(por_dia.items())]


def minimos_por_formato(historial_juego: dict[int, list], formato_de_producto: dict[int, str],
                        plataforma_de_producto: dict[int, str], msrp: dict[str, int | None]) -> dict[str, dict]:
    """Precio más bajo registrado por formato: {"digital": {"precio", "fecha", "descuento"}, "fisico": {...}}.

    ``descuento`` es el % respecto al MSRP de la plataforma de ese producto (0 si no hay MSRP). Ante empate de
    precio gana la fecha más antigua (la primera vez que se alcanzó).
    """
    mejores: dict[str, tuple] = {}
    for producto, observaciones in historial_juego.items():
        formato = formato_de_producto[producto]
        for fecha, centavos in observaciones:
            clave = (centavos, fecha)
            if formato not in mejores or clave < mejores[formato][0]:
                mejores[formato] = (clave, plataforma_de_producto[producto])
    resultado = {}
    for formato, ((centavos, fecha), plataforma) in sorted(mejores.items()):
        referencia = msrp.get(plataforma)
        resultado[formato] = {"precio": centavos, "fecha": fecha[:10],
                              "descuento": _descuento(centavos, referencia) if referencia else 0}
    return resultado


def _descuento(actual: int | None, regular: int | None) -> int:
    if actual is None or not regular or regular <= actual:
        return 0
    return round(100 * (regular - actual) / regular)


def generar_sitio(conexion: sqlite3.Connection, destino: Path, mediciones: Path | None = None) -> dict:
    """Genera el sitio completo. Devuelve un resumen (juegos publicados, etc.)."""
    destino.mkdir(parents=True, exist_ok=True)
    _copiar_estaticos(destino)
    generado = ahora_utc().isoformat()

    plataformas = {f["codigo"]: (f["nombre"], f["familia"]) for f in conexion.execute("SELECT * FROM plataforma")}

    # Último precio de cada producto ACEPTADO (con marca de desactualizado), agrupado por juego.
    precios_por_juego: dict[int, list] = defaultdict(list)
    for fila in conexion.execute(
        """
        SELECT up.*, p.juego_id, p.url, p.plataforma_codigo, p.formato, f.codigo AS tienda
        FROM v_ultimo_precio up
        JOIN producto_tienda p ON p.id = up.producto_id
        JOIN fuente f ON f.id = p.fuente_id
        WHERE p.estado_emparejamiento = 'aceptado'
        """
    ):
        precios_por_juego[fila["juego_id"]].append(fila)

    # Historial completo por producto aceptado (para el gráfico y el mínimo histórico).
    historial: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    tienda_de_producto: dict[int, str] = {}
    formato_de_producto: dict[int, str] = {}
    plataforma_de_producto: dict[int, str] = {}
    for fila in conexion.execute(
        """
        SELECT p.juego_id, p.id AS producto_id, f.codigo AS tienda, p.formato, p.plataforma_codigo,
               o.obtenida_en, o.precio_actual_centavos
        FROM observacion_precio o
        JOIN producto_tienda p ON p.id = o.producto_id
        JOIN fuente f ON f.id = p.fuente_id
        WHERE p.estado_emparejamiento = 'aceptado'
        ORDER BY o.obtenida_en
        """
    ):
        historial[fila["juego_id"]][fila["producto_id"]].append((fila["obtenida_en"], fila["precio_actual_centavos"]))
        formato_texto = "físico" if fila["formato"] == "fisico" else "digital"
        tienda_de_producto[fila["producto_id"]] = (
            f'{NOMBRES_TIENDA.get(fila["tienda"], fila["tienda"])} ({plataformas.get(fila["plataforma_codigo"], ("?",))[0]}, {formato_texto})'
        )
        formato_de_producto[fila["producto_id"]] = fila["formato"]
        plataforma_de_producto[fila["producto_id"]] = fila["plataforma_codigo"]

    # Última calificación por juego, fuente y plataforma.
    calificaciones: dict[int, list] = defaultdict(list)
    for fila in conexion.execute(
        """
        SELECT * FROM (
            SELECT c.*, f.nombre AS fuente, ROW_NUMBER() OVER (
                PARTITION BY c.juego_id, c.fuente_id, COALESCE(c.plataforma_codigo, '')
                ORDER BY c.obtenida_en DESC, c.id DESC) AS posicion
            FROM observacion_calificacion c JOIN fuente f ON f.id = c.fuente_id)
        WHERE posicion = 1
        """
    ):
        calificaciones[fila["juego_id"]].append(fila)

    plataformas_juego: dict[int, list] = defaultdict(list)
    for fila in conexion.execute("SELECT * FROM juego_plataforma ORDER BY plataforma_codigo"):
        plataformas_juego[fila["juego_id"]].append(fila)

    # Portada de mejor calidad de cada juego, en orden de preferencia (ver ``portada_steam``):
    # 1) Steam 600x900 (producto aceptado); 2) carátula de Best Buy 555x900 (producto aceptado); 3) Metacritic.
    # Si hay varios productos, el de URL menor, para que el resultado sea siempre el mismo.
    steam_por_juego: dict[int, str] = {}
    for fila in conexion.execute(
        "SELECT p.juego_id, MIN(p.url) AS url FROM producto_tienda p JOIN fuente f ON f.id = p.fuente_id "
        "WHERE f.codigo = 'steam' AND p.estado_emparejamiento = 'aceptado' GROUP BY p.juego_id"
    ):
        steam_por_juego[fila["juego_id"]] = fila["url"]
    caratula_por_juego: dict[int, str] = {}
    cuadrada_nintendo_por_juego: dict[int, str] = {}
    for fila in conexion.execute(
        "SELECT p.juego_id, f.codigo, p.imagen_url FROM producto_tienda p JOIN fuente f ON f.id = p.fuente_id "
        "WHERE f.codigo IN ('bestbuy', 'nintendo') AND p.estado_emparejamiento = 'aceptado' "
        "AND p.imagen_url IS NOT NULL ORDER BY p.juego_id, p.url"
    ):
        destino_imagen = caratula_por_juego if fila["codigo"] == "bestbuy" else cuadrada_nintendo_por_juego
        destino_imagen.setdefault(fila["juego_id"], fila["imagen_url"])

    tarjetas = []
    sin_precio_suficiente = 0
    carpeta_juegos = destino / "datos" / "juegos"
    if carpeta_juegos.exists():
        shutil.rmtree(carpeta_juegos)  # Se regenera completa: no quedan detalles de juegos ya no publicados.
    for juego in conexion.execute("SELECT * FROM juego WHERE activo = 1 ORDER BY clave"):
        precios = [p for p in precios_por_juego.get(juego["id"], []) if p["precio_actual_centavos"] is not None]
        if len({p["tienda"] for p in precios}) < MINIMO_TIENDAS or not CLAVE_VALIDA.match(juego["clave"]):
            sin_precio_suficiente += 1
            continue
        msrp = {p["plataforma_codigo"]: p["msrp_centavos"] for p in plataformas_juego[juego["id"]]}

        def en_oferta(p) -> bool:
            if p["precio_regular_centavos"] is not None and p["precio_regular_centavos"] != p["precio_actual_centavos"]:
                return p["precio_actual_centavos"] < p["precio_regular_centavos"]
            referencia = msrp.get(p["plataforma_codigo"])
            return referencia is not None and p["precio_actual_centavos"] < referencia

        precios.sort(key=lambda p: (p["precio_actual_centavos"], p["tienda"], p["url"]))
        mejor = precios[0]
        observaciones = [obs for serie in historial[juego["id"]].values() for obs in serie]
        minimo = min((c for _, c in observaciones), default=None)
        fechas_distintas = len({f[:10] for f, _ in observaciones})
        # Imágenes candidatas en orden de preferencia. El navegador elige según la CALIDAD REAL de cada una (ver
        # ``imagen`` en app.js): la primera vertical con resolución suficiente, o la de mayor resolución.
        steam_portada = portada_steam(steam_por_juego.get(juego["id"]))
        caratula = caratula_por_juego.get(juego["id"])
        cuadrada_nintendo = cuadrada_nintendo_por_juego.get(juego["id"])
        metacritic_imagen = juego["imagen_url"]
        metascores = [c["puntaje"] for c in calificaciones[juego["id"]] if c["fuente"] == "Metacritic"]
        steam = [c["puntaje"] for c in calificaciones[juego["id"]] if c["fuente"] == "Reseñas de usuarios de Steam"]

        tarjetas.append({
            "clave": juego["clave"],
            "titulo": juego["titulo_canonico"],
            "tipo": juego["tipo"],
            # Steam 600x900 -> carátula de Best Buy -> Metacritic 192x288 (con su original como "hd", que solo se
            # descarga en pantallas con escala) -> arte cuadrado de Nintendo 1024x1024.
            "imagenes": _candidatas([
                (steam_portada, None), (caratula, None, True),
                (metacritic_imagen, original_metacritic(metacritic_imagen)), (cuadrada_nintendo, None),
            ]),
            "plataformas": [p["plataforma_codigo"] for p in plataformas_juego[juego["id"]]],
            "familias": sorted({plataformas[p["plataforma_codigo"]][1] for p in plataformas_juego[juego["id"]]}),
            "formatos": sorted({p["formato"] for p in precios}),
            "tiendas": sorted({p["tienda"] for p in precios}),
            "tienda": mejor["tienda"],
            "precio": mejor["precio_actual_centavos"],
            "regular": mejor["precio_regular_centavos"],
            "descuento": _descuento(mejor["precio_actual_centavos"], mejor["precio_regular_centavos"]),
            "en_oferta": en_oferta(mejor),
            "minimo_historico": minimo is not None and fechas_distintas >= 2 and mejor["precio_actual_centavos"] <= minimo,
            "desactualizado": any(p["desactualizado"] for p in precios),
            "metascore": round(max(metascores)) if metascores else None,
            "steam": round(steam[0]) if steam else None,
        })
        _escribir_json(carpeta_juegos / f'{juego["clave"]}.json', {
            "generado_en": generado,
            "clave": juego["clave"],
            "titulo": juego["titulo_canonico"],
            "tipo": juego["tipo"],
            # En el detalle hay UNA sola imagen: se puede pedir directamente el original de Metacritic.
            "imagenes": _candidatas([
                (steam_portada, None), (caratula, None, True),
                (original_metacritic(metacritic_imagen), None), (cuadrada_nintendo, None),
            ]),
            "precios": [{
                "tienda": NOMBRES_TIENDA.get(p["tienda"], p["tienda"]),
                "url": p["url"],
                "plataforma": plataformas.get(p["plataforma_codigo"], (p["plataforma_codigo"],))[0],
                "formato": p["formato"],
                "precio": p["precio_actual_centavos"],
                "regular": p["precio_regular_centavos"],
                "en_oferta": en_oferta(p),
                "obtenido_en": p["obtenida_en"],
                "desactualizado": bool(p["desactualizado"]),
            } for p in precios],
            "plataformas": [{
                "nombre": plataformas[p["plataforma_codigo"]][0],
                "fecha_lanzamiento": p["fecha_lanzamiento"],
                "msrp": p["msrp_centavos"],
            } for p in plataformas_juego[juego["id"]]],
            "calificaciones": [{
                "fuente": c["fuente"],
                "plataforma": plataformas.get(c["plataforma_codigo"], (None,))[0],
                "puntaje": round(c["puntaje"]),
                "escala": c["escala"],
                "resenas": c["cantidad_resenas"],
                "obtenido_en": c["obtenida_en"],
            } for c in sorted(calificaciones[juego["id"]], key=lambda c: (c["fuente"], c["plataforma_codigo"] or ""))],
            # Un punto por tienda POR DÍA (el último precio de ese día). Antes se enviaba cada observación con su
            # hora exacta: con varias ejecuciones el mismo día, el gráfico mostraba puntos separados por minutos
            # y sin ninguna tendencia que leer.
            "historial": [{"tienda": tienda_de_producto[producto], "formato": formato_de_producto[producto],
                           "puntos": historial_por_dia(puntos)}
                          for producto, puntos in sorted(historial[juego["id"]].items())],
            # "Mínimo histórico" por formato (como el resumen de DekuDeals), con el % respecto al MSRP.
            "minimos": minimos_por_formato(historial[juego["id"]], formato_de_producto, plataforma_de_producto, msrp),
            "dias_con_historial": len({fecha[:10] for fecha, _ in observaciones}),
            "duracion_nota": NOTA_DURACION,
        })

    familias_usadas = sorted({f for t in tarjetas for f in t["familias"]})
    _escribir_json(destino / "datos" / "juegos.json", {
        "generado_en": generado,
        "tiendas": {codigo: nombre for codigo, nombre in NOMBRES_TIENDA.items() if any(codigo in t["tiendas"] for t in tarjetas)},
        "familias": {f: NOMBRES_FAMILIA.get(f, f) for f in familias_usadas},
        "plataformas": {codigo: nombre for codigo, (nombre, _) in plataformas.items()},
        "juegos": tarjetas,
    })
    generar_metricas(conexion, destino, mediciones)
    return {"publicados": len(tarjetas), "sin_precio_suficiente": sin_precio_suficiente}


def _mediciones(carpeta: Path | None) -> list[dict]:
    """Curvas de speedup a partir de CSV con columnas: etapa, modo, workers, repeticion, segundos.

    ``modo`` es 'secuencial' (da T_sec) o el modo paralelo medido. Se usa la MEDIANA de las repeticiones.
    """
    if carpeta is None or not carpeta.exists():
        return []
    tiempos: dict[str, dict] = defaultdict(lambda: {"sec": [], "par": defaultdict(list)})
    for archivo in sorted(carpeta.glob("*.csv")):
        with archivo.open(encoding="utf-8") as entrada:
            for fila in csv.DictReader(entrada):
                destino = tiempos[fila["etapa"]]
                if fila["modo"] == "secuencial":
                    destino["sec"].append(float(fila["segundos"]))
                else:
                    destino["par"][int(fila["workers"])].append(float(fila["segundos"]))
    curvas = []
    for etapa, datos in sorted(tiempos.items()):
        if not datos["sec"] or 1 not in datos["par"]:
            continue
        t_sec = statistics.median(datos["sec"])
        t_par_1 = statistics.median(datos["par"][1])
        puntos = []
        for p in sorted(datos["par"]):
            t = statistics.median(datos["par"][p])
            s_rel = t_par_1 / t
            puntos.append({"p": p, "s_abs": t_sec / t, "s_rel": s_rel, "eficiencia": s_rel / p})
        curvas.append({"etapa": etapa, "puntos": puntos})
    return curvas


def generar_metricas(conexion: sqlite3.Connection, destino: Path, mediciones: Path | None = None,
                     errores: tuple[ErrorEtapa, ...] = ()) -> None:
    """Genera ``datos/metricas.json`` (panel de métricas). Se puede llamar sola, sin regenerar todo."""
    ultima = conexion.execute("SELECT * FROM ejecucion ORDER BY id DESC LIMIT 1").fetchone()

    def duracion(fila) -> float | None:
        if not fila or not fila["terminada_en"]:
            return None
        return (datetime.fromisoformat(fila["terminada_en"]) - datetime.fromisoformat(fila["iniciada_en"])).total_seconds()

    etapas = solicitudes = fallidos = []
    if ultima:
        etapas = [{"etapa": f["etapa"], "elementos": f["elementos"], "ocupado_s": f["duracion_segundos"],
                   "ventana_s": f["ventana_segundos"]}
                  for f in conexion.execute(
                      "SELECT * FROM ejecucion_etapa WHERE ejecucion_id = ? ORDER BY CASE etapa "
                      "WHEN 'descubrir' THEN 0 WHEN 'descargar' THEN 1 WHEN 'parsear' THEN 2 WHEN 'emparejar' THEN 3 "
                      "WHEN 'persistir' THEN 4 ELSE 5 END", (ultima["id"],))]
        solicitudes = [dict(f) for f in conexion.execute(
            "SELECT dominio, exitosas, reintentos, fallidas, desde_almacen, bloqueadas_robots "
            "FROM ejecucion_metricas_dominio WHERE ejecucion_id = ? ORDER BY dominio", (ultima["id"],))]
        fallidos = [{"url": f["url"], "mensaje": f["mensaje"], "resuelto": bool(f["resuelto_al_final"])}
                    for f in conexion.execute("SELECT * FROM fallo WHERE ejecucion_id = ? ORDER BY url", (ultima["id"],))]

    dudosos = [{"juego": f["titulo_canonico"], "tienda": NOMBRES_TIENDA.get(f["tienda"], f["tienda"]),
                "producto": f["titulo_en_tienda"], "url": f["url"], "similitud": f["similitud"] or 0.0,
                "motivo": f["motivo_duda"]}
               for f in conexion.execute(
                   "SELECT j.titulo_canonico, f.codigo AS tienda, p.* FROM producto_tienda p "
                   "JOIN juego j ON j.id = p.juego_id JOIN fuente f ON f.id = p.fuente_id "
                   "WHERE p.estado_emparejamiento = 'dudoso' AND j.activo = 1 ORDER BY j.titulo_canonico, f.codigo")]
    sin_emparejar = [f["titulo_canonico"] for f in conexion.execute(
        "SELECT titulo_canonico FROM juego j WHERE activo = 1 AND NOT EXISTS ("
        "SELECT 1 FROM producto_tienda p WHERE p.juego_id = j.id AND p.estado_emparejamiento = 'aceptado') "
        "ORDER BY titulo_canonico")]
    activos = conexion.execute("SELECT COUNT(*) FROM juego WHERE activo = 1").fetchone()[0]
    publicados = 0
    ruta_juegos = destino / "datos" / "juegos.json"
    if ruta_juegos.exists():
        publicados = len(json.loads(ruta_juegos.read_text(encoding="utf-8"))["juegos"])

    _escribir_json(destino / "datos" / "metricas.json", {
        "generado_en": ahora_utc().isoformat(),
        "ultima_ejecucion": None if not ultima else {
            "id": ultima["id"], "iniciada_en": ultima["iniciada_en"], "duracion_s": duracion(ultima),
            "modo": ultima["modo"], "fuente_datos": ultima["fuente_datos"], "estado": ultima["estado"]},
        "etapas": etapas,
        "solicitudes": solicitudes,
        "fallidos": fallidos,
        "errores": [{"etapa": e.etapa, "clave": e.clave, "mensaje": e.mensaje} for e in errores],
        "dudosos": dudosos,
        "sin_emparejar": sin_emparejar,
        "cobertura": {"activos": activos, "publicados": publicados, "sin_precio_suficiente": activos - publicados},
        "mediciones": _mediciones(mediciones),
        "historial": [{"iniciada_en": f["iniciada_en"], "modo": f["modo"], "fuente_datos": f["fuente_datos"],
                       "duracion_s": duracion(f), "estado": f["estado"]}
                      for f in conexion.execute("SELECT * FROM ejecucion ORDER BY id DESC LIMIT 15")],
    })
