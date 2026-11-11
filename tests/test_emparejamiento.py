"""Pruebas de normalización, similitud y emparejamiento con los casos difíciles típicos."""

import pickle
import unittest

from radar.emparejamiento.emparejar import UMBRAL, emparejar_juego
from radar.emparejamiento.normalizar import normalizar
from radar.emparejamiento.similitud import levenshtein, proporcion, similitud
from radar.fuentes.modelos import Candidato
from radar.pipeline.modelos import Juego, PaqueteJuego, ResultadoFuente


def candidato(titulo, *, fuente="steam", plataforma="pc", url=None, tipo="juego", precio=1999):
    return Candidato(fuente, titulo, url or f"https://{fuente}.ejemplo/{titulo}", plataforma, "digital",
                     precio, precio, tipo)


def paquete(titulo, plataforma, *por_fuente, alternativos=()):
    juego = Juego(f"x@{plataforma}", titulo, tuple(alternativos), clave_catalogo="x", plataforma=plataforma)
    resultados = tuple(ResultadoFuente(juego, fuente, len(por_fuente), datos=tuple(cands)) for fuente, cands in por_fuente)
    return PaqueteJuego(juego, resultados)


class PruebasNormalizar(unittest.TestCase):
    def test_plataforma_puntuacion_acentos(self):
        self.assertEqual(normalizar("Hades - Nintendo Switch Lite, Nintendo Switch").texto, "hades")
        self.assertEqual(normalizar("Pokémon™ Legends: Arceus").texto, "pokemon legends arceus")
        self.assertEqual(normalizar("Assassin's Creed® Valhalla (PS5)").texto, "assassins creed valhalla")

    def test_casos_reales_de_best_buy_y_steam(self):
        # Títulos tal como los devolvieron las tiendas en la primera ejecución en vivo.
        bestbuy = ("The Legend of Zelda: Breath of the Wild - Nintendo Switch – OLED Model, "
                   "Nintendo Switch, Nintendo Switch Lite")
        self.assertEqual(normalizar(bestbuy).texto, normalizar("The Legend of Zelda: Breath of the Wild").texto)
        enhanced = normalizar("Grand Theft Auto V Enhanced")
        self.assertEqual(enhanced.texto, "grand theft auto 5")
        self.assertEqual(enhanced.ediciones, frozenset({"enhanced"}))

    def test_romanos_y_numeros(self):
        self.assertEqual(normalizar("Final Fantasy VII").texto, "final fantasy 7")
        self.assertEqual(normalizar("Hades II").numeros, frozenset({"2"}))
        self.assertEqual(normalizar("Hades").numeros, frozenset())

    def test_etiquetas_entre_corchetes_de_best_buy(self):
        bestbuy = "Death's Door - Nintendo Switch – OLED Model, Nintendo Switch, Nintendo Switch Lite [Digital]"
        self.assertEqual(normalizar(bestbuy).texto, normalizar("Death's Door").texto)
        self.assertEqual(normalizar("Tetris Effect: Connected - Nintendo Switch [Digital]").texto, "tetris effect connected")

    def test_marcas_de_formato_de_best_buy(self):
        self.assertEqual(normalizar("NSW - AZURE STRIKER GUNVOLT 3 (LRG) - Nintendo Switch").texto, "azure striker gunvolt 3")
        caja = normalizar("Mario + Rabbids Kingdom Battle (Code in Box) - Nintendo Switch – OLED Model, Nintendo Switch")
        self.assertEqual(caja.texto, normalizar("Mario + Rabbids: Kingdom Battle").texto)
        self.assertEqual(caja.ediciones, frozenset())  # Neutra: no es otra edición.
        self.assertEqual(normalizar("Ring Fit Adventure Physical Edition").texto, "ring fit adventure")

    def test_anio_entre_parentesis(self):
        # Metacritic distingue juegos homónimos con el año; las tiendas no lo escriben.
        self.assertEqual(normalizar("Unreal Tournament (1999)").texto, "unreal tournament")
        self.assertEqual(normalizar("Unreal Tournament (1999)").numeros, frozenset())
        self.assertEqual(normalizar("FIFA 2004").numeros, frozenset({"2004"}))  # Sin paréntesis es parte del nombre.
        self.assertGreaterEqual(similitud(normalizar("Unreal Tournament (1999)"), normalizar("Unreal Tournament")),
                                UMBRAL)

    def test_indice_de_nintendo_usa_las_mismas_reglas(self):
        from radar.ejecucion import palabras_para_indice
        self.assertEqual(palabras_para_indice("Pokémon™ Legends: Arceus"), {"pokemon", "legends", "arceus"})
        self.assertEqual(palabras_para_indice("Hades II (2025)"), {"hades", "ii"})  # Romanos intactos (como en la URL).

    def test_ediciones_y_dlc(self):
        goty = normalizar("The Witcher 3: Wild Hunt - Game of the Year Edition")
        self.assertEqual(goty.texto, "witcher 3 wild hunt")
        self.assertEqual(goty.ediciones, frozenset({"game of the year edition"}))
        self.assertEqual(normalizar("Hades Standard Edition").ediciones, frozenset())  # Neutra.
        self.assertIn("soundtrack", normalizar("Hades Original Soundtrack").dlc)


