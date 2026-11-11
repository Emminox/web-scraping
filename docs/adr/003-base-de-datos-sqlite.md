# ADR-003 · Base de datos: SQLite · 2026-11-11

## Contexto
El enunciado exige guardar al menos 500 juegos en una base de datos (no en el código) y conservar **cada
observación de precio** con su fecha, sin sobrescribirla, para el historial y la etiqueta de "mínimo histórico".
Volumen estimado: unas pocas miles de observaciones por ejecución; decenas de miles en las tres semanas.
El sitio público es estático (lo genera el pipeline), así que no consulta la base en línea. Las mediciones
formales se hacen en una sola máquina y en modo replay.

## Alternativas
1. **SQLite** — Ventajas: incluido en Python (`sqlite3`), sin dependencias ni servidor; un solo archivo que se
   puede copiar y versionar, útil para repetir mediciones; SQL completo para historial y mínimos; escritura
   local sin latencia de red. Desventajas: un solo escritor a la vez; la base no se conserva sola entre
   ejecuciones de GitHub Actions; cada integrante tiene su propia copia.
2. **PostgreSQL en la nube (Supabase, Neon…)** — Ventajas: base compartida por el equipo y por GitHub Actions;
   muchos escritores simultáneos. Desventajas: cada escritura de la etapa Persistir pasa por internet (latencia
   variable y ruido en las mediciones); credenciales como secretos; dependencia de un servicio externo;
   restricciones de unicidad para evitar observaciones duplicadas desde varias máquinas.
3. **Firebase** — Ventajas: base compartida y alojada. Desventajas: NoSQL, por lo que el historial y los mínimos
   históricos requieren más trabajo; SDK externo; latencia de red y costo por operación.

## Decisión
SQLite, escrito por un **único hilo** en la etapa 4 (Persistir), que consume una cola acotada. Las demás etapas
y los procesos del emparejamiento nunca abren la base.

## Consecuencias
- Se gana: cero dependencias, escritura rápida y estable, base reproducible para el replay y una explicación
  simple del diseño ("un escritor alimentado por una cola acotada").
- Se pierde: no hay base compartida en desarrollo. Se compensa versionando el **catálogo base** (juegos, títulos
  alternativos, casos difíciles) como archivo de texto en Git, desde el cual cada integrante regenera su base.
- Pendiente (ADR aparte): cómo se conserva la base entre ejecuciones de GitHub Actions. Opción preferida:
  descargarla de la última GitHub Release y publicar la versión actualizada como nueva Release.
- Qué medir para confirmar: el tiempo de la etapa Persistir frente al resto del pipeline. Si se convirtiera en
  cuello de botella, agrupar las inserciones en transacciones por lotes antes que agregar escritores.

## Estado
Propuesta (confirmar en la reunión de equipo).
