# CLAUDE.md — Radar de Ofertas Multinúcleo (IC-3101, TEC)

Proyecto universitario en equipo (3 personas): sitio público de ofertas de videojuegos alimentado por un
pipeline de web scraping **secuencial vs. concurrente vs. paralelo**, con experimentos de rendimiento
(speedup, eficiencia, Amdahl, Karp–Flatt) en modo replay.

## Antes de hacer cualquier cosa
Lee **`Contexto actual/CONTEXTO_PROYECTO.md`**: es la fuente única de contexto (requisitos, rúbrica,
hitos, reglas, estado actual y plan). El enunciado oficial está en `Requerimientos y guías/`.

## Reglas no negociables (detalle en la sección 6 del contexto)
- **No producir predicciones de rendimiento del Hito 1**: deben hacerse sin IA.
- Registrar los usos relevantes de IA en `docs/bitacora-ia.md` (`/bitacora-ia`). Nunca inventar la entrada de "error real".
- Scraping responsable: respetar robots.txt/ToS, rate limit por dominio, User-Agent con el nombre del proyecto, caché.
  **Prohibido** evadir CAPTCHAs, usar proxies, hacer login con cuentas personales o recolectar datos personales.
- Emparejamiento de títulos en **Python puro** (sin rapidfuzz/Levenshtein compilado) si el lenguaje es Python.
- Los **3 modos** de ejecución deben producir **resultados idénticos** con los mismos datos.
- Mediciones formales **solo en modo replay**.
- Toda decisión con alternativas reales → ADR en `docs/adr/` (`/adr`). Desviaciones del diseño H1 → `docs/cambios-diseno.md`.
- Al escribir código concurrente, explicar por qué es correcto: todos los integrantes serán interrogados en la defensa.

## Skills del proyecto
Definidas en `Agentes/skills/` (fuente) y activas en `.claude/skills/`. Catálogo y comandos en `Agentes/README.md`.

## Mantener actualizado
Cuando se acepte un ADR o cambie el estado del proyecto, actualizar la sección **"7. Estado actual"** de
`Contexto actual/CONTEXTO_PROYECTO.md` en el mismo commit.
