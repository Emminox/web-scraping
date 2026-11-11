"""Pruebas de los parsers con páginas reales guardadas en fixtures/ (sin internet).

Si un sitio cambia su HTML, estas pruebas siguen pasando con la página vieja: para detectar el cambio
hay que volver a capturar el fixture con ``radar.herramientas.explorar_fuente``.
"""

import unittest

from radar.config import RAIZ_PROYECTO
from radar.fuentes import bestbuy, gog, metacritic, nintendo, steam

FIXTURES = RAIZ_PROYECTO / "fixtures"


def leer(ruta: str) -> bytes:
    return (FIXTURES / ruta).read_bytes()


class PruebasMetacritic(unittest.TestCase):
    def test_listado(self):
        tarjetas = metacritic.parsear_listado(leer("www.metacritic.com/listado-ps5.html").decode("utf-8"), "ps5")
        self.assertEqual(len(tarjetas), 50)
        primera = tarjetas[0]
        self.assertEqual((primera.slug, primera.titulo, primera.plataforma), ("elden-ring", "Elden Ring", "ps5"))
        self.assertEqual(primera.fecha_lanzamiento, "2022-02-25")
        self.assertTrue(90 <= primera.metascore <= 100)
        self.assertTrue(primera.imagen_url.startswith("https://www.metacritic.com/"))
        self.assertNotIn("&amp;", primera.imagen_url)
        self.assertIn("width=192", primera.imagen_url)  # La versión de mayor resolución.
        self.assertEqual(len({t.slug for t in tarjetas}), 50)  # Sin repetidos dentro de una página.

    def test_url_listado(self):
        self.assertEqual(
            metacritic.url_listado("ps5", 2),
            "https://www.metacritic.com/browse/game/ps5/all/all-time/metascore/?platform=ps5&page=2",
        )


class PruebasSteam(unittest.TestCase):
    def test_busqueda(self):
        candidatos = steam.parsear_busqueda(leer("store.steampowered.com/busqueda-hades.json"))
        self.assertGreaterEqual(len(candidatos), 5)
        hades = next(c for c in candidatos if c.titulo == "Hades")
        self.assertEqual(hades.url, "https://store.steampowered.com/app/1145360/Hades/")
        self.assertEqual((hades.plataforma, hades.formato), ("pc", "digital"))
        self.assertGreater(hades.precio_actual_centavos, 0)
        self.assertGreaterEqual(hades.precio_regular_centavos, hades.precio_actual_centavos)
        self.assertTrue(50 <= hades.resena_porcentaje <= 100)
        self.assertGreater(hades.resena_cantidad, 1000)


class PruebasGog(unittest.TestCase):
    def test_busqueda(self):
        candidatos = gog.parsear_busqueda(leer("catalog.gog.com/busqueda-hades.json"))
        self.assertGreater(len(candidatos), 0)
        for candidato in candidatos:
            self.assertTrue(candidato.url.startswith("https://www.gog.com/"))
            self.assertEqual(candidato.plataforma, "pc")
        con_descuento = [c for c in candidatos if c.precio_regular_centavos and c.precio_actual_centavos
                         and c.precio_regular_centavos > c.precio_actual_centavos]
        self.assertTrue(con_descuento)  # El fixture tiene al menos un producto en oferta.


class PruebasNintendo(unittest.TestCase):
    def test_producto(self):
        url = "https://www.nintendo.com/us/store/products/hades-switch/"
        [candidato] = nintendo.parsear_producto(leer("www.nintendo.com/producto-hades.html"), url)
        self.assertEqual((candidato.titulo, candidato.plataforma, candidato.url), ("Hades", "switch", url))
        self.assertGreater(candidato.precio_actual_centavos, 0)
        self.assertGreaterEqual(candidato.precio_regular_centavos, candidato.precio_actual_centavos)
        self.assertTrue(candidato.imagen_url.startswith("https://assets.nintendo.com/"))
        self.assertTrue(candidato.imagen_url.endswith("_1024"))  # Arte cuadrado de 1024x1024.

    def test_indice_del_sitemap(self):
        sitemap = (
            b"<urlset><url><loc>https://www.nintendo.com/us/store/products/hades-switch/</loc></url>"
            b"<url><loc>https://www.nintendo.com/us/store/products/hades-ii-switch-2/</loc></url>"
            b"<url><loc>https://www.nintendo.com/us/store/products/hades-ii-switch/</loc></url>"
            b"<url><loc>https://www.nintendo.com/us/whatsnew/algo/</loc></url></urlset>"
        )
        indice = nintendo.IndiceNintendo(nintendo.parsear_sitemap(sitemap))
        self.assertEqual(len(indice), 3)
        self.assertTrue(indice.buscar(frozenset({"hades"}), "switch").endswith("/hades-switch/"))
        self.assertTrue(indice.buscar(frozenset({"hades", "ii"}), "switch2").endswith("/hades-ii-switch-2/"))
        self.assertIsNone(indice.buscar(frozenset({"zelda"}), "switch"))


