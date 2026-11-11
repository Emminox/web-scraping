# ADR-004 · Fuentes de datos por tipo · 2026-11-11

## Contexto
La sección 5 exige: 1 listado paginado para descubrir, ≥ 2 tiendas de plataforma, ≥ 1 minorista (4 tiendas en
total), Metacritic + otra calificación, How Long To Beat, imagen, y ≥ 3 fuentes por HTML (2 de ellas tiendas).
Se hicieron spikes el 2026-11-11 con `radar.herramientas.explorar_fuente` (User-Agent del proyecto, una
solicitud por página) revisando robots.txt, términos y si los datos vienen en el HTML.

| Sitio | robots.txt | Resultado del spike |
|---|---|---|
| Metacritic `/browse/` | Permite (prohíbe `/search/`) | 50 juegos por página con slug, fecha, imagen y Metascore por plataforma |
| Steam `/search/results/` | Permite | JSON con `results_html`: título, precio en centavos, reseñas |
| Nintendo eShop | Permite; publica sitemap | Búsqueda por JavaScript (no sirve). Página de producto con JSON-LD y precios |
| GOG `catalog.gog.com` | Sin robots.txt (404) | API JSON con precio actual y base |
| Best Buy | Permite la búsqueda | Desde Costa Rica muestra "elegir país"; con `intl=nosplash` trae JSON incrustado con nombre, URL y precios |
| PlayStation Store | Permite | La búsqueda NO trae productos en el HTML (se cargan después con JavaScript) |
| Epic, GameStop, Walmart, Target | **Prohíben** las rutas necesarias | Descartados |
| Amazon | Permite | Descartado: sus condiciones de uso prohíben la extracción automática |
| Play-Asia | — | HTTP 403 |
| How Long To Beat | Prohíbe `/api`; **su robots.txt declara prohibido cualquier robot sin permiso escrito** | Descartado (ver ADR-007) |

## Alternativas
1. **Metacritic + Steam + Nintendo + GOG + Best Buy** (las que funcionaron) — Ventajas: cumplen robots.txt;
   Metacritic resuelve a la vez descubrimiento, calificación por plataforma e imagen. Desventajas: los juegos
   exclusivos de PlayStation/Xbox solo tienen precio en Best Buy.
2. **Agregar PlayStation Store vía su API GraphQL interna** — Ventajas: cubriría PS5. Desventajas: API no
   documentada ni pública, con identificadores que cambian; riesgo de romperse y dudoso frente a sus términos.

## Decisión
Alternativa 1: descubrimiento y calificación 1 = Metacritic (HTML); calificación 2 = reseñas de Steam (HTML);
tiendas = Steam (HTML), Nintendo eShop (HTML, URLs desde su sitemap), GOG (API) y Best Buy (HTML, minorista);
imagen = Metacritic. HTML: Metacritic, Steam, Nintendo y Best Buy (3 tiendas).

## Consecuencias
- Se gana: todas las fuentes respetan robots.txt; se cumplen los mínimos de la sección 5 salvo la duración.
- Se pierde: los exclusivos de consola sin versión en PC/Switch no llegan a 2 tiendas y no se publican.
- Qué medir: por sitio, solicitudes exitosas, fallidas y bloqueadas (panel de métricas); cobertura de
  juegos con 2 o más tiendas.

## Estado
Aceptada (decisión delegada por el equipo; revisar en la próxima reunión).
