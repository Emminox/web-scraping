# Contexto del proyecto — Radar de Ofertas Multinúcleo

> **Para Claude (y para el equipo):** este archivo es la fuente única de contexto del proyecto.
> Resume el enunciado oficial (`Requerimientos y guías/III_ProyectoProgramado_IC3101_IIS2026.docx`)
> y el modelo de referencia (`Requerimientos y guías/MulticoreProyectoReferencia.pdf.pdf`).
> Si algo aquí contradice el enunciado, **manda el enunciado**. Actualicen la sección
> "Estado actual" cada vez que se tome una decisión (ADR) o se cierre un hito.

---

## 1. Ficha rápida

| Aspecto | Valor |
|---|---|
| Curso | IC-3101 Arquitectura de Computadoras — TEC San Carlos — II Semestre 2026 |
| Proyecto | III Proyecto Programado: **Radar de Ofertas Multinúcleo** |
| Producto | Sitio web **público** de ofertas de videojuegos (estilo DekuDeals) alimentado por un pipeline de web scraping **secuencial vs. paralelo**, con historial de precios y panel de métricas |
| Unidad | Paralelismo a nivel de hilos (TLP): concurrencia, paralelismo, sincronización y evaluación de rendimiento |
| Equipo | 3 personas |
| Duración | 3 semanas, 3 hitos (H1 diseño, H2 avance, H3 final + defensa oral) |
| Lenguaje | C# (.NET 8+) **o** Python 3.11+ → se decide en un ADR |
| IA | Permitida y esperada, **pero se declara** en `docs/bitacora-ia.md` |

**Pregunta central que hay que responder con datos propios:**
*¿Cuándo y por qué el paralelismo acelera un sistema, y qué lo limita?*

**Dónde está la nota:** 55 % diseño + experimentación + conducción, 45 % implementación.
Un sistema que funciona pero que el equipo no puede explicar ni medir **no aprueba**.

---

## 2. Vocabulario obligatorio (usarlo con precisión)

| Término | Significado | Dónde aparece |
|---|---|---|
| Secuencial | Una tarea a la vez, un solo hilo. Línea base. | Modo 1 |
| Concurrente | Varias tareas en progreso; mientras una espera la red, otra avanza. Funciona con 1 núcleo. | Descarga (E/S) |
| Paralelo | Varias tareas ejecutándose físicamente a la vez en núcleos distintos. Solo acelera cálculo. | Emparejamiento (CPU) |
| Multinúcleo | Característica del hardware que hace posible el paralelismo real. | Ficha del equipo de medición |

La ganancia de la **descarga** viene de la **concurrencia**; la del **emparejamiento**, del **paralelismo**.
Hacer visible esa diferencia es el objetivo central.

---

## 3. Requisitos técnicos (resumen fiel)

### 3.1 Repositorio de juegos
- **≥ 500 juegos** en una BD (SQLite, PostgreSQL, Firebase u otra justificada en un ADR). **Nada escrito en el código.**
- Se puebla **automáticamente** desde ≥ 1 listado público **paginado** (etapa 0). Se puede complementar a mano.
- **≥ 3 plataformas** (PlayStation, Switch, Xbox, PC).
- **≥ 50 casos difíciles** para emparejar: remasters, GOTY/Deluxe/Definitive, secuelas parecidas, números romanos, subtítulos, caracteres especiales.
- Por juego: título canónico, títulos alternativos, plataforma(s), fecha de lanzamiento, **MSRP**.
- Agregar/quitar juegos sin tocar código.

### 3.2 Fuentes de datos (mínimos)

| Tipo | Sitios admitidos | Mínimo |
|---|---|---|
| Descubrimiento (etapa 0) | Listados de Steam, PS Store, Nintendo eShop, Metacritic u OpenCritic | 1 listado con paginación |
| Tiendas de plataforma | Steam, PS Store, Nintendo eShop, Xbox/MS Store, Epic, GOG | ≥ 2 |
| Minoristas | Amazon, Walmart, GameStop, Best Buy, Target | ≥ 1 |
| Total tiendas | Suma de las dos filas anteriores | **4 tiendas**; cada juego publicado con precio en ≥ 2 |
| Calificación | **Metacritic (obligatoria)** + OpenCritic o reseñas de Steam | 2 fuentes |
| Duración | **How Long To Beat (obligatoria)**; IGDB solo como respaldo documentado | 1 |
| Imagen/metadatos | Tiendas, IGDB, RAWG o SteamGridDB | 1 |

