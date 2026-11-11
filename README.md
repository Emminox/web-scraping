# Radar de Ofertas Multinúcleo

III Proyecto Programado · IC-3101 Arquitectura de Computadoras · TEC Campus San Carlos · II Semestre 2026

Sitio web público de ofertas de videojuegos alimentado por un pipeline de web scraping
**secuencial, concurrente y paralelo**, para medir cuándo y por qué el paralelismo acelera un sistema
en una arquitectura multinúcleo.

> **Estado:** sistema funcional de punta a punta: descubre juegos en Metacritic, consulta 4 tiendas
> (Steam, Nintendo eShop, GOG, Best Buy), empareja títulos, guarda el historial en SQLite y genera el sitio,
> en los tres modos y en vivo o replay. Pendiente: duración (ADR-007), validación del umbral de
> emparejamiento, barridos de medición (después de entregar las predicciones del Hito 1).

## Enlaces
- Repositorio: https://github.com/Emminox/web-scraping
- Sitio público: https://emminox.github.io/web-scraping/ (cuando se active GitHub Pages, ver ADR-010)
- Tablero: _pendiente_
- Contexto completo del proyecto: [`Contexto actual/CONTEXTO_PROYECTO.md`](Contexto%20actual/CONTEXTO_PROYECTO.md)
- Enunciado oficial: [`Requerimientos y guías/`](Requerimientos%20y%20guías/)

## Equipo y roles
| Rol | Integrante |
|---|---|
| Arquitectura y sincronización | _por definir_ |
| Rendimiento y experimentación | _por definir_ |
| Datos y producto | _por definir_ |

## Estructura
```
config/config.toml  Configuración: modo, fuente (vivo/replay), límites de red, latencia simulada, rutas
radar/              Código del proyecto
  config.py         Carga y valida config.toml
  red/              Capa de red: robots.txt, límites por dominio, reintentos, almacén de capturas, métricas
  bd/               Base de datos SQLite: esquema.sql y conexión (ADR-003; explicado en docs/esquema-bd.md)
  catalogo.py       Lee, valida y carga el catálogo manual de juegos en la base
  pipeline/         Orquestador: 6 etapas con colas acotadas y los 3 modos (diseño en docs/pipeline.md)
  fuentes/          Parsers de Metacritic, Steam, Nintendo eShop, GOG y Best Buy (ADR-004)
  emparejamiento/   Normalización y similitud de títulos en Python puro (ADR-006)
  persistencia.py   Etapa Persistir: único escritor de SQLite
  sitio/            Etapa Publicar: genera el sitio estático (plantillas en sitio/estatico/)
  ejecucion.py      Une todo: ejecución completa, reintento final de fallidos y métricas
  herramientas/     Comandos: explorar_fuente.py (spikes) y cargar_catalogo.py
catalogo/           Juegos agregados a mano en JSON (los demás los descubre la etapa 0)
.github/workflows/  Tarea programada diaria que actualiza y publica el sitio (ADR-010)
tests/              Pruebas automáticas (no usan internet)
fixtures/           Páginas de ejemplo guardadas en los spikes (entradas de prueba de los parsers)
datos/capturas/     Respuestas descargadas: caché en vivo y fuente del modo replay (no se sube a Git)
Agentes/            Skills de Claude Code del proyecto (fuente; ver Agentes/README.md)
.claude/skills/     Copia activa de las skills (no editar directamente)
Contexto actual/    Contexto compartido para el equipo y para Claude
Requerimientos y guías/  Enunciado y modelo de referencia
docs/               Acta, seguimiento, ADRs, cambios de diseño, bitácora de IA
```

## Requisitos
- **Python 3.14** (última versión 3.14.x, compilación normal con GIL; ver ADR-001). Todo el equipo, GitHub
  Actions y la máquina de medición usan la misma versión. Por ahora no hay dependencias externas (ADR-002).
- En Windows, `python` puede apuntar a otra versión instalada. Usen el lanzador `py -3.14` (comprobar con
  `py -3.14 --version`). En macOS/Linux, `python3.14`.

## Cómo ejecutar
Todos los comandos se ejecutan desde la raíz del repositorio.

Correr las pruebas:
```bash
py -3.14 -m unittest -v
```

Explorar una fuente candidata (spike del Hito 1): revisa robots.txt, hace UNA solicitud con el
User-Agent del proyecto, detecta señales de bloqueo o de datos embebidos y guarda la página en `fixtures/`:
```bash
py -3.14 -m radar.herramientas.explorar_fuente "https://sitio.com/pagina" --buscar "59.99" --nombre ficha-juego
```

Cargar el catálogo de `catalogo/*.json` en la base y ver cuánto falta para los mínimos del enunciado:
```bash
py -3.14 -m radar.herramientas.cargar_catalogo
```

**Ejecutar el Radar completo** (etapas 0 a 5). El modo y la fuente de datos salen de `config/config.toml` o
de la línea de comandos:
```bash
py -3.14 -m radar ejecutar --modo concurrente --fuente vivo
```
- `--modo secuencial | concurrente | paralelo`: los tres modos del enunciado (mismos resultados).
- `--fuente vivo`: descarga de los sitios y guarda cada respuesta en `datos/capturas/`.
- `--fuente replay`: usa esas capturas con latencia simulada (`[replay]` en la configuración); escribe en
  `datos/radar-replay.sqlite` y `sitio-replay/` para no mezclar datos.
- Prueba rápida y liviana: `--plataformas pc --paginas 1 --por-pagina 5`.

Ver el sitio generado en el navegador (necesita un servidor local porque carga los datos con `fetch`):
```bash
py -3.14 -m http.server 8765 --directory sitio
```
y abrir http://localhost:8765. Para regenerar solo el sitio desde la base: `py -3.14 -m radar sitio`.

## Flujo de trabajo con Git
- `main` siempre estable; cada tarea en una rama `feat/<tema>`, `fix/<tema>` o `docs/<tema>`.
- Pull request revisado por **otro** integrante antes de fusionar (`/code-review` y `/revision-concurrencia` ayudan).
- Commits pequeños y frecuentes de los tres integrantes durante las tres semanas.
