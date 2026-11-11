# ADR-002 · Cliente HTTP con la biblioteca estándar · 2026-11-10

## Contexto
Todas las fuentes se consultan a través de una sola capa de red que aplica timeout, reintentos con backoff y
jitter, límite por dominio, robots.txt, User-Agent del proyecto y almacén de capturas (caché y modo replay).
Hay que elegir con qué biblioteca hace las solicitudes esa capa. Las mediciones formales se hacen en modo
replay, donde no hay red real.

## Alternativas
1. **`urllib.request` (biblioteca estándar)** — Ventajas: cero dependencias; segura para usar desde varios hilos
   (cada llamada abre su propia conexión); el código del curso queda explícito. Desventajas: sin keep-alive ni
   HTTP/2 (una conexión TCP por solicitud) y sin descompresión gzip automática; el timeout aplica a cada
   operación del socket, no al total de la solicitud.
2. **`httpx` o `requests`** — Ventajas: reutiliza conexiones, maneja compresión, API más cómoda. Desventajas:
   dependencia externa; el pool de conexiones agrega otro límite de concurrencia oculto que habría que
   configurar y explicar en la defensa.

## Decisión
Usar `urllib.request` detrás de una interfaz `Transporte`, de modo que cambiar a `httpx` solo requiera escribir
otro transporte sin tocar el resto del código.

## Consecuencias
- Se gana: base sin dependencias y límites de concurrencia que dependen solo del diseño propio (semáforo por
  dominio), fáciles de explicar.
- Se pierde: algo de rendimiento en modo vivo por no reutilizar conexiones. No afecta las mediciones formales
  (son en replay).
- Qué medir para confirmar: el tiempo medio por solicitud en vivo por dominio. Si el establecimiento de conexión
  domina, reconsiderar con un ADR que reemplace a este.

## Estado
Aceptada (confirmada por el equipo el 2026-11-11).