- **≥ 3 fuentes por scraping de HTML (no API), de las cuales ≥ 2 son tiendas.** APIs (IGDB, RAWG, Steam) permitidas para el resto y respaldos.
- Otro sitio equivalente es válido si se justifica en un ADR.

**Datos por juego:** precio actual por tienda, precio regular (si el sitio lo muestra), formato (físico/digital),
enlace al producto, **indicador de oferta** (definición propia en un ADR: < MSRP, < precio tachado o combinado),
calificaciones (por plataforma si aplica), HLTB (principal, principal+extras, completista), portada.

### 3.3 Pipeline (Figura 1 del enunciado)

```
0 Descubrir ──▶ 1 Descargar (E/S) ──▶ 2 Parsear ──▶ 3 Emparejar (CPU) ──▶ 4 Persistir ──▶ 5 Publicar
 listados →      tiendas, ratings,     precio,       compara títulos       cada observación   sitio público
 catálogo ≥500   HLTB; más workers     oferta,       entre tiendas;        de precio con      + panel de
                 que núcleos           score, HLTB,  workers ≈ núcleos     su fecha           métricas
                                       imagen
```
- Cada flecha es una **cola acotada**; el diseño fija **workers y tamaño de cola por etapa**.
- La etapa más lenta fija el throughput (analogía con la segmentación del procesador).
- Se pueden unir/dividir etapas con un ADR.

### 3.4 Emparejamiento de títulos (etapa de CPU obligatoria)
- Normalización: minúsculas, sin puntuación, sin sufijos de plataforma/edición.
- Similitud **implementada por el equipo** (Levenshtein, Jaro–Winkler, tokens…). **En Python: Python puro, sin librerías compiladas** (para que el GIL sea observable).
- Cada juego se compara contra **todos** los candidatos de **todas** las tiendas, en versión secuencial y paralela. Si es demasiado rápido para medir, se amplía el conjunto de candidatos (p. ej. catálogo completo de un listado en replay).
- Umbral justificado con **≥ 60 pares validados a mano** (incluye casos difíciles) → reportar **precisión y exhaustividad (recall)**.
- Casos dudosos (cerca del umbral, ediciones especiales, bundles, DLC) se marcan y salen en el panel de métricas.

### 3.5 Tres modos de ejecución del MISMO pipeline (seleccionables por configuración, mismos resultados con los mismos datos)

| Modo | Qué hace | Para qué |
|---|---|---|
| 1. Secuencial | Todo en un hilo, un juego y una fuente a la vez | Línea base `T_sec` |
| 2. Concurrente | Etapas de E/S (descubrir, descargar) con varios workers; resto secuencial | Aislar ganancia de solapar la red |
| 3. Paralelo completo | Modo 2 + emparejamiento repartido entre núcleos | Ganancia adicional del cálculo paralelo |

Mecanismos mínimos:

| Necesidad | C# | Python |
|---|---|---|
| Concurrencia E/S | async/await + Task.WhenAll, Parallel.ForEachAsync | ThreadPoolExecutor o asyncio |
| Paralelismo CPU | Parallel.For/ForEach, PLINQ | ProcessPoolExecutor o multiprocessing |
| Tareas por juego | Parallel.Invoke | executor.submit + as_completed |
| Colas entre etapas | Channel<T> / BlockingCollection<T> acotadas | queue.Queue(maxsize=…) |
| Estado local por hilo | ThreadLocal<T>, localInit/localFinally | threading.local() |
| Límite por sitio | SemaphoreSlim | threading.Semaphore / asyncio.Semaphore |

