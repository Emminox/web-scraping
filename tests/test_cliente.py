"""Pruebas del ClienteHttp: reintentos, robots.txt, caché y modo replay, sin usar internet."""

import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from radar.red import (
    BloqueadoPorRobots,
    ClienteHttp,
    DominioEnPausa,
    ErrorDefinitivo,
    ErrorTemporal,
    ReintentosAgotados,
    SinCaptura,
)
from radar.red.almacen import AlmacenCapturas
from radar.red.robots import VerificadorRobots
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

    def test_retry_after_largo_pausa_el_dominio_sin_reintentar(self):
        # CheapShark respondió 429 con Retry-After: 993. Recortarlo al backoff (30 s) y reintentar renovaba el bloqueo.
        otra = "https://tienda.ejemplo.com/juego/2"
        ahora = [0.0]
        self.transporte.programar(URL, respuesta(URL, 429, **{"Retry-After": "900"}))
        cliente = ClienteHttp(config_de_prueba(self.directorio), transporte=self.transporte,
                              dormir=self.esperas.append, reloj=lambda: ahora[0])
        with self.assertRaises(DominioEnPausa):
            cliente.obtener(URL)
        self.assertEqual(self.esperas, [])                    # No se quedó dormido en el hilo de descarga.
        with self.assertRaises(DominioEnPausa):
            cliente.obtener(otra)                             # Otra URL del mismo sitio: ni se intenta.
        self.assertNotIn(otra, self.transporte.llamadas)
        self.assertEqual(round(cliente.pausas_pendientes()["tienda.ejemplo.com"]), 900)
        # El reintento final espera la pausa completa y luego el sitio vuelve a estar disponible.
        cliente.esperar_pausas()
        self.assertEqual(self.esperas, [900.0])
        ahora[0] = 901.0
        self.transporte.programar(otra, respuesta(otra))
        self.assertEqual(cliente.obtener(otra).estado, 200)
        self.assertEqual(cliente.metricas.instantanea()["tienda.ejemplo.com"]["pausas"], 1)

    def test_429_sin_retry_after_tambien_pausa(self):
        # CheapShark pasó a responder 429 sin Retry-After: con el backoff normal se reintentaba cada pocos segundos.
        self.transporte.programar(URL, respuesta(URL, 429))
        cliente = self.crear_cliente()
        with self.assertRaises(DominioEnPausa):
            cliente.obtener(URL)
        self.assertEqual(self.esperas, [])
        self.assertEqual(self.transporte.llamadas.count(URL), 1)  # Una sola solicitud, sin reintentos.
        self.assertEqual(round(cliente.pausas_pendientes()["tienda.ejemplo.com"]), 900)

    def test_429_en_robots_txt_pausa_el_dominio(self):
        otra = "https://tienda.ejemplo.com/juego/2"
        self.transporte.programar(ROBOTS, respuesta(ROBOTS, 429))
        cliente = self.crear_cliente()
        with self.assertRaises(BloqueadoPorRobots):
            cliente.obtener(URL)                       # Sin reglas: por prudencia, no se descarga.
        with self.assertRaises(DominioEnPausa):
            cliente.obtener(otra)                      # Y el dominio queda en pausa: ni robots.txt se vuelve a pedir.
        self.assertEqual(self.transporte.llamadas, [ROBOTS])
        self.assertEqual(round(cliente.pausas_pendientes()["tienda.ejemplo.com"]), 900)

    def test_503_sin_retry_after_usa_el_backoff_normal(self):
        self.transporte.programar(URL, respuesta(URL, 503), respuesta(URL, 200))
        cliente = self.crear_cliente()
        self.assertEqual(cliente.obtener(URL).estado, 200)
        self.assertEqual(cliente.pausas_pendientes(), {})

    def test_retry_after_corto_sigue_siendo_un_reintento_normal(self):
        self.transporte.programar(URL, respuesta(URL, 503, **{"Retry-After": "5"}), respuesta(URL, 200))
        cliente = self.crear_cliente()
        self.assertEqual(cliente.obtener(URL).estado, 200)
        self.assertEqual(self.esperas, [5.0])
        self.assertEqual(cliente.pausas_pendientes(), {})

    def test_misma_url_en_varios_hilos_se_descarga_una_sola_vez(self):
        # El transporte se queda "descargando" hasta que todos los hilos ya pidieron la URL: sin el candado por URL,
        # los 4 verían la caché vacía a la vez y harían 4 descargas.
        todos_pidieron = threading.Event()
        transporte = self.transporte
        obtener_original = transporte.obtener

        def obtener_lento(url, cabeceras, timeout):
            if not url.endswith("/robots.txt"):
                todos_pidieron.wait(timeout=0.5)
            return obtener_original(url, cabeceras, timeout)

        transporte.obtener = obtener_lento
        transporte.programar(URL, respuesta(URL, cuerpo=b"una"))
        cliente = self.crear_cliente(max_conexiones=4)
        cuerpos = []
        hilos = [threading.Thread(target=lambda: cuerpos.append(cliente.obtener(URL).cuerpo)) for _ in range(4)]
        for hilo in hilos:
            hilo.start()
        todos_pidieron.set()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(cuerpos, [b"una"] * 4)
        self.assertEqual(transporte.llamadas.count(URL), 1)  # Los otros 3 usaron la copia que dejó el primero.

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


