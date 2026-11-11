# Agentes y skills del proyecto

Aquí viven las **skills especializadas** para el Radar de Ofertas Multinúcleo. `Agentes/skills/` es la
**fuente**: se editan aquí. Claude Code solo descubre skills en `.claude/skills/` (en la raíz del repo), así que
después de editar una skill hay que sincronizar la copia activa (comando abajo). Las dos carpetas se suben a Git,
de modo que al clonar el repo el Claude de cada integrante ya tiene los comandos.

## Comandos del proyecto

| Comando | Cuándo usarlo | Responsable natural |
|---|---|---|
| `/adr <tema>` | Cada decisión con alternativas reales (lenguaje, BD, oferta, límites, fuentes, hosting, emparejamiento). `--reemplaza NNN` para cambiar una decisión. | Todos (técnicos: Arquitectura) |
| `/revision-concurrencia [ruta]` | Antes de abrir o aprobar un PR que toque pipeline, colas, fetcher, emparejamiento o contención. | Arquitectura y sincronización |
| `/fuente-nueva <sitio>` | Spikes de fuentes (H1) o cuando un sitio bloquea y hay que sustituirlo. | Datos y producto |
| `/medicion <archivo>` | Después de cada barrido: tabla del Anexo 2, speedup, eficiencia, Karp–Flatt y lectura para las 8 preguntas. | Rendimiento y experimentación |
| `/validar-emparejamiento` | Al ajustar similitud/umbral: precisión, exhaustividad y casos dudosos. | Datos y producto |
| `/bitacora-ia` · `/bitacora-ia error-real` | Al cerrar una sesión de trabajo con IA. | Todos |
| `/reunion <notas>` | Después de cada reunión (≥ 2 por semana). | Quien modere |
| `/defensa <arquitectura\|rendimiento\|datos\|prediccion\|todo>` | Semana 3: simulacro de defensa oral y de predicción en vivo. | Todos |

`/bitacora-ia`, `/reunion` y `/defensa` solo se ejecutan cuando ustedes las invocan (Claude no las dispara solo).
Las demás también pueden activarse automáticamente cuando Claude detecta que aplican.

## Comandos integrados de Claude Code que conviene usar

| Comando | Para qué |
|---|---|
| `/code-review` | Revisión general de bugs del diff actual o de un PR (complementa a `/revision-concurrencia`). Acepta nivel: `/code-review high`. `--fix` aplica correcciones. |
| `/simplify` | Limpieza de calidad (duplicación, simplificación) del código cambiado; no busca bugs. |
| `/security-review` | Revisión de seguridad de los cambios pendientes (útil para la tarea programada y secretos de GitHub Actions). |
| `/init` | Regenera un `CLAUDE.md`; **no lo usen** sin revisar, porque ya existe uno curado. |
| `/engineering:testing-strategy` | Diseñar las pruebas (equivalencia de los 3 modos, parsers con fixtures, estrés de colas). |
| `/engineering:architecture` | Discutir una decisión antes de escribir el ADR. |
| `/engineering:debug` | Sesión estructurada de depuración (cuelgues, carreras). |

> Nota: no existe una skill llamada "ponytail" instalada ni en el catálogo de plugins. Para revisión de código
> usen `/code-review` (general) + `/revision-concurrencia` (lo que el profesor va a preguntar).

## Sincronizar después de editar una skill

Desde la raíz del repo (Git Bash):

```bash
mkdir -p .claude/skills && cp -r Agentes/skills/. .claude/skills/
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force .claude\skills | Out-Null; Copy-Item -Recurse -Force Agentes\skills\* .claude\skills\
```

Regla del equipo: **nunca editar `.claude/skills/` directamente**; editar en `Agentes/skills/` y sincronizar en el mismo commit.

## Estructura de una skill
```
Agentes/skills/<nombre>/SKILL.md   ← frontmatter (name, description, argument-hint) + instrucciones
```
La `description` decide cuándo Claude la usa sola: escríbanla con las palabras que ustedes usarían al pedirla.
