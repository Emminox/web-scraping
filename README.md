# Radar de Ofertas Multinúcleo

III Proyecto Programado · IC-3101 Arquitectura de Computadoras · TEC Campus San Carlos · II Semestre 2026

Sitio web público de ofertas de videojuegos alimentado por un pipeline de web scraping
**secuencial, concurrente y paralelo**, para medir cuándo y por qué el paralelismo acelera un sistema
en una arquitectura multinúcleo.

> **Estado:** Hito 1 (diseño). Existe la base: configuración, capa de red responsable y herramienta para
> explorar fuentes. El pipeline (etapas, colas y los tres modos) se implementa en la semana 2.

## Enlaces
- Sitio público: _pendiente_
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
  herramientas/     Utilidades de línea de comandos (explorar_fuente.py para los spikes)
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
- Python 3.12 o superior (ver ADR-001). Por ahora no hay dependencias externas (ADR-002).

## Cómo ejecutar
Todos los comandos se ejecutan desde la raíz del repositorio.

Correr las pruebas:
```bash
python -m unittest -v
```

Explorar una fuente candidata (spike del Hito 1): revisa robots.txt, hace UNA solicitud con el
User-Agent del proyecto, detecta señales de bloqueo o de datos embebidos y guarda la página en `fixtures/`:
```bash
python -m radar.herramientas.explorar_fuente "https://sitio.com/pagina" --buscar "59.99" --nombre ficha-juego
```

_Pendiente (semana 2): ejecutar el pipeline en modo vivo / replay y en los tres modos (secuencial, concurrente, paralelo)._

## Flujo de trabajo con Git
- `main` siempre estable; cada tarea en una rama `feat/<tema>`, `fix/<tema>` o `docs/<tema>`.
- Pull request revisado por **otro** integrante antes de fusionar (`/code-review` y `/revision-concurrencia` ayudan).
- Commits pequeños y frecuentes de los tres integrantes durante las tres semanas.
