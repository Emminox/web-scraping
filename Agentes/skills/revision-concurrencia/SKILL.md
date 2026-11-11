---
name: revision-concurrencia
description: Revisión de código especializada en concurrencia y paralelismo para el pipeline del Radar de Ofertas — condiciones de carrera, interbloqueos, sobresuscripción de hilos, mal uso del GIL, colas no acotadas, falta de timeouts/semáforos por dominio, cierre del pipeline y equivalencia de los 3 modos. Usar antes de abrir o aprobar un PR que toque el pipeline, las colas, el fetcher, el emparejamiento o el experimento de contención.
argument-hint: [ruta, rama o vacío para el diff actual]
---

# Revisión de concurrencia

Objetivo: **$ARGUMENTS** (si está vacío, revisa `git diff` de la rama actual contra `main`; si no hay repo o diff, pide la ruta).

Lee primero `Contexto actual/CONTEXTO_PROYECTO.md` (secciones 3.5, 3.6 y 6) y los ADRs de `docs/adr/` sobre límites de concurrencia, para comparar el código contra lo que el equipo decidió.

## Lista de verificación

### A. Correctitud de la sincronización
- Estado compartido mutable accedido desde varios hilos/procesos sin lock, sin `threading.local`/`ThreadLocal` y sin colección concurrente.
- Operaciones leer-modificar-escribir no atómicas (`x += 1`, `dict[k] = dict.get(k,0)+1`, `if k not in d: d[k] = …`). En Python el GIL **no** las hace atómicas.
- Locks adquiridos en distinto orden en distintos lugares (riesgo de interbloqueo); locks sin `with`/`try-finally`/`lock` de C#.
- Trabajo de E/S o de CPU pesado **dentro** de una sección crítica (serializa el pipeline y aumenta la fracción serial).
- Semáforo por dominio: ¿se libera siempre (también en excepción y timeout)? ¿se comparte la misma instancia entre todos los workers?

### B. Pipeline y colas
- Todas las colas entre etapas son **acotadas** (`queue.Queue(maxsize=…)`, `Channel.CreateBounded`, `BlockingCollection(capacity)`) con el tamaño del ADR.
- Cierre ordenado: centinelas/`CompleteAdding`/`Writer.Complete()` — uno por consumidor; sin hilos colgados al final; excepciones de un worker que no se pierdan en silencio.
- Productor que bloquea en `put()` con la cola llena mientras el consumidor espera algo del productor → interbloqueo.

### C. Sobresuscripción y niveles anidados
- Los 3 niveles (por juego, por fuente, por tienda) anidados sin límite global → explosión de tareas. Verificar que existen los topes del ADR.
- Pools creados dentro de bucles o por cada juego (deben crearse una vez y reutilizarse).
- `ProcessPoolExecutor` con más procesos de los decididos, o con tareas demasiado finas (el costo de serializar/pickle domina). Revisar `chunksize`/tamaño de lote.
- En C#: `Parallel.ForEach` con trabajo de E/S bloqueante, o `Task.Run` dentro de `Parallel.ForEach`; `.Result`/`.Wait()` sobre tareas async (riesgo de bloqueo).

### D. Python y el GIL
- Emparejamiento con `ThreadPoolExecutor` presentado como "paralelo": con el GIL no escala; debe ser `ProcessPoolExecutor`/`multiprocessing` en el modo 3 (salvo que sea la comparación intencional del informe).
- Uso de librerías compiladas de similitud (rapidfuzz, Levenshtein, jellyfish) en la etapa medida → **viola el enunciado**.
- En Windows, `ProcessPoolExecutor` necesita `if __name__ == "__main__":` y funciones a nivel de módulo (picklables).

### E. Robustez (sección 8 del enunciado)
- Timeout en **cada** solicitud. Reintentos con backoff exponencial **+ jitter** y máximo definido.
- Fallidos van a la cola de fallidos y se reintentan al final; se registran para el panel de métricas.
- Datos de una fuente caída se marcan como desactualizados con su fecha; nunca se publica un dato viejo como actual.

### F. Reproducibilidad y equivalencia de modos
- Los 3 modos deben producir **los mismos resultados**: buscar dependencias del orden de llegada (empates en el emparejamiento sin desempate estable, listas sin ordenar antes de persistir, `set` iterado, timestamps usados como clave).
- Aleatoriedad (jitter, latencia simulada) con semilla configurable en replay.
- La medición de tiempos no incluye trabajo ajeno (p. ej. arrancar el pool dentro del cronómetro sin decidirlo explícitamente).

## Formato del reporte
Para cada hallazgo:
- **Severidad:** Crítico (resultado incorrecto/cuelgue) · Alto (viola enunciado o ADR) · Medio (rendimiento/medición) · Bajo (estilo).
- **Ubicación:** `archivo:línea`.
- **Escenario concreto** que falla (intercalado de hilos o entrada que lo dispara).
- **Corrección sugerida** y **qué preguntaría el profesor en la defensa** sobre este punto.

Termina con: (1) si el cambio respeta los límites del ADR, (2) si conviene un test de equivalencia de modos o de estrés, y (3) si algún hallazgo fue un defecto **producido por IA** → sugerir registrarlo con `/bitacora-ia` (puede ser la entrada obligatoria de "error real").

No apliques cambios salvo que el usuario lo pida explícitamente.
