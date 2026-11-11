# ADR-001 · Lenguaje de implementación · 2026-11-10

## Contexto
El enunciado permite C# (.NET 8+) o Python 3.11+. El proyecto combina etapas de E/S (descarga de más de 3.500
páginas por ejecución) con una etapa de CPU obligatoria (emparejamiento de títulos), y el informe debe explicar
con datos propios la diferencia entre concurrencia y paralelismo, incluido el efecto del GIL si se usa Python.
El equipo ya tiene Python 3.12 instalado.

## Alternativas
1. **Python 3.12** — Ventajas: ecosistema maduro de scraping y generación de sitios estáticos; fácil de correr en
   GitHub Actions; el GIL hace *visible* la diferencia entre hilos (sirven para E/S) y procesos (necesarios para
   CPU), que es justo la pregunta 5 del informe. Desventajas: el paralelismo de CPU exige procesos
   (`ProcessPoolExecutor`), con costo de arranque y de serialización (pickle), mayor en Windows (spawn).
2. **C# (.NET 8+)** — Ventajas: hilos con paralelismo real, `Channel<T>`, `Parallel.ForEach` y `SemaphoreSlim`
   nativos; menor costo del andamiaje paralelo. Desventajas: más código para scraping y para generar el sitio;
   la pregunta del GIL no aplica y el contraste concurrencia/paralelismo es menos evidente.

## Decisión
Python 3.12 (mínimo 3.12 en las máquinas de los tres integrantes y en GitHub Actions).

## Consecuencias
- Se gana: rapidez de desarrollo y un experimento más rico (hilos vs procesos en el emparejamiento).
- Se pierde: el emparejamiento paraleliza con procesos, no con hilos; hay que diseñar lotes grandes para que el
  costo de pickle no domine.
- Qué medir para confirmar: `T_par(1) − T_sec` del emparejamiento con `ProcessPoolExecutor` (costo del
  andamiaje) y la curva ThreadPoolExecutor vs ProcessPoolExecutor en el emparejamiento.
- La similitud de títulos se escribe en Python puro (sin librerías compiladas), como exige el enunciado.

## Estado
Aceptada.
