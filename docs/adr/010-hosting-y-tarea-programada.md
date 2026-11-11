# ADR-010 · Hosting, tarea programada y almacenamiento de la base · 2026-11-11

## Contexto
El sitio debe estar en una URL pública (no localhost), regenerarse con una tarea programada y mostrar la fecha
de la última actualización. La base SQLite (ADR-003) guarda el historial de precios y debe conservarse entre
ejecuciones; un runner de GitHub Actions empieza vacío cada vez.

## Alternativas
1. **GitHub Pages + GitHub Actions + base en una GitHub Release** — Ventajas: todo dentro del repositorio,
   gratis para repos públicos; la base no infla el historial de Git. Desventajas: los runners usan IPs de centros
   de datos, que algunos sitios bloquean; Pages en repos privados requiere GitHub Pro.
2. **Netlify/Vercel + cron en una máquina del equipo** — Ventajas: IP residencial. Desventajas: depende de que
   una computadora esté encendida; credenciales de otro servicio.
3. **Base en la rama `datos` del repositorio** — Desventajas: cada día suma una copia completa de la base al
   historial de Git.

## Decisión
Alternativa 1 (`.github/workflows/actualizar-sitio.yml`): todos los días a las 12:00 UTC (6:00 en Costa Rica)
y a mano con "Run workflow". La base se descarga de la Release `datos`, se actualiza y se vuelve a subir. Las
capturas de replay NO se publican (pesan cientos de MB); cada integrante las genera con una ejecución en vivo.

## Consecuencias
- Se gana: publicación automática y reproducible, sin servidores propios.
- Se pierde: si un sitio bloquea las IPs de GitHub, ese día sus precios quedan marcados como desactualizados
  (el sitio lo muestra con su fecha) y el fallo aparece en el panel de métricas.
- Qué medir: solicitudes fallidas por sitio en las ejecuciones programadas frente a las locales.

## Cambio (2026-11-11)
Segundo workflow, "Publicar sitio (rápido)": regenera y publica el sitio desde la base de la Release "datos" sin
volver a descargar las tiendas (~2 min). Se lanza solo al subir cambios en `radar/sitio/` y comparte el grupo de
concurrencia con "Actualizar sitio": si la corrida completa está en curso, espera a que termine, así publica con
la base del día y su diseño no queda pisado por la corrida completa (que usa el código de cuando empezó).

## Estado
Aceptada. Requiere activar Settings → Pages → Source: GitHub Actions.
