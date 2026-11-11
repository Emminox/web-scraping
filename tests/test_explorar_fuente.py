"""Pruebas de la detección de señales de la herramienta de exploración de fuentes."""

import unittest

from radar.herramientas.explorar_fuente import decodificar, detectar_senales
from tests.utilidades import respuesta


class PruebasSenales(unittest.TestCase):
    def test_detecta_bloqueo_y_datos_embebidos(self):
        html = '<div class="g-recaptcha"></div><script id="__NEXT_DATA__">{}</script>'
        bloqueos, embebidos = detectar_senales(html)
        self.assertIn("CAPTCHA", bloqueos)
        self.assertIn("Next.js (__NEXT_DATA__)", embebidos)

    def test_pagina_limpia(self):
        self.assertEqual(detectar_senales("<html><h1>Juego</h1><span>$59.99</span></html>"), ([], []))

    def test_decodifica_con_el_charset_declarado(self):
        r = respuesta("https://a.com", cuerpo="Pokémon".encode("latin-1"),
                      **{"Content-Type": "text/html; charset=ISO-8859-1"})
        self.assertEqual(decodificar(r), "Pokémon")


if __name__ == "__main__":
    unittest.main()
