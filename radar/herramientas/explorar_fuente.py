"""Explora UNA página de un sitio candidato para el spike de fuentes del Hito 1.

Para qué sirve: antes de decidir qué sitios usar, el equipo debe averiguar por cada uno si
robots.txt lo permite, si los datos vienen en el HTML inicial o se cargan con JavaScript, y si el
sitio bloquea a los bots. Esta herramienta responde eso con UNA sola solicitud responsable (con el
User-Agent del proyecto, respetando robots.txt y el límite por dominio), guarda la página como
"fixture" para escribir y probar el parser después, e imprime un resumen en Markdown listo para
pegar en la ficha de la fuente (``/fuente-nueva``).

Uso (desde la raíz del repositorio)::

    py -3.14 -m radar.herramientas.explorar_fuente URL [--buscar TEXTO ...] [--nombre NOMBRE]

Ejemplo::

    py -3.14 -m radar.herramientas.explorar_fuente "https://sitio.com/juego/123" --buscar "59.99" --nombre ficha-juego

``--buscar`` sirve para comprobar si un dato que se VE en el navegador (un precio, un título) viene
en el HTML que recibe un programa. Si no aparece, probablemente lo genera JavaScript.

No usar esta herramienta para descargar muchas páginas: es para evaluar, no para recolectar.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from radar.config import Config, cargar_config
from radar.red import (
    BloqueadoPorRobots,
    ClienteHttp,
    ErrorDefinitivo,
    ReintentosAgotados,
    Respuesta,
)

# Pistas en el HTML que suelen indicar un bloqueo o desafío anti-bots. No se intenta evadirlos
# (está prohibido por el enunciado): si aparecen, la fuente se sustituye con un ADR.
#
# Las pistas son específicas a propósito: "captcha" a secas o "challenge-platform" aparecen también en páginas
# normales (configuración de inicio de sesión, script de Cloudflare que se carga en todo el sitio) y daban
# falsos positivos en el spike de Metacritic.
SENALES_BLOQUEO: dict[str, tuple[str, ...]] = {
    "CAPTCHA": ('class="g-recaptcha"', "h-captcha", "captcha-container", "please solve the captcha"),
    "Desafío de Cloudflare": ("cf-chl", "cf_chl_opt", "just a moment...", "checking your browser"),
    "Protección anti-bots (Akamai/PerimeterX/otros)": (
        "px-captcha", "_pxhd", "access denied", "robot or human", "are you a robot",
    ),
}

# Pistas de que los datos vienen como JSON dentro del HTML (fácil de extraer sin JavaScript).
SENALES_DATOS_EMBEBIDOS: dict[str, str] = {
    "JSON-LD (schema.org)": "application/ld+json",
    "Next.js (__NEXT_DATA__)": "__next_data__",
    "Nuxt (__NUXT__)": "__nuxt__",
    "Estado inicial (__INITIAL_STATE__ / __APOLLO_STATE__)": "_state__",
}


def decodificar(respuesta: Respuesta) -> str:
    """Convierte el cuerpo en texto usando el charset que declara el servidor (o UTF-8)."""
    coincidencia = re.search(r"charset=([\w-]+)", respuesta.tipo_contenido)
    codificacion = coincidencia.group(1) if coincidencia else "utf-8"
    try:
        return respuesta.cuerpo.decode(codificacion, errors="replace")
    except LookupError:  # El servidor declaró un charset que Python no conoce.
        return respuesta.cuerpo.decode("utf-8", errors="replace")


def detectar_senales(texto: str) -> tuple[list[str], list[str]]:
    """Devuelve (señales de bloqueo encontradas, señales de datos embebidos encontradas)."""
    minusculas = texto.lower()
    bloqueos = [
        nombre for nombre, pistas in SENALES_BLOQUEO.items()
        if any(pista in minusculas for pista in pistas)
    ]
    embebidos = [
        nombre for nombre, pista in SENALES_DATOS_EMBEBIDOS.items() if pista in minusculas
    ]
    return bloqueos, embebidos


def guardar_fixture(config: Config, respuesta: Respuesta, nombre: str | None) -> Path:
    """Guarda la página en ``fixtures/<dominio>/<nombre>.<ext>`` y devuelve la ruta."""
    dominio = urlsplit(respuesta.url).hostname or "sin-dominio"
    extension = ".json" if "json" in respuesta.tipo_contenido else ".html"
    # Si no se da nombre, se usa la hora para no sobrescribir fixtures anteriores.
    nombre_archivo = (nombre or time.strftime("pagina-%Y%m%d-%H%M%S")) + extension
    ruta = config.rutas.fixtures / dominio / nombre_archivo
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(respuesta.cuerpo)
    return ruta


def explorar(config: Config, url: str, buscar: list[str], nombre: str | None) -> int:
    """Hace la exploración completa e imprime el reporte. Devuelve el código de salida."""
    cliente = ClienteHttp(config)
    dominio = urlsplit(url).hostname
    print(f"## Exploración de `{dominio}`\n")
    print(f"- **URL:** {url}")
    print(f"- **User-Agent usado:** `{config.red.user_agent}`")

    # 1) robots.txt: si no lo permite, se informa y NO se descarga nada más.
    permitido = cliente.permitido_por_robots(url)
    retraso = cliente.retraso_sugerido_por_robots(url)
    print(f"- **robots.txt permite esta URL:** {'sí' if permitido else 'NO'}")
    print(f"- **Crawl-delay declarado:** {retraso if retraso is not None else 'no declara'}")
    if not permitido:
        print("\n> robots.txt no permite esta ruta. Buscar otra ruta del sitio o sustituir la fuente (ADR).")
        return 2

    # 2) Una sola descarga, sin usar la caché, para ver la respuesta real de hoy.
    inicio = time.perf_counter()
    try:
        respuesta = cliente.obtener(url, usar_almacen=False)
    except BloqueadoPorRobots as error:  # Por si robots.txt cambió entre la consulta y la descarga.
        print(f"\n> Bloqueado por robots.txt: {error}")
        return 2
    except ErrorDefinitivo as error:
        print(f"- **Resultado:** HTTP {error.estado} (no se reintenta). Posible bloqueo o URL incorrecta.")
        return 1
    except ReintentosAgotados as error:
        print(f"- **Resultado:** falló tras {error.intentos} intentos: {error.ultimo_error}")
        return 1
    duracion = time.perf_counter() - inicio

    texto = decodificar(respuesta)
    bloqueos, embebidos = detectar_senales(texto)
    print(f"- **Estado HTTP:** {respuesta.estado}")
    print(f"- **Content-Type:** {respuesta.tipo_contenido or 'no declarado'}")
    print(f"- **Tamaño:** {len(respuesta.cuerpo):,} bytes · **Tiempo:** {duracion:.2f} s")
    print(f"- **Señales de bloqueo anti-bots:** {', '.join(bloqueos) if bloqueos else 'ninguna detectada'}")
    print(f"- **Datos embebidos como JSON:** {', '.join(embebidos) if embebidos else 'ninguno detectado'}")

    # 3) ¿Los datos visibles en el navegador vienen en el HTML que recibe un programa?
    if buscar:
        print("- **¿El dato aparece en el HTML inicial?**")
        for termino in buscar:
            encontrado = termino.lower() in texto.lower()
            print(f"  - `{termino}`: {'sí' if encontrado else 'NO (posiblemente lo genera JavaScript)'}")

    # 4) Guardar la página para escribir y probar el parser sin volver a pedirla.
    ruta = guardar_fixture(config, respuesta, nombre)
    print(f"- **Fixture guardado en:** `{ruta.relative_to(config.rutas.fixtures.parent)}`")
    return 0


def main(argumentos: list[str] | None = None) -> int:
    """Lee los argumentos de la línea de comandos y ejecuta la exploración."""
    parser = argparse.ArgumentParser(
        description="Explora una página de un sitio candidato (spike de fuentes, Hito 1)."
    )
    parser.add_argument("url", help="URL completa de la página a evaluar")
    parser.add_argument(
        "--buscar", action="append", default=[], metavar="TEXTO",
        help="texto que se ve en el navegador (precio, título); se puede repetir",
    )
    parser.add_argument("--nombre", help="nombre del fixture a guardar (sin extensión)")
    parser.add_argument("--config", help="ruta a otro archivo de configuración")
    opciones = parser.parse_args(argumentos)

    config = cargar_config(opciones.config)
    if config.ejecucion.fuente != "vivo":
        print("Esta herramienta necesita 'fuente = \"vivo\"' en la configuración.", file=sys.stderr)
        return 1
    return explorar(config, opciones.url, opciones.buscar, opciones.nombre)


if __name__ == "__main__":
    # En Windows la consola puede no usar UTF-8; esto evita errores al imprimir tildes.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
