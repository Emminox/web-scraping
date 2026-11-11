# ADR-011 · Más tiendas de PC (CheapShark) y catálogo enfocado en PC y Switch · 2026-11-11

## Contexto
El sitio solo publica juegos con precio en 2 o más tiendas. Con las fuentes del ADR-004 se publicaban 107 de 615
juegos (17 %). Medición del 2026-11-11 por plataforma (productos aceptados): PC 200 juegos → Steam 126, GOG 42;
Switch 200 → Nintendo 186, Best Buy 62; PS5 200 → Best Buy 94; Xbox 199 → Best Buy 44. PS5 y Xbox tienen una sola
tienda, así que sus 236 juegos exclusivos nunca pueden publicarse. Spikes del mismo día:
- PlayStation Store: búsqueda, páginas de categoría y "sitemap.xml" devuelven la aplicación de JavaScript sin
  productos; su API interna (web.np.playstation.com) responde 403.
- Xbox: el catálogo trae solo 25 productos en el HTML; robots.txt prohíbe la búsqueda; no declara sitemap.
- CheapShark (API pública y documentada): permitida por robots.txt; devuelve precios de 13 tiendas oficiales de PC.

## Alternativas
1. **CheapShark para PC + más páginas de PC y Switch** — Ventajas: API pública y estable; una consulta por juego
   da varias tiendas (Humble, Fanatical, Green Man Gaming, Epic…). Desventajas: depende de un agregador; los
   exclusivos de PS5/Xbox siguen sin publicarse.
2. **API interna de PlayStation Store** — Desventajas: responde 403 y no está documentada (sección 10).
3. **Ampliar el catálogo sin nuevas fuentes** — Desventajas: con 17 % publicado harían falta ~3000 juegos.

## Decisión
Alternativa 1. CheapShark como fuente por API de las tiendas de PC (cada tienda es una fuente propia; se excluyen
Steam y GOG, que se consultan directamente). Descubrimiento: PC 12 páginas, Switch 8, PS5 y Xbox 4
(`[descubrimiento.paginas]` en config.toml). El emparejamiento elige el mejor producto por tienda.

## Consecuencias
- Se gana: la mayoría de los juegos de PC queda con 3 o más tiendas; más juegos publicados.
- Se pierde: los exclusivos de PS5/Xbox siguen sin publicarse; se informa en el panel.
- Qué medir: juegos publicados por plataforma y solicitudes fallidas a CheapShark.

## Cambio (2026-11-11, tarde)
- CheapShark respondió 429 con `Retry-After` de ~1 h tras 67 solicitudes en ~4,5 min. No publica un límite.
  El cliente recortaba esa espera a 30 s y reintentaba, lo que no respeta lo que pidió el sitio. Ahora una
  espera larga pausa el dominio completo (sin tocar la red) y sus tareas van a la cola de fallidos; el
  reintento final espera la pausa si no pasa de `red.pausa_maxima_segundos`. CheapShark baja a 1 solicitud cada 6 s.
- Con el arreglo de "[Digital]" (ADR-006, cambio 2) Switch tiene dos tiendas reales: Switch sube de 8 a 12 páginas.

## Cambio (2026-11-11, primera corrida en GitHub Actions)
Sin caché, desde GitHub: Steam respondió 429 tras ~150 búsquedas (pasa a 1 conexión, 1 cada 1,6 s) y el
robots.txt de CheapShark respondió 429 (un 429 en robots.txt ahora también pausa el dominio). Best Buy, Nintendo,
GOG y Metacritic no tuvieron problemas.

## Estado
Aceptada (decisión delegada por el equipo; revisar en la próxima reunión).
