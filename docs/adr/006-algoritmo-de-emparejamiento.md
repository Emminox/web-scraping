# ADR-006 · Algoritmo de emparejamiento de títulos · 2026-11-11

## Contexto
Cada tienda nombra el mismo juego distinto ("Hades - Nintendo Switch Lite, Nintendo Switch", "HADES™"). La
etapa debe ser propia, en Python puro (para que el GIL sea observable), comparar cada juego con todos los
candidatos de todas sus tiendas, tener un umbral validado con ≥ 60 pares y marcar los casos dudosos.

## Alternativas
1. **Levenshtein normalizado + palabras ordenadas** — Ventajas: simple de explicar; el costo O(n·m) por par
   da carga de CPU medible. Desventajas: sensible a palabras extra largas.
2. **Jaro–Winkler** — Ventajas: favorece prefijos comunes. Desventajas: puntúa alto títulos distintos con el
   mismo comienzo ("Hades" vs "Hades II"), justo el caso difícil más común.
3. **Jaccard de palabras** — Ventajas: rápido. Desventajas: casi sin trabajo de CPU y pierde el orden.

## Decisión
Alternativa 1 (`radar/emparejamiento/`). Normalización: sin acentos, ™/®, puntuación, frases de plataforma y
edición; romanos a arábigos. Similitud = máx(Levenshtein normalizado, Levenshtein de palabras ordenadas),
**× 0,6 si los números difieren** (secuelas). Umbral **0,88**, banda dudosa **[0,80; 0,88)**. También es
dudoso un candidato con edición especial, palabras de DLC, tipo distinto de "juego" o plataforma
desconocida; a igual similitud gana el candidato "limpio" y luego la URL menor (resultado determinista).
Un producto reclamado por dos juegos queda para el de mejor estado, luego mayor similitud, luego clave menor.

## Consecuencias
- Se gana: casos difíciles cubiertos (secuelas, ediciones, DLC, plataformas en el título) y resultados
  idénticos en los tres modos.
- Se pierde: el umbral es PROVISIONAL; falta el conjunto de validación de 60 pares revisados a mano.
- Qué medir: precisión y exhaustividad por umbral (`/validar-emparejamiento`); tiempo de la etapa vs núcleos.

## Cambio (2026-11-11)
Muchas tiendas venden SOLO una edición con contenido extra ("Game of the Year", "Complete",
"Definitive"…): eran dudosas y el juego no se publicaba. Ahora, si la única diferencia es una edición de ese tipo,
se **acepta** como "juego + DLC" y la edición queda anotada y visible en el panel. Las remasterizaciones siguen
siendo dudosas. El mejor candidato se elige **por tienda** (una consulta a CheapShark trae varias, ADR-011).

## Estado
Aceptada (el umbral se revisará con el conjunto de validación).
