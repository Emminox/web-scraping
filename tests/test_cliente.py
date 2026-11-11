"""Pruebas del ClienteHttp: reintentos, robots.txt, caché y modo replay, sin usar internet."""

import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from radar.red import (
    BloqueadoPorRobots,
    ClienteHttp,
    ErrorDefinitivo,
    ErrorTemporal,
    ReintentosAgotados,
    SinCaptura,
)
from radar.red.almacen import AlmacenCapturas
from tests.utilidades import TransporteFalso, config_de_prueba, respuesta

URL = "https://tienda.ejemplo.com/juego/1"
ROBOTS = "https://tienda.ejemplo.com/robots.txt"


class PruebasCliente(unittest.TestCase):
    def setUp(self):
        # Cada prueba usa su propia carpeta temporal, que se borra al terminar.
        self._carpeta = tempfile.TemporaryDirectory()
        self.directorio = Path(self._carpeta.name)
        self.transporte = TransporteFalso()
        self.esperas: list[float] = []

    def tearDown(self):
        self._carpeta.cleanup()

    def crear_cliente(self, **opciones) -> ClienteHttp:
        config = config_de_prueba(self.directorio, **opciones)
        # ``dormir`` falso: registra cuánto se habría esperado, sin esperar de verdad.
        return ClienteHttp(config, transporte=self.transporte, dormir=self.esperas.append)

    # --- Modo vivo -------------------------------------------------------

    def test_reintenta_errores_temporales_y_luego_tiene_exito(self):
        self.transporte.programar(URL, respuesta(URL, 503), ErrorTemporal("timeout"), respuesta(URL, 200))
        cliente = self.crear_cliente(max_reintentos=2)
        resultado = cliente.obtener(URL)
        self.assertEqual(resultado.estado, 200)
        self.assertEqual(len(self.esperas), 2)  # Esperó antes de cada uno de los 2 reintentos.
        contadores = cliente.metricas.instantanea()["tienda.ejemplo.com"]
        self.assertEqual((contadores["reintentos"], contadores["exitosas"]), (2, 1))
        # La respuesta exitosa quedó guardada en el almacén (servirá para el replay).
        self.assertIsNotNone(cliente.almacen.leer(URL))

    def test_respeta_retry_after(self):
        self.transporte.programar(URL, respuesta(URL, 429, **{"Retry-After": "7"}), respuesta(URL, 200))
        self.crear_cliente().obtener(URL)
        self.assertEqual(self.esperas, [7.0])

    def test_agota_reintentos(self):
        self.transporte.programar(URL, *[respuesta(URL, 500)] * 3)
        cliente = self.crear_cliente(max_reintentos=2)
        with self.assertRaises(ReintentosAgotados) as contexto:
            cliente.obtener(URL)
        self.assertEqual(contexto.exception.intentos, 3)
        self.assertEqual(cliente.metricas.instantanea()["tienda.ejemplo.com"]["fallidas"], 1)

    def test_no_reintenta_404(self):
        self.transporte.programar(URL, respuesta(URL, 404))
        with self.assertRaises(ErrorDefinitivo):
            self.crear_cliente().obtener(URL)
        self.assertEqual(self.esperas, [])
        self.assertEqual(self.transporte.llamadas.count(URL), 1)

    def test_respeta_robots_txt(self):
        reglas = b"User-agent: *\nDisallow: /juego/\n"
        self.transporte.programar(ROBOTS, respuesta(ROBOTS, 200, reglas, **{"Content-Type": "text/plain"}))
        cliente = self.crear_cliente()
        with self.assertRaises(BloqueadoPorRobots):
            cliente.obtener(URL)
        # Nunca se pidió la página prohibida, solo robots.txt.
        self.assertEqual(self.transporte.llamadas, [ROBOTS])

    def test_robots_se_descarga_una_sola_vez(self):
        otra = "https://tienda.ejemplo.com/juego/2"
        self.transporte.programar(URL, respuesta(URL))
        self.transporte.programar(otra, respuesta(otra))
        cliente = self.crear_cliente()
        cliente.obtener(URL)
        cliente.obtener(otra)
        self.assertEqual(self.transporte.llamadas.count(ROBOTS), 1)

    def test_usa_copia_fresca_del_almacen(self):
        AlmacenCapturas(self.directorio / "capturas").guardar(respuesta(URL, cuerpo=b"guardada"))
        cliente = self.crear_cliente()
        resultado = cliente.obtener(URL)
        self.assertEqual(resultado.cuerpo, b"guardada")
        self.assertEqual(self.transporte.llamadas, [])  # No tocó la red en absoluto.

    def test_descarga_si_la_copia_esta_vencida(self):
        # Copia guardada hace 2 días: con TTL de 12 h ya no es fresca.
        vieja = respuesta(URL, cuerpo=b"vieja")
        vieja = replace(vieja, obtenida_en=vieja.obtenida_en - timedelta(days=2))
        AlmacenCapturas(self.directorio / "capturas").guardar(vieja)
        self.transporte.programar(URL, respuesta(URL, cuerpo=b"nueva"))
        self.assertEqual(self.crear_cliente().obtener(URL).cuerpo, b"nueva")

    # --- Modo replay -----------------------------------------------------

    def test_replay_sirve_la_captura_con_latencia_simulada(self):
        AlmacenCapturas(self.directorio / "capturas").guardar(respuesta(URL, cuerpo=b"capturada"))
        cliente = self.crear_cliente(fuente="replay", latencia_ms=250)
        resultado = cliente.obtener(URL)
        self.assertEqual(resultado.cuerpo, b"capturada")
        self.assertEqual(self.esperas, [0.25])     # Esperó la latencia configurada.
        self.assertEqual(self.transporte.llamadas, [])  # Y nunca tocó la red (ni robots.txt).

    def test_replay_sin_captura(self):
        cliente = self.crear_cliente(fuente="replay")
        with self.assertRaises(SinCaptura):
            cliente.obtener(URL)


if __name__ == "__main__":
    unittest.main()
