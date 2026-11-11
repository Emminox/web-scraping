"""Pruebas de la etapa Persistir y de la generación del sitio (sin internet)."""

import json
import tempfile
import threading
import unittest
from pathlib import Path

from radar.bd import abrir_bd
from radar.ejecucion import registrar_fuentes
from radar.emparejamiento.emparejar import emparejar_juego
from radar.fuentes.modelos import Candidato
from radar.persistencia import Persistidor
from radar.pipeline.modelos import Juego, PaqueteJuego, ResultadoFuente
from radar.sitio import generar_sitio

OBTENIDA = "2026-11-11T12:00:00+00:00"


def juego(clave, titulo, plataforma="pc", metascore=90):
    return Juego(f"{clave}@{plataforma}", titulo, clave_catalogo=clave, plataforma=plataforma,
                 metascore=metascore, origen="descubrimiento", obtenida_en=OBTENIDA,
                 imagen_url="https://www.metacritic.com/a/img/x.jpg")


def candidato(fuente, titulo, url, actual, regular, plataforma="pc", resena=None):
    return Candidato(fuente, titulo, url, plataforma, "digital", actual, regular,
                     resena_porcentaje=resena, resena_cantidad=1000 if resena else None, obtenida_en=OBTENIDA)


def resultado(j, *por_fuente):
    paquete = PaqueteJuego(j, tuple(ResultadoFuente(j, f, len(por_fuente), datos=tuple(c)) for f, c in por_fuente))
    return emparejar_juego(paquete)


class BasePrueba(unittest.TestCase):
    def setUp(self):
        self._temporal = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._temporal.name)
        self.ruta = self.carpeta / "radar.sqlite"
        self.bd = abrir_bd(self.ruta)
        self.fuentes = registrar_fuentes(self.bd)
        with self.bd:
            self.ejecucion = self.bd.execute(
                "INSERT INTO ejecucion (iniciada_en, modo, fuente_datos, configuracion, estado) "
                "VALUES (?, 'secuencial', 'vivo', '{}', 'en_curso') RETURNING id", (OBTENIDA,)).fetchone()[0]

    def tearDown(self):
        self.bd.close()
        self._temporal.cleanup()

    def persistir(self, *resultados):
        persistidor = Persistidor(self.ruta, self.ejecucion, self.fuentes)
        try:
            for r in resultados:
                persistidor(r)
        finally:
            persistidor.cerrar()


class PruebasPersistencia(BasePrueba):
    def test_guarda_juego_precios_calificaciones_y_msrp(self):
        self.persistir(resultado(
            juego("hades", "Hades"),
            ("gog", [candidato("gog", "Hades", "https://www.gog.com/hades", 1999, 2499)]),
            ("steam", [candidato("steam", "Hades", "https://store.steampowered.com/app/1/", 1249, 2499, resena=98)]),
        ))
        self.assertEqual(self.bd.execute("SELECT COUNT(*) FROM observacion_precio").fetchone()[0], 2)
        fuentes_calif = {f[0] for f in self.bd.execute(
            "SELECT f.codigo FROM observacion_calificacion c JOIN fuente f ON f.id = c.fuente_id")}
        self.assertEqual(fuentes_calif, {"metacritic", "steam-resenas"})
        # MSRP desde la tienda oficial preferida (Steam), no desde GOG.
        self.assertEqual(self.bd.execute("SELECT msrp_centavos FROM juego_plataforma").fetchone()[0], 2499)

    def test_producto_disputado_no_depende_del_orden(self):
        """Dos juegos eligen el mismo producto: gana el de mayor similitud, en cualquier orden."""
        producto = [candidato("steam", "Hades II", "https://store.steampowered.com/app/2/", 2999, 2999)]
        hades = resultado(juego("hades", "Hades"), ("steam", producto))       # Secuela: similitud baja.
        hades2 = resultado(juego("hades-ii", "Hades II"), ("steam", producto))  # Coincidencia exacta.
        dueños = []
        for orden in ((hades, hades2), (hades2, hades)):
            with self.bd:
                for tabla in ("observacion_precio", "producto_tienda", "observacion_calificacion", "juego_plataforma", "juego"):
                    self.bd.execute(f"DELETE FROM {tabla}")
            self.persistir(*orden)
            dueños.append(self.bd.execute(
                "SELECT j.clave, p.estado_emparejamiento FROM producto_tienda p JOIN juego j ON j.id = p.juego_id").fetchone()[:])
        self.assertEqual(dueños[0], dueños[1])
        self.assertEqual(dueños[0], ("hades-ii", "aceptado"))

    def test_un_solo_hilo_escritor(self):
        persistidor = Persistidor(self.ruta, self.ejecucion, self.fuentes)
        persistidor(resultado(juego("a", "A"), ("steam", [])))
        errores = []

        def desde_otro_hilo():
            try:
                persistidor(resultado(juego("b", "B"), ("steam", [])))
            except RuntimeError as error:
                errores.append(error)

        hilo = threading.Thread(target=desde_otro_hilo)
        hilo.start()
        hilo.join()
        persistidor.cerrar()
        self.assertEqual(len(errores), 1)
        self.assertIn("ADR-003", str(errores[0]))


