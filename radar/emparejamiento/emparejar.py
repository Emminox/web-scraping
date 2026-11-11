"""Decide qué producto de cada tienda corresponde a cada juego (etapa 3 del pipeline).

Para un juego (en una plataforma) se compara cada uno de sus títulos (canónico y alternativos) contra
TODOS los candidatos que devolvieron todas sus tiendas (sección 6). Por cada tienda se elige el
candidato más parecido y se clasifica:

- **aceptado**: similitud >= UMBRAL y sin señales de edición especial ni DLC distintas a las del juego.
- **dudoso**: similitud en la banda [UMBRAL - BANDA_DUDA, UMBRAL), o similitud alta pero con edición
  especial, DLC, paquete o plataforma desconocida. Se guarda y se muestra en el panel de métricas,
  pero su precio NO se publica como precio del juego.
- **rechazado**: similitud menor. Solo cuenta para las métricas ("juegos sin emparejar").

``emparejar_juego`` está a nivel de módulo y solo depende de su argumento: en el modo paralelo se envía
a otros procesos con pickle.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def _clasificar(juego: Juego, candidato: Candidato, valor: float, titulo_juego, titulo_candidato) -> tuple[str, str | None]:
    if valor < UMBRAL - BANDA_DUDA:
        return "rechazado", f"similitud {valor:.2f} menor que el umbral"
    motivos = []
    if valor < UMBRAL:
        motivos.append(f"similitud {valor:.2f} cerca del umbral")
    if titulo_candidato.ediciones - titulo_juego.ediciones:
        motivos.append("edición especial: " + ", ".join(sorted(titulo_candidato.ediciones - titulo_juego.ediciones)))
    if titulo_candidato.dlc - titulo_juego.dlc:
        motivos.append("posible DLC: " + ", ".join(sorted(titulo_candidato.dlc - titulo_juego.dlc)))
    if candidato.tipo != "juego":
        motivos.append(f"la tienda lo clasifica como '{candidato.tipo}'")
    if candidato.plataforma is None:
        motivos.append("plataforma desconocida")
    if motivos:
        return "dudoso", "; ".join(motivos)
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
        mejor = None
        # Criterio de elección, en orden: (1) mayor similitud; (2) a igual similitud, el candidato "limpio"
        # (sin DLC, sin edición especial y clasificado como juego): así "Hades" gana a "Hades Soundtrack";
        # (3) a igualdad de todo, la URL menor (se recorren ordenados por URL y solo se reemplaza al mejor si
        # el nuevo es ESTRICTAMENTE mejor). Con este orden total el elegido es el mismo en los tres modos.
        for candidato in sorted(resultado.datos or (), key=lambda c: c.url):
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
        emparejamientos.append(Emparejamiento(candidato, round(valor, 4), estado, motivo))

    return ResultadoJuego(juego, tuple(emparejamientos), tuple(errores), comparaciones)
