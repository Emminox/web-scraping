"""Comando principal del Radar de Ofertas.

Uso (desde la raíz del repositorio)::

    py -3.14 -m radar ejecutar                       # Ejecución completa con la configuración por defecto.
    py -3.14 -m radar ejecutar --modo paralelo        # Otro modo (secuencial, concurrente, paralelo).
    py -3.14 -m radar ejecutar --fuente replay        # Mismo código, datos del almacén de capturas.
    py -3.14 -m radar ejecutar --plataformas pc --paginas 1 --por-pagina 5   # Prueba rápida y liviana.
    py -3.14 -m radar sitio                           # Solo regenera el sitio desde la base.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from radar.bd import abrir_bd
from radar.config import MODOS_VALIDOS, cargar_config
from radar.ejecucion import OpcionesEjecucion, ejecutar, rutas_para
from radar.fuentes.tipo_cambio import actualizar_tipo_cambio
from radar.red import crear_cliente
from radar.sitio import generar_sitio


def _lista(texto: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in texto.split(",") if p.strip())


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar", description="Radar de Ofertas Multinúcleo")
    parser.add_argument("--config", help="ruta a otro archivo de configuración")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_ejecutar = sub.add_parser("ejecutar", help="ejecuta el pipeline completo")
    p_ejecutar.add_argument("--modo", choices=MODOS_VALIDOS, help="por defecto, el de config.toml")
    p_ejecutar.add_argument("--fuente", choices=("vivo", "replay"), help="por defecto, la de config.toml")
    p_ejecutar.add_argument("--plataformas", type=_lista, help="plataformas de Metacritic, separadas por comas")
    p_ejecutar.add_argument("--paginas", type=int, help="páginas del listado por plataforma")
    p_ejecutar.add_argument("--por-pagina", type=int, help="solo los primeros N juegos de cada página (pruebas)")
    p_ejecutar.add_argument("--solo-fuentes", type=_lista,
                            help="solo estas tiendas, separadas por comas (p. ej. steam,cheapshark)")
    p_ejecutar.add_argument("--complementar", action="store_true",
                            help="agrega los precios a la última ejecución en vivo en vez de crear otra")

    p_sitio = sub.add_parser("sitio", help="regenera el sitio desde la base de datos")
    p_sitio.add_argument("--fuente", choices=("vivo", "replay"), default="vivo")

    opciones = parser.parse_args(argumentos)
    config = cargar_config(opciones.config)

    if opciones.comando == "sitio":
        ruta_bd, destino = rutas_para(config, opciones.fuente)
        conexion = abrir_bd(ruta_bd)
        try:
            resumen = generar_sitio(conexion, destino, config.rutas.mediciones)
        finally:
            conexion.close()
        if opciones.fuente == "vivo":
            # Una consulta (o ninguna, si está en la caché de 12 h) para las tasas de colones y euros.
            config_vivo = replace(config, ejecucion=replace(config.ejecucion, fuente="vivo"))
            actualizar_tipo_cambio(crear_cliente(config_vivo), destino)
        print(f"Sitio generado en {destino}: {resumen['publicados']} juegos publicados.")
        return 0

    corrida = ejecutar(config, OpcionesEjecucion(
        modo=opciones.modo or config.ejecucion.modo,
        fuente_datos=opciones.fuente or config.ejecucion.fuente,
        plataformas=opciones.plataformas or config.descubrimiento.plataformas,
        # None = usar las páginas de cada plataforma según config.toml ([descubrimiento.paginas]).
        paginas_por_plataforma=opciones.paginas,
        por_pagina=opciones.por_pagina,
        solo_fuentes=opciones.solo_fuentes,
        complementar=opciones.complementar,
    ))
    resultado = corrida.resultado
    print(f"Ejecución #{corrida.ejecucion_id} · modo {resultado.modo} · datos {opciones.fuente or config.ejecucion.fuente}")
    print(f"  Entradas juego-plataforma persistidas: {resultado.juegos_persistidos}")
    print(f"  Juegos publicados en el sitio (precio en 2+ tiendas): {corrida.publicados}")
    print(f"  Descargas fallidas: {len(resultado.fallidos)} (resueltas en el reintento final: {corrida.resueltos_al_final})")
    print(f"  Errores en etapas: {len(resultado.errores)}")
    for error in resultado.errores[:10]:
        print(f"    - [{error.etapa}] {error.clave}: {error.mensaje[:150]}")
    print(f"  Base de datos: {corrida.base_datos}")
    print(f"  Sitio: {corrida.sitio / 'index.html'}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
