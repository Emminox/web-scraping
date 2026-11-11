"""Carga el catálogo de ``catalogo/*.json`` en la base de datos y muestra qué falta del enunciado.

Uso (desde la raíz del repositorio)::

    py -3.14 -m radar.herramientas.cargar_catalogo [--config RUTA]

Qué hace:
1. Abre (o crea) la base configurada en ``[rutas] base_datos``.
2. Lee y valida todos los archivos del catálogo. Si hay errores, los muestra TODOS y no cambia nada.
3. Sincroniza la base con los archivos (nuevos, actualizados, desactivados).
4. Muestra cuánto falta para los mínimos de la sección 4 (500 juegos, 3 plataformas, 50 casos difíciles…).

Este comando escribe en la base, así que no debe ejecutarse mientras corre el pipeline (que tiene su
propio y único hilo escritor, ver ADR-003).
"""

from __future__ import annotations

import argparse
import sys

from radar.bd import abrir_bd
from radar.catalogo import ErrorCatalogo, cargar_en_bd, leer_catalogo, verificar_requisitos
from radar.config import cargar_config
from radar.red.modelos import ahora_utc


def main(argumentos: list[str] | None = None) -> int:
    """Ejecuta la carga. Devuelve 0 si salió bien y 1 si el catálogo tiene errores."""
    parser = argparse.ArgumentParser(description="Carga el catálogo de juegos en la base de datos.")
    parser.add_argument("--config", help="ruta a otro archivo de configuración")
    opciones = parser.parse_args(argumentos)

    config = cargar_config(opciones.config)
    conexion = abrir_bd(config.rutas.base_datos)
    try:
        plataformas = {fila["codigo"] for fila in conexion.execute("SELECT codigo FROM plataforma")}
        try:
            entradas = leer_catalogo(config.rutas.catalogo, plataformas)
            resumen = cargar_en_bd(conexion, entradas, ahora_utc().isoformat())
        except ErrorCatalogo as error:
            print(f"No se cargó nada. El catálogo tiene {len(error.problemas)} problema(s):")
            for problema in error.problemas:
                print(f"  - {problema}")
            return 1

        print(f"Catálogo cargado desde {config.rutas.catalogo}")
        print(f"  Juegos leídos: {resumen.total} · nuevos: {resumen.nuevos} · "
              f"actualizados: {resumen.actualizados} · desactivados: {resumen.desactivados}")
        print("\nMínimos del enunciado (sección 4):")
        for requisito in verificar_requisitos(conexion):
            marca = "OK " if requisito.cumplido else "FALTA"
            print(f"  [{marca}] {requisito.descripcion}: {requisito.actual} / {requisito.minimo}")
        return 0
    finally:
        conexion.close()  # Se cierra siempre, aunque haya errores (en Windows evita dejar el archivo bloqueado).


if __name__ == "__main__":
    # En Windows la consola puede no usar UTF-8; esto evita errores al imprimir tildes.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
