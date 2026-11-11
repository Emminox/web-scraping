"""Pruebas del orquestador del pipeline: equivalencia de modos, manejo de errores y ausencia de bloqueos.

Estas pruebas NO miden rendimiento (las mediciones formales se hacen en replay, después del Hito 1).
Solo comprueban que el comportamiento sea correcto.
"""

import threading
import unittest

from radar.pipeline import ETAPAS, ResultadoEjecucion, ejecutar_pipeline
from tests.pipeline_falso import PREFIJO_EXPLOTA, PipelineFalso
from tests.utilidades import config_pipeline_de_prueba

# Cada combinación que debe dar el mismo resultado. "paralelo-hilos" es la variante de la pregunta 5.
CONFIGURACIONES = {
    "secuencial": ("secuencial", config_pipeline_de_prueba()),
    "concurrente": ("concurrente", config_pipeline_de_prueba()),
    "paralelo-procesos": ("paralelo", config_pipeline_de_prueba(ejecutor_emparejar="procesos")),
    "paralelo-hilos": ("paralelo", config_pipeline_de_prueba(ejecutor_emparejar="hilos")),
}

# Escenario con un poco de todo: una descarga que falla, un parseo que falla, un juego que hace fallar
# al emparejamiento y un juego sin fuentes.
ESCENARIO_CON_FALLOS = dict(
    juegos=10,
    fallar_descarga=frozenset({("juego-002", "tienda-a")}),
    fallar_parseo=frozenset({("juego-005", "resenas")}),
    sin_fuentes=frozenset({"juego-007"}),
    claves_extra=(f"{PREFIJO_EXPLOTA}-1",),
)