class PruebasSitio(BasePrueba):
    def test_publica_solo_juegos_con_dos_tiendas(self):
        self.persistir(
            resultado(juego("hades", "Hades"),
                      ("gog", [candidato("gog", "Hades", "https://www.gog.com/hades", 1999, 2499)]),
                      ("steam", [candidato("steam", "Hades", "https://store.steampowered.com/app/1/", 1249, 2499, resena=98)])),
            resultado(juego("solo-una", "Solo Una"),
                      ("steam", [candidato("steam", "Solo Una", "https://store.steampowered.com/app/9/", 999, 999)])),
        )
        destino = self.carpeta / "sitio"
        resumen = generar_sitio(self.bd, destino)
        self.assertEqual(resumen, {"publicados": 1, "sin_precio_suficiente": 1})
        datos = json.loads((destino / "datos" / "juegos.json").read_text(encoding="utf-8"))
        [tarjeta] = datos["juegos"]
        self.assertEqual((tarjeta["clave"], tarjeta["precio"], tarjeta["tienda"]), ("hades", 1249, "steam"))
        self.assertEqual(tarjeta["descuento"], 50)
        self.assertTrue(tarjeta["en_oferta"])
        self.assertFalse(tarjeta["minimo_historico"])  # Con una sola fecha de observación, no se marca.
        self.assertEqual((tarjeta["metascore"], tarjeta["steam"]), (90, 98))
        # Candidatas en orden de preferencia: Steam (producto aceptado) primero, luego Metacritic.
        self.assertTrue(tarjeta["imagenes"][0]["url"].endswith("/apps/1/library_600x900_2x.jpg"))
        self.assertEqual(tarjeta["imagenes"][-1],
                         {"url": "https://www.metacritic.com/a/img/x.jpg", "hd": None, "solo_vertical": False})
        detalle = json.loads((destino / "datos" / "juegos" / "hades.json").read_text(encoding="utf-8"))
        self.assertEqual([p["precio"] for p in detalle["precios"]], [1249, 1999])  # De menor a mayor.
        for archivo in ("index.html", "juego.html", "metricas.html", "app.js", "estilos.css", "datos/metricas.json"):
            self.assertTrue((destino / archivo).exists(), archivo)


class PruebasImagenes(unittest.TestCase):
    def test_portada_steam_desde_url_del_producto(self):
        from radar.sitio.generar import portada_steam
        self.assertEqual(
            portada_steam("https://store.steampowered.com/app/1145360/Hades/"),
            "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1145360/library_600x900_2x.jpg",
        )
        self.assertIsNone(portada_steam("https://store.steampowered.com/bundle/123/Algo/"))
        self.assertIsNone(portada_steam(None))

    def test_original_de_metacritic(self):
        from radar.sitio.generar import original_metacritic
        redimensionada = ("https://www.metacritic.com/a/img/resize/2ad6447e240f2121347f4973e8c31413dd76505a/"
                          "catalog/provider/6/3/6-1-844837-13.jpg?auto=webp&fit=cover&height=288&quality=70&width=192")
        self.assertEqual(original_metacritic(redimensionada),
                         "https://www.metacritic.com/a/img/catalog/provider/6/3/6-1-844837-13.jpg")
        self.assertIsNone(original_metacritic(None))


if __name__ == "__main__":
    unittest.main()