**Tres niveles de paralelismo con control:** por juego, por fuente (tiendas/ratings/HLTB de un juego en paralelo)
y por tienda (variantes/resultados de una tienda en paralelo). **Obligatorio definir y justificar en ADR:**
máx. workers por etapa, límite de conexiones por dominio y tamaño de cada cola.

### 3.6 Sincronización y robustez
- Timeout en cada solicitud.
- Reintentos con **backoff exponencial + jitter**, con máximo definido.
- **Cola de fallidos** reintentada al final y registrada en el panel de métricas.
- Si una fuente falla, el juego se publica con lo disponible e indica **qué dato está desactualizado y desde cuándo**. Nunca mostrar dato viejo como actual.
- **Experimento de contención (obligatorio):** agregar un resultado compartido (p. ej. conteo de ofertas por plataforma) de 3 formas — **lock global**, **estado local por hilo combinado al final**, **colección concurrente** — medir y explicar. Además, **reproducir una condición de carrera real** sin sincronización y explicar por qué ocurre.

### 3.7 Sitio web público
- URL pública (GitHub Pages, Netlify, Vercel, Firebase…), **no localhost**. Puede ser estático generado por el pipeline.
- Se regenera con **tarea programada** (GitHub Actions, cron…) y muestra la fecha de última actualización.

| Vista | Requisitos |
|---|---|
| Resultados | Filtros: tipo (juego, juego+DLC, DLC, otro), plataforma, formato, tienda. Orden: nombre, mejor precio, % descuento, calificación. Paginación o carga progresiva. |
| Card | Imagen, título, mejor precio entre tiendas, precio regular tachado, % descuento, plataformas, calificación, etiqueta **"mínimo histórico"**. |
| Detalle | Precios de menor a mayor con enlace y **fecha de obtención**; MSRP, calificaciones, HLTB; **gráfico de historial por tienda**. La BD **conserva cada observación** (no sobrescribe). |
| Panel de métricas | Fecha y duración de la última ejecución, tiempo por etapa, solicitudes exitosas/reintentadas/fallidas por sitio, juegos sin emparejar o dudosos, curvas de speedup del informe. |

### 3.8 Scraping responsable (restricción de diseño)
- Revisar y respetar `robots.txt` y términos de uso; **documentarlo**.
- Limitar tasa por dominio; **User-Agent que nombre el proyecto**.
- **Caché local** para no repetir solicitudes.
- Playwright/Selenium solo si hay JS obligatorio, justificado en ADR.
- **PROHIBIDO:** evadir CAPTCHAs, proxies o servicios para burlar bloqueos, iniciar sesión con cuentas personales, recolectar datos personales.
- Un bloqueo permite **sustituir** la fuente por otra de la misma fila (o su API oficial) con ADR + evidencia; no permite abandonar el requisito.

---

## 4. Evaluación experimental

### 4.1 Modo replay
- Mediciones formales **solo en replay**.
- Capturar y guardar localmente las respuestas reales (HTML/JSON) de **todas** las fuentes para **todo** el catálogo.
- Servidor local o adaptador que sirve esas respuestas con **latencia simulada configurable** (fija y con variación aleatoria).
- **Mismo código** en replay y en vivo; solo cambia la fuente de datos.

### 4.2 Diseño del experimento
- Ficha del equipo de medición: CPU, núcleos físicos/lógicos, SMT, RAM, SO, versión del lenguaje.
- Barrido E/S: **1, 2, 4, 8, 16, 32, 64** workers.
- Barrido emparejamiento: **1, 2, 4, …, núcleos lógicos, 2× núcleos lógicos**.
- **≥ 5 repeticiones** por configuración; reportar **mediana** y dispersión (mín–máx o desviación).
- Medir **cada etapa** y el **pipeline completo**, en los **3 modos**.

### 4.3 Métricas
- Speedup absoluto: `S_abs(p) = T_sec / T_par(p)` (beneficio real).
- Speedup relativo: `S_rel(p) = T_par(1) / T_par(p)`; eficiencia `E(p) = S_rel(p) / p`.
- `T_par(1) − T_sec` = costo del andamiaje paralelo.
- Amdahl: `S(p) = 1 / (f + (1 − f)/p)`.
- Karp–Flatt: `e = (1/S_rel(p) − 1/p) / (1 − 1/p)`.

