# ADR-007 · Fuente de duración (How Long To Beat) · 2026-11-11

## Contexto
La sección 5 exige How Long To Beat (HLTB) para la duración e indica IGDB "solo como respaldo documentado".
En el spike del 2026-11-11 el robots.txt de HLTB (propiedad de Ziff Davis) dice textualmente que "el uso de
cualquier robot, crawler u otra herramienta para extraer contenido por medios automatizados está prohibido sin
permiso escrito", y prohíbe `/api`. Además, su búsqueda funciona solo con JavaScript. La sección 10 obliga a
respetar robots.txt y términos de uso, y permite sustituir una fuente con evidencia.

## Alternativas
1. **Scrapear HLTB igualmente** — Desventajas: viola su robots.txt y sus términos; incumple la sección 10.
2. **IGDB (respaldo previsto por el enunciado)** — Ventajas: API oficial con tiempos ("game_time_to_beats").
   Desventajas: requiere credenciales de desarrollador de Twitch, que debe crear un integrante (Claude no
   puede crear cuentas).
3. **Pedir permiso escrito a Ziff Davis** — Desventajas: improbable a tiempo para el proyecto.

## Decisión
No scrapear HLTB. Usar IGDB como respaldo cuando el equipo tenga credenciales (variables de entorno
`IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET`). Hasta entonces el sitio muestra la duración como "no disponible" con
el motivo. Se informará al profesor con esta evidencia.

## Consecuencias
- Se gana: cumplimiento de la sección 10 con evidencia documentada.
- Se pierde: la duración no aparece hasta implementar IGDB.
- Pendiente: un integrante crea la aplicación en Twitch Developers y se implementa la fuente IGDB.

## Estado
Propuesta (pendiente de credenciales de IGDB y de comunicarlo al profesor).