class PruebasRobots(unittest.TestCase):
    def test_fallo_temporal_bloquea_solo_un_rato(self):
        ahora = [0.0]
        intentos = []

        def descargar(url):
            intentos.append(url)
            if len(intentos) == 1:
                raise ErrorTemporal("timeout")
            return respuesta(url, 200, b"User-agent: *\nDisallow: /privado/\n")

        robots = VerificadorRobots(descargar, "RadarPruebas", reloj=lambda: ahora[0], espera_tras_fallo=60.0)
        self.assertFalse(robots.permitido(URL))   # Timeout: por prudencia, bloqueado...
        ahora[0] = 30.0
        self.assertFalse(robots.permitido(URL))   # ...durante la ventana, sin volver a descargar...
        self.assertEqual(len(intentos), 1)
        ahora[0] = 61.0
        self.assertTrue(robots.permitido(URL))    # ...y al vencer se vuelve a leer robots.txt.
        self.assertFalse(robots.permitido("https://tienda.ejemplo.com/privado/x"))
        self.assertEqual(len(intentos), 2)        # Las reglas leídas bien ya no vencen.

    def test_error_5xx_tambien_es_temporal_y_403_es_definitivo(self):
        ahora = [0.0]
        estados = {"https://a.ejemplo/robots.txt": [503, 200], "https://b.ejemplo/robots.txt": [403, 200],
                   "https://c.ejemplo/robots.txt": [429, 200]}

        def descargar(url):
            return respuesta(url, estados[url].pop(0), b"")

        robots = VerificadorRobots(descargar, "RadarPruebas", reloj=lambda: ahora[0], espera_tras_fallo=10.0)
        self.assertFalse(robots.permitido("https://a.ejemplo/x"))
        self.assertFalse(robots.permitido("https://b.ejemplo/x"))
        ahora[0] = 11.0
        self.assertTrue(robots.permitido("https://a.ejemplo/x"))
        self.assertFalse(robots.permitido("https://b.ejemplo/x"))  # 403 no se reintenta.
        # 429 no significa "no hay robots.txt" (antes se tomaba como todo permitido): es temporal.
        ahora[0] = 0.0
        robots_c = VerificadorRobots(descargar, "RadarPruebas", reloj=lambda: ahora[0], espera_tras_fallo=10.0)
        self.assertFalse(robots_c.permitido("https://c.ejemplo/x"))
        ahora[0] = 11.0
        self.assertTrue(robots_c.permitido("https://c.ejemplo/x"))


if __name__ == "__main__":
    unittest.main()
