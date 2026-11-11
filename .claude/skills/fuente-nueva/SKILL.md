---
name: fuente-nueva
description: Evalúa un sitio candidato como fuente de datos del Radar de Ofertas (descubrimiento, tienda de plataforma, minorista, calificación, HLTB o imagen) con criterios de scraping responsable — robots.txt, términos de uso, HTML vs JavaScript, bloqueos, paginación — y produce su ficha. Usar en los spikes de fuentes del Hito 1 o cuando una fuente se bloquea y hay que sustituirla.
argument-hint: <sitio o URL> [tipo de dato]
---

# Ficha de evaluación de fuente

Sitio a evaluar: **$ARGUMENTS**

Contexto obligatorio: sección 3.2 (mínimos por tipo) y 3.8 (scraping responsable) de `Contexto actual/CONTEXTO_PROYECTO.md`.

## Reglas
- Solo solicitudes **manuales y puntuales** para evaluar (pocas páginas). Nada de barridos durante la evaluación.
- **Prohibido** proponer evasión de CAPTCHAs, proxies, rotación de User-Agent/IP para ocultarse, cookies de sesión de cuentas personales o cualquier técnica para burlar bloqueos. Si el sitio bloquea, la salida correcta es **sustituir** la fuente (misma fila de la tabla o su API oficial) con un ADR.
- No recolectar datos personales (reseñas con nombres de usuario, perfiles, etc.).

## Qué averiguar (y con qué evidencia)
1. **Tipo de dato y fila** de la tabla del enunciado que cubre. ¿Cuenta como tienda de plataforma, minorista o ninguna?
2. **robots.txt:** URL, rutas relevantes permitidas/prohibidas, `Crawl-delay` si existe. Copiar las líneas relevantes.
3. **Términos de uso:** si mencionan scraping/automatización. Enlace y resumen en una frase.
4. **¿Los datos vienen en el HTML inicial?** (precio actual, precio regular, formato, enlace, título, plataforma, imagen, score/HLTB según el tipo). ¿O hay JSON embebido (`__NEXT_DATA__`, `application/ld+json`)? ¿O requiere JS → Playwright (justificar en ADR)?
5. **¿API pública oficial?** Si existe, ¿requiere clave? Recordar: se necesitan ≥ 3 fuentes por HTML, de ellas ≥ 2 tiendas.
6. **Búsqueda por título:** ¿cómo se encuentra un juego? (URL de búsqueda, parámetros). ¿Devuelve varias variantes/ediciones? (3er nivel de paralelismo).
7. **Paginación** (si es fuente de descubrimiento): patrón de URL, resultados por página, cuántas páginas para llegar a 500+ juegos y ≥ 3 plataformas.
8. **Comportamiento ante automatización:** códigos 403/429, desafíos JS, CAPTCHA, Cloudflare/Akamai. Probar con el User-Agent del proyecto.
9. **Región y moneda:** ¿precios en USD? ¿depende de la IP? (afecta comparabilidad y el modo replay).
10. **Riesgo** (bajo/medio/alto) y **fuente de respaldo** de la misma fila.

## Salida
1. Agregar una fila a `docs/fuentes.md` (crearlo si no existe) con: sitio · tipo · HTML/API/JS · robots.txt OK · ToS · riesgo · respaldo · fecha · quién evaluó.
2. Guardar en `docs/fuentes/<sitio>.md` la ficha completa con la evidencia (líneas de robots.txt, códigos HTTP observados).
3. Si se recomienda usarla, sugerir el rate limit inicial por dominio y el timeout, para que alimente el ADR de límites de concurrencia.
4. Si es una **sustitución**, invocar el flujo de `/adr` con la evidencia del bloqueo.
5. Sugerir guardar 2–3 respuestas de ejemplo como fixtures de parser / semilla del modo replay.
