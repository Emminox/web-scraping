---
name: bitacora-ia
description: Registra una entrada en la Bitácora de IA del proyecto (docs/bitacora-ia.md) — qué se pidió, qué se obtuvo, qué se aceptó, qué se modificó y por qué — incluida la entrada obligatoria de error real de concurrencia. Usar al final de cada sesión de trabajo relevante con Claude.
argument-hint: [resumen opcional | error-real]
disable-model-invocation: true
---

# Entrada de Bitácora de IA

Argumento: **$ARGUMENTS**

## Pasos
1. Si `docs/bitacora-ia.md` no existe, créalo con un encabezado breve y una nota: "Formato: una entrada por uso relevante; la entrada de error real está marcada con [ERROR REAL]".
2. Reconstruye a partir de **esta sesión** (no de suposiciones) qué se le pidió a la IA y qué produjo. Muestra el borrador al usuario y **pregúntale** lo que solo él/ella sabe:
   - ¿Qué partes aceptó tal cual, cuáles modificó y por qué?
   - ¿Qué verificó (pruebas, lectura, medición) antes de aceptarlo?
   - ¿Quién del equipo es responsable de poder explicarlo en la defensa?
3. Agrega la entrada **al final** del archivo (nunca reescribas entradas anteriores):

```markdown
### <AAAA-MM-DD> · <Integrante> · <Tema corto>
- **Herramienta:** Claude Code (<modelo>)
- **Se pidió:** …
- **Se obtuvo:** …
- **Se aceptó:** …
- **Se modificó y por qué:** …
- **Cómo se verificó:** …
- **Archivos/commits:** …
```

4. Si el argumento es `error-real` o la sesión incluyó un defecto de concurrencia **introducido por la IA** (condición de carrera, interbloqueo, sobresuscripción de hilos, uso incorrecto del GIL), usa esta variante marcada `[ERROR REAL]`:

```markdown
### [ERROR REAL] <AAAA-MM-DD> · <Integrante> · <Tipo de defecto>
- **Qué generó la IA:** (fragmento o descripción y commit)
- **Síntoma observado:** …
- **Cómo se detectó:** (prueba, revisión con /revision-concurrencia, medición anómala, …)
- **Causa raíz:** (intercalado de hilos concreto / por qué el GIL no protegía / por qué se sobresuscribió)
- **Corrección:** (commit)
- **Lección:** …
```

## Reglas
- **Nunca inventes** un error real ni lo "fabriques" a propósito para llenar la bitácora: debe haber ocurrido y estar en el historial de Git.
- No registres conversaciones triviales; sí todo código, diseño o texto del informe que haya salido de la IA.
- Las predicciones de rendimiento del Hito 1 **no** se hacen con IA; si aparecen en la sesión, señálalo.
