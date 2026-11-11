"""Pruebas del esquema de la base de datos: que las reglas del diseño realmente se cumplen."""

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from radar.bd import VERSION_ESQUEMA, ErrorEsquema, abrir_bd

AHORA = "2026-11-11T12:00:00+00:00"


def poblar_minimo(bd: sqlite3.Connection) -> dict[str, int]:
    """Inserta un juego, una fuente, dos productos y una ejecución. Devuelve sus ids."""
    with bd:
        fuente = bd.execute(
            "INSERT INTO fuente (codigo, nombre, tipo, dominio, metodo) "
            "VALUES ('tienda-x', 'Tienda X', 'tienda_plataforma', 'tienda.x.com', 'html')"
        ).lastrowid
        juego = bd.execute(
            "INSERT INTO juego (clave, titulo_canonico, origen, agregado_en) "
            "VALUES ('hades', 'Hades', 'manual', ?)", (AHORA,)
        ).lastrowid
        productos = [
            bd.execute(
                "INSERT INTO producto_tienda (fuente_id, url, titulo_en_tienda, formato, juego_id, "
                "estado_emparejamiento, visto_por_primera_vez) VALUES (?, ?, 'Hades', ?, ?, 'aceptado', ?)",
                (fuente, f"https://tienda.x.com/{n}", formato, juego, AHORA),
            ).lastrowid
            for n, formato in ((1, "digital"), (2, "fisico"))
        ]
    return {"fuente": fuente, "juego": juego, "producto_a": productos[0], "producto_b": productos[1]}


def nueva_ejecucion(bd: sqlite3.Connection, fecha: str = AHORA) -> int:
    with bd:
        return bd.execute(
            "INSERT INTO ejecucion (iniciada_en, modo, fuente_datos, configuracion) "
            "VALUES (?, 'secuencial', 'vivo', '{}')", (fecha,)
        ).lastrowid


def observar_precio(bd, producto: int, ejecucion: int, centavos: int, fecha: str) -> None:
    with bd:
        bd.execute(
            "INSERT INTO observacion_precio (producto_id, ejecucion_id, obtenida_en, precio_actual_centavos) "
            "VALUES (?, ?, ?, ?)", (producto, ejecucion, fecha, centavos),
        )


