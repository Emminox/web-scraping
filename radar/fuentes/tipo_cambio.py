"""Tipo de cambio para mostrar los precios en colones y euros (ADR-012).

Los precios se obtienen y se guardan SIEMPRE en USD (ADR-005). La conversión es solo de presentación: el sitio
multiplica por estas tasas cuando la persona elige otra moneda.

Fuente: API abierta de ExchangeRate-API (https://open.er-api.com/v6/latest/USD). Sin clave, se actualiza una vez
al día y sus condiciones permiten guardar la respuesta en caché; piden consultarla como mucho una vez por hora (la
caché del cliente dura 12 h, así que se pide una vez por corrida) y mostrar el enlace "Rates By Exchange Rate API"
en las páginas que usan las tasas. No permiten redistribuir los datos: el sitio publica solo las dos tasas que usa.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from radar.red import ClienteHttp, ErrorRed

URL = "https://open.er-api.com/v6/latest/USD"
MONEDAS = ("CRC", "EUR")
ATRIBUCION = {"texto": "Rates By Exchange Rate API", "url": "https://www.exchangerate-api.com"}
ARCHIVO = Path("datos") / "tipo_cambio.json"


@dataclass(frozen=True)
class TipoCambio:
    tasas: dict[str, float]   # Unidades de cada moneda por 1 USD.
    actualizado_en: str       # Cuándo publicó la fuente estas tasas (ISO 8601, UTC).


def parsear(cuerpo: bytes) -> TipoCambio:
    """Extrae las tasas de CRC y EUR. Lanza ``ValueError`` si la respuesta no sirve."""
    datos = json.loads(cuerpo)
    if datos.get("result") != "success" or datos.get("base_code") != "USD":
        raise ValueError(f"respuesta inesperada del tipo de cambio: {datos.get('result')!r}")
    tasas = {}
    for moneda in MONEDAS:
        tasa = datos.get("rates", {}).get(moneda)
        if not isinstance(tasa, (int, float)) or tasa <= 0:
            raise ValueError(f"tipo de cambio sin tasa válida para {moneda}")
        tasas[moneda] = float(tasa)
    actualizado = datetime.fromtimestamp(int(datos["time_last_update_unix"]), tz=UTC).isoformat()
    return TipoCambio(tasas, actualizado)


def guardar(tipo_cambio: TipoCambio, destino_sitio: Path) -> None:
    ruta = destino_sitio / ARCHIVO
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({
        "base": "USD", "tasas": tipo_cambio.tasas, "actualizado_en": tipo_cambio.actualizado_en,
        "atribucion": ATRIBUCION,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def actualizar_tipo_cambio(cliente: ClienteHttp, destino_sitio: Path) -> TipoCambio | None:
    """Obtiene las tasas y las publica en el sitio. Si falla, se conserva el archivo anterior (si existe) y el
    sitio sigue funcionando: sin archivo, solo ofrece USD. Nunca detiene la corrida por esto."""
    try:
        tipo_cambio = parsear(cliente.obtener(URL).cuerpo)
    except (ErrorRed, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Aviso: no se pudo actualizar el tipo de cambio ({error}); se conserva el anterior.", flush=True)
        return None
    guardar(tipo_cambio, destino_sitio)
    return tipo_cambio
