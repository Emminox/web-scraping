"""Tablas en PDF sin dependencias externas (solo la biblioteca estándar de Python).

Las usa el panel de métricas para las listas largas (emparejamientos dudosos, cola de fallidos): en la página se
ve un resumen y la lista completa se descarga en PDF. GitHub Actions no instala librerías extra, por eso no se usa
reportlab ni similares.

Formato: carta horizontal; tabla en Courier (monoespaciada: el ancho de cada letra es fijo y así se puede cortar el
texto en líneas sin medirlo); encabezado de la tabla repetido en cada página; filas alternadas en gris claro;
"Página X de N" al pie. Se usan las fuentes estándar de PDF (no hace falta incrustarlas) con la codificación
WinAnsi (= cp1252): acentos, ñ, ™ y € se ven bien; un carácter fuera de cp1252 (p. ej. japonés) se muestra como "?".
"""

from __future__ import annotations

import textwrap
import zlib
from dataclasses import dataclass

# Carta horizontal, en puntos (1/72 de pulgada).
ANCHO, ALTO = 792, 612
MARGEN = 36
TAMANO = 7.5                      # Letra de la tabla.
ANCHO_LETRA = TAMANO * 0.6        # En Courier cada carácter mide 600/1000 del tamaño.
INTERLINEA = 9.5
SEPARACION = 2                    # Caracteres de espacio entre columnas.


@dataclass(frozen=True)
class Columna:
    titulo: str
    ancho: int                    # En caracteres.


def _texto(valor: str) -> str:
    """Escapa un texto para un string de PDF: \\, ( y ) llevan barra invertida."""
    return valor.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _lineas(valor: str, ancho: int) -> list[str]:
    return textwrap.wrap(str(valor), width=ancho, break_long_words=True, break_on_hyphens=False) or [""]


def _columnas_ajustadas(columnas: list[Columna]) -> list[Columna]:
    """Si las columnas no caben en la página, se reparte el exceso achicando las más anchas."""
    disponibles = int((ANCHO - 2 * MARGEN) / ANCHO_LETRA) - SEPARACION * (len(columnas) - 1)
    anchos = [c.ancho for c in columnas]
    while sum(anchos) > disponibles:
        anchos[anchos.index(max(anchos))] -= 1
    return [Columna(c.titulo, a) for c, a in zip(columnas, anchos)]


def tabla_pdf(titulo: str, subtitulo: str, columnas: list[Columna], filas: list[list[str]]) -> bytes:
    """Devuelve un PDF con ``filas`` como tabla (en el orden recibido)."""
    columnas = _columnas_ajustadas(columnas)
    posiciones, x = [], MARGEN
    for c in columnas:
        posiciones.append(x)
        x += (c.ancho + SEPARACION) * ANCHO_LETRA

    # 1) Cortar cada celda en líneas y repartir las filas en páginas (la primera tiene título).
    filas_en_lineas = [[_lineas(valor, c.ancho) for valor, c in zip(fila, columnas)] for fila in filas]
    paginas: list[list[list[list[str]]]] = [[]]
    alto_libre = ALTO - 2 * MARGEN - 46 - 2 * INTERLINEA          # Título, subtítulo y encabezado de tabla.
    for celdas in filas_en_lineas:
        alto = max(len(c) for c in celdas) * INTERLINEA + 2
        if alto > alto_libre and paginas[-1]:
            paginas.append([])
            alto_libre = ALTO - 2 * MARGEN - 2 * INTERLINEA - 14    # Sin título en las siguientes.
        paginas[-1].append(celdas)
        alto_libre -= alto

    # 2) Dibujar cada página.
    contenidos = []
    for numero, filas_pagina in enumerate(paginas, start=1):
        c: list[str] = []
        y = ALTO - MARGEN
        if numero == 1:
            c.append(f"BT /F3 14 Tf {MARGEN} {y - 14} Td ({_texto(titulo)}) Tj ET")
            c.append(f"BT /F4 8.5 Tf {MARGEN} {y - 30} Td ({_texto(subtitulo)}) Tj ET")
            y -= 46
        # Encabezado de la tabla (se repite en cada página) con una línea debajo.
        y -= INTERLINEA
        for columna, xc in zip(columnas, posiciones):
            c.append(f"BT /F2 {TAMANO} Tf {xc:.1f} {y:.1f} Td ({_texto(columna.titulo)}) Tj ET")
        c.append(f"0.6 G 0.6 w {MARGEN} {y - 3:.1f} m {ANCHO - MARGEN} {y - 3:.1f} l S 0 G")
        y -= INTERLINEA + 2
        for i, celdas in enumerate(filas_pagina):
            n = max(len(lineas) for lineas in celdas)
            if i % 2 == 1:   # Fondo gris claro en filas alternas: se sigue la fila con la vista.
                c.append(f"0.94 g {MARGEN - 2} {y - (n - 1) * INTERLINEA - 3:.1f} {ANCHO - 2 * MARGEN + 4} "
                         f"{n * INTERLINEA + 1:.1f} re f 0 g")
            for lineas, xc in zip(celdas, posiciones):
                for k, linea in enumerate(lineas):
                    c.append(f"BT /F1 {TAMANO} Tf {xc:.1f} {y - k * INTERLINEA:.1f} Td ({_texto(linea)}) Tj ET")
            y -= n * INTERLINEA + 2
        pie = f"Página {numero} de {len(paginas)}"
        c.append(f"BT /F4 7.5 Tf {ANCHO - MARGEN - len(pie) * 3.6:.1f} {MARGEN - 16} Td ({_texto(pie)}) Tj ET")
        c.append(f"BT /F4 7.5 Tf {MARGEN} {MARGEN - 16} Td ({_texto(titulo)}) Tj ET")
        contenidos.append("\n".join(c).encode("cp1252", errors="replace"))

    # 3) Armar el archivo: objetos numerados + tabla de referencias cruzadas (posición en bytes de cada objeto).
    objetos: list[bytes] = []
    fuentes = {"F1": "Courier", "F2": "Courier-Bold", "F3": "Helvetica-Bold", "F4": "Helvetica"}
    primer_pagina = 3 + len(fuentes) + 1          # 1 catálogo, 2 páginas, fuentes, info y luego las páginas.
    ids_paginas = [primer_pagina + 2 * i for i in range(len(contenidos))]
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append(f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in ids_paginas)}] "
                   f"/Count {len(ids_paginas)} >>".encode())
    recursos = " ".join(f"/{nombre} {3 + k} 0 R" for k, nombre in enumerate(fuentes))
    for base in fuentes.values():
        objetos.append(f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>".encode())
    objetos.append(b"<< /Title (" + _texto(titulo).encode("cp1252", errors="replace")
                   + b") /Producer (Radar de Ofertas Multinucleo) >>")
    for i, contenido in enumerate(contenidos):
        comprimido = zlib.compress(contenido)
        objetos.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {ANCHO} {ALTO}] "
                       f"/Resources << /Font << {recursos} >> >> /Contents {ids_paginas[i] + 1} 0 R >>".encode())
        objetos.append(f"<< /Length {len(comprimido)} /Filter /FlateDecode >>\nstream\n".encode()
                       + comprimido + b"\nendstream")

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posiciones_bytes = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones_bytes.append(len(salida))
        salida += f"{numero} 0 obj\n".encode() + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    salida += "".join(f"{p:010d} 00000 n \n" for p in posiciones_bytes).encode()
    info = 3 + len(fuentes)
    salida += (f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R /Info {info} 0 R >>\n"
               f"startxref\n{inicio_xref}\n%%EOF\n").encode()
    return bytes(salida)