Tabla mínima por etapa (Anexo 2): `Workers | Mediana (s) | Mín–máx (s) | S_abs | S_rel | E | e (Karp–Flatt)`.

### 4.4 Las 8 preguntas que el informe debe responder con datos propios
1. ¿Por qué la descarga sigue mejorando con más workers que núcleos y el emparejamiento no? ¿Qué significa E > 1 en la descarga?
2. ¿Qué etapa es el cuello de botella y cómo cambia al variar la latencia simulada?
3. ¿Cuál es la fracción serial estimada y de dónde viene en el código?
4. ¿Qué pasa al superar los núcleos lógicos? ¿Qué efecto tiene SMT?
5. Python: ThreadPoolExecutor vs ProcessPoolExecutor en el emparejamiento, ¿por qué? / C#: Parallel.ForEach vs Task.WhenAll por etapa.
6. ¿Cuánto cuesta el andamiaje paralelo (T_par(1) − T_sec) y de dónde viene?
7. ¿Qué tan cerca está una ejecución en vivo de lo que predice el replay?
8. ¿Qué tanto se acercaron las predicciones del Hito 1 a las mediciones y qué supuesto falló?

---

## 5. Conducción, entregables y evaluación

### 5.1 Roles (cada quien responde por su área, pero **todos** deben poder explicar todo)

| Rol | Responde por | Persona |
|---|---|---|
| Arquitectura y sincronización | Pipeline, colas, límites de concurrencia, ADRs técnicos, experimento de contención | _por definir_ |
| Rendimiento y experimentación | Modo replay, banco de pruebas, barridos, speedup y Karp–Flatt, informe técnico | _por definir_ |
| Datos y producto | Repositorio, fuentes y descubrimiento, emparejamiento, sitio público, panel de métricas, actualización programada | _por definir_ |

### 5.2 Artefactos de conducción (rutas exigidas)
- `docs/acta.md` — roles, comunicación, criterio de decisión, resolución de conflictos.
- Tablero (GitHub Projects/Trello) con tareas, responsables y fechas, actualizado las 3 semanas.
- `docs/seguimiento.md` — ≥ 2 reuniones/semana, ~5 líneas: decisiones, bloqueos, acciones.
- `docs/adr/NNN-titulo.md` — un ADR por decisión con alternativas reales (lenguaje, BD, oferta, límites de concurrencia, sustitución de fuentes, hosting, algoritmo de emparejamiento…).
- `docs/cambios-diseno.md` — cada desviación respecto al diseño del H1 y su motivo (cambiar no se penaliza; no justificar sí).
- `docs/bitacora-ia.md` — qué se pidió, qué se obtuvo, qué se aceptó/modificó y por qué. **Entrada obligatoria de error real:** un defecto de concurrencia producido por la IA (carrera, interbloqueo, sobresuscripción, mal uso del GIL), cómo se detectó, causa y corrección.
- **Historial de Git** con commits de los 3 integrantes distribuidos en las 3 semanas. Commits masivos al final = evidencia insuficiente.

### 5.3 Plantilla ADR (Anexo 1, ≤ media página)
`Título y fecha` (ADR-003 · Límite de conexiones por dominio · fecha) · `Contexto` · `Alternativas` (≥ 2 reales con pros/contras) · `Decisión` (1–2 frases) · `Consecuencias` (qué se gana, qué se pierde, qué medir para confirmar) · `Estado` (propuesta / aceptada / reemplazada por ADR-X).

### 5.4 Hitos

| Hito | Cuándo | Contenido |
|---|---|---|
| **H1 · Diseño (NO revisable, 15 %)** | Fin semana 1 | Acta, tablero, diagrama del pipeline con workers/colas/límites, ADRs iniciales, esquema de BD, fuentes por tipo, definición de oferta, **predicciones de rendimiento hechas SIN IA** |
| H2 · Avance funcional | Fin semana 2 | 500 juegos poblados, replay con catálogo completo, 3 modos funcionando, sitio publicado con datos reales, primer barrido y experimento de contención |
| H3 · Entrega final | Fin semana 3 | Barridos completos, emparejamiento validado, historial y panel de métricas, informe técnico, bitácora de IA, defensa oral |

