"""Pruebas del catálogo: lectura, validación, carga sincronizada y verificación de requisitos.

Los juegos de estas pruebas son INVENTADOS ("Saga Estelar"...), para no confundirlos con datos reales.
"""

import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from radar.bd import abrir_bd
from radar.catalogo import (
    CATEGORIAS_DIFICULTAD,
    TIPOS,
    ErrorCatalogo,
    cargar_en_bd,
    leer_catalogo,
    verificar_requisitos,
)
from radar.config import RAIZ_PROYECTO
from radar.herramientas.cargar_catalogo import main as cargar_catalogo_main

PLATAFORMAS = {"ps4", "ps5", "switch", "switch2", "xbox-one", "xbox-series", "pc"}
AHORA = "2026-11-11T12:00:00+00:00"


def juego(clave: str, **extra) -> dict:
    """Juego mínimo válido; ``extra`` agrega o reemplaza campos."""
    datos = {"clave": clave, "titulo": clave.replace("-", " ").title(), "plataformas": [{"plataforma": "pc"}]}
    datos.update(extra)
    return datos


class BaseCatalogo(unittest.TestCase):
    """Crea una carpeta temporal de catálogo para cada prueba."""

    def setUp(self):
        self._temporal = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._temporal.name)

    def tearDown(self):
        self._temporal.cleanup()

    def escribir(self, nombre: str, juegos) -> None:
        texto = juegos if isinstance(juegos, str) else json.dumps(juegos, ensure_ascii=False)
        (self.carpeta / nombre).write_text(texto, encoding="utf-8")

    def leer(self):
        return leer_catalogo(self.carpeta, PLATAFORMAS)


class PruebasLectura(BaseCatalogo):
    def test_lee_juego_completo(self):
        self.escribir("manual.json", [juego(
            "saga-estelar-ii",
            titulo="Saga Estelar II",
            titulos_alternativos=["Saga Estelar 2", "Saga Estelar 2", "  SE2 "],
            caso_dificil="numeros_romanos",
            plataformas=[{"plataforma": "ps5", "fecha_lanzamiento": "2024-03-15", "msrp": 69.99}],
        )])
        [entrada] = self.leer()
        self.assertEqual(entrada.titulos_alternativos, ("Saga Estelar 2", "SE2"))  # Sin repetidos y sin espacios.
        self.assertEqual(entrada.plataformas[0].msrp_centavos, 6999)
        self.assertEqual(entrada.categoria_dificultad, "numeros_romanos")

    def test_msrp_sin_error_de_redondeo(self):
        # Con float, 0.29 * 100 = 28.999999999999996 -> se guardaría 28. Con Decimal, 29.
        self.escribir("a.json", [juego("barato", plataformas=[{"plataforma": "pc", "msrp": 0.29}])])
        self.assertEqual(self.leer()[0].plataformas[0].msrp_centavos, 29)

    def test_reporta_todos_los_problemas_juntos(self):
        self.escribir("a.json", [
            juego("Clave Mala"),
            juego("con-typo", titulos_alternativo=["x"]),
            juego("plataforma-rara", plataformas=[{"plataforma": "dreamcast"}]),
            juego("msrp-raro", plataformas=[{"plataforma": "pc", "msrp": 9.999}]),
            juego("fecha-rara", plataformas=[{"plataforma": "pc", "fecha_lanzamiento": "20240315"}]),
            juego("fecha-imposible", plataformas=[{"plataforma": "pc", "fecha_lanzamiento": "2024-02-30"}]),
            juego("sin-plataformas", plataformas=[]),
            juego("descubierto-sin-fuente", origen="descubrimiento"),
        ])
        with self.assertRaises(ErrorCatalogo) as contexto:
            self.leer()
        texto = "\n".join(contexto.exception.problemas)
        for esperado in ("'clave'", "campo desconocido 'titulos_alternativo'", "'dreamcast'",
                         "2 decimales", "'20240315'", "'2024-02-30'", "al menos una plataforma",
                         "falta 'descubierto_por'"):
            self.assertIn(esperado, texto)

    def test_clave_repetida_en_dos_archivos(self):
        self.escribir("a.json", [juego("saga-estelar")])
        self.escribir("b.json", [juego("saga-estelar")])
        with self.assertRaises(ErrorCatalogo) as contexto:
            self.leer()
        self.assertIn("repetida en a.json y b.json", contexto.exception.problemas[0])

    def test_json_invalido_y_no_lista(self):
        self.escribir("roto.json", "[{")
        self.escribir("objeto.json", {"clave": "x"})
        with self.assertRaises(ErrorCatalogo) as contexto:
            self.leer()
        self.assertEqual(len(contexto.exception.problemas), 2)


