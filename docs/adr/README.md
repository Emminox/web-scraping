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
| [001](001-lenguaje-python.md) | Lenguaje de implementación | Aceptada |
| [002](002-cliente-http-biblioteca-estandar.md) | Cliente HTTP con la biblioteca estándar | Aceptada |
| [003](003-base-de-datos-sqlite.md) | Base de datos: SQLite | Aceptada |
| [004](004-fuentes-de-datos.md) | Fuentes de datos por tipo | Aceptada |
| [005](005-definicion-de-oferta-y-msrp.md) | Definición de "oferta" y origen del MSRP | Aceptada |
| [006](006-algoritmo-de-emparejamiento.md) | Algoritmo de emparejamiento de títulos | Aceptada |
| [007](007-duracion-how-long-to-beat.md) | Fuente de duración (How Long To Beat) | Propuesta |
| [008](008-limites-de-concurrencia.md) | Límites de concurrencia por etapa y por dominio | Propuesta |
| [009](009-modo-replay.md) | Modo replay: adaptador en el cliente HTTP | Aceptada |
| [010](010-hosting-y-tarea-programada.md) | Hosting, tarea programada y almacenamiento de la base | Aceptada |
| [011](011-cobertura-cheapshark-y-catalogo-pc-switch.md) | Más tiendas de PC (CheapShark) y catálogo enfocado en PC y Switch | Aceptada |
