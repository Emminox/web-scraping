# ADR-009 · Modo replay: adaptador en el cliente HTTP · 2026-11-11

## Contexto
La sección 11 exige medir en modo replay: respuestas reales capturadas para todo el catálogo, servidas con
latencia simulada (fija y con variación), con el mismo código que en vivo.

## Alternativas
1. **Adaptador dentro de `ClienteHttp`** — el almacén de capturas (que en vivo es la caché) sirve las respuestas
   y se duerme la latencia simulada ocupando el turno del dominio. Ventajas: mismo código en ambos modos; sin
   procesos extra que compitan por CPU; determinista con semilla. Desventajas: no ejercita sockets reales.
2. **Servidor HTTP local** — Ventajas: ejercita la pila de red. Desventajas: el servidor corre en la misma
   máquina y consume CPU que se mezclaría con la etapa de emparejamiento al medir; hay que mapear dominios.

## Decisión
Alternativa 1. Toda descarga en vivo queda guardada en `datos/capturas/`; `--fuente replay` lee de ahí con
`[replay] latencia_ms` y `variacion_ms` (semilla fija). En replay se usa otra base y otro sitio (`-replay`).

## Consecuencias
- Se gana: una ejecución completa en vivo deja las capturas del catálogo entero; mediciones repetibles.
- Se pierde: el costo de abrir sockets no se mide en replay (se compara aparte con la pregunta 7).
- Qué medir: diferencia entre una ejecución en vivo y su predicción en replay.

## Estado
Aceptada.
