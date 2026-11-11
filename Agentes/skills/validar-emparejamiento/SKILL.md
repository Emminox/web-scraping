---
name: validar-emparejamiento
description: Valida el emparejamiento de títulos del Radar de Ofertas — revisa el conjunto de validación (≥60 pares manuales con casos difíciles), calcula precisión y exhaustividad por umbral, propone el umbral justificado y lista los casos dudosos (cerca del umbral, ediciones, bundles, DLC) para el panel de métricas. Usar al ajustar el algoritmo de similitud o el umbral.
argument-hint: [archivo del set de validación] [archivo de resultados]
---

# Validación del emparejamiento

Entradas: **$ARGUMENTS**

## 1. Revisar el conjunto de validación
- ¿Tiene **≥ 60 pares revisados manualmente** (título del repositorio ↔ título de tienda ↔ ¿es el mismo juego? sí/no)?
- ¿Incluye los **casos difíciles** del repositorio? Debe haber de cada tipo: remasterizaciones, GOTY/Deluxe/Definitive, secuelas con nombres parecidos, números romanos vs arábigos, subtítulos, caracteres especiales/acentos/marcas ™®, sufijos de plataforma, bundles y DLC.
- ¿Hay **negativos** suficientes (pares parecidos que NO son el mismo juego)? Sin negativos la precisión no significa nada.
- ¿Quién etiquetó y con qué criterio (p. ej. "Deluxe Edition" ≡ juego base o no)? Ese criterio debe estar en el ADR del algoritmo.

## 2. Revisar el algoritmo (si hay código)
- Normalización: minúsculas, sin puntuación, sin sufijos de plataforma/edición; ¿romanos ↔ arábigos?; ¿Unicode normalizado?
- Similitud **implementada por el equipo** y, en Python, **en Python puro** (sin rapidfuzz/Levenshtein compilado).
- Cada juego contra **todos** los candidatos de **todas** las tiendas. Desempate **estable** (mismo resultado en los 3 modos).
- Si la etapa es demasiado rápida para medirse, sugerir ampliar candidatos (catálogo completo de un listado en replay), no hacer el algoritmo artificialmente lento.

## 3. Calcular
Para un rango de umbrales (p. ej. 0,70 a 0,98 en pasos de 0,02):
- VP, FP, FN, VN → **precisión** = VP/(VP+FP), **exhaustividad** = VP/(VP+FN), F1.
- Tabla umbral vs métricas y el umbral recomendado con su justificación (qué error es más caro para el sitio: mostrar un precio de otro juego (FP) o no mostrar un precio (FN)).
- **Banda de duda** alrededor del umbral (p. ej. ±0,05) → esos pares van marcados como "dudosos" al panel.

## 4. Salida
- Tabla y conclusión en `docs/informe/validacion-emparejamiento.md`.
- Lista de errores (FP/FN) con la causa probable de cada uno y si un ajuste de normalización lo corregiría **sin sobreajustar** al set de validación.
- Si el umbral cambia respecto al diseño del H1 → línea en `docs/cambios-diseno.md` (o `/adr ... --reemplaza`).
