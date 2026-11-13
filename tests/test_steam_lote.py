"""Precios de Steam por lote (ADR-013), sin internet."""

import unittest
from datetime import datetime, timezone

from radar.bd import abrir_bd
from radar.ejecucion import precios_steam_por_lote, registrar_fuentes
from radar.fuentes import steam_lote
from radar.red import ErrorTemporal
from tests.test_fuentes import leer


class PruebasParser(unittest.TestCase):
    def test_precios_en_centavos_y_omite_gratis_o_fallidos(self):
        precios = steam_lote.parsear_lote(leer("store.steampowered.com/appdetails-lote.json"))
        # 1172470 es gratuito (sin price_overview) y 999999999 no existe: se siguen buscando por título.
        self.assertEqual(precios, {"1145360": (2499, 2499), "620": (199, 999)})

    def test_appid_de_la_url(self):
        self.assertEqual(steam_lote.appid_de("https://store.steampowered.com/app/1145360/Hades/"), "1145360")
        self.assertIsNone(steam_lote.appid_de("https://www.gog.com/game/hades"))

    def test_lotes_ordenados_y_del_tamano_pedido(self):
        urls = steam_lote.urls_por_lote(["30", "100", "20", "100"], tamano=2)
        self.assertEqual(len(urls), 2)
        self.assertIn("appids=20,30&", urls[0])   # Orden numérico y sin duplicados: misma URL (y caché) cada día.
        self.assertIn("appids=100&", urls[1])
        self.assertTrue(all("filters=price_overview" in u and "cc=us" in u for u in urls))


class _Respuesta:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo
        self.obtenida_en = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


class ClienteFalso:
    def __init__(self, falla=False):
        self.falla, self.urls = falla, []

    def obtener(self, url):
        self.urls.append(url)
        if self.falla:
            raise ErrorTemporal("sin red")
        return _Respuesta(leer("store.steampowered.com/appdetails-lote.json"))


class PruebasPasoPorLote(unittest.TestCase):
    def setUp(self):
        self.bd = abrir_bd(":memory:")
        fuentes = registrar_fuentes(self.bd)
        with self.bd:
            self.ejecucion = self.bd.execute(
                "INSERT INTO ejecucion (iniciada_en, modo, fuente_datos, configuracion, estado) "
                "VALUES ('2026-11-13T12:00:00+00:00', 'concurrente', 'vivo', '{}', 'en_curso') RETURNING id").fetchone()[0]
            for clave, url, estado in [("hades", "https://store.steampowered.com/app/1145360/Hades/", "aceptado"),
                                       ("portal-2", "https://store.steampowered.com/app/620/Portal_2/", "aceptado"),
                                       ("apex", "https://store.steampowered.com/app/1172470/Apex/", "aceptado"),
                                       ("dudoso", "https://store.steampowered.com/app/999/Otro/", "dudoso")]:
                juego = self.bd.execute("INSERT INTO juego (clave, titulo_canonico, origen, agregado_en) "
                                        "VALUES (?, ?, 'manual', '2026-11-13') RETURNING id", (clave, clave)).fetchone()[0]
                self.bd.execute("INSERT INTO producto_tienda (fuente_id, url, titulo_en_tienda, formato, juego_id, "
                                "estado_emparejamiento, visto_por_primera_vez) VALUES (?, ?, ?, 'digital', ?, ?, "
                                "'2026-11-13')", (fuentes["steam"], url, clave, juego, estado))

    def tearDown(self):
        self.bd.close()

    def test_guarda_precios_y_devuelve_los_juegos_actualizados(self):
        cliente = ClienteFalso()
        actualizados = precios_steam_por_lote(self.bd, cliente, self.ejecucion)
        self.assertEqual(actualizados, {"hades", "portal-2"})   # Apex (gratis) y el dudoso se buscan por título.
        self.assertEqual(len(cliente.urls), 1)                   # Los 3 aceptados caben en un solo lote.
        filas = self.bd.execute("SELECT p.url, o.precio_actual_centavos, o.precio_regular_centavos, o.ejecucion_id "
                                "FROM observacion_precio o JOIN producto_tienda p ON p.id = o.producto_id "
                                "ORDER BY o.precio_actual_centavos").fetchall()
        self.assertEqual([tuple(f)[1:] for f in filas], [(199, 999, self.ejecucion), (2499, 2499, self.ejecucion)])

    def test_si_el_lote_falla_se_buscan_por_titulo(self):
        self.assertEqual(precios_steam_por_lote(self.bd, ClienteFalso(falla=True), self.ejecucion), frozenset())
        self.assertEqual(self.bd.execute("SELECT COUNT(*) FROM observacion_precio").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
