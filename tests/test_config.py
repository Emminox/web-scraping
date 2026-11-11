"""Pruebas de la carga y validación de la configuración."""

import tempfile
import unittest
from pathlib import Path

from radar.config import RAIZ_PROYECTO, ErrorConfiguracion, cargar_config


class PruebasConfig(unittest.TestCase):
    def test_carga_el_archivo_real_del_proyecto(self):
        # El config.toml que está en el repo siempre debe ser válido.
        config = cargar_config()
        self.assertIn(config.ejecucion.modo, ("secuencial", "concurrente", "paralelo"))
        self.assertIn("RadarOfertas", config.red.user_agent)
        # Las rutas relativas se resuelven desde la raíz del repositorio.
        self.assertEqual(config.rutas.capturas, RAIZ_PROYECTO / "datos" / "capturas")

    def test_rechaza_valores_invalidos(self):
        texto_original = (RAIZ_PROYECTO / "config" / "config.toml").read_text(encoding="utf-8")
        casos = {
            "modo desconocido": texto_original.replace('modo = "secuencial"', 'modo = "turbo"'),
            "timeout negativo": texto_original.replace("timeout_segundos = 15.0", "timeout_segundos = -1"),
            "conexiones en cero": texto_original.replace(
                "max_conexiones_por_dominio = 2", "max_conexiones_por_dominio = 0"
            ),
        }
        for descripcion, texto in casos.items():
            with self.subTest(descripcion), tempfile.TemporaryDirectory() as carpeta:
                ruta = Path(carpeta) / "config" / "config.toml"
                ruta.parent.mkdir()
                ruta.write_text(texto, encoding="utf-8")
                with self.assertRaises(ErrorConfiguracion):
                    cargar_config(ruta)

    def test_regla_especifica_por_dominio(self):
        texto = (RAIZ_PROYECTO / "config" / "config.toml").read_text(encoding="utf-8")
        texto += '\n[red.dominios."ejemplo.com"]\nmax_conexiones = 5\nintervalo_minimo_segundos = 0.25\n'
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "config" / "config.toml"
            ruta.parent.mkdir()
            ruta.write_text(texto, encoding="utf-8")
            config = cargar_config(ruta)
        self.assertEqual(config.red.limite_para("ejemplo.com").max_conexiones, 5)
        # Un dominio sin regla propia usa el límite por defecto.
        self.assertEqual(config.red.limite_para("otro.com").max_conexiones, 2)


if __name__ == "__main__":
    unittest.main()
