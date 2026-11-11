# ADR-008 · Límites de concurrencia por etapa y por dominio · 2026-11-11

## Contexto
La sección 7 exige fijar y justificar: workers por etapa, conexiones simultáneas por dominio y tamaño de cada
cola, para que los tres niveles de paralelismo (por juego, por fuente, por tienda) no se anidan sin control.
La máquina de desarrollo tiene 16 núcleos lógicos. Ningún sitio declara Crawl-delay.

## Alternativas
1. **Valores conservadores fijos** (los de abajo) — Ventajas: no saturan los sitios; sencillos de explicar.
   Desventajas: en vivo, el límite real es el intervalo por dominio, no los workers.
2. **Un pool por nivel** (juegos × fuentes × variantes) — Desventajas: miles de tareas simultáneas; es justo lo
   que el enunciado pide evitar.

## Decisión (valores en `config/config.toml`)
- Descubrir: 4 hilos · Descargar: 16 hilos · Parsear: 1 · Emparejar: 4 procesos (modo paralelo) · Persistir: 1.
- Colas: tareas 64, descargas 64, resultados 64, persistir 32 (≈ 4 × workers de la etapa consumidora).
- Por dominio: Metacritic y Best Buy 1 conexión y 2 s entre solicitudes (páginas de 0,6 MB); Steam, GOG y
  Nintendo 2 conexiones y 1 s. Todo el trabajo pasa por un pool fijo por etapa, nunca por pools anidados.

## Consecuencias
- Se gana: el máximo de trabajo simultáneo está acotado por diseño en cada etapa y en cada sitio.
- Se pierde: en vivo, más de 16 workers de descarga no aceleran (los frena el intervalo por dominio).
- Qué medir (en replay, DESPUÉS de las predicciones del Hito 1): los barridos de la sección 12 para elegir los
  valores definitivos; este ADR se reemplazará con los datos.

## Estado
Propuesta (valores provisionales hasta los barridos).