class PruebasCarga(BaseCatalogo):
    def setUp(self):
        super().setUp()
        self.bd = abrir_bd(":memory:")

    def tearDown(self):
        self.bd.close()
        super().tearDown()

    def cargar(self):
        return cargar_en_bd(self.bd, self.leer(), AHORA)

    def test_carga_y_recarga_idempotente(self):
        self.escribir("a.json", [juego("saga-estelar", titulos_alternativos=["SE"]), juego("otra-saga")])
        primera = self.cargar()
        self.assertEqual((primera.nuevos, primera.actualizados), (2, 0))
        segunda = self.cargar()  # Cargar de nuevo lo mismo no duplica nada.
        self.assertEqual((segunda.nuevos, segunda.actualizados), (0, 2))
        self.assertEqual(self.bd.execute("SELECT COUNT(*) FROM juego").fetchone()[0], 2)
        self.assertEqual(self.bd.execute("SELECT COUNT(*) FROM titulo_alternativo").fetchone()[0], 1)

    def test_quitar_del_archivo_desactiva_sin_borrar(self):
        self.escribir("a.json", [juego("saga-estelar"), juego("otra-saga")])
        self.cargar()
        self.escribir("a.json", [juego("saga-estelar")])
        resumen = self.cargar()
        self.assertEqual(resumen.desactivados, 1)
        fila = self.bd.execute("SELECT activo FROM juego WHERE clave = 'otra-saga'").fetchone()
        self.assertEqual(fila["activo"], 0)  # Sigue en la base (con su historial), pero inactivo.

    def test_activo_false_en_el_archivo(self):
        self.escribir("a.json", [juego("saga-estelar", activo=False)])
        self.cargar()
        self.assertEqual(self.bd.execute("SELECT activo FROM juego").fetchone()["activo"], 0)

    def test_fuente_desconocida_no_cambia_nada(self):
        self.escribir("a.json", [juego("saga-estelar")])
        self.cargar()
        self.escribir("a.json", [juego("nuevo", origen="descubrimiento", descubierto_por="no-existe")])
        with self.assertRaises(ErrorCatalogo):
            self.cargar()
        # La carga fallida no tocó la base: el juego anterior sigue activo y el nuevo no existe.
        filas = {f["clave"]: f["activo"] for f in self.bd.execute("SELECT clave, activo FROM juego")}
        self.assertEqual(filas, {"saga-estelar": 1})

    def test_constantes_coinciden_con_el_esquema(self):
        """Si alguien cambia los CHECK de esquema.sql y no catalogo.py (o al revés), esto falla."""
        for numero, tipo in enumerate(TIPOS):
            self.bd.execute(
                "INSERT INTO juego (clave, titulo_canonico, tipo, origen, agregado_en) VALUES (?, 't', ?, 'manual', ?)",
                (f"tipo-{numero}", tipo, AHORA),
            )
        for numero, categoria in enumerate(CATEGORIAS_DIFICULTAD):
            self.bd.execute(
                "INSERT INTO juego (clave, titulo_canonico, es_caso_dificil, categoria_dificultad, origen, agregado_en) "
                "VALUES (?, 't', 1, ?, 'manual', ?)",
                (f"cat-{numero}", categoria, AHORA),
            )
        plataformas_bd = {f["codigo"] for f in self.bd.execute("SELECT codigo FROM plataforma")}
        self.assertEqual(plataformas_bd, PLATAFORMAS)

    def test_verificar_requisitos(self):
        self.escribir("a.json", [
            juego("uno", caso_dificil="edicion", plataformas=[{"plataforma": "ps5", "msrp": 59.99}]),
            juego("dos", plataformas=[{"plataforma": "switch"}, {"plataforma": "pc"}]),
        ])
        self.cargar()
        requisitos = {r.descripcion: r for r in verificar_requisitos(self.bd)}
        self.assertEqual(requisitos["Juegos activos"].actual, 2)
        self.assertFalse(requisitos["Juegos activos"].cumplido)  # 2 < 500
        self.assertEqual(requisitos["Familias de plataforma distintas"].actual, 3)
        self.assertTrue(requisitos["Familias de plataforma distintas"].cumplido)
        self.assertEqual(requisitos["Casos difíciles"].actual, 1)
        self.assertEqual(requisitos["Juegos con MSRP en al menos una plataforma"].actual, 1)


class PruebasComando(unittest.TestCase):
    def test_comando_completo_con_configuracion_temporal(self):
        with tempfile.TemporaryDirectory() as carpeta:
            raiz = Path(carpeta)
            (raiz / "config").mkdir()
            # Se copia la configuración real: sus rutas relativas apuntarán dentro de la carpeta temporal.
            texto = (RAIZ_PROYECTO / "config" / "config.toml").read_text(encoding="utf-8")
            (raiz / "config" / "config.toml").write_text(texto, encoding="utf-8")
            (raiz / "catalogo").mkdir()
            (raiz / "catalogo" / "manual.json").write_text(json.dumps([juego("saga-estelar")]), encoding="utf-8")

            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                codigo = cargar_catalogo_main(["--config", str(raiz / "config" / "config.toml")])
            self.assertEqual(codigo, 0)
            self.assertIn("nuevos: 1", salida.getvalue())
            self.assertIn("[FALTA] Juegos activos: 1 / 500", salida.getvalue())

            conexion = sqlite3.connect(raiz / "datos" / "radar.sqlite")
            self.assertEqual(conexion.execute("SELECT clave FROM juego").fetchone()[0], "saga-estelar")
            conexion.close()


if __name__ == "__main__":
    unittest.main()
