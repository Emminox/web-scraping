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
        # Steam y GOG ajustan el precio al país del comprador: la página del juego lo advierte (no Best Buy).
        self.assertEqual([p["precio_regional"] for p in detalle["precios"]], [True, True])
        for archivo in ("index.html", "juego.html", "metricas.html", "app.js", "estilos.css", "datos/metricas.json"):
            self.assertTrue((destino / archivo).exists(), archivo)
        # Las listas largas del panel van en PDF; el JSON solo lleva el resumen y la ruta del PDF.
        metricas = json.loads((destino / "datos" / "metricas.json").read_text(encoding="utf-8"))
        for clave, pdf in (("dudosos_resumen", "datos/emparejamientos-dudosos.pdf"),
                           ("fallidos_resumen", "datos/cola-de-fallidos.pdf")):
            self.assertEqual(metricas[clave]["pdf"], pdf)
            self.assertTrue((destino / pdf).read_bytes().startswith(b"%PDF"))
        self.assertNotIn("dudosos", metricas)

    def test_tipos_de_la_tarjeta_incluyen_ediciones_con_contenido(self):
        # Una tienda solo vende la edición GOTY: el filtro "Juego + DLC" del sitio debe encontrarlo.
        self.persistir(resultado(
            juego("hades", "Hades"),
            ("steam", [candidato("steam", "Hades", "https://store.steampowered.com/app/1/", 1249, 2499)]),
            ("gog", [candidato("gog", "Hades Game of the Year Edition", "https://www.gog.com/hades", 1999, 2499)]),
        ))
        destino = self.carpeta / "sitio"
        generar_sitio(self.bd, destino)
        [tarjeta] = json.loads((destino / "datos" / "juegos.json").read_text(encoding="utf-8"))["juegos"]
        self.assertEqual(tarjeta["tipos"], ["juego", "juego_dlc"])

    def test_ofertas_por_producto_para_filtros_combinados(self):
        # Hades en PC (Steam, digital) y en Switch (Best Buy, físico). El filtro "PC + Físico" no debe encontrarlo:
        # para eso el sitio necesita cada oferta con su plataforma, formato y tienda juntos.
        hades_pc, hades_switch = juego("hades", "Hades"), juego("hades", "Hades", plataforma="switch")
        fisico = Candidato("bestbuy", "Hades - Nintendo Switch", "https://www.bestbuy.com/hades", "switch", "fisico",
                           2999, 3499, obtenida_en=OBTENIDA)
        self.persistir(
            resultado(hades_pc, ("steam", [candidato("steam", "Hades", "https://store.steampowered.com/app/1/", 1249, 2499)])),
            resultado(hades_switch, ("bestbuy", [fisico])),
        )
        destino = self.carpeta / "sitio"
        generar_sitio(self.bd, destino)
        [tarjeta] = json.loads((destino / "datos" / "juegos.json").read_text(encoding="utf-8"))["juegos"]
        ofertas = [(o["familia"], o["formato"], o["tienda"], o["precio"], o["en_oferta"]) for o in tarjeta["ofertas"]]
        self.assertEqual(ofertas, [("pc", "digital", "steam", 1249, True), ("nintendo", "fisico", "bestbuy", 2999, True)])
        pc_fisico = [o for o in tarjeta["ofertas"] if o["familia"] == "pc" and o["formato"] == "fisico"]
        self.assertEqual(pc_fisico, [])  # Antes el juego pasaba porque "pc" y "fisico" estaban en listas separadas.


class PruebasHistorial(unittest.TestCase):
    def test_un_punto_por_dia_con_el_ultimo_precio(self):
        from radar.sitio.generar import historial_por_dia
        observaciones = [
            ("2026-11-10T08:00:00+00:00", 2999),
            ("2026-11-11T09:00:00+00:00", 2499),
            ("2026-11-11T21:00:00+00:00", 1999),  # Mismo día, más tarde: este es el que cuenta.
        ]
        self.assertEqual(historial_por_dia(observaciones), [["2026-11-10", 2999], ["2026-11-11", 1999]])
        self.assertEqual(historial_por_dia([]), [])

    def test_minimos_por_formato(self):
        from radar.sitio.generar import minimos_por_formato
        historial = {
            1: [("2026-10-01T10:00:00+00:00", 1999), ("2026-10-10T10:00:00+00:00", 399)],   # digital, switch
            2: [("2026-10-05T10:00:00+00:00", 3599), ("2026-10-20T10:00:00+00:00", 1799)],  # físico, switch
            3: [("2026-10-03T10:00:00+00:00", 399)],                                       # digital, pc (empate)
        }
        resultado = minimos_por_formato(historial, {1: "digital", 2: "fisico", 3: "digital"},
                                        {1: "switch", 2: "switch", 3: "pc"}, {"switch": 1999, "pc": None})
        self.assertEqual(resultado["fisico"], {"precio": 1799, "fecha": "2026-10-20", "descuento": 10})
        # Empate a $3.99: gana el primero en alcanzarlo (3 de octubre, PC, sin MSRP -> 0 %).
        self.assertEqual(resultado["digital"], {"precio": 399, "fecha": "2026-10-03", "descuento": 0})


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
