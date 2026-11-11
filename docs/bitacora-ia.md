# Bitácora de IA

Formato: una entrada por uso relevante (qué se pidió, qué se obtuvo, qué se aceptó, qué se modificó y por qué).
La entrada obligatoria de error real de concurrencia está marcada con **[ERROR REAL]**.
Usar `/bitacora-ia` (o `/bitacora-ia error-real`) para agregar entradas al final; no reescribir entradas anteriores.

Recordatorio: las predicciones de rendimiento del Hito 1 se hacen **sin IA**.

### 2026-11-10 → 2026-11-11 · Emminox · Base del proyecto y sistema funcional de punta a punta
- **Herramienta:** Claude Code (Claude Opus 5.5).
- **Se pidió:** leer el enunciado y armar un plan; contexto compartido, `CLAUDE.md` y skills; estructura de
  `docs/`; luego, de forma autónoma, la base de código y un sistema funcional para el mismo día.
- **Se obtuvo:** capa de red (robots.txt, límites por dominio, reintentos, caché/replay), esquema SQLite,
  catálogo manual, orquestador del pipeline con los 3 modos, spikes y parsers de 5 fuentes, emparejamiento en
  Python puro, persistencia, sitio estático con panel de métricas, workflow de GitHub Actions, ADR 001–010 y
  pruebas automáticas.
- **Defectos introducidos por la IA y detectados por las pruebas (corregidos):**
  1. `abrir_bd` no cerraba la conexión cuando fallaba la verificación del esquema (archivo bloqueado en Windows).
  2. La duración total y las etapas se medían desde orígenes de tiempo distintos (prueba intermitente: fallaba
     7 de cada 10 veces). No era una carrera entre hilos.
  3. La normalización convertía "™" en las letras "TM" ("hadestm") por aplicar NFKD antes de quitar símbolos.
  4. Un DLC con el mismo título base podía ganarle al juego en un empate de similitud.
  5. `.gitignore` con `sitio/` excluía también el código de `radar/sitio/`.
  Ninguno es un defecto de concurrencia: NO sirven como entrada **[ERROR REAL]**.
- **Decisión ética tomada por la IA:** no scrapear How Long To Beat porque su robots.txt lo prohíbe
  explícitamente (ADR-007); se borraron las 2 páginas descargadas en el spike antes de leer esa cláusula.
- **Se aceptó / se modificó y por qué:** _(completar por el equipo después de revisar el código)_
- **Cómo se verificó:** pruebas automáticas (`py -3.14 -m unittest`), pruebas de concurrencia repetidas 20–30
  veces, ejecuciones reales en vivo y en replay, revisión visual del sitio. _(agregar la revisión del equipo)_
- **Archivos/commits:** `ef6a768` a `6b35976` y siguientes en las ramas `feat/esqueleto-pipeline` y
  `feat/sistema-funcional`.

### 2026-11-11 · Emminox · Revisión de código con IA (`/code-review`) y correcciones
- **Herramienta:** Claude Code (Claude Opus 5.5), skill `/code-review` sobre `radar/`.
- **Se pidió:** revisar el código en busca de defectos y luego corregir los hallazgos.
- **Se obtuvo:** 7 hallazgos, todos corregidos con pruebas nuevas (102 pruebas en total):
  1. Un fallo temporal (timeout/5xx) al leer robots.txt bloqueaba el dominio toda la ejecución → ahora solo
     durante 60 s y luego se vuelve a leer. Un 401/403 sigue siendo bloqueo definitivo.
  2. El filtro "Juego + DLC" del sitio nunca encontraba nada (miraba el tipo del catálogo, no el de los productos).
  3. Etiquetas del eje Y del historial redondeadas al dólar (se repetían en juegos baratos).
  4. Dos hilos con la misma URL la descargaban dos o tres veces (p. ej. Best Buy para PS5, Xbox y Switch) →
     candado por URL; orden de candados fijo (URL → semáforo del dominio), sin interbloqueo posible.
  5. El año entre paréntesis de Metacritic ("Unreal Tournament (1999)") activaba la penalización de números.
  6. El índice de Nintendo duplicaba las reglas de normalización → ahora reutiliza `texto_basico`.
  7. La exportación de pares de validación tomaba los primeros N por clave (sesgo alfabético) → muestra repartida.
- **Nota:** el hallazgo 4 es un defecto de concurrencia introducido por la IA y detectado por la IA; NO se
  marca como **[ERROR REAL]** (esa entrada debe describir un error que viva el equipo).
- **Se aceptó / se modificó y por qué:** _(completar por el equipo)_
- **Cómo se verificó:** `py -3.14 -m unittest` (102 pruebas, incluida una de 4 hilos pidiendo la misma URL).
