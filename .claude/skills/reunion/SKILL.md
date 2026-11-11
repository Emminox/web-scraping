---
name: reunion
description: Registra una reunión del equipo en docs/seguimiento.md (decisiones, bloqueos, acciones con responsable y fecha) y, si hubo desviaciones del diseño del Hito 1, en docs/cambios-diseno.md. Usar después de cada reunión (mínimo dos por semana).
argument-hint: [notas rápidas de la reunión]
disable-model-invocation: true
---

# Registro de reunión

Notas: **$ARGUMENTS**

## Pasos
1. Si faltan datos, pregunta: fecha, asistentes, decisiones, bloqueos y acciones (con responsable y fecha). No inventes asistentes ni acuerdos.
2. Agrega al final de `docs/seguimiento.md` (créalo si no existe) una entrada de ~5 líneas:

```markdown
### Reunión <N> · <AAAA-MM-DD> · Semana <1|2|3>
- **Asistentes:** …
- **Decisiones:** … (enlazar ADR si aplica)
- **Bloqueos:** …
- **Acciones:** <tarea> → <responsable>, <fecha>; …
- **Estado del hito:** …
```

3. Si alguna decisión **cambia el diseño entregado en el Hito 1**, agrega en `docs/cambios-diseno.md`: fecha · qué cambió · motivo (con evidencia/medición) · ADR relacionado. Si la decisión tiene alternativas reales, sugiere `/adr`.
4. Revisa el ritmo: si en la semana actual hay menos de 2 reuniones registradas, avísalo.
5. Sugiere qué tarjetas del tablero (GitHub Projects) mover o crear a partir de las acciones.
6. Si cambió el estado del proyecto, actualiza la sección "7. Estado actual" de `Contexto actual/CONTEXTO_PROYECTO.md`.
