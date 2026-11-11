"""Decide qué producto de cada tienda corresponde a cada juego (etapa 3 del pipeline).

Para un juego (en una plataforma) se compara cada uno de sus títulos (canónico y alternativos) contra
TODOS los candidatos que devolvieron todas sus tiendas (sección 6). Por cada tienda se elige el
candidato más parecido y se clasifica:

- **aceptado**: similitud >= UMBRAL y sin DLC, paquete ni edición distinta. Si la única diferencia es una edición
  con contenido extra (GOTY, Complete, Definitive…), también se acepta, como "juego + DLC", con la edición anotada.
- **dudoso**: similitud en la banda [UMBRAL - BANDA_DUDA, UMBRAL), o similitud alta pero con remasterización,
  DLC, paquete o plataforma desconocida. Se guarda y se muestra en el panel de métricas, pero su precio NO se
  publica como precio del juego.
- **rechazado**: similitud menor. Solo cuenta para las métricas ("juegos sin emparejar").

``emparejar_juego`` está a nivel de módulo y solo depende de su argumento: en el modo paralelo se envía
a otros procesos con pickle.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from radar.emparejamiento.normalizar import normalizar
from radar.emparejamiento.similitud import similitud
from radar.fuentes.modelos import Candidato
from radar.pipeline.modelos import Juego, PaqueteJuego

# Valores PROVISIONALES hasta validar con el conjunto de 60 o más pares revisados a mano (ADR-006).
UMBRAL = 0.88
BANDA_DUDA = 0.08


@dataclass(frozen=True)
class Emparejamiento:
    """Resultado para una tienda: el mejor candidato y cómo se clasificó."""

    candidato: Candidato
    similitud: float
    estado: str            # 'aceptado', 'dudoso' o 'rechazado'.
    motivo: str | None     # Por qué es dudoso o rechazado.


@dataclass(frozen=True)
class ResultadoJuego:
    """Todo lo que la etapa Persistir necesita guardar de un juego en una plataforma."""

    juego: Juego
    emparejamientos: tuple[Emparejamiento, ...]   # Uno por tienda que devolvió candidatos.
    errores_fuente: tuple[tuple[str, str], ...]   # (fuente, error) de las tiendas que fallaron.
    comparaciones: int                            # Cuántas similitudes se calcularon (trabajo de CPU).


# Ediciones que son el MISMO juego con contenido extra (DLC incluidos o mejoras). Muchas tiendas venden SOLO esa
# edición (p. ej. Steam vende "Batman: Arkham Asylum Game of the Year Edition" y no la base), así que, si todo lo
# demás coincide, se aceptan como "juego + DLC" y la edición queda anotada (aparece en el panel de métricas).
# Las remasterizaciones NO están aquí: son otro lanzamiento y siguen siendo dudosas (ADR-006, cambio del 2026-11-11).
EDICIONES_CON_CONTENIDO = frozenset({
    "game of the year edition", "game of the year", "goty edition", "goty", "definitive edition",
    "deluxe edition", "digital deluxe edition", "digital deluxe", "deluxe", "complete edition", "ultimate edition",
    "gold edition", "premium edition", "special edition", "collectors edition", "launch edition",
    "enhanced edition", "enhanced", "director s cut", "directors cut",
})


def _clasificar(juego: Juego, candidato: Candidato, valor: float, titulo_juego, titulo_candidato) -> tuple[str, str | None]:
    """Devuelve (estado, motivo). Un "aceptado" puede traer motivo: la edición con contenido que se aceptó."""
    if valor < UMBRAL - BANDA_DUDA:
        return "rechazado", f"similitud {valor:.2f} menor que el umbral"
    motivos = []
    ediciones_extra = titulo_candidato.ediciones - titulo_juego.ediciones
    if valor < UMBRAL:
        motivos.append(f"similitud {valor:.2f} cerca del umbral")
    if ediciones_extra - EDICIONES_CON_CONTENIDO:
        motivos.append("edición distinta: " + ", ".join(sorted(ediciones_extra - EDICIONES_CON_CONTENIDO)))
    if titulo_candidato.dlc - titulo_juego.dlc:
        motivos.append("posible DLC: " + ", ".join(sorted(titulo_candidato.dlc - titulo_juego.dlc)))
    if candidato.tipo != "juego":
        motivos.append(f"la tienda lo clasifica como '{candidato.tipo}'")
    if candidato.plataforma is None:
        motivos.append("plataforma desconocida")
    if motivos:
        return "dudoso", "; ".join(motivos)
    if ediciones_extra:
        return "aceptado", "edición con contenido extra (juego + DLC): " + ", ".join(sorted(ediciones_extra))
    return "aceptado", None


def emparejar_juego(paquete: PaqueteJuego) -> ResultadoJuego:
    juego = paquete.juego
    titulos = [normalizar(t) for t in (juego.titulo, *juego.titulos_alternativos)]
    emparejamientos: list[Emparejamiento] = []
    errores: list[tuple[str, str]] = []
    comparaciones = 0

    for resultado in paquete.resultados:  # Ya vienen ordenados por fuente (PaqueteJuego).
        if resultado.error is not None:
            errores.append((resultado.fuente, resultado.error))
            continue
        # Se elige el mejor candidato POR TIENDA (``candidato.fuente``), no por descarga: una sola consulta a
        # CheapShark trae ofertas de varias tiendas (Humble, Fanatical…). Para las demás fuentes es lo mismo,
        # porque cada descarga trae una sola tienda. Las tiendas se recorren en orden alfabético (determinismo).
        por_tienda: dict[str, list] = {}
        for candidato in resultado.datos or ():
            por_tienda.setdefault(candidato.fuente, []).append(candidato)
        for tienda in sorted(por_tienda):
            mejor = None
            # Criterio de elección, en orden: (1) mayor similitud; (2) a igual similitud, el candidato "limpio"
            # (sin DLC, sin edición especial y clasificado como juego): así "Hades" gana a "Hades Soundtrack";
            # (3) a igualdad de todo, la URL menor (se recorren ordenados por URL y solo se reemplaza al mejor si
            # el nuevo es ESTRICTAMENTE mejor). Con este orden total el elegido es el mismo en los tres modos.
            for candidato in sorted(por_tienda[tienda], key=lambda c: c.url):
                # Un producto de otra plataforma no puede ser este juego en esta plataforma.
                if candidato.plataforma is not None and candidato.plataforma != juego.plataforma:
                    continue
                titulo_candidato = normalizar(candidato.titulo)
                for titulo_juego in titulos:
                    valor = similitud(titulo_juego, titulo_candidato)
                    comparaciones += 1
                    limpio = (
                        candidato.tipo == "juego"
                        and not (titulo_candidato.dlc - titulo_juego.dlc)
                        and not (titulo_candidato.ediciones - titulo_juego.ediciones)
                    )
                    if mejor is None or (valor, limpio) > (mejor[1], mejor[4]):
                        mejor = (candidato, valor, titulo_juego, titulo_candidato, limpio)
            if mejor is None:
                continue
            candidato, valor, titulo_juego, titulo_candidato, _ = mejor
            estado, motivo = _clasificar(juego, candidato, valor, titulo_juego, titulo_candidato)
            if estado == "aceptado" and motivo:  # Edición con contenido extra aceptada: es "juego + DLC".
                candidato = replace(candidato, tipo="juego_dlc")
            emparejamientos.append(Emparejamiento(candidato, round(valor, 4), estado, motivo))

    return ResultadoJuego(juego, tuple(emparejamientos), tuple(errores), comparaciones)