### 5.5 Entregables
Repositorio con README (replay/vivo y los 3 modos) y tarea programada activa · Sitio público · Informe técnico
(ficha, gráficos, 8 respuestas, contención, validación del emparejamiento, ADRs, cambios de diseño) ·
Evidencia de conducción · Defensa oral.

### 5.6 Rúbrica

| # | Criterio | Peso | Cuándo |
|---|---|---|---|
| 1a | Diseño arquitectónico + ADRs iniciales + predicciones (no revisable) | 15 % | H1 |
| 1b | Coherencia diseño ↔ implementación y registro de cambios | 5 % | Final |
| 2 | 3 modos, mecanismos de paralelismo/sincronización, contención | 15 % | H2 y final |
| 3 | Emparejamiento: algoritmo propio, umbral validado, versión paralela, dudosos | 10 % | Final |
| 4 | Fuentes, robustez, scraping responsable | 10 % | Final |
| 5 | Evaluación experimental (replay, barridos, métricas, respuestas) | **20 %** | Final |
| 6 | Sitio público completo + actualización programada | 10 % | Final |
| 7 | Conducción del equipo | 10 % | 3 semanas |
| 8 | Bitácora de IA con error real | 5 % | Final |

**Factor individual 0,6–1,0** asignado en la defensa: quien no explica su área no recibe la nota completa.

### 5.7 Defensa oral (20 min)
1. Demo en vivo (5 min): sitio público, panel de métricas, pipeline en replay.
2. **Predicción antes de ejecutar** (5 min): el profesor elige una configuración no medida (workers o latencia); el equipo predice tiempo y speedup, lo justifica y ejecuta.
3. Preguntas por rol (10 min): cada quien sobre su área y ≥ 1 ajena (p. ej. "¿qué pasa si quito este semáforo?", "¿por qué ese tamaño de cola?", "¿de dónde sale la fracción serial?").

### 5.8 Extras (hasta +10, solo con todo lo obligatorio completo)
Procesamiento paralelo de imágenes (+5) · Lista de deseos con alertas (+3) · Misma etapa con 2 mecanismos medidos (+2).

---

## 6. Reglas para Claude en este proyecto

1. **No generar predicciones de rendimiento para el Hito 1.** El enunciado exige que se hagan sin IA. Si alguien las pide, Claude se niega amablemente y, como mucho, explica conceptos (Amdahl, latencia vs throughput) sin números del sistema.
2. **Todo uso relevante de IA se registra** en `docs/bitacora-ia.md` (usar `/bitacora-ia`). Nunca inventar la entrada de "error real": debe ser un defecto que realmente ocurrió.
3. **Scraping responsable siempre:** nada de evadir CAPTCHAs, proxies, rotación de User-Agent para esconderse, login con cuentas personales ni datos personales. Ante un bloqueo → proponer sustitución + ADR.
4. **Emparejamiento en Python puro** (si el lenguaje es Python): no usar rapidfuzz, python-Levenshtein, jellyfish ni similares en la etapa medida.
5. **Los 3 modos deben dar resultados idénticos** con los mismos datos. Cualquier cambio en el pipeline debe preservar esa propiedad.
6. **Las mediciones formales se hacen en replay**, nunca contra sitios en vivo.
7. **Cada decisión con alternativas reales → ADR** (usar `/adr`). Cada desviación del diseño del H1 → `docs/cambios-diseno.md`.
8. **Explicar, no solo entregar:** al generar código de concurrencia, explicar por qué es correcto (qué carrera evita, qué pasa si se quita el lock/semáforo), porque cada integrante será interrogado en la defensa.
9. Commits pequeños y frecuentes por cada integrante; no hacer commits masivos en nombre de otra persona.

---

## 7. Estado actual (ACTUALIZAR SIEMPRE)

**Fecha de última actualización:** 2026-11-10
**Hito en curso:** H1 · Diseño (semana 1)