class PruebasSimilitud(unittest.TestCase):
    def test_levenshtein(self):
        self.assertEqual(levenshtein("hades", "hades"), 0)
        self.assertEqual(levenshtein("hades", "hadez"), 1)
        self.assertEqual(levenshtein("kitten", "sitting"), 3)
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertAlmostEqual(proporcion("abcd", "abce"), 0.75)

    def test_secuela_penalizada(self):
        self.assertEqual(similitud(normalizar("Hades"), normalizar("HADES™")), 1.0)
        self.assertLess(similitud(normalizar("Hades"), normalizar("Hades II")), UMBRAL)

    def test_orden_de_palabras(self):
        self.assertGreater(similitud(normalizar("Zelda Breath of the Wild"), normalizar("Breath of the Wild Zelda")), 0.95)


class PruebasEmparejar(unittest.TestCase):
    def test_elige_el_correcto_y_descarta_la_secuela(self):
        resultado = emparejar_juego(paquete("Hades", "pc", ("steam", [candidato("Hades II"), candidato("Hades")])))
        [elegido] = resultado.emparejamientos
        self.assertEqual((elegido.candidato.titulo, elegido.estado), ("Hades", "aceptado"))

    def test_edicion_con_contenido_se_acepta_como_juego_dlc(self):
        # Caso real: muchas tiendas venden SOLO la edición GOTY/Complete. Se acepta y queda anotada.
        resultado = emparejar_juego(paquete("The Witcher 3: Wild Hunt", "pc",
                                            ("gog", [candidato("The Witcher 3: Wild Hunt - Game of the Year Edition", fuente="gog")])))
        [e] = resultado.emparejamientos
        self.assertEqual(e.estado, "aceptado")
        self.assertIn("juego + DLC", e.motivo)
        self.assertEqual(e.candidato.tipo, "juego_dlc")

    def test_una_descarga_con_varias_tiendas_da_un_emparejamiento_por_tienda(self):
        # Una consulta a CheapShark trae ofertas de varias tiendas: se elige el mejor producto de CADA una.
        resultado = emparejar_juego(paquete("Hades", "pc", ("cheapshark", [
            candidato("Hades", fuente="humble"), candidato("Hades II", fuente="humble"),
            candidato("Hades", fuente="epic"), candidato("Hades Soundtrack", fuente="fanatical"),
        ])))
        por_tienda = {e.candidato.fuente: (e.candidato.titulo, e.estado) for e in resultado.emparejamientos}
        self.assertEqual(por_tienda["humble"], ("Hades", "aceptado"))
        self.assertEqual(por_tienda["epic"], ("Hades", "aceptado"))
        self.assertEqual(por_tienda["fanatical"][1], "dudoso")  # Solo vendía la banda sonora.

    def test_remasterizacion_sigue_siendo_dudosa(self):
        resultado = emparejar_juego(paquete("Deus Ex", "pc", ("steam", [candidato("Deus Ex Remastered")])))
        [e] = resultado.emparejamientos
        self.assertEqual(e.estado, "dudoso")
        self.assertIn("edición distinta: remastered", e.motivo)

    def test_si_existe_la_base_gana_a_la_edicion(self):
        resultado = emparejar_juego(paquete("Batman: Arkham City", "pc", ("steam", [
            candidato("Batman: Arkham City - Game of the Year Edition", url="https://steam.ejemplo/a-goty"),
            candidato("Batman: Arkham City", url="https://steam.ejemplo/z-base"),
        ])))
        [e] = resultado.emparejamientos
        self.assertEqual((e.candidato.titulo, e.estado, e.motivo), ("Batman: Arkham City", "aceptado", None))

    def test_dlc_y_paquetes_son_dudosos(self):
        resultado = emparejar_juego(paquete("Hades", "pc", ("gog", [candidato("Hades Soundtrack", fuente="gog")])))
        self.assertEqual(resultado.emparejamientos[0].estado, "dudoso")
        self.assertIn("posible DLC", resultado.emparejamientos[0].motivo)
        # Un paquete de varios juegos (otro nombre) sigue siendo dudoso o rechazado.
        resultado = emparejar_juego(paquete("Hades", "pc", ("gog", [candidato("Hades Bundle Pack", fuente="gog", tipo="otro")])))
        self.assertNotEqual(resultado.emparejamientos[0].estado, "aceptado")

    def test_paquete_con_el_mismo_nombre_es_juego_mas_contenido(self):
        # Caso real: GOG vende "Planescape: Torment: Enhanced Edition" como 'pack' (el juego y sus extras).
        resultado = emparejar_juego(paquete("Planescape: Torment", "pc", (
            "gog", [candidato("Planescape: Torment: Enhanced Edition", fuente="gog", tipo="otro")])))
        [e] = resultado.emparejamientos
        self.assertEqual((e.estado, e.candidato.tipo), ("aceptado", "juego_dlc"))
        resultado = emparejar_juego(paquete("Hades", "pc", ("gog", [candidato("Hades", fuente="gog", tipo="otro")])))
        self.assertIn("paquete con el mismo nombre", resultado.emparejamientos[0].motivo)

    def test_prefiere_el_juego_base_frente_al_dlc_con_igual_similitud(self):
        # La URL del DLC es alfabéticamente menor: sin la preferencia por "limpio", ganaría el DLC.
        resultado = emparejar_juego(paquete("Hades", "pc", ("steam", [
            candidato("Hades Soundtrack", url="https://steam.ejemplo/a-soundtrack"),
            candidato("Hades", url="https://steam.ejemplo/z-juego"),
        ])))
        self.assertEqual(resultado.emparejamientos[0].candidato.titulo, "Hades")
        self.assertEqual(resultado.emparejamientos[0].estado, "aceptado")

    def test_ignora_otra_plataforma_y_usa_titulos_alternativos(self):
        resultado = emparejar_juego(paquete(
            "The Legend of Zelda: Breath of the Wild", "switch",
            ("bestbuy", [candidato("Zelda BOTW - PlayStation 5", fuente="bestbuy", plataforma="ps5"),
                         candidato("Zelda BOTW - Nintendo Switch", fuente="bestbuy", plataforma="switch")]),
            alternativos=["Zelda BOTW"],
        ))
        [e] = resultado.emparejamientos
        self.assertEqual((e.candidato.plataforma, e.estado), ("switch", "aceptado"))

    def test_sin_parecido_es_rechazado_y_errores_se_reportan(self):
        juego_pc = paquete("Hades", "pc", ("steam", [candidato("Cyberpunk 2077")]))
        self.assertEqual(emparejar_juego(juego_pc).emparejamientos[0].estado, "rechazado")
        juego = Juego("x@pc", "Hades", clave_catalogo="x", plataforma="pc")
        con_error = PaqueteJuego(juego, (ResultadoFuente(juego, "gog", 1, error="HTTP 503"),))
        self.assertEqual(emparejar_juego(con_error).errores_fuente, (("gog", "HTTP 503"),))

    def test_es_determinista_e_independiente_del_orden(self):
        a = candidato("Hades", url="https://steam.ejemplo/b")
        b = candidato("Hades", url="https://steam.ejemplo/a")
        uno = emparejar_juego(paquete("Hades", "pc", ("steam", [a, b])))
        dos = emparejar_juego(paquete("Hades", "pc", ("steam", [b, a])))
        self.assertEqual(uno, dos)
        self.assertEqual(uno.emparejamientos[0].candidato.url, "https://steam.ejemplo/a")

    def test_se_puede_enviar_a_otro_proceso(self):
        resultado = emparejar_juego(paquete("Hades", "pc", ("steam", [candidato("Hades")])))
        self.assertEqual(pickle.loads(pickle.dumps(resultado)), resultado)
        pickle.dumps(emparejar_juego)  # La función también (está a nivel de módulo).


class PruebasValidacion(unittest.TestCase):
    def test_metricas_por_umbral(self):
        from radar.herramientas.validar_emparejamiento import evaluar
        pares = [("Hades", "HADES™", True), ("Hades", "Hades II", False),
                 ("Zelda Breath of the Wild", "The Legend of Zelda: Breath of the Wild", True)]
        resultados = {r["umbral"]: r for r in evaluar(pares)}
        r = resultados[0.88]
        self.assertEqual((r["fp"], r["precision"]), (0, 1.0))  # "Hades II" no pasa el umbral.
        self.assertEqual(r["vp"] + r["fn"], 2)


    def test_muestra_repartida_cubre_toda_la_lista(self):
        from radar.herramientas.validar_emparejamiento import muestra_repartida
        filas = list(range(100))
        self.assertEqual(muestra_repartida(filas, 4), [0, 25, 50, 75])  # No solo las primeras 4.
        self.assertEqual(muestra_repartida(filas[:3], 4), [0, 1, 2])
        self.assertEqual(muestra_repartida(filas, 4), muestra_repartida(filas, 4))  # Determinista.


if __name__ == "__main__":
    unittest.main()