class PruebasEsquema(unittest.TestCase):
    def setUp(self):
        self.bd = abrir_bd(":memory:")

    def tearDown(self):
        self.bd.close()

    def test_crea_tablas_version_y_plataformas(self):
        self.assertEqual(self.bd.execute("PRAGMA user_version").fetchone()[0], VERSION_ESQUEMA)
        familias = {f["familia"] for f in self.bd.execute("SELECT familia FROM plataforma")}
        self.assertEqual(familias, {"playstation", "nintendo", "xbox", "pc"})

    def test_claves_foraneas_activas(self):
        # Un título alternativo de un juego que no existe debe rechazarse.
        with self.assertRaises(sqlite3.IntegrityError):
            with self.bd:
                self.bd.execute("INSERT INTO titulo_alternativo (juego_id, titulo) VALUES (999, 'X')")

    def test_strict_rechaza_tipos_incorrectos(self):
        ids = poblar_minimo(self.bd)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.bd:
                self.bd.execute(
                    "INSERT INTO juego_plataforma (juego_id, plataforma_codigo, msrp_centavos) "
                    "VALUES (?, 'pc', 'cincuenta')", (ids["juego"],)
                )

    def test_observaciones_no_se_pueden_modificar(self):
        ids = poblar_minimo(self.bd)
        ejecucion = nueva_ejecucion(self.bd)
        observar_precio(self.bd, ids["producto_a"], ejecucion, 2499, AHORA)
        with self.assertRaises(sqlite3.IntegrityError) as contexto:
            with self.bd:
                self.bd.execute("UPDATE observacion_precio SET precio_actual_centavos = 1")
        self.assertIn("no se modifican", str(contexto.exception))

    def test_no_duplica_observacion_en_la_misma_ejecucion(self):
        ids = poblar_minimo(self.bd)
        ejecucion = nueva_ejecucion(self.bd)
        observar_precio(self.bd, ids["producto_a"], ejecucion, 2499, AHORA)
        with self.assertRaises(sqlite3.IntegrityError):
            observar_precio(self.bd, ids["producto_a"], ejecucion, 2499, AHORA)

    def test_calificacion_sin_plataforma_no_se_duplica(self):
        ids = poblar_minimo(self.bd)
        ejecucion = nueva_ejecucion(self.bd)
        sql = ("INSERT INTO observacion_calificacion (juego_id, fuente_id, puntaje, escala, ejecucion_id, "
               "obtenida_en) VALUES (?, ?, 93, 100, ?, ?)")
        with self.bd:
            self.bd.execute(sql, (ids["juego"], ids["fuente"], ejecucion, AHORA))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.bd:
                self.bd.execute(sql, (ids["juego"], ids["fuente"], ejecucion, AHORA))

    def test_aceptado_exige_juego(self):
        ids = poblar_minimo(self.bd)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.bd:
                self.bd.execute(
                    "INSERT INTO producto_tienda (fuente_id, url, titulo_en_tienda, formato, "
                    "estado_emparejamiento, visto_por_primera_vez) VALUES (?, 'u', 't', 'digital', 'aceptado', ?)",
                    (ids["fuente"], AHORA),
                )

    def test_ultimo_precio_y_desactualizado(self):
        ids = poblar_minimo(self.bd)
        ayer = nueva_ejecucion(self.bd, "2026-11-10T12:00:00+00:00")
        hoy = nueva_ejecucion(self.bd)
        observar_precio(self.bd, ids["producto_a"], ayer, 2999, "2026-11-10T12:00:00+00:00")
        observar_precio(self.bd, ids["producto_a"], hoy, 1999, AHORA)
        # El producto B solo tiene precio de ayer: hoy su tienda "falló".
        observar_precio(self.bd, ids["producto_b"], ayer, 3999, "2026-11-10T12:00:00+00:00")

        filas = {f["producto_id"]: f for f in self.bd.execute("SELECT * FROM v_ultimo_precio")}
        self.assertEqual(filas[ids["producto_a"]]["precio_actual_centavos"], 1999)
        self.assertEqual(filas[ids["producto_a"]]["desactualizado"], 0)
        self.assertEqual(filas[ids["producto_b"]]["precio_actual_centavos"], 3999)
        self.assertEqual(filas[ids["producto_b"]]["desactualizado"], 1)

    def test_minimo_historico_por_formato(self):
        ids = poblar_minimo(self.bd)
        for numero, precio in enumerate((2999, 1499, 1999)):
            ejecucion = nueva_ejecucion(self.bd, f"2026-11-0{numero + 1}T12:00:00+00:00")
            observar_precio(self.bd, ids["producto_a"], ejecucion, precio, f"2026-11-0{numero + 1}T12:00:00+00:00")
        fila = self.bd.execute(
            "SELECT minimo_centavos FROM v_minimo_historico WHERE juego_id = ? AND formato = 'digital'",
            (ids["juego"],),
        ).fetchone()
        self.assertEqual(fila["minimo_centavos"], 1499)

    def test_la_conexion_no_se_comparte_entre_hilos(self):
        """Refuerza el diseño de un solo escritor: otro hilo no puede usar esta conexión."""
        errores = []

        def usar_desde_otro_hilo():
            try:
                self.bd.execute("SELECT 1")
            except sqlite3.ProgrammingError as error:
                errores.append(error)

        hilo = threading.Thread(target=usar_desde_otro_hilo)
        hilo.start()
        hilo.join()
        self.assertEqual(len(errores), 1)


class PruebasArchivo(unittest.TestCase):
    def test_reabrir_no_rompe_y_detecta_otra_version(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "sub" / "radar.sqlite"
            abrir_bd(ruta).close()
            abrir_bd(ruta).close()  # Abrir dos veces es seguro.
            # Simula una base creada por una versión futura del esquema.
            otra = sqlite3.connect(ruta)
            otra.execute("PRAGMA user_version = 99")
            otra.close()
            with self.assertRaises(ErrorEsquema):
                abrir_bd(ruta)


if __name__ == "__main__":
    unittest.main()