| Decisión | Estado | ADR |
|---|---|---|
| Lenguaje | **Aceptada: Python 3.14** (compilación normal con GIL; ejecutar con `py -3.14` en Windows) | ADR-001 |
| Cliente HTTP (urllib vs httpx) | Propuesta: urllib de la biblioteca estándar detrás de una interfaz `Transporte` | ADR-002 |
| Base de datos | Propuesta: SQLite, escrita solo por la etapa Persistir (un hilo); catálogo base versionado como archivo de texto | ADR-003 |
| Definición de "oferta" | Pendiente | — |
| Fuentes por tipo de dato | Pendiente — requiere spikes | — |
| Límites de concurrencia (workers, colas, por dominio) | Pendiente | — |
| Modo replay: servidor vs adaptador | Pendiente | — |
| Algoritmo de emparejamiento | Pendiente | — |
| Hosting + tarea programada | Pendiente | — |
| Almacenamiento de capturas replay y BD (Git LFS / Releases / BD en la nube) | Pendiente — preferida: GitHub Releases | — |
| Asignación de roles | Pendiente | `docs/acta.md` |

**Repositorio Git:** https://github.com/Emminox/web-scraping (rama `main`). Falta confirmar que el equipo
fue invitado y que `main` está protegida (pull request con 1 aprobación).
**Commits y PRs:** NO agregar `Co-Authored-By: Claude` ni "Generated with Claude Code" (acordado el
2026-11-11). El uso de IA se declara en `docs/bitacora-ia.md`.
**Estructura `docs/`:** creada con plantillas (acta, seguimiento, cambios de diseño, bitácora de IA, ADRs).
**URL del sitio:** aún no existe. **Tablero:** aún no existe.

**Código existente (rama `feat/base-proyecto`):**
- `config/config.toml` + `radar/config.py`: configuración validada (modo, fuente vivo/replay, límites de red
  PROVISIONALES, latencia simulada, rutas).
- `radar/red/`: `ClienteHttp` único para todo el proyecto — robots.txt, User-Agent del proyecto, semáforo e
  intervalo por dominio, timeout, reintentos con backoff exponencial + jitter (y Retry-After), almacén de
  capturas en `datos/capturas/` (caché en vivo = fuente del replay), latencia simulada en replay, métricas
  por dominio. Errores tipados: `ErrorTemporal`, `ErrorDefinitivo`, `BloqueadoPorRobots`, `SinCaptura`,
  `ReintentosAgotados` (este último alimentará la cola de fallidos).
- `radar/herramientas/explorar_fuente.py`: herramienta para los spikes de fuentes; guarda fixtures en `fixtures/`.
- `radar/bd/`: esquema SQLite versión 1 (propuesta, ver `docs/esquema-bd.md`) y `abrir_bd()`, que activa
  claves foráneas, WAL y aplica el esquema. Observaciones de precio/calificación/duración son SOLO INSERT
  (trigger). Vistas `v_ultimo_precio` (con marca de desactualizado) y `v_minimo_historico`. Dinero en centavos.
- `catalogo/*.json` es la fuente de verdad del catálogo (formato en `catalogo/README.md`); hoy está VACÍO:
  lo llenarán la etapa 0 (`descubiertos.json`) y el equipo (`casos-dificiles.json`, `manual.json`).
  `radar/catalogo.py` lo valida (reporta todos los errores juntos) y lo sincroniza con la base en una sola
  transacción: quitar un juego del archivo lo desactiva sin borrar su historial. Comando:
  `py -3.14 -m radar.herramientas.cargar_catalogo` (muestra cuánto falta para 500 juegos / 3 plataformas / 50 casos).
- `radar/pipeline/` (rama `feat/esqueleto-pipeline`): orquestador de las 6 etapas con colas acotadas y los
  3 modos (`ejecutar_pipeline(definicion, modo, config.pipeline)`). Secuencial = bucles sin hilos (T_sec);
  concurrente = hilos en Descubrir/Descargar; paralelo = además ProcessPoolExecutor (o hilos) en Emparejar.
  Las etapas son funciones de una `DefinicionPipeline` (aún solo falsas, en `tests/pipeline_falso.py`).
  Límites provisionales en `[pipeline]` de config.toml. Diseño y argumentos de corrección: `docs/pipeline.md`.