class PruebasPipeline(unittest.TestCase):
    def ejecutar(self, falso: PipelineFalso, nombre: str, *, limite_segundos: float = 60) -> ResultadoEjecucion:
        """Ejecuta el pipeline en otro hilo con un límite de tiempo: si se cuelga, la prueba FALLA."""
        modo, config = CONFIGURACIONES[nombre]
        salida: dict = {}

        def correr():
            try:
                salida["resultado"] = ejecutar_pipeline(falso.definicion(), modo, config)
            except BaseException as error:  # Se reenvía al hilo de la prueba.
                salida["error"] = error

        hilo = threading.Thread(target=correr, daemon=True)
        hilo.start()
        hilo.join(limite_segundos)
        if hilo.is_alive():
            self.fail(f"El pipeline en modo {nombre} no terminó en {limite_segundos} s (posible bloqueo)")
        if "error" in salida:
            raise salida["error"]
        return salida["resultado"]

    # --- Equivalencia (sección 7: "mismos resultados con los mismos datos") ------------------------

    def test_los_modos_dan_el_mismo_resultado(self):
        referencia = None
        for nombre in CONFIGURACIONES:
            with self.subTest(modo=nombre):
                falso = PipelineFalso(**ESCENARIO_CON_FALLOS)
                resultado = self.ejecutar(falso, nombre)
                # Lo persistido llega en distinto orden según el modo; se compara ordenado.
                huella = (
                    sorted(falso.persistidos),
                    sorted((e.etapa, e.clave, e.mensaje) for e in resultado.errores),
                    sorted((d.tarea.juego.clave, d.tarea.fuente, d.error) for d in resultado.fallidos),
                    resultado.juegos_persistidos,
                )
                if referencia is None:
                    referencia = huella
                else:
                    self.assertEqual(huella, referencia)

    # --- Comportamiento ----------------------------------------------------------------------------

    def test_cada_juego_se_procesa_una_vez_y_se_publica_una_vez(self):
        for nombre in CONFIGURACIONES:
            with self.subTest(modo=nombre):
                falso = PipelineFalso(juegos=9)
                resultado = self.ejecutar(falso, nombre)
                claves = [persistido[0] for persistido in falso.persistidos]
                self.assertEqual(sorted(claves), sorted(falso.claves))  # El repetido de la página 1 no se duplica.
                self.assertEqual(resultado.juegos_persistidos, 9)
                self.assertEqual(falso.publicaciones, 1)

    def test_persistir_usa_un_solo_hilo(self):
        for nombre in ("concurrente", "paralelo-procesos"):
            with self.subTest(modo=nombre):
                falso = PipelineFalso(juegos=15)
                self.ejecutar(falso, nombre)
                self.assertEqual(len(falso.hilos_persistir), 1)  # Único escritor (ADR-003).

    def test_descargas_se_solapan_solo_en_modos_concurrentes(self):
        secuencial = PipelineFalso(juegos=6, latencia=0.02)
        self.ejecutar(secuencial, "secuencial")
        self.assertEqual(secuencial.max_descargas_simultaneas, 1)

        concurrente = PipelineFalso(juegos=6, latencia=0.02)
        self.ejecutar(concurrente, "concurrente")
        workers = CONFIGURACIONES["concurrente"][1].workers_descargar
        self.assertGreater(concurrente.max_descargas_simultaneas, 1)
        self.assertLessEqual(concurrente.max_descargas_simultaneas, workers)  # Nunca más que los workers.

    def test_colas_de_tamano_uno_no_bloquean(self):
        """Con colas mínimas hay contrapresión en todo momento; aun así debe terminar."""
        CONFIGURACIONES["colas-minimas"] = (
            "paralelo",
            config_pipeline_de_prueba(cola_tareas=1, cola_descargas=1, cola_resultados=1, cola_persistir=1,
                                      ejecutor_emparejar="hilos"),
        )
        try:
            falso = PipelineFalso(juegos=20)
            resultado = self.ejecutar(falso, "colas-minimas")
            self.assertEqual(resultado.juegos_persistidos, 20)
        finally:
            del CONFIGURACIONES["colas-minimas"]

    # --- Errores: el juego sigue con los datos disponibles (sección 8) ---------------------------

    def test_fuente_caida_va_a_fallidos_y_el_juego_se_publica_igual(self):
        falso = PipelineFalso(**ESCENARIO_CON_FALLOS)
        resultado = self.ejecutar(falso, "concurrente")
        self.assertEqual([(d.tarea.juego.clave, d.tarea.fuente) for d in resultado.fallidos], [("juego-002", "tienda-a")])
        persistido = next(p for p in falso.persistidos if p[0] == "juego-002")
        por_fuente = {fuente: (datos, error) for fuente, datos, error in persistido[1]}
        self.assertIn("ReintentosAgotados", por_fuente["tienda-a"][1])  # La fuente caída queda marcada.
        self.assertIsNotNone(por_fuente["tienda-b"][0])                  # Las demás sí aportaron datos.

    def test_errores_de_parseo_emparejamiento_y_fuentes(self):
        falso = PipelineFalso(**ESCENARIO_CON_FALLOS)
        resultado = self.ejecutar(falso, "paralelo-procesos")
        errores = {(e.etapa, e.clave) for e in resultado.errores}
        self.assertIn(("parsear", "juego-005"), errores)
        self.assertIn(("emparejar", f"{PREFIJO_EXPLOTA}-1"), errores)  # La excepción cruzó desde otro proceso.
        self.assertIn(("descubrir", "juego-007"), errores)
        claves = {p[0] for p in falso.persistidos}
        self.assertIn("juego-005", claves)                    # Se publicó con las fuentes que sí funcionaron.
        self.assertNotIn(f"{PREFIJO_EXPLOTA}-1", claves)      # Sin emparejamiento no hay nada que guardar.
        self.assertNotIn("juego-007", claves)

    def test_emparejar_debe_poder_enviarse_a_otro_proceso(self):
        falso = PipelineFalso(juegos=2)
        definicion = falso.definicion()
        from dataclasses import replace
        con_lambda = replace(definicion, emparejar=lambda paquete: paquete.juego.clave)
        with self.assertRaises(ValueError) as contexto:
            ejecutar_pipeline(con_lambda, "paralelo", CONFIGURACIONES["paralelo-procesos"][1])
        self.assertIn("nivel de módulo", str(contexto.exception))

    def test_modo_desconocido(self):
        with self.assertRaises(ValueError):
            ejecutar_pipeline(PipelineFalso().definicion(), "turbo", CONFIGURACIONES["concurrente"][1])

    # --- Estadísticas por etapa --------------------------------------------------------------------

    def test_estadisticas_por_etapa(self):
        for nombre in CONFIGURACIONES:
            with self.subTest(modo=nombre):
                falso = PipelineFalso(juegos=6)
                resultado = self.ejecutar(falso, nombre)
                self.assertEqual(set(resultado.etapas), set(ETAPAS))
                self.assertEqual(resultado.etapas["descubrir"].elementos, 3)      # 3 páginas.
                self.assertEqual(resultado.etapas["descargar"].elementos, 6 * 3)  # 6 juegos × 3 fuentes.
                self.assertEqual(resultado.etapas["emparejar"].elementos, 6)
                self.assertEqual(resultado.etapas["publicar"].elementos, 1)
                for estadistica in resultado.etapas.values():
                    self.assertGreaterEqual(estadistica.tiempo_ocupado_s, 0)
                    self.assertGreaterEqual(estadistica.ventana_s, 0)
                    self.assertLessEqual(estadistica.fin_s, resultado.duracion_total_s)


if __name__ == "__main__":
    unittest.main()
