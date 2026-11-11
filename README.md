# Radar de Ofertas Multinúcleo

III Proyecto Programado · IC-3101 Arquitectura de Computadoras · TEC Campus San Carlos · II Semestre 2026

Sitio web público de ofertas de videojuegos alimentado por un pipeline de web scraping
**secuencial, concurrente y paralelo**, para medir cuándo y por qué el paralelismo acelera un sistema
en una arquitectura multinúcleo.

> **Estado:** Hito 1 (diseño). Todavía no hay código.

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
Agentes/            Skills de Claude Code del proyecto (fuente; ver Agentes/README.md)
.claude/skills/     Copia activa de las skills (no editar directamente)
Contexto actual/    Contexto compartido para el equipo y para Claude
Requerimientos y guías/  Enunciado y modelo de referencia
docs/               Acta, seguimiento, ADRs, cambios de diseño, bitácora de IA
```

## Cómo ejecutar
_Pendiente: modo vivo / modo replay y los tres modos de ejecución (secuencial, concurrente, paralelo)._

## Flujo de trabajo con Git
- `main` siempre estable; cada tarea en una rama `feat/<tema>`, `fix/<tema>` o `docs/<tema>`.
- Pull request revisado por **otro** integrante antes de fusionar (`/code-review` y `/revision-concurrencia` ayudan).
- Commits pequeños y frecuentes de los tres integrantes durante las tres semanas.
