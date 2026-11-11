"""Validación del umbral de emparejamiento (sección 6: ≥ 60 pares revisados a mano, precisión y exhaustividad).

Dos pasos:

1. **Exportar** pares reales de la base a un CSV para etiquetar::

       py -3.14 -m radar.herramientas.validar_emparejamiento exportar

   Escribe ``datos/validacion/pares.csv`` con columnas: juego, producto, tienda, similitud, estado_actual,
   es_el_mismo. Se eligen pares de todas las bandas (aceptados, dudosos y rechazados) para que el conjunto
   tenga positivos Y negativos. Una persona del equipo completa ``es_el_mismo`` con "si" o "no".
   (Si la IA lo etiquetara, el conjunto no sería "revisado manualmente".)

2. **Evaluar** el CSV etiquetado::

       py -3.14 -m radar.herramientas.validar_emparejamiento evaluar

   Recalcula la similitud con el algoritmo ACTUAL (por si cambió) y muestra precisión, exhaustividad y F1
   para cada umbral entre 0,70 y 0,98, y el umbral con mejor F1. El resultado va al ADR-006.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from radar.bd import abrir_bd
from radar.config import cargar_config
from radar.emparejamiento.normalizar import normalizar
from radar.emparejamiento.similitud import similitud

COLUMNAS = ["juego", "producto", "tienda", "similitud", "estado_actual", "es_el_mismo"]
MINIMO_PARES = 60


def muestra_repartida(filas: list, cantidad: int) -> list:
    """Toma ``cantidad`` filas repartidas a lo largo de toda la lista (una cada ``len/cantidad``).

    Antes se tomaban las primeras con ``ORDER BY j.clave LIMIT``: las claves empiezan por el slug, así que la
    muestra eran casi solo juegos que empiezan por "a" o un número, casi siempre de una sola plataforma. Repartir
    por toda la lista mantiene la muestra determinista (la misma base da el mismo CSV) y cubre todo el abecedario,
    todas las plataformas y todas las tiendas.
    """
    if len(filas) <= cantidad:
        return list(filas)
    return [filas[i * len(filas) // cantidad] for i in range(cantidad)]


def exportar(ruta_bd: Path, salida: Path, por_estado: int = 40) -> int:
    """Exporta hasta ``por_estado`` pares de cada estado (aceptado, dudoso, rechazado). Devuelve cuántos."""
    conexion = abrir_bd(ruta_bd)
    try:
        filas = []
        for estado in ("aceptado", "dudoso", "rechazado"):
            todas = conexion.execute(
                "SELECT j.titulo_canonico, p.titulo_en_tienda, f.nombre, p.similitud, p.estado_emparejamiento "
                "FROM producto_tienda p JOIN juego j ON j.id = p.juego_id JOIN fuente f ON f.id = p.fuente_id "
                "WHERE p.estado_emparejamiento = ? ORDER BY j.clave, f.codigo", (estado,)
            ).fetchall()
            filas += muestra_repartida(todas, por_estado)
    finally:
        conexion.close()
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(COLUMNAS)
        for fila in filas:
            escritor.writerow([fila[0], fila[1], fila[2], f"{fila[3] or 0:.2f}", fila[4], ""])
    return len(filas)


def leer_etiquetados(ruta: Path) -> list[tuple[str, str, bool]]:
    """(juego, producto, es_el_mismo) de las filas ya etiquetadas con 'si' o 'no'."""
    pares = []
    with ruta.open(encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            etiqueta = (fila.get("es_el_mismo") or "").strip().lower()
            if etiqueta in ("si", "sí", "no"):
                pares.append((fila["juego"], fila["producto"], etiqueta != "no"))
    return pares


def evaluar(pares: list[tuple[str, str, bool]]) -> list[dict]:
    """Precisión, exhaustividad y F1 para cada umbral."""
    puntajes = [(similitud(normalizar(juego), normalizar(producto)), es_mismo) for juego, producto, es_mismo in pares]
    resultados = []
    for centesimas in range(70, 99, 2):
        umbral = centesimas / 100
        vp = sum(1 for s, real in puntajes if s >= umbral and real)
        fp = sum(1 for s, real in puntajes if s >= umbral and not real)
        fn = sum(1 for s, real in puntajes if s < umbral and real)
        precision = vp / (vp + fp) if vp + fp else 1.0
        exhaustividad = vp / (vp + fn) if vp + fn else 1.0
        f1 = 2 * precision * exhaustividad / (precision + exhaustividad) if precision + exhaustividad else 0.0
        resultados.append({"umbral": umbral, "vp": vp, "fp": fp, "fn": fn,
                           "precision": precision, "exhaustividad": exhaustividad, "f1": f1})
    return resultados


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validación del umbral de emparejamiento")
    parser.add_argument("accion", choices=("exportar", "evaluar"))
    parser.add_argument("--archivo", help="CSV de pares (por defecto datos/validacion/pares.csv)")
    parser.add_argument("--config", help="otro archivo de configuración")
    opciones = parser.parse_args(argumentos)
    config = cargar_config(opciones.config)
    archivo = Path(opciones.archivo) if opciones.archivo else config.rutas.base_datos.parent / "validacion" / "pares.csv"

    if opciones.accion == "exportar":
        cantidad = exportar(config.rutas.base_datos, archivo)
        print(f"{cantidad} pares exportados a {archivo}. Completen la columna 'es_el_mismo' con si/no "
              f"(al menos {MINIMO_PARES}, incluidos los casos difíciles).")
        return 0

    pares = leer_etiquetados(archivo)
    if len(pares) < MINIMO_PARES:
        print(f"Aviso: solo hay {len(pares)} pares etiquetados; el enunciado pide al menos {MINIMO_PARES}.")
    if not pares:
        return 1
    resultados = evaluar(pares)
    print("Umbral  VP  FP  FN  Precisión  Exhaustividad  F1")
    for r in resultados:
        print(f"{r['umbral']:.2f}  {r['vp']:3d} {r['fp']:3d} {r['fn']:3d}  {r['precision']:8.2%}  {r['exhaustividad']:12.2%}  {r['f1']:.3f}")
    mejor = max(resultados, key=lambda r: (r["f1"], r["precision"]))
    print(f"\nUmbral con mejor F1: {mejor['umbral']:.2f} (precisión {mejor['precision']:.2%}, "
          f"exhaustividad {mejor['exhaustividad']:.2%}). Registrar en el ADR-006.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
