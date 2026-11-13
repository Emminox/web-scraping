"""PDF del panel de métricas (sin librerías externas)."""

import re
import unittest
import zlib

from radar.sitio.pdf import Columna, tabla_pdf


def contenidos(pdf: bytes) -> list[str]:
    """Texto de los flujos de contenido de cada página (descomprimidos)."""
    return [zlib.decompress(m).decode("cp1252") for m in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S)]


class PruebasPdf(unittest.TestCase):
    def setUp(self):
        self.filas = [[f"Juego {i} (edición GOTY™)", "Steam", "x" * 120] for i in range(150)]
        self.pdf = tabla_pdf("Título de prueba", "Subtítulo áéíóú ñ €",
                             [Columna("Juego", 40), Columna("Tienda", 12), Columna("Producto", 60)], self.filas)

    def test_estructura_valida(self):
        self.assertTrue(self.pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(self.pdf.rstrip().endswith(b"%%EOF"))
        # startxref apunta exactamente al inicio de la tabla de referencias cruzadas.
        inicio = int(re.search(rb"startxref\n(\d+)", self.pdf).group(1))
        self.assertTrue(self.pdf[inicio:].startswith(b"xref"))
        # Cada entrada de la tabla apunta al "N 0 obj" que corresponde.
        entradas = re.findall(rb"(\d{10}) 00000 n ", self.pdf)
        for numero, posicion in enumerate(entradas, start=1):
            self.assertTrue(self.pdf[int(posicion):].startswith(f"{numero} 0 obj".encode()))

    def test_varias_paginas_con_encabezado_y_numeracion(self):
        paginas = contenidos(self.pdf)
        total = int(re.search(rb"/Count (\d+)", self.pdf).group(1))
        self.assertGreater(total, 1)
        self.assertEqual(len(paginas), total)
        for numero, pagina in enumerate(paginas, start=1):
            self.assertIn("(Juego) Tj", pagina)                         # Encabezado repetido en cada página.
            self.assertIn(f"(Página {numero} de {total}) Tj", pagina)

    def test_todas_las_filas_y_caracteres_especiales(self):
        texto = "\n".join(contenidos(self.pdf))
        for i in range(150):
            self.assertIn(f"(Juego {i} \\(edición GOTY™\\)) Tj", texto)  # Paréntesis escapados; ™ en WinAnsi.
        self.assertIn("Subtítulo áéíóú ñ €", texto)


if __name__ == "__main__":
    unittest.main()
