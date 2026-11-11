# Registro de cambios de diseño

Cada desviación respecto al diseño entregado en el Hito 1, con su motivo.
Cambiar el diseño no se penaliza; no justificarlo, sí.

| Fecha | Qué cambió (respecto al H1) | Motivo / evidencia | ADR |
|---|---|---|---|
| 2026-11-11 | Ediciones con contenido extra (GOTY, Complete…) pasan de dudosas a aceptadas como "juego + DLC" | Muchas tiendas solo venden esa edición; 89 de 200 juegos de PC no se emparejaban | ADR-006 |
| 2026-11-11 | Nueva fuente CheapShark (tiendas de PC) y más páginas de PC (12) y Switch (8) | Solo el 17 % del catálogo tenía 2 tiendas; PS5/Xbox no tienen segunda tienda consultable | ADR-011 |
| 2026-11-11 | Un `Retry-After` largo pausa el dominio en vez de reintentar con el backoff recortado | CheapShark pidió esperar ~1 h; reintentar antes no respeta al sitio y ocupaba hilos de descarga | ADR-011 |
| 2026-11-11 | La normalización quita etiquetas entre corchetes y el año entre paréntesis; paquetes con el mismo nombre se aceptan | 177 juegos de Switch se rechazaban por "[Digital]" | ADR-006 |
| 2026-11-11 | Switch pasa de 8 a 12 páginas de descubrimiento | Con el arreglo anterior Switch tiene 2 tiendas reales | ADR-011 |
