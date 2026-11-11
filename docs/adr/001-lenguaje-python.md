# ADR-001 · Lenguaje de implementación · 2026-11-10 (versión corregida el 2026-11-11)

## Contexto
El enunciado permite C# (.NET 8+) o Python 3.11+. El proyecto combina etapas de E/S (descarga de más de 3.500
páginas por ejecución) con una etapa de CPU obligatoria (emparejamiento de títulos), y el informe debe explicar
con datos propios la diferencia entre concurrencia y paralelismo, incluido el efecto del GIL si se usa Python.

## Alternativas
1. **Python 3.14** — Ventajas: ecosistema maduro de scraping y generación de sitios estáticos; fácil de correr en
   GitHub Actions; el GIL hace *visible* la diferencia entre hilos (sirven para E/S) y procesos (necesarios para
   CPU), que es justo la pregunta 5 del informe. Además, 3.14 ofrece una compilación oficial **sin GIL**
   (free-threaded, `python3.14t`) y `InterpreterPoolExecutor`, que permiten comparar mecanismos de paralelismo
   (extra de la sección 19). Desventajas: el paralelismo de CPU en la compilación normal exige procesos
   (`ProcessPoolExecutor`), con costo de arranque y de serialización (pickle), mayor en Windows (spawn).
2. **Python 3.12** — Ventajas: más años de estabilidad; ya instalado en las máquinas. Desventajas: no tiene una
   compilación sin GIL con soporte oficial, por lo que se pierde ese experimento.
3. **C# (.NET 8+)** — Ventajas: hilos con paralelismo real, `Channel<T>`, `Parallel.ForEach` y `SemaphoreSlim`
   nativos; menor costo del andamiaje paralelo. Desventajas: más código para scraping y para generar el sitio;
   la pregunta del GIL no aplica y el contraste concurrencia/paralelismo es menos evidente.

Se descartó Python 3.15 (publicado en octubre de 2026) por ser demasiado reciente: riesgo de que alguna
biblioteca no tenga soporte todavía, sin aportar nada que el proyecto necesite.

## Decisión
Python 3.14 (compilación normal, con GIL), en la última versión 3.14.x, idéntica en las máquinas de los tres
integrantes, en GitHub Actions y en la máquina de medición. El paquete se niega a importarse con una versión
anterior (`radar/__init__.py`).

## Consecuencias
- Se gana: rapidez de desarrollo y un experimento más rico (hilos vs procesos en el emparejamiento y, como
  extra, la misma etapa en la compilación sin GIL).
- Se pierde: el emparejamiento de las mediciones principales paraleliza con procesos, no con hilos; hay que
  diseñar lotes grandes para que el costo de pickle no domine.
- Qué medir para confirmar: `T_par(1) − T_sec` del emparejamiento con `ProcessPoolExecutor` (costo del
  andamiaje) y la curva ThreadPoolExecutor vs ProcessPoolExecutor en el emparejamiento.
- La similitud de títulos se escribe en Python puro (sin librerías compiladas), como exige el enunciado.
- En Windows, `python` puede apuntar a otra versión instalada: ejecutar con `py -3.14`.

## Estado
Aceptada. Corregida antes de la entrega del Hito 1: la versión pasó de 3.12 a 3.14 (mismo lenguaje).
