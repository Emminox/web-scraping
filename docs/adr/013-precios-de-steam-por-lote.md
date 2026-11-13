# ADR-013 · Precios de Steam por lote · 2026-11-13

## Contexto
Desde GitHub Actions, la búsqueda de Steam (una solicitud por juego, ~600 por corrida) recibe 429 después de
unas 200–300 solicitudes aunque se vaya a 1 cada 1,6 s: los servidores de GitHub son compartidos y Steam cuenta
todas las solicitudes de esa IP. Resultado: ~130 juegos de PC con el precio de Steam desactualizado cada día.

## Alternativas
1. **Bajar más el ritmo de la búsqueda** — Desventajas: la IP compartida puede seguir llena; la corrida se alarga.
2. **Correr Steam desde otra máquina** (opción `--complementar`) — Desventajas: depende de que una computadora del
   equipo esté encendida y de subir la base a mano.
3. **`/api/appdetails` con `filters=price_overview`, muchos appids por solicitud** — Ventajas: ~400 juegos en 2
   solicitudes; robots.txt de store.steampowered.com no prohíbe /api/; el enunciado permite la API de Steam.
   Desventajas: Valve no la documenta oficialmente (podría cambiar); no trae reseñas.

## Decisión
Alternativa 3 para los juegos cuyo producto de Steam ya está emparejado (el appid sale de su URL). Se ejecuta antes
del pipeline, solo en vivo, y esos juegos no se vuelven a buscar por título. La búsqueda por título se mantiene para
los juegos nuevos y como respaldo si un lote falla. Configurable con `ejecucion.steam_precios_por_lote`.

## Consecuencias
- Se gana: precios de Steam al día desde GitHub Actions; ~600 solicitudes menos a Steam por corrida.
- Se pierde: la reseña de Steam de esos juegos no se refresca a diario (se conserva la última; cambia lento).
- Replay y experimentos: sin cambios. En replay el paso no se ejecuta, así la carga de trabajo medida no depende de
  lo que ya haya en la base.
- Los 3 modos siguen dando resultados idénticos: el paso es secuencial y previo al pipeline, igual en los tres.

## Estado
Aceptada (pedido del equipo; revisar en la próxima reunión).
