# Catálogo de juegos

Esta carpeta es la **fuente de verdad** del catálogo (sección 4 del enunciado). La base de datos se llena
desde aquí con:

```bash
py -3.14 -m radar.herramientas.cargar_catalogo
```

Así se cumple "se pueden agregar o quitar juegos sin modificar el código": se edita un archivo de esta
carpeta y se vuelve a cargar.

## Reglas

- Cada archivo `*.json` contiene una **lista** de juegos. Puede haber varios archivos, por ejemplo:
  - `descubiertos.json`: lo genera la etapa 0 a partir del listado público (no editar a mano);
  - `casos-dificiles.json`: los 50 o más casos difíciles elegidos por el equipo;
  - `manual.json`: juegos agregados a mano.

  Tener archivos separados reduce los conflictos de Git cuando varios integrantes editan a la vez.
- Una misma `clave` **no puede aparecer en dos archivos** (el cargador lo detecta y dice dónde está repetida).
- **Agregar** un juego: añadir su entrada y volver a cargar.
- **Quitar** un juego: borrar su entrada (o poner `"activo": false`) y volver a cargar. En la base queda
  marcado como inactivo: **su historial de precios no se borra**.
- El cargador revisa todo antes de escribir y muestra **todos** los errores juntos. Si hay alguno, no cambia
  nada en la base.

## Formato de cada juego

```json
[
  {
    "clave": "god-of-war-2018",
    "titulo": "God of War",
    "titulos_alternativos": ["God of War (2018)", "God of War 4"],
    "tipo": "juego",
    "plataformas": [
      {"plataforma": "ps4", "fecha_lanzamiento": "AAAA-MM-DD", "msrp": 19.99},
      {"plataforma": "pc"}
    ],
    "caso_dificil": "secuela"
  }
]
```

(Los valores de fecha y precio del ejemplo son ilustrativos: usen los datos reales de las fuentes.)

| Campo | Obligatorio | Valores |
|---|---|---|
| `clave` | Sí | Identificador único y estable: minúsculas, números y guiones (`the-witcher-3`). No cambiarla después: enlaza el historial. |
| `titulo` | Sí | Título canónico. |
| `titulos_alternativos` | No | Otros nombres del juego; mejoran el emparejamiento. |
| `tipo` | No (por defecto `juego`) | `juego`, `juego_dlc`, `dlc`, `otro` |
| `plataformas` | Sí, al menos una | Cada una con `plataforma` (`ps4`, `ps5`, `switch`, `switch2`, `xbox-one`, `xbox-series`, `pc`) y, si se conocen, `fecha_lanzamiento` (`AAAA-MM-DD`) y `msrp` en dólares con hasta 2 decimales. |
| `caso_dificil` | No | Categoría si es un caso difícil: `remasterizacion`, `edicion`, `secuela`, `numeros_romanos`, `subtitulo`, `caracteres_especiales`, `otro` |
| `activo` | No (por defecto `true`) | `false` para quitarlo sin borrar la entrada. |
| `origen` | No (por defecto `manual`) | `manual` o `descubrimiento` (lo pone la etapa 0). |
| `descubierto_por` | Solo si `origen` es `descubrimiento` | Código de la fuente en la tabla `fuente` (p. ej. `steam-listado`). |

La fecha y el MSRP pueden faltar mientras el catálogo se completa: el cargador los reporta como pendientes,
porque el enunciado los exige para cada juego.
