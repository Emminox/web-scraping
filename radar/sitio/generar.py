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


def _descuento(actual: int | None, regular: int | None) -> int:
    if actual is None or not regular or regular <= actual:
        return 0
    return round(100 * (regular - actual) / regular)


def generar_sitio(conexion: sqlite3.Connection, destino: Path, mediciones: Path | None = None) -> dict:
    """Genera el sitio completo. Devuelve un resumen (juegos publicados, etc.)."""
    destino.mkdir(parents=True, exist_ok=True)
    for archivo in ESTATICO.iterdir():
        shutil.copy2(archivo, destino / archivo.name)
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
        tienda_de_producto[fila["producto_id"]] = (
            f'{NOMBRES_TIENDA.get(fila["tienda"], fila["tienda"])} ({plataformas.get(fila["plataforma_codigo"], ("?",))[0]}, {fila["formato"]})'
        )

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
        metascores = [c["puntaje"] for c in calificaciones[juego["id"]] if c["fuente"] == "Metacritic"]
        steam = [c["puntaje"] for c in calificaciones[juego["id"]] if c["fuente"] == "Reseñas de usuarios de Steam"]

        tarjetas.append({
            "clave": juego["clave"],
            "titulo": juego["titulo_canonico"],
            "tipo": juego["tipo"],
            "imagen": juego["imagen_url"],
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
            "imagen": juego["imagen_url"],
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
            "historial": [{"tienda": tienda_de_producto[producto], "puntos": puntos}
                          for producto, puntos in sorted(historial[juego["id"]].items())],
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