- `tests/`: 59 pruebas con `unittest` (sin internet), incluida la de equivalencia de los 3 modos.
  Ejecutar: `py -3.14 -m unittest -v`.
- Aún NO existe: etapas reales (descubrimiento, descarga, parsers, emparejamiento, persistencia, sitio),
  reintento final de la cola de fallidos, guardado de métricas por ejecución.

---

## 8. Plan de ejecución propuesto (pendiente de aprobar por el equipo)

### Semana 1 — Hito 1 (diseño; no revisable, 15 %)
1. **Arranque (día 1):** reunión de kickoff → `docs/acta.md`, roles, tablero en GitHub Projects, repo creado, ADR-001 lenguaje.
2. **Spikes de fuentes (días 1–3), repartidos entre los 3:** por cada sitio candidato revisar robots.txt y términos, si el HTML trae los datos o depende de JS, si hay bloqueo, paginación y estructura de URL. Guardar 2–3 páginas de muestra por sitio (servirán de fixtures de parsers y semilla del replay). Resultado: tabla de fuentes elegidas + respaldo por fila + ADRs.
3. **Diseño (días 3–4):** diagrama del pipeline con workers/colas/límites por etapa, esquema de BD (observaciones de precio append-only), definición de oferta, algoritmo de emparejamiento, estrategia replay, hosting.
4. **Predicciones SIN IA (día 4–5):** cada integrante predice por separado y luego se consolidan, escribiendo los **supuestos** explícitos (en la semana 3 se evalúa cuál falló).
5. Entregar H1.

### Semana 2 — Hito 2 (avance funcional)
6. Etapa 0: descubrimiento paginado → 500+ juegos en BD; curar los 50 casos difíciles.
7. Capa de acceso a datos única (vivo / caché / replay) con timeout, reintentos con backoff+jitter, límite por dominio y cola de fallidos.
8. **Captura completa para replay lo antes posible** (es lenta por el rate limit y los sitios pueden bloquear).
9. Parsers por fuente con pruebas sobre las páginas guardadas.
10. Pipeline con colas acotadas y los 3 modos + prueba automática de que los 3 dan el mismo resultado.
11. Emparejamiento v1, persistencia, sitio estático v1 publicado, tarea programada.
12. Primer barrido + experimento de contención (incluida la carrera reproducida).

### Semana 3 — Hito 3 (final)
13. Barridos completos automatizados (5 reps × configuraciones × 3 modos × etapas) en **una sola máquina fija**.
14. Validación del emparejamiento (≥ 60 pares, precisión/recall), casos dudosos en el panel.
15. Historial de precios con gráfico, panel de métricas con curvas de speedup.
16. Informe técnico (8 preguntas), bitácora de IA, cambios de diseño.
17. Ensayos de defensa: simulacro de predicción en vivo y preguntas cruzadas por rol (`/defensa`).

---

## 9. Skills del proyecto (ver `Agentes/README.md`)

| Comando | Para qué |
|---|---|
| `/adr <tema>` | Crear un ADR con la plantilla del Anexo 1 |
| `/revision-concurrencia [ruta]` | Revisión de código enfocada en carreras, interbloqueos, sobresuscripción, GIL, colas y límites |
| `/fuente-nueva <sitio>` | Ficha de evaluación de una fuente (robots, ToS, HTML/JS, bloqueos) + ADR si es sustitución |
| `/medicion <archivo>` | Analizar mediciones: tabla del Anexo 2, speedup, eficiencia, Amdahl, Karp–Flatt |
| `/validar-emparejamiento` | Precisión/recall del emparejamiento con el set de validación y casos dudosos |
| `/bitacora-ia` | Registrar una entrada en la bitácora de IA |
| `/reunion` | Registrar una reunión en `docs/seguimiento.md` (y cambios de diseño) |
| `/defensa <rol>` | Simulacro de defensa oral: preguntas por rol sin dar las respuestas |
