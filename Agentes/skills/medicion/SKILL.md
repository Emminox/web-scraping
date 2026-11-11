---
name: medicion
description: Analiza resultados de los barridos de rendimiento del Radar de Ofertas — construye la tabla del Anexo 2 (mediana, mín–máx, S_abs, S_rel, E, Karp–Flatt), revisa la validez del experimento (≥5 repeticiones, replay, ficha del equipo) y ayuda a responder las 8 preguntas del informe con datos propios. Usar con un CSV/JSON de mediciones o al diseñar un barrido. NO genera predicciones del Hito 1.
argument-hint: <archivo de mediciones> [etapa]
---

# Análisis de mediciones

Entrada: **$ARGUMENTS**

## Regla dura
**No produzcas predicciones de tiempo ni de speedup para el Hito 1** (el enunciado exige hacerlas sin IA).
Tampoco "precalcules" la predicción de la defensa oral. Si te las piden, explica el porqué y ofrece
repasar conceptos (Amdahl, Little, latencia vs throughput) sin números del sistema.
Sí puedes comparar **después** las predicciones ya escritas del H1 contra las mediciones (pregunta 8).

## 1. Validar el experimento antes de calcular
- ¿Se midió en **modo replay**? ¿Con qué latencia simulada (fija o con jitter, semilla)?
- ¿Hay **≥ 5 repeticiones** por configuración?
- ¿Están todos los puntos del barrido? E/S: 1, 2, 4, 8, 16, 32, 64. Emparejamiento: 1, 2, 4, …, núcleos lógicos, 2× núcleos lógicos.
- ¿Existe la **ficha del equipo de medición** (CPU, núcleos físicos/lógicos, SMT, RAM, SO, versión del lenguaje)? ¿Todas las mediciones son de la **misma máquina**?
- ¿Se midieron las etapas por separado **y** el pipeline completo, en los 3 modos?
- Señales de ruido: dispersión alta, valores atípicos, máquina con otras cargas, carpeta sincronizada por OneDrive, modo de energía de laptop.
Reporta lo que falte antes de seguir.

## 2. Calcular (por etapa y para el pipeline completo)
- `T_sec`: mediana del modo secuencial. `T_par(p)`: mediana con p workers.
- `S_abs(p) = T_sec / T_par(p)`
- `S_rel(p) = T_par(1) / T_par(p)`, `E(p) = S_rel(p) / p`
- Karp–Flatt (p > 1): `e = (1/S_rel(p) − 1/p) / (1 − 1/p)`
- Andamiaje: `T_par(1) − T_sec` (absoluto y %).
- Amdahl: con `f` estimada por Karp–Flatt, curva teórica `S(p) = 1 / (f + (1 − f)/p)` para comparar.

Entrega la tabla con formato del Anexo 2:

| Workers (p) | Mediana (s) | Mín – máx (s) | S_abs(p) | S_rel(p) | E(p) | e (Karp–Flatt) |
|---|---|---|---|---|---|---|
| Secuencial | | | 1,00 | — | — | — |
| 1 | | | | 1,00 | 1,00 | — |

Usa coma decimal en las tablas del informe si el equipo así lo decide; sé consistente.
Si se pide un gráfico, generar un script reproducible que lea el archivo de datos (no valores copiados a mano), con speedup y eficiencia vs p y la línea ideal/Amdahl.

## 3. Interpretar (guía para las 8 preguntas)
Para cada observación, ligarla a una causa **comprobable en el código o el hardware**:
- E > 1 en E/S: los workers esperan la red, no compiten por núcleos; el límite real es la latencia, el semáforo por dominio y el tamaño de cola.
- Emparejamiento se aplana cerca de núcleos físicos/lógicos: SMT comparte unidades de ejecución; >lógicos solo agrega cambio de contexto.
- Python: hilos en emparejamiento ≈ secuencial por el GIL; procesos escalan pero pagan arranque y serialización (pickle).
- `e` de Karp–Flatt que **crece** con p → sobrecosto de paralelización (sincronización, colas, serialización); `e` constante → fracción serial real.
- Cuello de botella: comparar throughput por etapa; al subir la latencia simulada la descarga domina, al bajarla puede dominar el emparejamiento o la persistencia.
Señala qué afirmaciones aún **no** tienen respaldo en los datos y qué medición adicional lo daría.

## 4. Salida
- Guarda las tablas en `docs/informe/resultados-<etapa>.md` (o donde el equipo indique).
- Recuerda registrar en `/bitacora-ia` si el análisis o el script se hicieron con IA.
