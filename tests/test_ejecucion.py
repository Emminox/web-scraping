"""Pruebas de las opciones de ejecución para completar tiendas desde otra máquina (sin internet)."""

import tempfile
import unittest
from pathlib import Path

from radar.bd import abrir_bd
from radar.ejecucion import OpcionesEjecucion, _ultima_ejecucion_viva, construir_definicion
from radar.fuentes import nintendo
from radar.pipeline.modelos import Juego
from tests.utilidades import config_de_prueba


def fuentes_para(juego: Juego, steam_actualizados=frozenset(), **opciones) -> list[str]:
    with tempfile.TemporaryDirectory() as carpeta:
        config = config_de_prueba(Path(carpeta))
        definicion = construir_definicion(
            config, OpcionesEjecucion("secuencial", "vivo", ("pc",), **opciones),
            cliente=None, indice=nintendo.IndiceNintendo([]), persistidor=None,
            ruta_bd=Path(carpeta) / "radar.sqlite", destino_sitio=Path(carpeta) / "sitio",
            steam_actualizados=steam_actualizados)
        return [fuente for fuente, _url in definicion.fuentes_de(juego)]


class PruebasSoloFuentes(unittest.TestCase):
    juego = Juego("hades@pc", "Hades", clave_catalogo="hades", plataforma="pc")

    def test_por_defecto_todas_las_tiendas_de_la_plataforma(self):
        self.assertEqual(set(fuentes_para(self.juego)), {"steam", "gog", "cheapshark"})

    def test_steam_actualizado_por_lote_no_se_busca(self):
        self.assertEqual(set(fuentes_para(self.juego, steam_actualizados=frozenset({"hades"}))), {"gog", "cheapshark"})
        otro = Juego("celeste@pc", "Celeste", clave_catalogo="celeste", plataforma="pc")
        self.assertIn("steam", fuentes_para(otro, steam_actualizados=frozenset({"hades"})))  # Los demás sí.

    def test_solo_las_tiendas_pedidas(self):
        self.assertEqual(set(fuentes_para(self.juego, solo_fuentes=("steam", "cheapshark"))), {"steam", "cheapshark"})


class PruebasComplementar(unittest.TestCase):
    def test_usa_la_ultima_ejecucion_en_vivo_completa(self):
        bd = abrir_bd(":memory:")
        try:
            with bd:
                for modo, fuente, estado in [("concurrente", "vivo", "completa"), ("paralelo", "replay", "completa"),
                                             ("concurrente", "vivo", "fallida")]:
                    bd.execute("INSERT INTO ejecucion (iniciada_en, modo, fuente_datos, configuracion, estado) "
                               "VALUES ('2026-11-12T00:00:00+00:00', ?, ?, '{}', ?)", (modo, fuente, estado))
            # La 1 es la única en vivo y completa: ni la de replay (2) ni la fallida (3) cuentan como "actual".
            self.assertEqual(_ultima_ejecucion_viva(bd), 1)
        finally:
            bd.close()

    def test_sin_ejecuciones_no_hay_nada_que_complementar(self):
        bd = abrir_bd(":memory:")
        try:
            with self.assertRaises(ValueError):
                _ultima_ejecucion_viva(bd)
        finally:
            bd.close()


if __name__ == "__main__":
    unittest.main()
