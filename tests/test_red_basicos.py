"""Pruebas de las piezas pequeñas de la capa de red: reintentos, limitador, almacén y métricas."""

import random
import tempfile
import threading
import time
import unittest
from pathlib import Path

from radar.red.almacen import AlmacenCapturas, normalizar_url
from radar.red.limitador import LimitadorPorDominio
from radar.red.metricas import MetricasRed
from radar.red.reintentos import calcular_espera, leer_retry_after
from tests.utilidades import config_de_prueba, respuesta


class PruebasReintentos(unittest.TestCase):
    def test_espera_dentro_del_tope_exponencial(self):
        aleatorio = random.Random(0)
        for intento, tope in [(0, 1.0), (1, 2.0), (2, 4.0), (3, 8.0), (10, 30.0)]:
            for _ in range(50):
                espera = calcular_espera(intento, 1.0, 30.0, aleatorio)
                self.assertGreaterEqual(espera, 0.0)
                self.assertLessEqual(espera, tope)

    def test_retry_after(self):
        self.assertEqual(leer_retry_after({"Retry-After": "5"}, 30.0), 5.0)
        self.assertEqual(leer_retry_after({"retry-after": "999"}, 30.0), 30.0)  # Se limita al máximo.
        self.assertIsNone(leer_retry_after({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, 30.0))
        self.assertIsNone(leer_retry_after({}, 30.0))


class PruebasLimitador(unittest.TestCase):
    def test_no_supera_las_conexiones_simultaneas(self):
        """Con 8 hilos y límite 2, nunca debe haber más de 2 dentro del turno a la vez."""
        with tempfile.TemporaryDirectory() as carpeta:
            config = config_de_prueba(Path(carpeta), max_conexiones=2)
        limitador = LimitadorPorDominio(config.red, aplicar_intervalo=False)
        activos = 0
        maximo_visto = 0
        lock = threading.Lock()

        def trabajo():
            nonlocal activos, maximo_visto
            with limitador.turno("ejemplo.com"):
                with lock:
                    activos += 1
                    maximo_visto = max(maximo_visto, activos)
                time.sleep(0.05)  # Simula una descarga.
                with lock:
                    activos -= 1

        hilos = [threading.Thread(target=trabajo) for _ in range(8)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(maximo_visto, 2)

    def test_respeta_el_intervalo_minimo(self):
        """Con un reloj falso detenido, cada turno debe esperar un intervalo más que el anterior."""
        with tempfile.TemporaryDirectory() as carpeta:
            config = config_de_prueba(Path(carpeta), intervalo=1.0)
        esperas: list[float] = []
        limitador = LimitadorPorDominio(config.red, reloj=lambda: 100.0, dormir=esperas.append)
        for _ in range(3):
            with limitador.turno("ejemplo.com"):
                pass
        # El primero no espera; el segundo 1 s; el tercero 2 s (los turnos quedan a 100, 101, 102).
        self.assertEqual(esperas, [1.0, 2.0])

    def test_dominios_distintos_no_se_esperan_entre_si(self):
        with tempfile.TemporaryDirectory() as carpeta:
            config = config_de_prueba(Path(carpeta), intervalo=1.0)
        esperas: list[float] = []
        limitador = LimitadorPorDominio(config.red, reloj=lambda: 100.0, dormir=esperas.append)
        for dominio in ("a.com", "b.com", "c.com"):
            with limitador.turno(dominio):
                pass
        self.assertEqual(esperas, [])


class PruebasAlmacen(unittest.TestCase):
    def test_guardar_y_leer(self):
        with tempfile.TemporaryDirectory() as carpeta:
            almacen = AlmacenCapturas(Path(carpeta))
            original = respuesta("https://Ejemplo.com/juego?id=1", cuerpo=b"<html>precio</html>")
            almacen.guardar(original)
            # La URL se normaliza: mayúsculas en el dominio y el fragmento no importan.
            leida = almacen.leer("https://ejemplo.com/juego?id=1#detalles")
            self.assertIsNotNone(leida)
            self.assertEqual(leida.cuerpo, b"<html>precio</html>")
            self.assertEqual(leida.obtenida_en, original.obtenida_en)
            self.assertTrue(leida.desde_almacen)
            # Se guardó como .html para poder abrirlo a mano.
            self.assertEqual(len(list(Path(carpeta).rglob("*.html"))), 1)

    def test_url_inexistente_y_urls_distintas(self):
        with tempfile.TemporaryDirectory() as carpeta:
            almacen = AlmacenCapturas(Path(carpeta))
            self.assertIsNone(almacen.leer("https://ejemplo.com/nada"))
            almacen.guardar(respuesta("https://ejemplo.com/a", cuerpo=b"A"))
            almacen.guardar(respuesta("https://ejemplo.com/b", cuerpo=b"B"))
            self.assertEqual(almacen.leer("https://ejemplo.com/a").cuerpo, b"A")
            self.assertEqual(almacen.leer("https://ejemplo.com/b").cuerpo, b"B")

    def test_normalizar_url_no_reordena_parametros(self):
        self.assertEqual(normalizar_url("HTTPS://A.COM/X?b=2&a=1#f"), "https://a.com/X?b=2&a=1")


class PruebasMetricas(unittest.TestCase):
    def test_no_pierde_incrementos_con_muchos_hilos(self):
        """Si el lock faltara, con suficientes hilos se perderían incrementos (condición de carrera)."""
        metricas = MetricasRed()

        def sumar():
            for _ in range(2000):
                metricas.registrar("ejemplo.com", "exitosas")

        hilos = [threading.Thread(target=sumar) for _ in range(8)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(metricas.instantanea()["ejemplo.com"]["exitosas"], 16000)

    def test_campo_desconocido(self):
        with self.assertRaises(ValueError):
            MetricasRed().registrar("ejemplo.com", "inventado")


if __name__ == "__main__":
    unittest.main()