class PruebasCheapShark(unittest.TestCase):
    def test_ofertas_por_tienda_sin_steam_ni_gog(self):
        from radar.fuentes import cheapshark
        candidatos = cheapshark.parsear_busqueda(leer("www.cheapshark.com/deals-hades.json"))
        self.assertGreater(len(candidatos), 0)
        fuentes = {c.fuente for c in candidatos}
        self.assertNotIn("steam", fuentes)  # Steam y GOG ya se consultan directamente.
        self.assertNotIn("gog", fuentes)
        self.assertTrue(fuentes <= {codigo for codigo, _, _ in cheapshark.TIENDAS.values()})
        for c in candidatos:
            self.assertTrue(c.url.startswith("https://www.cheapshark.com/redirect?dealID="))
            self.assertEqual((c.plataforma, c.formato), ("pc", "digital"))
        hades2 = next(c for c in candidatos if c.titulo == "Hades II")
        self.assertEqual((hades2.fuente, hades2.precio_actual_centavos), ("epic", 2999))


class PruebasBestBuy(unittest.TestCase):
    def test_busqueda(self):
        candidatos = bestbuy.parsear_busqueda(leer("www.bestbuy.com/busqueda-hades.html"))
        self.assertGreaterEqual(len(candidatos), 3)
        hades = next(c for c in candidatos if c.titulo.startswith("Hades - "))
        self.assertEqual((hades.plataforma, hades.formato), ("switch", "fisico"))
        self.assertTrue(hades.url.startswith("https://www.bestbuy.com/product/"))
        self.assertGreater(hades.precio_actual_centavos, 0)
        self.assertTrue(hades.imagen_url.startswith("https://pisces.bbystatic.com/"))
        self.assertTrue(hades.imagen_url.endswith(";maxHeight=900;maxWidth=600"))
        self.assertEqual(bestbuy._plataforma("Hades II Nintendo Switch 2 - Nintendo Switch 2"), "switch2")
        self.assertEqual(bestbuy._plataforma("Elden Ring - PlayStation 5"), "ps5")


class PruebasTipoCambio(unittest.TestCase):
    def test_parsea_colones_y_euros(self):
        from radar.fuentes import tipo_cambio
        tc = tipo_cambio.parsear(leer("open.er-api.com/latest-usd.json"))
        self.assertEqual(tc.tasas, {"CRC": 452.888176, "EUR": 0.893927})
        self.assertEqual(tc.actualizado_en, "2026-11-11T00:02:32+00:00")

    def test_respuesta_invalida(self):
        from radar.fuentes import tipo_cambio
        with self.assertRaises(ValueError):
            tipo_cambio.parsear(b'{"result": "error", "error-type": "unsupported-code"}')
        with self.assertRaises(ValueError):
            tipo_cambio.parsear(b'{"result": "success", "base_code": "USD", "rates": {"EUR": 0.9}, "time_last_update_unix": 1}')

    def test_si_falla_conserva_el_archivo_anterior(self):
        import json
        import tempfile
        from pathlib import Path
        from radar.fuentes import tipo_cambio
        from radar.red import ErrorTemporal

        class ClienteQueFalla:
            def obtener(self, url):
                raise ErrorTemporal("sin red")

        class ClienteBueno:
            def obtener(self, url):
                class R:
                    cuerpo = leer("open.er-api.com/latest-usd.json")
                return R()

        with tempfile.TemporaryDirectory() as carpeta:
            sitio = Path(carpeta)
            self.assertIsNotNone(tipo_cambio.actualizar_tipo_cambio(ClienteBueno(), sitio))
            self.assertIsNone(tipo_cambio.actualizar_tipo_cambio(ClienteQueFalla(), sitio))
            publicado = json.loads((sitio / "datos" / "tipo_cambio.json").read_text(encoding="utf-8"))
            self.assertEqual(publicado["tasas"]["CRC"], 452.888176)          # Se conservó el anterior.
            self.assertEqual(publicado["atribucion"]["texto"], "Rates By Exchange Rate API")
            self.assertEqual(set(publicado["tasas"]), {"CRC", "EUR"})        # Solo las tasas que usa el sitio.


if __name__ == "__main__":
    unittest.main()
