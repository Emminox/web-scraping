# ADRs (Architecture Decision Records)

Un archivo por decisión: `NNN-titulo-en-kebab-case.md` (001, 002, …), media página o menos.
Usar `/adr <tema>` para crearlos con la plantilla del Anexo 1 del enunciado.

## Plantilla
```markdown
# ADR-NNN · <Título> · <AAAA-MM-DD>

## Contexto
Qué problema o restricción obliga a decidir. Datos disponibles al momento.

## Alternativas
1. **Opción A** — Ventajas: … / Desventajas: …
2. **Opción B** — Ventajas: … / Desventajas: …

## Decisión
La opción elegida, en una o dos frases.

## Consecuencias
Qué se gana, qué se pierde y qué habría que medir para confirmar la decisión.

## Estado
Propuesta | Aceptada | Reemplazada por ADR-XXX
```

## ADRs esperados para el Hito 1
Lenguaje · Base de datos · Definición de oferta · Fuentes por tipo de dato · Límites de concurrencia
(workers por etapa, conexiones por dominio, tamaño de colas) · Modo replay · Algoritmo de emparejamiento ·
Hosting y tarea programada · Almacenamiento de capturas y BD.

## Índice
| # | Título | Estado |
|---|---|---|
| [001](001-lenguaje-python.md) | Lenguaje de implementación: Python 3.14 | Aceptada |
| [002](002-cliente-http-biblioteca-estandar.md) | Cliente HTTP con la biblioteca estándar | Propuesta |
