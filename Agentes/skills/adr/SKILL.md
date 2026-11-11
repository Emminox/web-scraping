---
name: adr
description: Crea o actualiza un ADR (Architecture Decision Record) del proyecto Radar de Ofertas con la plantilla del Anexo 1 del enunciado. Usar cuando el equipo toma una decisión con alternativas reales (lenguaje, BD, definición de oferta, límites de concurrencia, sustitución de fuentes, hosting, algoritmo de emparejamiento, replay, etc.).
argument-hint: <tema de la decisión> [--reemplaza NNN]
---

# Crear un ADR

Tema solicitado: **$ARGUMENTS**

## Pasos
1. Lista `docs/adr/` para obtener el siguiente número (`NNN` con 3 dígitos, empezando en 001). Si la carpeta no existe, créala.
2. Antes de redactar, pregunta al usuario lo que falte para que el ADR sea honesto:
   - ¿Qué problema o restricción obliga a decidir? ¿Qué datos tenían en ese momento (spike, medición, bloqueo observado)?
   - ¿Cuáles son las **al menos dos alternativas reales** que consideraron?
   - ¿Ya está decidido o es una propuesta?
   No inventes datos, mediciones ni evidencia. Si no hay datos, el ADR lo dice.
3. Crea `docs/adr/NNN-titulo-en-kebab-case.md` con exactamente esta estructura (media página o menos):

```markdown
# ADR-NNN · <Título> · <AAAA-MM-DD>

## Contexto
<Qué obliga a decidir. Datos disponibles al momento.>

## Alternativas
1. **<Opción A>** — Ventajas: … / Desventajas: …
2. **<Opción B>** — Ventajas: … / Desventajas: …

## Decisión
<La opción elegida en una o dos frases.>

## Consecuencias
- Se gana: …
- Se pierde: …
- Qué hay que medir para confirmar la decisión: …

## Estado
Propuesta | Aceptada | Reemplazada por ADR-XXX
```

4. Si el argumento incluye `--reemplaza NNN`, cambia el estado del ADR anterior a "Reemplazada por ADR-<nuevo>" y agrega una línea en `docs/cambios-diseno.md` con fecha, qué cambió respecto al diseño del Hito 1 y por qué.
5. Si el ADR es una **sustitución de fuente** por bloqueo, exige evidencia (código HTTP, captura del bloqueo, línea de robots.txt o cláusula de ToS) y que la nueva fuente sea de la **misma fila** de la tabla de fuentes del enunciado (o su API oficial).
6. Actualiza la tabla de la sección **"7. Estado actual"** en `Contexto actual/CONTEXTO_PROYECTO.md`.
7. Recuerda al usuario registrar el uso de IA con `/bitacora-ia` si el ADR se redactó con ayuda de Claude.

## Criterios de calidad
- Las consecuencias deben incluir **qué medir** para validar la decisión (esto se evalúa en la coherencia diseño ↔ implementación).
- Para límites de concurrencia: el ADR debe fijar números concretos (workers por etapa, conexiones por dominio, tamaño de cada cola) y su justificación.
- Lenguaje claro en español; nada de relleno.
