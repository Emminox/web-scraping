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

    def test_edicion_especial_es_dudosa(self):
        resultado = emparejar_juego(paquete("The Witcher 3: Wild Hunt", "pc",
                                            ("gog", [candidato("The Witcher 3: Wild Hunt - Game of the Year Edition", fuente="gog")])))
        [e] = resultado.emparejamientos
        self.assertEqual(e.estado, "dudoso")
        self.assertIn("edición especial", e.motivo)

    def test_dlc_y_paquetes_son_dudosos(self):
        resultado = emparejar_juego(paquete("Hades", "pc", ("gog", [candidato("Hades Soundtrack", fuente="gog")])))
        self.assertEqual(resultado.emparejamientos[0].estado, "dudoso")
        self.assertIn("posible DLC", resultado.emparejamientos[0].motivo)
        resultado = emparejar_juego(paquete("Hades", "pc", ("gog", [candidato("Hades", fuente="gog", tipo="otro")])))
        self.assertEqual(resultado.emparejamientos[0].estado, "dudoso")

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


if __name__ == "__main__":
    unittest.main()
